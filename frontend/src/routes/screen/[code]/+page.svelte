<script lang="ts">
  import { joinSession, listResponses, startSession, clearResponses, getScreenControl, getPresentationPageImageUrl, getPageImageUrl } from '$lib/api';
  import { RforumWebSocket } from '$lib/ws';
  import type { ConnectionStatus as WsStatus } from '$lib/ws';
  import type { VideoControlPayload } from '$lib/components/ContentSlideCanvas.svelte';
  import { onMount, onDestroy, untrack } from 'svelte';
  import { BarChart3, MessageSquare, AlignLeft, Cloud, Orbit, Maximize2 } from 'lucide-svelte';
  import JoinScreen from '$lib/components/JoinScreen.svelte';
  import QRModal from '$lib/components/QRModal.svelte';
  import PresentationLiveView from '$lib/components/timeline/PresentationLiveView.svelte';
  import InteractionView from '$lib/components/timeline/InteractionView.svelte';
  import ContentSlideCanvas from '$lib/components/ContentSlideCanvas.svelte';
  import { upsertTimelineItemFromWs } from '$lib/timelineTypes';
  import { getFitTitleStyle, mergeResponsesById, responsesForSlide } from '$lib/fitTitle';
  import { HiddenResponseTracker } from '$lib/hiddenResponses';

  let code = $state('');
  let session: any = $state(null);
  let activeSlide: any = $state(null);
  let responses: any[] = $state([]);
  // Presentation Timeline (additive — only populated when session.presentation_id is set)
  let presentationTimeline: any = $state(null);
  let timelineResponses: any[] = $state([]);
  // Responses the moderator hid while this page is open (see $lib/hiddenResponses).
  const hiddenResponses = new HiddenResponseTracker();
  const shownResponses = $derived(responses.filter(hiddenResponses.isShown));
  const shownTimelineResponses = $derived(timelineResponses.filter(hiddenResponses.isShown));
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
  // Shown in the header: the projector must never claim "Live" while it can't
  // receive the presenter's changes.
  let wsStatus: WsStatus = $state('disconnected');
  let loading = $state(true);
  let error = $state('');
  let guestUrl = $state('');
  let showQRModal = $state(false);
  let lastScreenControlId = $state('');
  let isStartingSession = $state(false);
  // Shown on the join screen (a blocking alert() would sit on the projector).
  let startError = $state('');
  let isClearingResponses = $state(false);
  let screenControlPollTimer: ReturnType<typeof setInterval> | null = null;
  // Live audience count — server-pushed via the 'presence_count' event
  // (see app/routers/ws.py::ConnectionManager._broadcast_presence), sent on
  // every guest connect/disconnect for this session. null until the first
  // count arrives, so the header can omit it rather than flash "0 joined".
  let guestCount: number | null = $state(null);

  // Latest video_control command received from the moderator. ContentSlideCanvas
  // (and PresentationLiveView) watch this via $effect and apply it only when
  // the slide_id matches the currently displayed slide.
  let videoCommand: VideoControlPayload | null = $state(null);

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

  /** Run `task` in the message queue: WS messages arriving meanwhile are
   * handled after it, on top of its result, instead of being overwritten by
   * it (e.g. a new or unhidden response arriving during the initial load). */
  function runSerialized(task: () => Promise<void>): Promise<void> {
    return new Promise((resolve, reject) => {
      queueMessage({ event: '__task', run: () => task().then(resolve, reject) });
    });
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
    startError = '';
    try {
      await startSession(session.id);
      // The session_update websocket message will handle the state update
    } catch (e: any) {
      console.error('[screen] Error starting session:', e);
      startError = 'Failed to start session: ' + (e.message || 'Unknown error');
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

  /** Load the live session's current state (active slide / timeline item and
   * its responses) from the server. Used on first load, when the session goes
   * live after this screen was opened, and after a WS reconnect — slide
   * changes broadcast while the socket was down are never replayed. */
  /** Responses for a slide; on failure (e.g. offline, with the session itself
   * served from the offline cache) keep what we already had for that slide
   * rather than failing the whole state load. */
  async function fetchSlideResponses(slideId: string, previous: any[]): Promise<any[]> {
    try {
      return await fetchFreshResponses(slideId);
    } catch {
      return responsesForSlide(previous, slideId);
    }
  }

  /** A slide's responses, fresh from the server (throws on failure). Every
   * such fetch is authoritative for that slide: it drops hides older than the
   * fetch, so a response unhidden while this page missed the event — offline,
   * or while another slide was shown — reappears (see $lib/hiddenResponses). */
  async function fetchFreshResponses(slideId: string): Promise<any[]> {
    const startedAt = hiddenResponses.fetchStarted();
    const fresh = responsesForSlide(await listResponses(slideId), slideId);
    hiddenResponses.fetchSucceeded(slideId, startedAt);
    return fresh;
  }

  async function loadSessionState() {
    const fresh = await joinSession(code);
    const active = fresh.slides?.find((s: any) => s.is_active);
    const nextResponses = active ? await fetchSlideResponses(active.id, responses) : [];
    let nextTimeline: any = null;
    let nextTimelineResponses: any[] = [];
    if (fresh.presentation_id && fresh.timeline) {
      nextTimeline = fresh.timeline;
      const activeItem = (nextTimeline.items || []).find((i: any) => i.id === nextTimeline.active_timeline_item_id);
      if (activeItem?.slide) {
        nextTimelineResponses = await fetchSlideResponses(activeItem.slide.id, timelineResponses);
      }
    }
    session = fresh;
    error = '';
    activeSlide = active ? { ...active, type: active.type?.toUpperCase() } : null;
    responses = nextResponses;
    presentationTimeline = nextTimeline;
    timelineResponses = nextTimelineResponses;
  }

  // ── Look-ahead image prefetch ──────────────────────────────────────
  // Warm the next few slides' rendered images: transitions stay instant on a
  // slow network, and the service worker keeps them for an outage (see
  // src/service-worker.ts). Same URLs (and the same code-based authorization)
  // the slides themselves use.
  const PREFETCH_AHEAD = 2;
  const prefetchedUrls = new Set<string>();
  function imageUrlFor(slide: any): string | null {
    const cj = slide?.content_json;
    if (!slide?.id || !session?.id || !(cj?.has_file || cj?.file_url)) return null;
    return getPageImageUrl(session.id, slide.id, cj.file_page || 1, code);
  }
  function prefetchUpcoming() {
    if (typeof window === 'undefined' || !session) return;
    const urls: string[] = [];
    if (session.presentation_id && presentationTimeline) {
      const items = timelineOrderedItems;
      const start = items.findIndex((i: any) => i.id === presentationTimeline.active_timeline_item_id);
      for (const item of items.slice(start + 1, start + 1 + PREFETCH_AHEAD)) {
        if (item.item_type === 'PAGE' && item.page) {
          urls.push(getPresentationPageImageUrl(session.presentation_id, item.page.page_number, code));
        } else {
          const url = imageUrlFor(item.slide);
          if (url) urls.push(url);
        }
      }
    } else {
      const start = orderedLegacySlides.findIndex((sl: any) => sl.id === activeSlide?.id);
      for (const slide of orderedLegacySlides.slice(start + 1, start + 1 + PREFETCH_AHEAD)) {
        const url = imageUrlFor(slide);
        if (url) urls.push(url);
      }
    }
    for (const url of urls) {
      if (prefetchedUrls.has(url)) continue;
      prefetchedUrls.add(url);
      const img = new Image();
      img.decoding = 'async';
      img.onerror = () => prefetchedUrls.delete(url); // allow a later retry
      img.src = url;
    }
  }
  $effect(() => {
    void activeTimelineItem?.id;
    void activeSlide?.id;
    void session?.id;
    untrack(prefetchUpcoming);
  });

  onMount(async () => {
    // Session codes are uppercase server-side (WS endpoint, screen-control key).
    code = typeof window !== 'undefined'
      ? (window.location.pathname.split('/').pop() || '').toUpperCase()
      : '';
    guestUrl = typeof window !== 'undefined' ? `${window.location.origin}/session/${code}` : '';
    lastScreenControlId = readSeenScreenControlId(code);
    window.addEventListener("storage", handleLocalScreenControl);

    // Always connect WS so the screen auto-recovers when the session starts.
    // role: 'screen' marks this connection as strictly read-only.
    ws = new RforumWebSocket(code, { role: 'screen' });
    ws.onStatusChange((s) => {
      // Any interruption (retrying or browser-offline) needs an authoritative resync.
      const wasReconnecting = lastWsStatus === 'reconnecting' || lastWsStatus === 'offline';
      lastWsStatus = s;
      wsStatus = s;
      // Resync through the message queue so it can't interleave with (and
      // be overwritten by, or overwrite) live messages arriving meanwhile.
      if (s === 'connected' && wasReconnecting) queueMessage({ event: '__resync' });
    });
    ws.onMessage(queueMessage);
    ws.connect();
    void pollScreenControl();
    screenControlPollTimer = setInterval(pollScreenControl, 2000);

    try {
      await runSerialized(loadSessionState);
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
    if (msg.event === '__task') {
      // Local-only (see runSerialized): a server message can't carry a function.
      if (typeof msg.run === 'function') await msg.run();
      return;
    }
    if (msg.event === '__resync') {
      try {
        await loadSessionState();
      } catch {
        // Keep the last known state if the resync fails; the next reconnect retries.
      }
      return;
    }
    // Presentation-timeline activation — distinct payload shape from the legacy
    // slide_change (timeline_item_id instead of slide_id), same event name per design.
    if (msg.event === 'slide_change' && msg.data?.timeline_item_id !== undefined) {
      // Content edits carry activation: false — refresh that item's data
      // without moving the audience off the item that is actually live.
      const isActivation = msg.data.activation !== false;
      if (presentationTimeline) {
        presentationTimeline = {
          ...presentationTimeline,
          active_timeline_item_id: isActivation ? msg.data.timeline_item_id : presentationTimeline.active_timeline_item_id,
          items: upsertTimelineItemFromWs(presentationTimeline.items || [], msg.data)
        };
      }
      if (!isActivation) return;
      // A playback command belongs to the slide it was issued on; returning
      // to that video later must start fresh, not replay a stale play/seek.
      videoCommand = null;
      if (msg.data.slide) {
        try {
          timelineResponses = await fetchFreshResponses(msg.data.slide.id);
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
      // The moderator also broadcasts content saves (activation: false) for
      // slides that are not live — those must not replace what is on screen.
      if (msg.data?.activation === false && msg.data?.slide?.id !== activeSlide?.id) return;
      if (msg.data?.activation !== false) videoCommand = null;
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
          responses = await fetchFreshResponses(msg.data.slide.id);
        } catch (err) {
          console.error('[screen] Failed to load responses for new slide:', err);
          // Retry once more after delay
          await new Promise(resolve => setTimeout(resolve, 200));
          try {
            responses = await fetchFreshResponses(msg.data.slide.id);
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
            responses = await fetchFreshResponses(active.id);
          } else {
            responses = [];
          }
        } catch (err) {
          console.error('[screen] Failed to load session after slide change:', err);
          responses = [];
        }
      }
    } else if (msg.event === 'new_response') {
      // A moderator unhiding a response re-announces it as a new_response.
      if (msg.data?.id) hiddenResponses.unhide(msg.data.id);
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
        presentationTimeline = null;
        videoCommand = null;
        error = 'Session has ended.';
      } else if (msg.data?.is_live === true) {
        // Session just went live. `session` is null here when this screen was
        // opened before going live (join only succeeds for live sessions), so
        // always load fresh state rather than patching the old object.
        try {
          await loadSessionState();
        } catch (err) {
          console.error('[screen] Failed to load session after going live:', err);
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
    } else if (msg.event === 'response_hidden') {
      const hiddenId = msg.data?.id;
      if (!hiddenId) return;
      hiddenResponses.hide(hiddenId, msg.data?.slide_id);
      responses = responses.filter((r) => r.id !== hiddenId);
      timelineResponses = timelineResponses.filter((r) => r.id !== hiddenId);
    } else if (msg.event === 'video_control') {
      // Only accept commands from the moderator (role is enforced server-side).
      // Replace any pending command immediately — stale commands are irrelevant
      // because ContentSlideCanvas reacts synchronously via $effect.
      if (msg.data?.slide_id) videoCommand = msg.data as VideoControlPayload;
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
    {startError}
  />
{:else}
  <!-- LIVE PRESENTATION SCREEN (Theme Aware). Fixed to the viewport on
       purpose: the stage below scales slides to fit, it never scrolls. -->
  <div class="h-screen flex flex-col bg-surface-50 text-surface-900 dark:bg-surface-950 dark:text-surface-100 font-sans select-none overflow-hidden transition-colors">
    <header class="grid min-h-[64px] flex-shrink-0 grid-cols-[1fr_auto_1fr] items-center gap-4 border-b border-surface-200 bg-white dark:border-surface-800 dark:bg-surface-950 px-5 py-2 sm:px-8">
      <div class="flex items-center gap-2.5">
        <Orbit class="h-6 w-6 text-brand-600 dark:text-brand-400" />
        <span class="font-heading text-lg font-extrabold tracking-wide text-surface-900 dark:text-white">Rforum</span>
      </div>
      <div class="text-center">
        <p class="max-w-[16rem] truncate text-sm font-bold text-surface-900 dark:text-white sm:text-base">{session?.title || 'Presentation'}</p>
        <p class="mt-0.5 text-xs text-surface-600 dark:text-surface-400" role="status">
          {#if session?.moderator_name}{session.moderator_name}&nbsp;&middot;&nbsp;{/if}{#if wsStatus === 'offline'}<span class="font-semibold text-red-600 dark:text-red-400">&#9679; Offline — showing last received slide</span>{:else if wsStatus === 'reconnecting'}<span class="font-semibold text-amber-700 dark:text-amber-400">&#9679; Reconnecting…</span>{:else if wsStatus === 'connected'}<span class="font-semibold text-emerald-700 dark:text-emerald-400">&#9679; Live</span>{:else}<span class="font-semibold text-surface-600 dark:text-surface-400">&#9679; Connecting…</span>{/if}{#if guestCount !== null}&nbsp;&middot;&nbsp;{guestCount} joined{/if}
        </p>
      </div>
      <div class="flex items-center justify-end">
        <button type="button" onclick={() => document.documentElement.requestFullscreen?.()} class="rounded-lg p-2 text-surface-600 transition-colors hover:bg-surface-100 hover:text-surface-900 dark:text-surface-300 dark:hover:bg-surface-800 dark:hover:text-white" title="Fullscreen" aria-label="Fullscreen"><Maximize2 class="h-5 w-5" /></button>
      </div>
    </header>

    {#if slideTotal > 0}
      <div
        class="h-[3px] flex-shrink-0 bg-surface-200 dark:bg-surface-800"
        role="progressbar"
        aria-valuenow={slideIndex}
        aria-valuemin="1"
        aria-valuemax={slideTotal}
        aria-label="Slide progress"
      >
        <div class="h-full bg-brand-500 transition-[width] duration-500" style={`width: ${slideProgressPct}%`}></div>
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

      {#if loading}
        <div class="text-center animate-fade-in space-y-4 py-16" role="status">
          <Orbit class="w-16 h-16 mx-auto text-brand-500 animate-spin" />
          <p class="text-2xl font-heading font-bold text-surface-700 dark:text-surface-300">Connecting to session…</p>
          <p class="font-mono text-2xl font-bold text-brand-700 dark:text-brand-300">{code}</p>
        </div>

      {:else if error}
        <div class="text-center animate-fade-in space-y-4 py-16 px-4">
          <Orbit class="w-16 h-16 mx-auto text-brand-500/60 animate-spin" />
          <p class="text-2xl font-heading font-bold text-surface-700 dark:text-surface-300">Waiting for session…</p>
          <p class="text-base text-surface-600 dark:text-surface-400 break-words">{error}</p>
          <div class="mt-4 inline-flex items-center gap-2 bg-brand-50 dark:bg-brand-900/30 px-4 py-2 rounded-xl border border-brand-200 dark:border-brand-800">
            <span class="text-surface-600 dark:text-surface-400 text-xs font-bold uppercase">Code</span>
            <span class="font-mono text-2xl font-bold text-brand-700 dark:text-brand-300">{code}</span>
          </div>
        </div>

      {:else if !hasActiveContent}
        <div class="text-center animate-fade-in space-y-4 py-12 px-4">
          <Orbit class="w-16 h-16 mx-auto text-brand-500 animate-spin" />
          <p class="text-2xl font-heading font-bold text-surface-700 dark:text-surface-300">Waiting for presenter…</p>
          <p class="text-base text-surface-600 dark:text-surface-400">The presentation session is active. Slides will display automatically.</p>
          <div class="mt-6 inline-flex max-w-full flex-wrap items-center justify-center gap-2 bg-surface-200 dark:bg-surface-800 px-5 py-2.5 rounded-2xl">
            <span class="text-xs text-surface-600 dark:text-surface-400 uppercase font-bold tracking-wider">Join at</span>
            <span class="font-mono text-xl font-bold text-brand-700 dark:text-brand-300 break-all">{guestUrl || code}</span>
          </div>
        </div>

      {:else if session?.presentation_id}
        <div class="flex min-h-0 flex-1 items-center justify-center px-2 pb-2" style="container-type: size;">
          <div class="overflow-hidden rounded-xl border p-3 sm:p-4 presentation-stage bg-white border-surface-200 dark:bg-surface-950 dark:border-surface-800" style="width: min(100cqw, calc(100cqh * 16 / 9)); height: min(100cqh, calc(100cqw * 9 / 16));">
          <PresentationLiveView
            activeItem={activeTimelineItem}
            presentationId={session.presentation_id}
            sessionId={session.id}
            sessionCode={code || session?.unique_code || ''}
            responses={shownTimelineResponses}
            variant="screen"
            {videoCommand}
          />
          </div>
        </div>

      {:else}
        <div class="flex min-h-0 flex-1 items-center justify-center px-2 pb-2" style="container-type: size;">
          <div class="overflow-hidden rounded-xl border p-3 sm:p-4 presentation-stage transition-colors bg-white border-surface-200 dark:bg-surface-950 dark:border-surface-800" style="width: min(100cqw, calc(100cqh * 16 / 9)); height: min(100cqh, calc(100cqw * 9 / 16));">
          {#if activeSlide.type?.toUpperCase() === 'CONTENT'}
            <ContentSlideCanvas slide={activeSlide} sessionId={session?.id} sessionCode={code} variant="screen" {videoCommand} />
          {:else}
            <InteractionView slide={activeSlide} responses={shownResponses} variant="screen" readOnly />
          {/if}
          </div>
        </div>
      {/if}
    </main>

    <!-- Session code — de-emphasized, no longer a header headline. There's
         no manual code-entry anywhere in the app (join is QR/link only), so
         this exists purely as a fallback for reading the code aloud. -->
    <div class="flex flex-shrink-0 items-center justify-center py-1.5">
      <span class="font-mono text-xs tracking-[0.15em] text-surface-600 dark:text-surface-400">{code}</span>
    </div>

    <!-- Footer -->
    <footer class="flex items-center justify-center px-6 py-2.5 bg-white dark:bg-surface-900 border-t border-surface-200 dark:border-surface-800 flex-shrink-0 text-surface-600 dark:text-surface-400 text-xs transition-colors">
      <div class="flex flex-col sm:flex-row items-center justify-center gap-3">
        <span>Powered by <span class="font-semibold text-surface-700 dark:text-surface-300">Tech4Good Community</span></span>
        <span class="hidden sm:inline text-surface-300 dark:text-surface-700" aria-hidden="true">•</span>
        <span>Built with <span class="text-red-500">❤</span> by Ajith</span>
        <span class="hidden sm:inline text-surface-300 dark:text-surface-700" aria-hidden="true">•</span>
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