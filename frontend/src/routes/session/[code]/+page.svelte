<script lang="ts">
  import { joinSession, submitResponse, upvoteResponse, listResponses, getPageImageUrl } from '$lib/api';
  import { RforumWebSocket } from '$lib/ws';
  import { onMount, onDestroy } from 'svelte';
  import {
    Radio, Send, ChevronUp, BarChart3, MessageSquare, AlignLeft, FileText, CheckCircle2, Cloud
  } from 'lucide-svelte';

  let code = $state('');

  let session: any = $state(null);
  let activeSlide: any = $state(null);
  let responses: any[] = $state([]);
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
        responses = await listResponses(active.id);
      }

      // Connect WebSocket
      ws = new RforumWebSocket(code);
      ws.connect();
      ws.onMessage(handleWsMessage);
    } catch (e: any) {
      error = e.message || 'Session not found';
    } finally {
      loading = false;
    }
  });

  onDestroy(() => {
    ws?.disconnect();
  });

  async function handleWsMessage(msg: any) {
    if (msg.event === 'slide_change') {
      // Reload session to get new active slide
      session = await joinSession(code);
      const active = normalizeSlide(session.slides?.find((s: any) => s.is_active));
      activeSlide = active || null;
      submitted = false;
      selectedOption = '';
      inputValue = '';
      if (active) responses = await listResponses(active.id);
    } else if (msg.event === 'new_response') {
      responses = [...responses, msg.data];
    } else if (msg.event === 'upvote') {
      responses = responses.map((r) =>
        r.id === msg.data.id ? { ...r, upvotes: msg.data.upvotes } : r
      );
    } else if (msg.event === 'session_update') {
      if (msg.data.is_live === false) {
        session = null;
        error = 'This session has ended.';
      }
    }
  }

  async function handlePollVote(option: string) {
    selectedOption = option;
    submitted = true;
    try {
      const response = await submitResponse(activeSlide.id, option, guestId);
      ws?.send('new_response', response);
    } catch (err: any) {
      actionError = err?.message || 'Could not submit vote';
      submitted = false;
    }
  }

  async function handleTextSubmit() {
    if (!inputValue.trim()) return;
    if ((activeSlide.type === 'QNA' || activeSlide.type === 'FEEDBACK' || activeSlide.type === 'WORD_CLOUD') && !guestName.trim()) {
      alert('Please enter your name.');
      return;
    }
    if (activeSlide.type === 'POLL') {
      submitted = true;
    }
    try {
      const response = await submitResponse(
        activeSlide.id,
        inputValue.trim(),
        guestId,
        guestName || undefined,
        activeSlide.type === 'FEEDBACK' ? feedbackRating : undefined
      );
      ws?.send('new_response', response);
      inputValue = '';
      actionError = '';
      if (activeSlide.type !== 'POLL') {
        submitted = false;
      }
      if (activeSlide.type === 'QNA' || activeSlide.type === 'WORD_CLOUD') {
        guestName = guestName.trim();
        thankYou = true;
        setTimeout(() => { thankYou = false; }, 2000);
      }
    } catch (err: any) {
      actionError = err?.message || 'Could not submit';
      submitted = false;
    }
  }

  async function handleUpvote(responseId: string) {
    try {
      const updated = await upvoteResponse(activeSlide.id, responseId);
      ws?.send('upvote', updated);
      responses = responses.map((r) =>
        r.id === responseId ? { ...r, upvotes: updated.upvotes } : r
      );
      actionError = '';
    } catch (err: any) {
      actionError = err?.message || 'Could not upvote';
    }
  }
</script>

<svelte:head>
  <title>Session {code} – Rforum</title>
</svelte:head>

