<script lang="ts">
  import { joinSession, submitResponse, upvoteResponse, listResponses, ApiError, isConnectivityError } from '$lib/api';
  import { parseEventDate } from '$lib/dates';
  import { RforumWebSocket } from '$lib/ws';
  import type { ConnectionStatus as WsStatus } from '$lib/ws';
  import { theme, toggleTheme } from '$lib/theme';
  import { onMount, onDestroy, untrack } from 'svelte';
  import PresentationLiveView from '$lib/components/timeline/PresentationLiveView.svelte';
  import InteractionView from '$lib/components/timeline/InteractionView.svelte';
  import ContentSlideCanvas from '$lib/components/ContentSlideCanvas.svelte';
  import { upsertTimelineItemFromWs } from '$lib/timelineTypes';
  import { getFitTitleStyle, mergeResponsesById, responsesForSlide } from '$lib/fitTitle';
  import { HiddenResponseTracker } from '$lib/hiddenResponses';
  import { forgetAnswered, reconcileAnsweredWithClears } from '$lib/respondedState';
  import { startAutoFlush, flushPending, rejectedSubmissions, dismissRejected } from '$lib/responseQueue';
  import {
    Orbit, Send, ChevronUp, BarChart3, MessageSquare, AlignLeft, CheckCircle2, Cloud, Sun, Moon
  } from 'lucide-svelte';

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
  // Bumped when the moderator clears the shown slide's responses: remounts the
  // response form so a guest who already answered can answer again.
  let responsesResetCount = $state(0);
  const activeTimelineItem = $derived(
    presentationTimeline
      ? [...(presentationTimeline.items || [])].sort((a: any, b: any) => a.order - b.order)
          .find((i: any) => i.id === presentationTimeline.active_timeline_item_id) || null
      : null
  );
  const hasActiveContent = $derived(session?.presentation_id ? !!activeTimelineItem : !!activeSlide);
  let ws: RforumWebSocket | null = $state(null);
  let lastWsStatus: WsStatus = 'disconnected';
  let wsStatus: WsStatus = $state('disconnected');
  let stopAutoFlush: (() => void) | null = null;
  let error = $state('');
  // Why the page has no session: drives the copy and whether "Try again" is offered.
  let errorKind: '' | 'not_found' | 'network' | 'ended' | 'other' = $state('');
  let loading = $state(true);
  let retrying = $state(false);
  let inputValue = $state('');
  let selectedOption = $state('');
  let submitted = $state(false);
  let guestId = $state('');
  let guestName = $state('');
  let feedbackRating = $state(5);
  let actionError = $state('');
  let thankYou = $state(false);
  let isSubmitting = $state(false);

  // "Already responded" is persisted per-guest so a page refresh doesn't
  // resurface a fresh voting form for a poll/feedback slide already answered —
  // mirrors the InteractionView.svelte presentation-timeline equivalent.
  function respondedStorageKey() {
    return `rforum_responded_${guestId}`;
  }
  function getRespondedMap(): Record<string, string> {
    if (!guestId || typeof localStorage === 'undefined') return {};
    try {
      return JSON.parse(localStorage.getItem(respondedStorageKey()) || '{}');
    } catch {
      return {};
    }
  }
  function markResponded(slideId: string, value: string) {
    if (!guestId || typeof localStorage === 'undefined') return;
    try {
      const map = getRespondedMap();
      map[slideId] = value;
      localStorage.setItem(respondedStorageKey(), JSON.stringify(map));
    } catch {
      // localStorage unavailable — non-fatal, just skip persistence
    }
  }
  function restoreSubmittedState(slide: any) {
    if (!slide || (slide.type !== 'POLL' && slide.type !== 'FEEDBACK')) {
      submitted = false;
      selectedOption = '';
      return;
    }
    const prior = getRespondedMap()[slide.id];
    submitted = prior !== undefined;
    selectedOption = slide.type === 'POLL' && prior !== undefined ? prior : '';
  }

  // Message queue to prevent race conditions
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

  // Countdown
  let countdown = $state<{ days: number; hours: number; minutes: number; seconds: number } | null>(null);
  let countdownInterval: ReturnType<typeof setInterval> | null = null;

  function getEventDate(): Date | null {
    const eventDate = session?.event?.event_date;
    if (!eventDate) return null;
    // event_date is YYYY-MM-DD; treat as start of that day in local time
    return parseEventDate(eventDate);
  }

  function updateCountdown() {
    const target = getEventDate();
    if (!target) { countdown = null; return; }
    const now = new Date();
    const diff = target.getTime() - now.getTime();
    if (diff <= 0) { countdown = null; return; }
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    const seconds = Math.floor((diff % (1000 * 60)) / 1000);
    countdown = { days, hours, minutes, seconds };
  }

  function generateGuestId() {
    if (typeof crypto !== 'undefined') {
      if (typeof crypto.randomUUID === 'function') {
        return crypto.randomUUID().slice(0, 8);
      }
      if (typeof crypto.getRandomValues === 'function') {
        const bytes = crypto.getRandomValues(new Uint8Array(8));
        return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('').slice(0, 8);
      }
    }
    return Math.random().toString(36).slice(2, 10);
  }

  function normalizeSlide(slide: any) {
    if (!slide) return null;
    return {
      ...slide,
      type: slide.type?.toUpperCase()
    };
  }

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

  /** Load the live session's current state from the server. Used on first
   * load, when the session goes live after this page was opened, and after a
   * WS reconnect — slide changes broadcast while the socket was down are
   * never replayed. */
  async function loadSessionState() {
    const fresh = await joinSession(code);
    const active = normalizeSlide(fresh.slides?.find((s: any) => s.is_active));
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
    const slideChanged = active?.id !== activeSlide?.id;
    session = fresh;
    error = '';
    errorKind = '';
    activeSlide = active;
    if (slideChanged) restoreSubmittedState(activeSlide);
    responses = nextResponses;
    presentationTimeline = nextTimeline;
    timelineResponses = nextTimelineResponses;
  }
  
  // A clear this guest missed (e.g. while disconnected) shows up as a higher
  // responses_cleared count in the slide data from a join/resync or a later
  // slide_change: drop the stale "already answered" state and reset the form.
  $effect(() => {
    const id = guestId;
    let reset = false;
    for (const slide of [activeSlide, activeTimelineItem?.slide]) {
      if (slide && reconcileAnsweredWithClears(id, slide)) reset = true;
    }
    if (reset) untrack(() => { responsesResetCount += 1; });
  });

  onMount(async () => {
    // Generate guest ID
    const storedGuestId = typeof localStorage !== 'undefined' ? localStorage.getItem('rforum_guest_id') : null;
    guestId = storedGuestId || generateGuestId();
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem('rforum_guest_id', guestId);
    }

    // Session codes are uppercase server-side (join already uppercases; the
    // WS endpoint and the per-session offline queue need the same form).
    code = typeof window !== 'undefined'
      ? (window.location.pathname.split('/').pop() || '').toUpperCase()
      : '';

    // Connect the WebSocket before joining (same as the screen view): join
    // only succeeds once the session is live, and the socket is how this
    // page learns that it went live (session_update) if it was opened early.
    ws = new RforumWebSocket(code);
    ws.onStatusChange((s) => {
      // Any interruption (retrying or browser-offline) needs an authoritative resync.
      const wasReconnecting = lastWsStatus === 'reconnecting' || lastWsStatus === 'offline';
      lastWsStatus = s;
      wsStatus = s;
      // Queued so the resync can't interleave with live messages.
      if (s === 'connected' && wasReconnecting) queueMessage({ event: '__resync' });
    });
    ws.onMessage(queueMessage);
    ws.connect();

    try {
      await runSerialized(loadSessionState);
    } catch (e: any) {
      setJoinError(e);
    } finally {
      loading = false;
    }

    // Retry responses saved on this device while offline (now, on 'online',
    // and periodically while any are pending) — this session's only.
    stopAutoFlush = startAutoFlush(code);

    // Start countdown if event has a future date
    updateCountdown();
    countdownInterval = setInterval(updateCountdown, 1000);
  });

  /** 404 = wrong code or not live yet (this page still updates by itself if
   * it goes live); no response / gateway errors = the venue network. */
  function setJoinError(e: any) {
    error = e?.message || 'Session not found';
    errorKind = e instanceof ApiError && e.status === 404
      ? 'not_found'
      : isConnectivityError(e) ? 'network' : 'other';
  }

  async function retryJoin() {
    if (retrying) return;
    retrying = true;
    try {
      await runSerialized(loadSessionState);
    } catch (e: any) {
      setJoinError(e);
    } finally {
      retrying = false;
    }
  }

  onDestroy(() => {
    stopAutoFlush?.();
    ws?.disconnect();
    if (countdownInterval) clearInterval(countdownInterval);
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
      // Authoritative state first, then let the server accept or refuse
      // anything saved on this device while disconnected.
      void flushPending(code);
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
      if (msg.data.slide) {
        try {
          timelineResponses = await fetchFreshResponses(msg.data.slide.id);
        } catch (err) {
          console.error('Failed to load responses for new timeline item:', err);
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
      if (msg.data?.slide) {
        // Use the slide data embedded in the message — no HTTP round-trip needed
        const cj = { ...(msg.data.slide.content_json || {}) };
        if ('file_url' in cj) { cj.has_file = true; delete cj.file_url; }
        delete cj.file_name;
        activeSlide = normalizeSlide({ ...msg.data.slide, content_json: cj });
        restoreSubmittedState(activeSlide);
        inputValue = '';
        // Always reload responses for the new slide to prevent stale data
        try {
          responses = await fetchFreshResponses(msg.data.slide.id);
        } catch (err) {
          console.error('Failed to load responses for new slide:', err);
          responses = [];
        }
      } else {
        try {
          // Fallback: re-fetch session (messages missing slide data)
          session = await joinSession(code);
          const active = normalizeSlide(session.slides?.find((s: any) => s.is_active));
          activeSlide = active || null;
          restoreSubmittedState(activeSlide);
          inputValue = '';
          if (active) {
            responses = await fetchFreshResponses(active.id);
          } else {
            responses = [];
          }
        } catch (err) {
          console.error('Failed to load session after slide change:', err);
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
    } else if (msg.event === 'clear_responses') {
      const clearedId = msg.data?.slide_id;
      if (!clearedId) return;
      if (clearedId === activeSlide?.id) responses = [];
      if (clearedId === activeTimelineItem?.slide?.id) timelineResponses = [];
      responses = responses.filter((r) => r.slide_id !== clearedId);
      timelineResponses = timelineResponses.filter((r) => r.slide_id !== clearedId);
      const clearedCount = msg.data?.responses_cleared;
      if (typeof clearedCount !== 'number') {
        // Older server without the count: this guest's earlier answer was
        // deleted too — let them respond again.
        forgetAnswered(guestId, clearedId);
        if (clearedId === activeSlide?.id || clearedId === activeTimelineItem?.slide?.id) responsesResetCount += 1;
      } else {
        // Update the local slide copies' clear count; the reconciliation
        // effect above then resets the form only if this guest's recorded
        // answer predates this clear — not one still queued on this device,
        // which the clear could not have removed.
        const withCount = (slide: any) => ({ ...slide, content_json: { ...(slide.content_json || {}), responses_cleared: clearedCount } });
        if (activeSlide?.id === clearedId) activeSlide = withCount(activeSlide);
        if (presentationTimeline) {
          presentationTimeline = {
            ...presentationTimeline,
            items: (presentationTimeline.items || []).map((i: any) => (i.slide?.id === clearedId ? { ...i, slide: withCount(i.slide) } : i))
          };
        }
      }
    } else if (msg.event === 'response_hidden') {
      const hiddenId = msg.data?.id;
      if (!hiddenId) return;
      hiddenResponses.hide(hiddenId, msg.data?.slide_id);
      responses = responses.filter((r) => r.id !== hiddenId);
      timelineResponses = timelineResponses.filter((r) => r.id !== hiddenId);
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
        error = 'This session has ended.';
        errorKind = 'ended';
      } else if (msg.data?.is_live === true) {
        try {
          await loadSessionState();
        } catch (err) {
          console.error('Failed to load session after it went live:', err);
        }
      }
    }
  }

  async function handlePollVote(option: string) {
    if (submitted) return;
    selectedOption = option;
    submitted = true;
    try {
      await submitResponse(activeSlide.id, option, guestId);
      markResponded(activeSlide.id, option);
      // No need to manually broadcast - backend handles publishing via Redis
    } catch (err: any) {
      actionError = err?.message || 'Could not submit vote';
      submitted = false;
    }
  }

  async function handleTextSubmit() {
    if (isSubmitting) return;
    if (!inputValue.trim()) return;
    isSubmitting = true;
    try {
      // Trim name and default to "Guest" if empty
      const trimmedName = guestName.trim() || "Guest";
      await submitResponse(
        activeSlide.id,
        inputValue.trim(),
        guestId,
        trimmedName !== "Guest" ? trimmedName : undefined,
        activeSlide.type === 'FEEDBACK' ? feedbackRating : undefined
      );
      // No need to manually broadcast - backend handles publishing via Redis
      inputValue = '';
      actionError = '';
      if (activeSlide.type === 'FEEDBACK') {
        submitted = true;
        markResponded(activeSlide.id, String(feedbackRating));
      }
      if (activeSlide.type === 'QNA' || activeSlide.type === 'WORD_CLOUD') {
        guestName = trimmedName;
        thankYou = true;
        setTimeout(() => { thankYou = false; }, 2000);
      }
    } catch (err: any) {
      actionError = err?.message || 'Could not submit';
      submitted = false;
    } finally {
      isSubmitting = false;
    }
  }

  async function handleUpvote(responseId: string) {
    try {
      await upvoteResponse(activeSlide.id, responseId);
      // No need to manually broadcast - backend handles publishing via Redis
      actionError = '';
    } catch (err: any) {
      actionError = err?.message || 'Could not upvote';
    }
  }
</script>

<svelte:head>
  <title>Session {code} – Rforum</title>
</svelte:head>

<div class="min-h-screen flex flex-col bg-surface-50 dark:bg-surface-950 text-surface-900 dark:text-white">
  <!-- Top Navbar with Logo, Rforum, Theme Toggle, and Code -->
  <header class="flex items-center justify-between px-4 py-1.5 border-b border-surface-200 dark:border-surface-800">
    <div class="flex items-center gap-2 flex-shrink-0">
      <Orbit class="w-5 h-5 text-brand-500" />
      <span class="font-heading font-bold text-sm tracking-wide">Rforum</span>
    </div>
    <div class="flex items-center gap-2 flex-shrink-0">
      <button
        type="button"
        onclick={toggleTheme}
        class="border border-surface-200 dark:border-surface-700 hover:bg-surface-100 dark:hover:bg-surface-800 p-2.5 rounded-lg transition active:scale-95"
        title="Toggle theme"
        aria-label={$theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
      >
        {#if $theme === 'dark'}
          <Sun class="w-4 h-4 text-surface-300" />
        {:else}
          <Moon class="w-4 h-4 text-surface-600" />
        {/if}
      </button>
      <span class="font-mono text-xs text-surface-600 dark:text-surface-400 bg-surface-100 dark:bg-surface-900 px-3 py-1 rounded-lg">{code}</span>
    </div>
  </header>

  <!-- Centered Header Section: Logo, Session Title, Moderator -->
  <div class="w-full px-4 py-3 border-b border-surface-200 dark:border-surface-800">
    <div class="flex flex-col items-center gap-2">
      <!-- Logo -->
      <img src="/logo-mascot.webp" alt="Tech Good Community" width="64" height="80" class="w-12 h-auto sm:w-14 md:w-16 opacity-90" />

      <!-- Session Title -->
      {#if session?.title}
        <h1 class="text-xl sm:text-2xl font-heading font-bold text-center text-surface-900 dark:text-white max-w-full break-words">{session.title}</h1>
      {:else if loading}
        <div class="skeleton h-7 w-48 max-w-full rounded-lg" aria-hidden="true"></div>
      {/if}

      <!-- Moderator -->
      {#if session?.moderator_name}
        <p class="text-sm text-surface-600 dark:text-surface-400 text-center break-words">
          <span class="text-xs uppercase tracking-widest text-surface-600 dark:text-surface-400">Moderator</span>
          <span class="block sm:inline">· {session.moderator_name}</span>
        </p>
      {/if}

      <!-- Speakers (if any) -->
      {#if session?.speaker_names && session.speaker_names.length > 0}
        <div class="flex flex-wrap gap-1.5 justify-center mt-1">
          <p class="w-full text-xs uppercase tracking-widest text-surface-600 dark:text-surface-400 text-center">Speakers</p>
          {#each session.speaker_names as speaker, index (speaker + index)}
            <span class="text-xs px-2 py-0.5 rounded-full bg-surface-100 dark:bg-surface-800 text-surface-700 dark:text-surface-300 break-words">{speaker}</span>
          {/each}
        </div>
      {/if}
    </div>
  </div>

  <main class="flex-1 flex flex-col items-center px-4 pt-4 pb-6 sm:pt-6 md:pt-8 overflow-y-auto">
    {#if !loading && (wsStatus === 'offline' || wsStatus === 'reconnecting')}
      <div class="w-full max-w-lg mb-3 rounded-xl border px-3 py-2 text-sm text-center {wsStatus === 'offline' ? 'border-red-300 bg-red-50 text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300' : 'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800/60 dark:bg-amber-950/30 dark:text-amber-300'}" role="status" aria-live="polite">
        {#if wsStatus === 'offline'}
          You're offline — this may not be the current slide. Answers you submit are saved on this device and sent when you reconnect.
        {:else}
          Reconnecting… the slide will update automatically.
        {/if}
      </div>
    {/if}
    {#each $rejectedSubmissions as rejection (rejection.id)}
      <div class="w-full max-w-lg mb-3 flex items-start justify-between gap-3 rounded-xl border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300" role="alert">
        <span class="min-w-0 break-words">A response saved while you were offline could not be delivered: {rejection.reason}</span>
        <button type="button" class="shrink-0 -my-1 rounded-lg px-2 py-1 font-semibold underline hover:bg-red-100 dark:hover:bg-red-950/50" onclick={() => dismissRejected(rejection.id)}>Dismiss</button>
      </div>
    {/each}

    {#if loading}
      <!-- First load: the page shell is already up; only the session itself is pending. -->
      <div class="w-full max-w-lg mt-6 space-y-3" role="status" aria-live="polite">
        <p class="text-center text-sm font-medium text-surface-600 dark:text-surface-400">Joining session…</p>
        <div class="skeleton h-40 rounded-2xl" aria-hidden="true"></div>
        <div class="skeleton h-12 rounded-xl" aria-hidden="true"></div>
      </div>
    {:else if error && !hasActiveContent}
      <div class="text-center max-w-sm w-full mt-8 animate-fade-in" role="alert">
        {#if errorKind === 'ended'}
          <h2 class="text-xl font-heading font-bold text-surface-900 dark:text-white mb-2">This session has ended</h2>
          <p class="text-sm text-surface-600 dark:text-surface-400 mb-4">Thanks for taking part.</p>
        {:else if errorKind === 'not_found'}
          <h2 class="text-xl font-heading font-bold text-surface-900 dark:text-white mb-2">Session not available</h2>
          <p class="text-sm text-surface-600 dark:text-surface-400 mb-4">Check the code <span class="font-mono font-semibold">{code}</span>. If the session hasn't started yet, keep this page open — it will update automatically when it goes live.</p>
        {:else if errorKind === 'network'}
          <h2 class="text-xl font-heading font-bold text-surface-900 dark:text-white mb-2">Can't reach the session</h2>
          <p class="text-sm text-surface-600 dark:text-surface-400 mb-4">Check your Wi-Fi connection and try again.</p>
        {:else}
          <h2 class="text-xl font-heading font-bold text-surface-900 dark:text-white mb-2">Couldn't join the session</h2>
          <p class="text-sm text-red-700 dark:text-red-300 mb-4 break-words">{error}</p>
        {/if}
        <div class="flex flex-col items-center gap-3">
          {#if errorKind !== 'ended'}
            <button
              type="button"
              class="btn-primary w-full sm:w-auto"
              onclick={retryJoin}
              disabled={retrying}
              aria-busy={retrying}
            >
              {retrying ? 'Trying again…' : 'Try again'}
            </button>
          {/if}
          <a href="/" class="inline-block px-2 py-1 text-sm font-medium text-brand-600 dark:text-brand-400 hover:underline">Go home</a>
        </div>
      </div>
    {:else if !hasActiveContent}
      <div class="text-center text-surface-600 dark:text-surface-400 animate-fade-in max-w-sm w-full mt-8">
        <Orbit class="w-16 h-16 mx-auto mb-3 text-brand-500 animate-pulse-live" />
        {#if session?.event?.title}
          <h2 class="text-xl font-heading font-bold text-surface-900 dark:text-white mb-1 break-words">{session.event.title}</h2>
        {/if}
        <p class="text-base font-medium mb-1" role="status">Waiting for the presenter...</p>
        <p class="text-sm mt-1 mb-4">The next slide will appear here automatically</p>

        {#if countdown}
          <div class="mt-4">
            <p class="text-xs uppercase tracking-widest text-surface-600 dark:text-surface-400 mb-3">Event starts in</p>
            <div class="grid grid-cols-4 gap-2 sm:gap-3">
              {#each [{ label: 'Days', value: countdown.days }, { label: 'Hours', value: countdown.hours }, { label: 'Min', value: countdown.minutes }, { label: 'Sec', value: countdown.seconds }] as unit}
                <div class="rounded-2xl bg-surface-100 dark:bg-surface-900 border border-surface-200 dark:border-surface-800 px-2 sm:px-3 py-4 flex flex-col items-center gap-1">
                  <span class="text-2xl font-heading font-bold text-surface-900 dark:text-white tabular-nums">{String(unit.value).padStart(2, '0')}</span>
                  <span class="text-xs text-surface-600 dark:text-surface-400 uppercase tracking-wider">{unit.label}</span>
                </div>
              {/each}
            </div>
          </div>
        {/if}
      </div>
    {:else if session?.presentation_id}
      <div class="w-full max-w-lg animate-fade-in mt-6">
        {#key responsesResetCount}
          <PresentationLiveView
            activeItem={activeTimelineItem}
            presentationId={session.presentation_id}
            sessionId={session.id}
            sessionCode={code || session?.unique_code || ''}
            responses={shownTimelineResponses}
            variant="guest"
            {guestId}
          />
        {/key}
      </div>
    {:else}
      <div class="w-full max-w-lg animate-fade-in mt-6">
        {#if activeSlide.type?.toUpperCase() === 'CONTENT'}
          <div class="rounded-2xl border border-surface-200 dark:border-surface-800 bg-white dark:bg-surface-900 p-4 sm:p-6 animate-fade-in min-h-[16rem] break-words">
            <ContentSlideCanvas slide={activeSlide} sessionId={session?.id} sessionCode={code} variant="guest" />
          </div>
        {:else}
          {#key responsesResetCount}
            <InteractionView
              slide={activeSlide}
              responses={shownResponses}
              variant="guest"
              {guestId}
              sessionCode={code}
            />
          {/key}
        {/if}
      </div>
    {/if}
  </main>

  <footer class="border-t mt-auto">
    <div class="flex flex-col sm:flex-row items-center justify-center gap-3 px-4 md:px-8 py-3 text-surface-600 dark:text-surface-400 text-xs">
      <span>Powered by <span class="font-semibold text-surface-700 dark:text-surface-300">Tech4Good Community</span></span>
      <span class="hidden sm:inline" aria-hidden="true">•</span>
      <span>Built with <span class="text-red-500">❤</span> by Ajith</span>
      <span class="hidden sm:inline" aria-hidden="true">•</span>
      <span>Rforum@2026</span>
    </div>
  </footer>
</div>
