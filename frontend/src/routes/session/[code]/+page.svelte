<script lang="ts">
  import { joinSession, submitResponse, upvoteResponse, listResponses, getPageImageUrl } from '$lib/api';
  import { RforumWebSocket } from '$lib/ws';
  import { theme, toggleTheme } from '$lib/theme';
  import { onMount, onDestroy } from 'svelte';
  import PageImageViewer from '$lib/components/PageImageViewer.svelte';
  import PresentationLiveView from '$lib/components/timeline/PresentationLiveView.svelte';
  import { upsertTimelineItemFromWs } from '$lib/timelineTypes';
  import {
    Orbit, Send, ChevronUp, BarChart3, MessageSquare, AlignLeft, FileText, CheckCircle2, Cloud, Sun, Moon
  } from 'lucide-svelte';

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
  let ws: RforumWebSocket | null = $state(null);
  let error = $state('');
  let loading = $state(true);
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
    return new Date(eventDate + 'T00:00:00');
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
  
  onMount(async () => {
    // Generate guest ID
    const storedGuestId = typeof localStorage !== 'undefined' ? localStorage.getItem('rforum_guest_id') : null;
    guestId = storedGuestId || generateGuestId();
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem('rforum_guest_id', guestId);
    }

    code = typeof window !== 'undefined'
      ? window.location.pathname.split('/').pop() || ''
      : '';

    try {
      session = await joinSession(code);
      const active = normalizeSlide(session.slides?.find((s: any) => s.is_active));
      if (active) {
        activeSlide = active;
        restoreSubmittedState(active);
        responses = await listResponses(active.id);
      }

      if (session.presentation_id && session.timeline) {
        presentationTimeline = session.timeline;
        const items = [...(presentationTimeline.items || [])].sort((a: any, b: any) => a.order - b.order);
        const activeItem = items.find((i: any) => i.id === presentationTimeline.active_timeline_item_id);
        if (activeItem?.slide) {
          timelineResponses = await listResponses(activeItem.slide.id);
        }
      }

      // Connect WebSocket
      ws = new RforumWebSocket(code);
      ws.connect();
      ws.onMessage(queueMessage);

      // Start countdown if event has a future date
      updateCountdown();
      countdownInterval = setInterval(updateCountdown, 1000);
    } catch (e: any) {
      error = e.message || 'Session not found';
    } finally {
      loading = false;
    }
  });

  onDestroy(() => {
    ws?.disconnect();
    if (countdownInterval) clearInterval(countdownInterval);
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
          timelineResponses = await listResponses(msg.data.slide.id);
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
          responses = await listResponses(msg.data.slide.id);
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
            responses = await listResponses(active.id);
          } else {
            responses = [];
          }
        } catch (err) {
          console.error('Failed to load session after slide change:', err);
          responses = [];
        }
      }
    } else if (msg.event === 'new_response') {
      // Only add response if it's for the current slide
      if (msg.data && activeSlide && msg.data.slide_id === activeSlide.id) {
        // Check if response already exists to prevent duplicates
        const exists = responses.some((r) => r.id === msg.data.id);
        if (!exists) {
          responses = [...responses, msg.data];
        }
      }
      if (msg.data && activeTimelineItem?.slide && msg.data.slide_id === activeTimelineItem.slide.id) {
        const timelineExists = timelineResponses.some((r) => r.id === msg.data.id);
        if (!timelineExists) {
          timelineResponses = [...timelineResponses, msg.data];
        }
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
      if (msg.data.is_live === false) {
        session = null;
        error = 'This session has ended.';
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

<div class="min-h-screen flex flex-col bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-white">
  <!-- Top Navbar with Logo, Rforum, Theme Toggle, and Code -->
  <header class="flex items-center justify-between px-4 py-1.5 border-b border-slate-200 dark:border-slate-800">
    <div class="flex items-center gap-2 flex-shrink-0">
      <Orbit class="w-5 h-5 text-purple-500" />
      <span class="font-heading font-bold text-sm tracking-wide">Rforum</span>
    </div>
    <div class="flex items-center gap-2 flex-shrink-0">
      <button
        onclick={toggleTheme}
        class="border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 p-2 rounded-lg transition active:scale-95"
        title="Toggle theme"
      >
        {#if $theme === 'dark'}
          <Sun class="w-4 h-4 text-slate-400" />
        {:else}
          <Moon class="w-4 h-4 text-slate-600" />
        {/if}
      </button>
      <span class="font-mono text-xs text-slate-500 bg-slate-100 dark:bg-slate-900 px-3 py-1 rounded-lg">{code}</span>
    </div>
  </header>

  <!-- Centered Header Section: Logo, Session Title, Moderator -->
  <div class="w-full px-4 py-3 border-b border-slate-200 dark:border-slate-800">
    <div class="flex flex-col items-center gap-2">
      <!-- Logo -->
      <img src="/logo-mascot.webp" alt="Tech Good Community" class="w-12 h-auto sm:w-14 md:w-16 opacity-90 hover:opacity-100 transition-opacity" />
      
      <!-- Session Title -->
      {#if session?.title}
        <h1 class="text-xl sm:text-2xl font-heading font-bold text-center text-slate-900 dark:text-white max-w-full">{session.title}</h1>
      {/if}
      
      <!-- Moderator -->
      {#if session?.moderator_name}
        <p class="text-sm text-slate-600 dark:text-slate-400 text-center">
          <span class="text-xs uppercase tracking-widest text-slate-500 dark:text-slate-500">Moderator</span> 
          <span class="block sm:inline">· {session.moderator_name}</span>
        </p>
      {/if}
      
      <!-- Speakers (if any) -->
      {#if session?.speaker_names && session.speaker_names.length > 0}
        <div class="flex flex-wrap gap-1.5 justify-center mt-1">
          <p class="w-full text-xs uppercase tracking-widest text-slate-500 dark:text-slate-500 text-center">Speakers</p>
          {#each session.speaker_names as speaker, index (speaker + index)}
            <span class="text-xs px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">{speaker}</span>
          {/each}
        </div>
      {/if}
    </div>
  </div>

  <main class="flex-1 flex flex-col items-center px-4 pt-4 sm:pt-6 md:pt-8 overflow-y-auto">

    {#if loading}
      <p class="text-slate-500">Connecting...</p>
    {:else if error && !hasActiveContent}
      <div class="text-center">
        <p class="text-red-500 text-lg mb-2" role="alert" aria-live="polite">{error}</p>
        <a href="/" class="text-purple-600 hover:underline text-sm">Go home</a>
      </div>
    {:else if !hasActiveContent}
      <div class="text-center text-slate-500 animate-fade-in max-w-sm w-full mt-8">
        <Orbit class="w-16 h-16 mx-auto mb-3 text-purple-400 animate-pulse-live" />
        {#if session?.event?.title}
          <h2 class="text-xl font-heading font-bold text-slate-900 dark:text-white mb-1">{session.event.title}</h2>
        {/if}
        <p class="text-base font-medium mb-1">Waiting for the presenter...</p>
        <p class="text-sm mt-1 mb-4">The next slide will appear here automatically</p>

        {#if countdown}
          <div class="mt-4">
            <p class="text-xs uppercase tracking-widest text-slate-400 mb-3">Event starts in</p>
            <div class="grid grid-cols-4 gap-3">
              {#each [{ label: 'Days', value: countdown.days }, { label: 'Hours', value: countdown.hours }, { label: 'Min', value: countdown.minutes }, { label: 'Sec', value: countdown.seconds }] as unit}
                <div class="rounded-2xl bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 px-3 py-4 flex flex-col items-center gap-1">
                  <span class="text-2xl font-heading font-bold text-slate-900 dark:text-white tabular-nums">{String(unit.value).padStart(2, '0')}</span>
                  <span class="text-xs text-slate-400 uppercase tracking-wider">{unit.label}</span>
                </div>
              {/each}
            </div>
          </div>
        {/if}
      </div>
    {:else if session?.presentation_id}
      <div class="w-full max-w-lg animate-fade-in mt-6">
        <PresentationLiveView
          activeItem={activeTimelineItem}
          presentationId={session.presentation_id}
          sessionCode={code}
          responses={timelineResponses}
          variant="guest"
          {guestId}
        />
      </div>
    {:else}
      <div class="w-full max-w-lg animate-fade-in mt-6">
        <!-- Poll Slide -->
        {#if activeSlide.type === 'POLL'}
          <div class="text-center mb-4">
            <BarChart3 class="w-10 h-10 text-purple-600 mx-auto mb-2" />
            <h1 class="text-2xl font-bold text-slate-900 dark:text-white">{activeSlide.content_json?.question}</h1>
          </div>

          {#if submitted}
            <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 text-center animate-slide-up" role="status" aria-live="polite">
              <CheckCircle2 class="w-12 h-12 text-emerald-500 mx-auto mb-3" />
              <p class="font-semibold text-slate-900 dark:text-white">Vote submitted!</p>
              <p class="text-sm text-slate-500 mt-1">You chose: {selectedOption}</p>
            </div>
          {:else}
            <div class="space-y-2">
              {#each activeSlide.content_json?.options || [] as option}
                <button
                  onclick={() => handlePollVote(option)}
                  aria-pressed={selectedOption === option}
                  class="w-full rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4
                         hover:border-purple-400 dark:hover:border-purple-500/50 hover:bg-purple-50 dark:hover:bg-purple-500/5
                         transition-all duration-200 text-left text-lg font-medium text-slate-900 dark:text-white
                         active:scale-[0.98] cursor-pointer"
                >
                  {option}
                </button>
              {/each}
            </div>
          {/if}
        {/if}

        <!-- Q&A Slide -->
        {#if activeSlide.type === 'QNA'}
          <div class="text-center mb-4">
            <MessageSquare class="w-10 h-10 text-purple-600 mx-auto mb-2" />
            <h1 class="text-2xl font-bold text-slate-900 dark:text-white">{activeSlide.content_json?.prompt}</h1>
          </div>

          <form onsubmit={(event) => { event.preventDefault(); handleTextSubmit(); }} class="space-y-2 mb-4">
            <input
              type="text"
              bind:value={guestName}
              placeholder="Your name (optional)"
              class="w-full rounded-xl px-4 py-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500/50 transition"
            />
            <div class="flex gap-2">
              <input
                type="text"
                bind:value={inputValue}
                placeholder="Type your question..."
                class="flex-1 rounded-xl px-4 py-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500/50 transition"
              />
              <button type="submit" class="btn-primary p-2" disabled={isSubmitting} aria-label="Submit question">
                <Send class="w-5 h-5" />
              </button>
            </div>
          </form>

          {#if thankYou}
            <div class="flex items-center justify-center gap-2 mb-4 text-sm text-emerald-500 animate-fade-in" role="status" aria-live="polite">
              <CheckCircle2 class="w-4 h-4" />
              Thanks for submitting your question!
            </div>
          {/if}

          {#if actionError}
            <p class="text-red-500 text-sm mb-4 text-center" role="alert">{actionError}</p>
          {/if}

          <div class="space-y-3 max-h-[50vh] overflow-y-auto">
            {#each [...responses].sort((a, b) => b.upvotes - a.upvotes) as response (response.id)}
              <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 flex items-start gap-3 animate-slide-up">
                <button
                  onclick={() => handleUpvote(response.id)}
                  aria-label={`Upvote (${response.upvotes} votes)`}
                  class="flex flex-col items-center text-slate-400 hover:text-purple-600 transition-colors shrink-0"
                >
                  <ChevronUp class="w-5 h-5" />
                  <span class="text-xs font-bold">{response.upvotes}</span>
                </button>
                <div>
                  <p class="text-slate-700 dark:text-slate-200 text-sm">{response.value}</p>
                  {#if response.name}
                    <p class="text-xs text-slate-500 mt-1">{response.name}</p>
                  {/if}
                </div>
              </div>
            {/each}
          </div>
        {/if}

        <!-- Feedback Slide -->
        {#if activeSlide.type === 'FEEDBACK'}
          <div class="text-center mb-4">
            <AlignLeft class="w-10 h-10 text-purple-600 mx-auto mb-2" />
            <h1 class="text-2xl font-bold text-slate-900 dark:text-white">{activeSlide.content_json?.prompt}</h1>
          </div>

          {#if submitted}
            <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 text-center animate-slide-up" role="status" aria-live="polite">
              <CheckCircle2 class="w-12 h-12 text-emerald-500 mx-auto mb-3" />
              <p class="font-semibold text-slate-900 dark:text-white">Thanks for your feedback!</p>
            </div>
          {:else}
            <form onsubmit={(event) => { event.preventDefault(); handleTextSubmit(); }}>
              <input
                type="text"
                bind:value={guestName}
                placeholder="Your name (optional)"
                class="w-full rounded-xl px-4 py-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500/50 transition mb-2"
              />
              <textarea
                bind:value={inputValue}
                placeholder="Share your thoughts..."
                rows="4"
                class="w-full rounded-xl px-4 py-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500/50 transition mb-2 resize-none"
              ></textarea>
              <div class="flex items-center gap-2 mb-3">
                <label for="feedback-rating" class="text-sm text-slate-500 dark:text-slate-400">Rating</label>
                <input
                  id="feedback-rating"
                  type="number"
                  min="1"
                  max="5"
                  bind:value={feedbackRating}
                  class="w-24 rounded-xl px-4 py-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-purple-500/50 transition"
                />
              </div>
              <button type="submit" class="btn-primary w-full flex items-center justify-center gap-2" disabled={isSubmitting}>
                <Send class="w-4 h-4" />
                Submit
              </button>
            </form>
          {/if}
        {/if}

        <!-- Word Cloud Slide -->
        {#if activeSlide.type === 'WORD_CLOUD'}
          <div class="text-center mb-4">
            <Cloud class="w-10 h-10 text-purple-600 mx-auto mb-2" />
            <h1 class="text-2xl font-bold text-slate-900 dark:text-white">{activeSlide.content_json?.prompt}</h1>
          </div>

          <form onsubmit={(event) => { event.preventDefault(); handleTextSubmit(); }} class="space-y-2 mb-4">
            <input
              type="text"
              bind:value={guestName}
              placeholder="Your name (optional)"
              class="w-full rounded-xl px-4 py-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500/50 transition"
            />
            <div class="flex gap-2">
              <input
                type="text"
                bind:value={inputValue}
                placeholder="Type your answer..."
                class="flex-1 rounded-xl px-4 py-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500/50 transition"
              />
              <button type="submit" class="btn-primary p-2" disabled={isSubmitting} aria-label="Submit answer">
                <Send class="w-5 h-5" />
              </button>
            </div>
          </form>

          {#if thankYou}
            <div class="flex items-center justify-center gap-2 text-sm text-emerald-500 animate-fade-in" role="status" aria-live="polite">
              <CheckCircle2 class="w-4 h-4" />
              Thanks for your answer!
            </div>
          {/if}

          {#if actionError}
            <p class="text-red-500 text-sm text-center" role="alert">{actionError}</p>
          {/if}
        {/if}

        <!-- Content Slide -->
        {#if activeSlide.type === 'CONTENT'}
          <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 text-center animate-fade-in">
            <FileText class="w-10 h-10 text-purple-600 mx-auto mb-4" />
            <h1 class="text-2xl font-bold text-slate-900 dark:text-white mb-4">{activeSlide.content_json?.title}</h1>
            <p class="text-slate-600 dark:text-slate-300 leading-relaxed">{activeSlide.content_json?.body}</p>
              {#if (activeSlide.content_json?.file_url || activeSlide.content_json?.has_file) && session?.id}
                <div style="-webkit-touch-callout: none; -webkit-user-select: none;">
                  <PageImageViewer
                    src={getPageImageUrl(session.id, activeSlide.id, activeSlide.content_json?.file_page || 1, code)}
                    page={activeSlide.content_json?.file_page || 1}
                    alt={`Slide page ${activeSlide.content_json?.file_page || 1}`}
                    imgClass="w-full mt-6 rounded-xl border border-slate-200 dark:border-slate-800 select-none pointer-events-none"
                  />
                </div>
                <div class="text-xs text-slate-500 mt-2">Page {activeSlide.content_json?.file_page || 1}{activeSlide.content_json?.total_pages ? ` / ${activeSlide.content_json.total_pages}` : ''}</div>
              {/if}
          </div>
        {/if}
      </div>
    {/if}
  </main>

  <footer class="border-t mt-auto">
    <div class="flex flex-col sm:flex-row items-center justify-center gap-3 px-4 md:px-8 py-3 text-slate-500 dark:text-slate-400 text-xs">
      <span>Powered by <span class="font-semibold text-slate-600 dark:text-slate-300">Tech4Good Community</span></span>
      <span class="hidden sm:inline">•</span>
      <span>Built with <span class="text-red-500">❤</span> by Ajith</span>
      <span class="hidden sm:inline">•</span>
      <span>Rforum@2026</span>
    </div>
  </footer>
</div>