<div class="min-h-screen flex flex-col bg-surface-950">
  <!-- Header -->
  <header class="flex items-center justify-between px-4 py-3 border-b border-surface-800">
    <div class="flex items-center gap-2">
      <Radio class="w-5 h-5 text-brand-400" />
      <span class="font-bold text-sm">Rforum</span>
    </div>
    <span class="font-mono text-xs text-surface-500 bg-surface-900 px-3 py-1 rounded-lg">{code}</span>
  </header>

  <main class="flex-1 flex flex-col items-center justify-center px-4 py-6">
    {#if loading}
      <p class="text-surface-500">Connecting...</p>
    {:else if error && !activeSlide}
      <div class="text-center">
        <p class="text-danger text-lg mb-2">{error}</p>
        <a href="/" class="text-brand-400 hover:underline text-sm">Go home</a>
      </div>
    {:else if !activeSlide}
      <div class="text-center text-surface-500 animate-fade-in">
        <Radio class="w-16 h-16 mx-auto mb-4 text-surface-700 animate-pulse-live" />
        <p class="text-lg font-medium">Waiting for the presenter...</p>
        <p class="text-sm mt-2">The next slide will appear here automatically</p>
      </div>
    {:else}
      <div class="w-full max-w-lg animate-fade-in">
        <!-- Poll Slide -->
        {#if activeSlide.type === 'POLL'}
          <div class="text-center mb-8">
            <BarChart3 class="w-10 h-10 text-brand-400 mx-auto mb-3" />
            <h1 class="text-2xl font-bold">{activeSlide.content_json?.question}</h1>
          </div>

          {#if submitted}
            <div class="card text-center animate-slide-up">
              <CheckCircle2 class="w-12 h-12 text-success mx-auto mb-3" />
              <p class="font-semibold">Vote submitted!</p>
              <p class="text-sm text-surface-400 mt-1">You chose: {selectedOption}</p>
            </div>
          {:else}
            <div class="space-y-3">
              {#each activeSlide.content_json?.options || [] as option}
                <button
                  onclick={() => handlePollVote(option)}
                  class="w-full card hover:border-brand-500/50 hover:bg-brand-500/5
                         transition-all duration-200 text-left text-lg font-medium
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
          <div class="text-center mb-8">
            <MessageSquare class="w-10 h-10 text-brand-400 mx-auto mb-3" />
            <h1 class="text-2xl font-bold">{activeSlide.content_json?.prompt}</h1>
          </div>

          <form onsubmit={(event) => { event.preventDefault(); handleTextSubmit(); }} class="space-y-3 mb-6">
            <input
              type="text"
              bind:value={guestName}
              placeholder="Your name"
              class="input-field"
            />
            <div class="flex gap-3">
              <input
                type="text"
                bind:value={inputValue}
                placeholder="Type your question..."
                class="input-field flex-1"
              />
              <button type="submit" class="btn-primary p-3">
                <Send class="w-5 h-5" />
              </button>
            </div>
          </form>

          {#if thankYou}
            <div class="flex items-center justify-center gap-2 mb-4 text-sm text-success animate-fade-in">
              <CheckCircle2 class="w-4 h-4" />
              Thanks for submitting your question!
            </div>
          {/if}

          {#if actionError}
            <p class="text-danger text-sm mb-4 text-center">{actionError}</p>
          {/if}

          <div class="space-y-3 max-h-[50vh] overflow-y-auto">
            {#each [...responses].sort((a, b) => b.upvotes - a.upvotes) as response (response.id)}
              <div class="card flex items-start gap-3 animate-slide-up">
                <button
                  onclick={() => handleUpvote(response.id)}
                  class="flex flex-col items-center text-surface-400 hover:text-brand-400 transition-colors shrink-0"
                >
                  <ChevronUp class="w-5 h-5" />
                  <span class="text-xs font-bold">{response.upvotes}</span>
                </button>
                <div>
                  <p class="text-surface-200 text-sm">{response.value}</p>
                  {#if response.name}
                    <p class="text-xs text-surface-500 mt-1">{response.name}</p>
                  {/if}
                </div>
              </div>
            {/each}
          </div>
        {/if}

        <!-- Feedback Slide -->
        {#if activeSlide.type === 'FEEDBACK'}
          <div class="text-center mb-8">
            <AlignLeft class="w-10 h-10 text-brand-400 mx-auto mb-3" />
            <h1 class="text-2xl font-bold">{activeSlide.content_json?.prompt}</h1>
          </div>

          {#if submitted}
            <div class="card text-center animate-slide-up">
              <CheckCircle2 class="w-12 h-12 text-success mx-auto mb-3" />
              <p class="font-semibold">Thanks for your feedback!</p>
            </div>
          {:else}
            <form onsubmit={(event) => { event.preventDefault(); handleTextSubmit(); }}>
              <input
                type="text"
                bind:value={guestName}
                placeholder="Your name"
                class="input-field mb-3"
              />
              <textarea
                bind:value={inputValue}
                placeholder="Share your thoughts..."
                rows="4"
                class="input-field mb-4 resize-none"
              ></textarea>
              <div class="flex items-center gap-3 mb-4">
                <label for="feedback-rating" class="text-sm text-surface-400">Rating</label>
                <input
                  id="feedback-rating"
                  type="number"
                  min="1"
                  max="5"
                  bind:value={feedbackRating}
                  class="input-field w-24"
                />
              </div>
              <button type="submit" class="btn-primary w-full flex items-center justify-center gap-2">
                <Send class="w-4 h-4" />
                Submit
              </button>
            </form>
          {/if}
        {/if}

        <!-- Word Cloud Slide -->
        {#if activeSlide.type === 'WORD_CLOUD'}
          <div class="text-center mb-8">
            <Cloud class="w-10 h-10 text-brand-400 mx-auto mb-3" />
            <h1 class="text-2xl font-bold">{activeSlide.content_json?.prompt}</h1>
          </div>

          <form onsubmit={(event) => { event.preventDefault(); handleTextSubmit(); }} class="space-y-3 mb-6">
            <input
              type="text"
              bind:value={guestName}
              placeholder="Your name"
              class="input-field"
            />
            <div class="flex gap-3">
              <input
                type="text"
                bind:value={inputValue}
                placeholder="Type your answer..."
                class="input-field flex-1"
              />
              <button type="submit" class="btn-primary p-3">
                <Send class="w-5 h-5" />
              </button>
            </div>
          </form>

          {#if thankYou}
            <div class="flex items-center justify-center gap-2 mb-4 text-sm text-success animate-fade-in">
              <CheckCircle2 class="w-4 h-4" />
              Thanks for your answer!
            </div>
          {/if}

          {#if actionError}
            <p class="text-danger text-sm mb-4 text-center">{actionError}</p>
          {/if}
        {/if}

        <!-- Content Slide -->
        {#if activeSlide.type === 'CONTENT'}
          <div class="card text-center animate-fade-in">
            <FileText class="w-10 h-10 text-brand-400 mx-auto mb-4" />
            <h1 class="text-2xl font-bold mb-4">{activeSlide.content_json?.title}</h1>
            <p class="text-surface-300 leading-relaxed">{activeSlide.content_json?.body}</p>
              {#if activeSlide.content_json?.file_url && session?.id}
                {#key activeSlide.content_json?.file_page}
                  <img
                    alt={`Slide page ${activeSlide.content_json?.file_page || 1}`}
                    src={getPageImageUrl(session.id, activeSlide.id, activeSlide.content_json?.file_page || 1)}
                    class="w-full mt-6 rounded-xl border border-surface-800 select-none"
                    draggable="false"
                    oncontextmenu={(e) => e.preventDefault()}
                  />
                {/key}
                <div class="text-xs text-surface-500 mt-2">Page {activeSlide.content_json?.file_page || 1} / {activeSlide.content_json?.total_pages || 1}</div>
              {/if}
          </div>
        {/if}
      </div>
    {/if}
  </main>
</div>
