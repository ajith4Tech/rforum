<script lang="ts">
  import { joinSession, listResponses, startSession, clearResponses, getScreenControl } from '$lib/api';
  import { RforumWebSocket } from '$lib/ws';
  import type { ConnectionStatus as WsStatus } from '$lib/ws';
  import { onMount, onDestroy } from 'svelte';
  import { theme } from '$lib/theme';
  import { BarChart3, MessageSquare, AlignLeft, Cloud, Orbit, Maximize2 } from 'lucide-svelte';
  import JoinScreen from '$lib/components/JoinScreen.svelte';
  import QRModal from '$lib/components/QRModal.svelte';
  import PresentationLiveView from '$lib/components/timeline/PresentationLiveView.svelte';
  import InteractionView from '$lib/components/timeline/InteractionView.svelte';
  import ContentSlideCanvas from '$lib/components/ContentSlideCanvas.svelte';
  import { upsertTimelineItemFromWs } from '$lib/timelineTypes';
  import { getFitTitleStyle, mergeResponsesById, responsesForSlide } from '$lib/fitTitle';

  let code = $state('');
  let session: any = $state(null);
  let activeSlide: any = $state(null);
  let responses: any[] = $state([]);
  // Presentation Timeline (additive — only populated when session.presentation_id is set)
  let presentationTimeline: any = $state(null);
  let timelineResponses: any[] = $state([]);
  const activeTimelineItem = $derived(
    presentationTimeline
      ? [...(presentationTimeline.items || [])].sort((a: any, b: any) => a.order - b.order)
          .find((i: any) => i.id === presentationTimeline.active_timeline_item_id) || null
      : null
  );
  const hasActiveContent = $derived(session?.presentation_id ? !!activeTimelineItem : !!activeSlide);
  // Slide progress (header progress bar) — computed for both the
  // presentation-timeline path and the legacy slide-list path, same
  // pattern as hasActiveContent above.
  const timelineOrderedItems = $derived(
    presentationTimeline ? [...(presentationTimeline.items || [])].sort((a: any, b: any) => a.order - b.order) : []
  );
  const orderedLegacySlides = $derived(
    session?.slides ? [...session.slides].sort((a: any, b: any) => (a.order ?? 0) - (b.order ?? 0)) : []
  );
  const slideTotal = $derived(session?.presentation_id ? timelineOrderedItems.length : orderedLegacySlides.length);
  const slideIndex = $derived(
    session?.presentation_id
      ? timelineOrderedItems.findIndex((i: any) => i.id === presentationTimeline?.active_timeline_item_id) + 1
      : orderedLegacySlides.findIndex((s: any) => s.id === activeSlide?.id) + 1
  );
  const slideProgressPct = $derived(slideTotal > 0 && slideIndex > 0 ? Math.round((slideIndex / slideTotal) * 100) : 0);
  let ws: RforumWebSocket | null = $state(null);
  let lastWsStatus: WsStatus = 'disconnected';
  let loading = $state(true);
  let error = $state('');
  let guestUrl = $state('');
  let showQRModal = $state(false);
  let lastScreenControlId = $state('');
  let isStartingSession = $state(false);
  let isClearingResponses = $state(false);
  let screenControlPollTimer: ReturnType<typeof setInterval> | null = null;
  // Live audience count — server-pushed via the 'presence_count' event
  // (see app/routers/ws.py::ConnectionManager._broadcast_presence), sent on
  // every guest connect/disconnect for this session. null until the first
  // count arrives, so the header can omit it rather than flash "0 joined".
  let guestCount: number | null = $state(null);

  // Refresh does window.location.reload(), which wipes in-memory
  // lastScreenControlId. Redis keeps the command for 15s and onMount polls
  // it immediately — without persisting the id, the projector reloads in a
  // loop until TTL expires (and it looks infinite).
  function screenControlSeenKey(sessionCode: string) {
    return `rforum_last_screen_control_${sessionCode}`;
  }
  function readSeenScreenControlId(sessionCode: string): string {
    try {
      return sessionStorage.getItem(screenControlSeenKey(sessionCode)) || '';
    } catch {
      return '';
    }
  }
  function rememberScreenControlId(sessionCode: string, commandId: string) {
    lastScreenControlId = commandId;
    try {
      sessionStorage.setItem(screenControlSeenKey(sessionCode), commandId);
    } catch {
      // sessionStorage blocked — in-memory dedupe still covers this page lifetime.
    }
  }

  // Use a queue to prevent race conditions when handling WebSocket messages
  let messageQueue: any[] = [];
  let isProcessingMessage = false;

  async function processMessageQueue() {
    if (isProcessingMessage || messageQueue.length === 0) return;
    
    isProcessingMessage = true;
    const msg = messageQueue.shift();
    
    try {
      await handleWsMessage(msg);
    } finally {
      isProcessingMessage = false;
      // Process next message if any
      if (messageQueue.length > 0) {
        await processMessageQueue();
      }
    }
  }

  function queueMessage(msg: any) {
    messageQueue.push(msg);
    processMessageQueue();
  }

  function handleLocalScreenControl(event: StorageEvent) {
    if (event.key !== "rforum_screen_control_" + code || !event.newValue) return;
    try {
      const data = JSON.parse(event.newValue);
      if (data?.action === "refresh" || data?.action === "maximize_qr" || data?.action === "toggle_qr") {
        queueMessage({ event: "screen_control", data: { action: data.action, command_id: data.command_id } });
      }
    } catch {
      // Ignore malformed values from outside the application.
    }
  }

  async function pollScreenControl() {
    if (!code) return;
    try {
      const result: any = await getScreenControl(code);
      if (result?.command?.event === "screen_control") queueMessage(result.command);
    } catch {
      // WebSocket delivery remains active when polling is temporarily unavailable.
    }
  }

  async function handleStartSession() {
    if (!session || isStartingSession) return;
    isStartingSession = true;
    try {
      await startSession(session.id);
      // The session_update websocket message will handle the state update
    } catch (e: any) {
      console.error('[screen] Error starting session:', e);
      alert('Failed to start session: ' + (e.message || 'Unknown error'));
    } finally {
      isStartingSession = false;
    }
  }

  async function handleClearResponses() {
    const slide = session?.presentation_id ? activeTimelineItem?.slide : activeSlide;
    if (!slide || isClearingResponses) return;
    if (!confirm('Are you sure you want to clear all responses for this slide?')) return;
    
    isClearingResponses = true;
    try {
      await clearResponses(slide.id);
    } catch (e: any) {
      console.error('[screen] Error clearing responses:', e);
      alert('Failed to clear responses: ' + (e.message || 'Unknown error'));
    } finally {
      isClearingResponses = false;
    }
  }

  async function refetchScreenResponses() {
    try {
      if (session?.presentation_id) {
        const slideId = activeTimelineItem?.slide?.id;
        timelineResponses = slideId ? responsesForSlide(await listResponses(slideId), slideId) : [];
      } else if (activeSlide?.id) {
        responses = responsesForSlide(await listResponses(activeSlide.id), activeSlide.id);
      }
    } catch {
      // Keep last known responses if reconnect refetch fails.
    }
  }

  onMount(async () => {
    code = typeof window !== 'undefined'
      ? window.location.pathname.split('/').pop() || ''
      : '';
    guestUrl = typeof window !== 'undefined' ? `${window.location.origin}/session/${code}` : '';
    lastScreenControlId = readSeenScreenControlId(code);
    window.addEventListener("storage", handleLocalScreenControl);

    // Always connect WS so the screen auto-recovers when the session starts.
    // role: 'screen' marks this connection as strictly read-only.
    ws = new RforumWebSocket(code, { role: 'screen' });
    ws.onStatusChange((s) => {
      const wasReconnecting = lastWsStatus === 'reconnecting';
      lastWsStatus = s;
      if (s === 'connected' && wasReconnecting) void refetchScreenResponses();
    });
    ws.onMessage(queueMessage);
    ws.connect();
    void pollScreenControl();
    screenControlPollTimer = setInterval(pollScreenControl, 2000);

    try {
      session = await joinSession(code);

      const active = session.slides?.find((s: any) => s.is_active);
      if (active) {
        activeSlide = { ...active, type: active.type?.toUpperCase() };
        responses = responsesForSlide(await listResponses(active.id), active.id);
      }

      if (session.presentation_id && session.timeline) {
        presentationTimeline = session.timeline;
        const items = [...(presentationTimeline.items || [])].sort((a: any, b: any) => a.order - b.order);
        const activeItem = items.find((i: any) => i.id === presentationTimeline.active_timeline_item_id);
        if (activeItem?.slide) {
          timelineResponses = responsesForSlide(await listResponses(activeItem.slide.id), activeItem.slide.id);
        }
      }
    } catch (e: any) {
      console.error('[screen] Error in onMount:', e);
      error = e.message || 'Session not found';
    } finally {
      loading = false;
    }
  });

  onDestroy(() => {
    window.removeEventListener("storage", handleLocalScreenControl);
    if (screenControlPollTimer) clearInterval(screenControlPollTimer);
    ws?.disconnect();
  });

  async function handleWsMessage(msg: any) {
    // Presentation-timeline activation — distinct payload shape from the legacy
    // slide_change (timeline_item_id instead of slide_id), same event name per design.
    if (msg.event === 'slide_change' && msg.data?.timeline_item_id !== undefined) {
      if (presentationTimeline) {
        presentationTimeline = {
          ...presentationTimeline,
          active_timeline_item_id: msg.data.timeline_item_id,
          items: upsertTimelineItemFromWs(presentationTimeline.items || [], msg.data)
        };
      }
      if (msg.data.slide) {
        try {
          timelineResponses = responsesForSlide(await listResponses(msg.data.slide.id), msg.data.slide.id);
        } catch (err) {
          console.error('[screen] Failed to load responses for new timeline item:', err);
          timelineResponses = [];
        }
      } else {
        timelineResponses = [];
      }
      return;
    }

    if (msg.event === 'slide_change') {
      if (msg.data?.slide) {
        // Use the slide data embedded in the message — no HTTP round-trip needed
        const cj = { ...(msg.data.slide.content_json || {}) };
        if ('file_url' in cj) { cj.has_file = true; delete cj.file_url; }
        delete cj.file_name;
        activeSlide = { ...msg.data.slide, type: msg.data.slide.type?.toUpperCase(), content_json: cj };

        // Always reload responses for the new slide to prevent stale data
        // Reload immediately with a small delay to ensure DB is updated
        try {
          await new Promise(resolve => setTimeout(resolve, 100));
          const fetchedResponses = await listResponses(msg.data.slide.id);
          responses = fetchedResponses;
        } catch (err) {
          console.error('[screen] Failed to load responses for new slide:', err);
          // Retry once more after delay
          await new Promise(resolve => setTimeout(resolve, 200));
          try {
            const retryResponses = await listResponses(msg.data.slide.id);
            responses = retryResponses;
          } catch (retryErr) {
            console.error('[screen] Retry also failed:', retryErr);
            responses = [];
          }
        }
      } else {
        try {
          session = await joinSession(code);
          const active = session.slides?.find((s: any) => s.is_active);
          activeSlide = active ? { ...active, type: active.type?.toUpperCase() } : null;
          if (active) {
            await new Promise(resolve => setTimeout(resolve, 100));
            const fetchedResponses = await listResponses(active.id);
            responses = fetchedResponses;
          } else {
            responses = [];
          }
        } catch (err) {
          console.error('[screen] Failed to load session after slide change:', err);
          responses = [];
        }
      }
    } else if (msg.event === 'new_response') {
      if (msg.data && activeSlide && msg.data.slide_id === activeSlide.id) {
        responses = mergeResponsesById(responses, [msg.data]);
      }
      if (msg.data && activeTimelineItem?.slide && msg.data.slide_id === activeTimelineItem.slide.id) {
        timelineResponses = mergeResponsesById(timelineResponses, [msg.data]);
      }
    } else if (msg.event === 'upvote') {
      // Update the response with new upvote count
      responses = responses.map((r) =>
        r.id === msg.data.id ? { ...r, upvotes: msg.data.upvotes } : r
      );
      timelineResponses = timelineResponses.map((r) =>
        r.id === msg.data.id ? { ...r, upvotes: msg.data.upvotes } : r
      );
    } else if (msg.event === 'page_change') {
      if (activeSlide && msg.data?.slide_id === activeSlide.id) {
        activeSlide = {
          ...activeSlide,
          content_json: {
            ...activeSlide.content_json,
            file_page: msg.data.file_page,
            total_pages: msg.data.total_pages ?? activeSlide.content_json?.total_pages
          }
        };
      }
    } else if (msg.event === 'session_update') {
      if (msg.data?.is_live === false) {
        session = null;
        activeSlide = null;
        error = 'Session has ended.';
      } else if (msg.data?.is_live === true && session) {
        // Session just went live - update state and load first slide if available
        session = { ...session, is_live: true };
        if (!activeSlide) {
          const active = session.slides?.find((s: any) => s.is_active);
          if (active) {
            activeSlide = { ...active, type: active.type?.toUpperCase() };
            const fetchedResponses = await listResponses(active.id);
            responses = fetchedResponses;
          }
        }
        if (session.presentation_id && !presentationTimeline) {
          try {
            const fresh = await joinSession(code);
            session = fresh;
            if (fresh.timeline) {
              presentationTimeline = fresh.timeline;
              const items = [...(fresh.timeline.items || [])].sort((a: any, b: any) => a.order - b.order);
              const activeItem = items.find((i: any) => i.id === fresh.timeline.active_timeline_item_id);
              if (activeItem?.slide) {
                timelineResponses = await listResponses(activeItem.slide.id);
              }
            }
          } catch (err) {
            console.error('[screen] Failed to load presentation timeline after going live:', err);
          }
        }
      }
    } else if (msg.event === 'screen_control') {
      if (msg.data?.command_id && msg.data.command_id === lastScreenControlId) return;
      if (msg.data?.command_id) rememberScreenControlId(code, msg.data.command_id);
      console.log('[screen] received screen_control', msg.data);
      if (msg.data?.action === 'refresh') {
        window.location.reload();
        return;
      } else if (msg.data?.action === 'maximize_qr') {
        showQRModal = true;
      } else if (msg.data?.action === 'toggle_qr') {
        showQRModal = !showQRModal;
      }
    } else if (msg.event === 'presence_count') {
      if (typeof msg.data?.count === 'number') guestCount = msg.data.count;
    } else if (msg.event === 'clear_responses') {
      const clearedId = msg.data?.slide_id;
      if (!clearedId) return;
      if (clearedId === activeSlide?.id) responses = [];
      if (clearedId === activeTimelineItem?.slide?.id) timelineResponses = [];
      responses = responses.filter((r) => r.slide_id !== clearedId);
      timelineResponses = timelineResponses.filter((r) => r.slide_id !== clearedId);
    }
  }

  function getPollResults(slide: any) {
    const options: string[] = slide.content_json?.options || [];
    const counts: Record<string, number> = {};
    options.forEach((opt) => (counts[opt] = 0));
    responses.forEach((r) => {
      if (counts[r.value] !== undefined) counts[r.value]++;
    });
    const total = responses.length || 1;
    return options.map((opt) => ({
      label: opt,
      count: counts[opt],
      percent: Math.round((counts[opt] / total) * 100)
    }));
  }

  function getWordCloudData() {
    const freq: Record<string, number> = {};
    for (const r of responses) {
      const word = r.value?.trim().toLowerCase();
      if (word) freq[word] = (freq[word] || 0) + 1;
    }
    const entries = Object.entries(freq).sort((a, b) => b[1] - a[1]);
    const maxCount = entries[0]?.[1] || 1;
    return entries.map(([word, count]) => ({
      word,
      count,
      size: Math.max(1, (count / maxCount) * 3.5)
    }));
  }
</script>

<svelte:head>
  <title>Screen {code} – Rforum</title>
</svelte:head>

{#if !loading && session && !session.is_live}
  <!-- PRE-LIVE JOIN SCREEN -->
  <JoinScreen
    sessionCode={code}
    sessionTitle={session.title}
    joinUrl={guestUrl}
    onStartSession={handleStartSession}
    isStarting={isStartingSession}
    isModerator={true}
  />
{:else}
  <!-- LIVE PRESENTATION SCREEN (Theme Aware) -->
  <div class="h-screen flex flex-col {$theme === 'dark' ? 'bg-slate-950 text-slate-100' : 'bg-slate-50 text-slate-900'} font-sans select-none overflow-hidden transition-colors">
    <header class="grid min-h-[64px] flex-shrink-0 grid-cols-[1fr_auto_1fr] items-center gap-4 border-b {$theme === 'dark' ? 'border-slate-800 bg-slate-950' : 'border-slate-200 bg-white'} px-5 py-2 sm:px-8">
      <div class="flex items-center gap-2.5">
        <Orbit class="h-6 w-6 text-purple-600 dark:text-purple-400" />
        <span class="font-heading text-lg font-extrabold tracking-wide text-slate-900 dark:text-white">Rforum</span>
      </div>
      <div class="text-center">
        <p class="max-w-[16rem] truncate text-sm font-bold text-slate-900 dark:text-white sm:text-base">{session?.title || 'Presentation'}</p>
        <p class="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
          {#if session?.moderator_name}{session.moderator_name}&nbsp;&middot;&nbsp;{/if}<span class="font-semibold text-emerald-500">&#9679; Live</span>{#if guestCount !== null}&nbsp;&middot;&nbsp;{guestCount} joined{/if}
        </p>
      </div>
      <div class="flex items-center justify-end">
        <button onclick={() => document.documentElement.requestFullscreen?.()} class="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800" title="Fullscreen" aria-label="Fullscreen"><Maximize2 class="h-5 w-5" /></button>
      </div>
    </header>

    {#if slideTotal > 0}
      <div
        class="h-[3px] flex-shrink-0 {$theme === 'dark' ? 'bg-slate-800' : 'bg-slate-200'}"
        role="progressbar"
        aria-valuenow={slideIndex}
        aria-valuemin="1"
        aria-valuemax={slideTotal}
        aria-label="Slide progress"
      >
        <div class="h-full bg-purple-500 transition-all duration-500" style={`width: ${slideProgressPct}%`}></div>
      </div>
    {/if}

    <!-- Main Presentation Workspace Stage -->
    <main class="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div class="flex flex-shrink-0 items-center justify-center pt-3 pb-1.5">
        <img
          src="/logo-mascot.webp"
          alt="Rforum Mascot"
          width="128"
          height="128"
          class="h-16 w-16 object-contain opacity-85 sm:h-20 sm:w-20 md:h-24 md:w-24 lg:h-28 lg:w-28 xl:h-32 xl:w-32"
        />
      </div>

      {#if error}
        <div class="text-center animate-fade-in space-y-4 py-16">
          <Orbit class="w-16 h-16 mx-auto text-purple-500/40 animate-spin" />
          <p class="text-2xl font-heading font-bold text-slate-600 dark:text-slate-400">Waiting for session…</p>
          <p class="text-slate-400 text-base">{error}</p>
          <div class="mt-4 inline-flex items-center gap-2 bg-purple-50 dark:bg-purple-950/40 px-4 py-2 rounded-xl border border-purple-200 dark:border-purple-800">
            <span class="text-slate-500 dark:text-slate-400 text-xs font-bold uppercase">Code</span>
            <span class="font-mono text-2xl font-bold text-purple-600 dark:text-purple-400">{code}</span>
          </div>
        </div>

      {:else if !hasActiveContent}
        <div class="text-center animate-fade-in space-y-4 py-12">
          <Orbit class="w-16 h-16 mx-auto text-purple-500 animate-spin" />
          <p class="text-2xl font-heading font-bold text-slate-700 dark:text-slate-300">Waiting for presenter…</p>
          <p class="text-slate-400 text-base">The presentation session is active. Slides will display automatically.</p>
          <div class="mt-6 inline-flex items-center gap-2 bg-slate-200 dark:bg-slate-800 px-5 py-2.5 rounded-2xl">
            <span class="text-xs text-slate-500 dark:text-slate-400 uppercase font-bold tracking-wider">Join at</span>
            <span class="font-mono text-xl font-bold text-purple-600 dark:text-purple-400">{guestUrl || code}</span>
          </div>
        </div>

      {:else if session?.presentation_id}
        <div class="flex min-h-0 flex-1 items-center justify-center px-2 pb-2" style="container-type: size;">
          <div class="overflow-hidden rounded-xl border p-3 sm:p-4 presentation-stage {$theme === 'dark' ? 'bg-slate-950 border-slate-800' : 'bg-white border-slate-200'}" style="width: min(100cqw, calc(100cqh * 16 / 9)); height: min(100cqh, calc(100cqw * 9 / 16));">
          <PresentationLiveView
            activeItem={activeTimelineItem}
            presentationId={session.presentation_id}
            sessionId={session.id}
            sessionCode={code || session?.unique_code || ''}
            responses={timelineResponses}
            variant="screen"
          />
          </div>
        </div>

      {:else}
        <div class="flex min-h-0 flex-1 items-center justify-center px-2 pb-2" style="container-type: size;">
          <div class="overflow-hidden rounded-xl border p-3 sm:p-4 presentation-stage transition-colors {$theme === 'dark' ? 'bg-slate-950 border-slate-800' : 'bg-white border-slate-200'}" style="width: min(100cqw, calc(100cqh * 16 / 9)); height: min(100cqh, calc(100cqw * 9 / 16));">
          {#if activeSlide.type?.toUpperCase() === 'CONTENT'}
            <ContentSlideCanvas slide={activeSlide} sessionId={session?.id} sessionCode={code} variant="screen" />
          {:else}
            <InteractionView slide={activeSlide} responses={responses} variant="screen" readOnly />
          {/if}
          </div>
        </div>
      {/if}
    </main>

    <!-- Session code — de-emphasized, no longer a header headline. There's
         no manual code-entry anywhere in the app (join is QR/link only), so
         this exists purely as a fallback for reading the code aloud. -->
    <div class="flex flex-shrink-0 items-center justify-center py-1.5">
      <span class="font-mono text-[11px] tracking-[0.15em] text-slate-400 dark:text-slate-600">{code}</span>
    </div>

    <!-- Footer -->
    <footer class="flex items-center justify-center px-6 py-2.5 bg-white dark:bg-slate-900 border-t border-slate-200 dark:border-slate-800 flex-shrink-0 text-slate-400 text-xs transition-colors">
      <div class="flex flex-col sm:flex-row items-center justify-center gap-3">
        <span>Powered by <span class="font-semibold text-slate-600 dark:text-slate-300">Tech4Good Community</span></span>
        <span class="hidden sm:inline text-slate-300 dark:text-slate-700">•</span>
        <span>Built with <span class="text-red-500">❤</span> by Ajith</span>
        <span class="hidden sm:inline text-slate-300 dark:text-slate-700">•</span>
        <span>Rforum@2026</span>
      </div>
    </footer>
  </div>
{/if}

<!-- QR Modal for late joiners -->
<QRModal
  bind:isOpen={showQRModal}
  sessionCode={code}
  joinUrl={guestUrl}
  sessionTitle={session?.title || ''}
/>