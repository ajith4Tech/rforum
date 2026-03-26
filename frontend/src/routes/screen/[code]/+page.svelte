<script lang="ts">
  import { joinSession, listResponses, getPageImageUrl } from '$lib/api';
  import { RforumWebSocket } from '$lib/ws';
  import { onMount, onDestroy } from 'svelte';
  import { BarChart3, MessageSquare, AlignLeft, FileText, Orbit, Cloud } from 'lucide-svelte';

  let code = $state('');
  let session: any = $state(null);
  let activeSlide: any = $state(null);
  let responses: any[] = $state([]);
  let ws: RforumWebSocket | null = $state(null);
  let loading = $state(true);
  let error = $state('');
  let guestUrl = $state('');

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

  onMount(async () => {
    code = typeof window !== 'undefined'
      ? window.location.pathname.split('/').pop() || ''
      : '';
    guestUrl = typeof window !== 'undefined' ? `${window.location.origin}/session/${code}` : '';
    
    console.log('[screen] Mounting with code:', code);

    // Always connect WS so the screen auto-recovers when the session starts
    ws = new RforumWebSocket(code);
    ws.connect();
    ws.onMessage(queueMessage);

    try {
      console.log('[screen] Loading session:', code);
      session = await joinSession(code);
      console.log('[screen] Session loaded, slides:', session.slides?.length);
      
      const active = session.slides?.find((s: any) => s.is_active);
      if (active) {
        console.log('[screen] Found active slide:', active.id);
        activeSlide = { ...active, type: active.type?.toUpperCase() };
        console.log('[screen] Loading responses for slide:', active.id);
        responses = await listResponses(active.id);
        console.log('[screen] Loaded initial responses:', responses.length);
      } else {
        console.log('[screen] No active slide found yet');
      }
    } catch (e: any) {
      console.error('[screen] Error in onMount:', e);
      error = e.message || 'Session not found';
    } finally {
      loading = false;
    }
  });

  onDestroy(() => {
    ws?.disconnect();
  });

  async function handleWsMessage(msg: any) {
    console.log('[screen] WebSocket message received:', msg.event);
    
    if (msg.event === 'slide_change') {
      console.log('[screen] Slide change event - has slide data:', !!msg.data?.slide);
      if (msg.data?.slide) {
        // Use the slide data embedded in the message — no HTTP round-trip needed
        const cj = { ...(msg.data.slide.content_json || {}) };
        if ('file_url' in cj) { cj.has_file = true; delete cj.file_url; }
        delete cj.file_name;
        activeSlide = { ...msg.data.slide, type: msg.data.slide.type?.toUpperCase(), content_json: cj };
        console.log('[screen] Active slide updated:', activeSlide.id);
        
        // Always reload responses for the new slide to prevent stale data
        // Reload immediately with a small delay to ensure DB is updated
        try {
          console.log('[screen] Starting response fetch for slide:', msg.data.slide.id);
          await new Promise(resolve => setTimeout(resolve, 100));
          const fetchedResponses = await listResponses(msg.data.slide.id);
          console.log('[screen] Responses fetched successfully:', fetchedResponses.length, 'responses');
          responses = fetchedResponses;
        } catch (err) {
          console.error('[screen] Failed to load responses for new slide:', err);
          // Retry once more after delay
          await new Promise(resolve => setTimeout(resolve, 200));
          try {
            const retryResponses = await listResponses(msg.data.slide.id);
            responses = retryResponses;
            console.log('[screen] Retry successful:', retryResponses.length, 'responses');
          } catch (retryErr) {
            console.error('[screen] Retry also failed:', retryErr);
            responses = [];
          }
        }
      } else {
        console.log('[screen] No slide data in message, re-fetching session');
        try {
          session = await joinSession(code);
          const active = session.slides?.find((s: any) => s.is_active);
          activeSlide = active ? { ...active, type: active.type?.toUpperCase() } : null;
          if (active) {
            await new Promise(resolve => setTimeout(resolve, 100));
            const fetchedResponses = await listResponses(active.id);
            responses = fetchedResponses;
            console.log('[screen] Re-fetched session, loaded', fetchedResponses.length, 'responses');
          } else {
            responses = [];
          }
        } catch (err) {
          console.error('[screen] Failed to load session after slide change:', err);
          responses = [];
        }
      }
    } else if (msg.event === 'new_response') {
      // Only add response if it's for the current slide
      if (msg.data && activeSlide && msg.data.slide_id === activeSlide.id) {
        // Check if response already exists to prevent duplicates
        const exists = responses.some((r) => r.id === msg.data.id);
        if (!exists) {
          console.log('[screen] Adding new response');
          responses = [...responses, msg.data];
        }
      }
    } else if (msg.event === 'upvote') {
      // Update the response with new upvote count
      responses = responses.map((r) =>
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
      } else if (msg.data?.is_live === true && !session) {
        // Session started — load it now
        try {
          error = '';
          session = await joinSession(code);
          const active = session.slides?.find((s: any) => s.is_active);
          if (active) {
            activeSlide = { ...active, type: active.type?.toUpperCase() };
            const fetchedResponses = await listResponses(active.id);
            responses = fetchedResponses;
          }
        } catch (e: any) {
          console.error('[screen] Failed to load session:', e);
          error = e.message || 'Failed to load session';
        }
      }
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

<div class="min-h-screen flex flex-col bg-gray-950 text-white font-sans select-none overflow-hidden">
  <!-- Header -->
  <header class="flex items-center justify-between px-4 md:px-8 py-3 md:py-4 border-b border-white/10 flex-shrink-0 gap-4">
    <!-- Left: Logo -->
    <div class="flex items-center gap-2.5 flex-shrink-0">
      <Orbit class="w-5 md:w-6 h-5 md:h-6 text-brand-400" />
      <span class="font-heading font-bold text-base md:text-lg tracking-wide text-white/80">Rforum</span>
    </div>

    <!-- Center: Code -->
    <div class="flex flex-col items-center gap-0.5 flex-1 justify-center">
      <span class="text-[10px] md:text-xs text-white/40 uppercase tracking-widest">Code</span>
      <span class="font-mono font-bold text-2xl md:text-3xl tracking-[0.15em] md:tracking-[0.25em] text-white">{code}</span>
    </div>

    <!-- Right: Session, Moderator and QR -->
    <div class="flex items-center gap-4 flex-shrink-0">
      <!-- Session and Moderator info -->
      <div class="flex flex-col gap-1 text-right">
        {#if session?.title}
          <div class="flex flex-col gap-0.5">
            <p class="text-[10px] md:text-xs text-white/40 uppercase tracking-widest">Session</p>
            <p class="text-xs md:text-sm font-semibold text-white truncate max-w-xs">{session.title}</p>
          </div>
        {/if}
        {#if session?.moderator_name}
          <div class="flex flex-col gap-0.5">
            <p class="text-[10px] md:text-xs text-white/40 uppercase tracking-widest">Moderator</p>
            <p class="text-xs md:text-sm font-semibold text-white truncate max-w-xs">{session.moderator_name}</p>
          </div>
        {/if}
      </div>

      <!-- QR code -->
      <div class="flex flex-col items-center gap-1">
        {#if guestUrl}
          <span class="text-[10px] md:text-xs text-white/40 tracking-wide">Scan to Join</span>
          <img
            src={`https://api.qrserver.com/v1/create-qr-code/?size=120x120&data=${encodeURIComponent(guestUrl)}&bgcolor=0f172a&color=ffffff&qzone=1`}
            alt="Join QR"
            class="rounded-xl border border-white/10 w-14 md:w-16 h-14 md:h-16"
          />
        {/if}
      </div>
    </div>
  </header>

  <!-- Centered Logo Section -->
  <div class="flex justify-center pt-4 sm:pt-5 md:pt-6 pb-6 sm:pb-8 md:pb-10">
    <img src="/logo-mascot.webp" alt="Tech Good Community" class="w-16 h-auto sm:w-20 md:w-24 lg:w-28 opacity-90 hover:opacity-100 transition-opacity" />
  </div>

  <!-- Main -->
  <main class="flex-1 flex flex-col items-center justify-start px-4 md:px-8 overflow-y-auto overflow-x-hidden">
    {#if loading}
      <div class="text-center py-20">
        <Orbit class="w-12 h-12 text-brand-400 mx-auto mb-4 animate-pulse" />
        <p class="text-white/50 text-lg">Connecting…</p>
      </div>

    {:else if error}
      <div class="text-center animate-fade-in space-y-6 py-16">
        <Orbit class="w-20 h-20 mx-auto text-brand-400/50 animate-pulse" />
        <p class="text-3xl font-heading font-bold text-white/60">Waiting for session…</p>
        <p class="text-white/40 text-lg">{error}</p>
        <div class="mt-6 flex flex-col items-center gap-1">
          <span class="text-white/30 text-sm tracking-widest uppercase">Code</span>
          <span class="font-mono text-5xl font-bold tracking-[0.3em] text-brand-400">{code}</span>
        </div>
      </div>

    {:else if !activeSlide}
      <div class="text-center animate-fade-in space-y-6 py-12 mt-6">
        <Orbit class="w-20 h-20 mx-auto text-brand-400 animate-pulse" />
        <p class="text-3xl font-heading font-bold text-white/80">Waiting for presenter…</p>
        <p class="text-white/40 text-lg">The session is live. Slides will appear here automatically.</p>
        <div class="mt-8 flex flex-col items-center gap-1">
          <span class="text-white/30 text-sm tracking-widest uppercase">Join with code</span>
          <span class="font-mono text-5xl font-bold tracking-[0.3em] text-brand-400">{code}</span>
        </div>
      </div>

    {:else}
      <div class="w-full max-w-5xl flex flex-col gap-4 mt-6">

        <!-- POLL -->
        {#if activeSlide.type === 'POLL'}
          <div class="flex flex-col gap-4 w-full">
            <div class="text-center">
              <div class="inline-flex items-center gap-2 bg-brand-500/10 text-brand-400 text-xs font-bold uppercase tracking-widest px-3 py-1 rounded-full mb-3">
                <BarChart3 class="w-3.5 h-3.5" /> Poll
              </div>
              <h1 class="text-4xl font-heading font-bold text-white leading-snug">{activeSlide.content_json?.question}</h1>
              <p class="text-white/40 mt-1 text-sm">{responses.length} response{responses.length === 1 ? '' : 's'}</p>
            </div>
            <div class="space-y-4 max-h-[60vh] overflow-y-auto pr-1">
              {#each getPollResults(activeSlide) as row, i}
                {@const hues = ['bg-brand-500','bg-cyan-500','bg-emerald-500','bg-amber-500','bg-rose-500','bg-violet-500']}
                <div class="space-y-1">
                  <div class="flex items-center justify-between text-sm">
                    <span class="font-semibold text-white/80 text-lg">{row.label}</span>
                    <span class="font-mono font-bold text-white text-xl">{row.percent}%</span>
                  </div>
                  <div class="relative h-10 bg-white/5 rounded-xl overflow-hidden">
                    <div
                      class="absolute inset-y-0 left-0 rounded-xl transition-all duration-700 {hues[i % hues.length]}"
                      style={`width: ${row.percent}%; min-width: ${row.percent > 0 ? '12px' : '0'}`}
                    ></div>
                    <span class="absolute inset-y-0 right-3 flex items-center text-white/50 text-sm font-mono">{row.count}</span>
                  </div>
                </div>
              {/each}
            </div>
          </div>

        <!-- Q&A -->
        {:else if activeSlide.type === 'QNA'}
          <div class="flex flex-col gap-4 w-full">
            <div class="text-center">
              <div class="inline-flex items-center gap-2 bg-cyan-500/10 text-cyan-400 text-xs font-bold uppercase tracking-widest px-3 py-1 rounded-full mb-3">
                <MessageSquare class="w-3.5 h-3.5" /> Q&A
              </div>
              <h1 class="text-4xl font-heading font-bold text-white leading-snug">{activeSlide.content_json?.prompt}</h1>
              <p class="text-white/40 mt-1 text-sm">{responses.length} question{responses.length === 1 ? '' : 's'}</p>
            </div>
            {#if responses.length === 0}
              <div class="text-center text-white/30 text-lg py-8">No questions yet…</div>
            {:else}
              <div class="max-h-[60vh] overflow-y-auto space-y-3 pr-1 mask-fade-bottom">
                {#each [...responses].sort((a, b) => (b.upvotes ?? 0) - (a.upvotes ?? 0)) as response (response.id)}
                  <div class="flex items-start gap-4 bg-white/5 border border-white/10 rounded-2xl px-5 py-4">
                    <div class="flex flex-col items-center gap-0.5 flex-shrink-0 min-w-[2.5rem]">
                      <span class="text-2xl font-bold text-brand-400">{response.upvotes ?? 0}</span>
                      <span class="text-[10px] text-white/30 uppercase tracking-wide">votes</span>
                    </div>
                    <div class="flex-1">
                      <p class="text-white text-lg font-medium leading-snug">{response.value}</p>
                      <p class="text-white/30 text-xs mt-1">{response.name || response.guest_identifier}</p>
                    </div>
                  </div>
                {/each}
              </div>
            {/if}
          </div>

        <!-- FEEDBACK -->
        {:else if activeSlide.type === 'FEEDBACK'}
          <div class="flex flex-col gap-4 w-full">
            <div class="text-center">
              <div class="inline-flex items-center gap-2 bg-rose-500/10 text-rose-400 text-xs font-bold uppercase tracking-widest px-3 py-1 rounded-full mb-3">
                <AlignLeft class="w-3.5 h-3.5" /> Feedback
              </div>
              <h1 class="text-4xl font-heading font-bold text-white leading-snug">{activeSlide.content_json?.prompt}</h1>
              <p class="text-white/40 mt-1 text-sm">{responses.length} response{responses.length === 1 ? '' : 's'}</p>
            </div>
            {#if responses.length === 0}
              <div class="text-center text-white/30 text-lg py-8">No feedback yet…</div>
            {:else}
              <div class="max-h-[60vh] overflow-y-auto space-y-3 pr-1">
                {#each responses as response (response.id)}
                  <div class="bg-white/5 border border-white/10 rounded-2xl px-5 py-4">
                    <div class="flex items-center justify-between mb-2">
                      <span class="text-white/30 text-xs">{response.name || response.guest_identifier}</span>
                      {#if response.rating}
                        <span class="text-amber-400 text-sm font-bold">{'★'.repeat(response.rating)}{'☆'.repeat(5 - response.rating)}</span>
                      {/if}
                    </div>
                    <p class="text-white text-lg leading-snug">{response.value}</p>
                  </div>
                {/each}
              </div>
            {/if}
          </div>

        <!-- WORD CLOUD -->
        {:else if activeSlide.type === 'WORD_CLOUD'}
          <div class="flex flex-col gap-4 w-full">
            <div class="text-center">
              <div class="inline-flex items-center gap-2 bg-violet-500/10 text-violet-400 text-xs font-bold uppercase tracking-widest px-3 py-1 rounded-full mb-3">
                <Cloud class="w-3.5 h-3.5" /> Word Cloud
              </div>
              <h1 class="text-4xl font-heading font-bold text-white leading-snug">{activeSlide.content_json?.prompt}</h1>
              <p class="text-white/40 mt-1 text-sm">{responses.length} response{responses.length === 1 ? '' : 's'}</p>
            </div>
            {#if responses.length === 0}
              <div class="text-center text-white/30 text-lg py-12">Waiting for responses…</div>
            {:else}
              {@const palette = ['text-brand-400','text-cyan-400','text-emerald-400','text-amber-400','text-rose-400','text-violet-400','text-sky-400','text-pink-400']}
              <div class="flex flex-wrap items-center justify-center gap-x-6 gap-y-3 max-h-[60vh] overflow-y-auto p-4">
                {#each getWordCloudData() as item, i}
                  <span
                    class="font-heading font-bold transition-all duration-500 {palette[i % palette.length]}"
                    style={`font-size: ${item.size}rem; opacity: ${0.55 + (item.count / (responses.length || 1)) * 0.45}`}
                  >{item.word}</span>
                {/each}
              </div>
            {/if}
          </div>

        <!-- CONTENT -->
        {:else if activeSlide.type === 'CONTENT'}
          <div class="flex flex-col items-center gap-4 w-full">
            {#if !activeSlide.content_json?.file_url && !activeSlide.content_json?.has_file}
              <!-- Text-only content slide -->
              <div class="flex flex-col items-center justify-start text-center px-8 gap-6 max-w-3xl mx-auto py-8">
                <FileText class="w-14 h-14 text-brand-400 opacity-60" />
                <h1 class="text-5xl font-heading font-bold text-white leading-tight">{activeSlide.content_json?.title}</h1>
                {#if activeSlide.content_json?.body}
                  <p class="text-white/60 text-2xl leading-relaxed whitespace-pre-wrap">{activeSlide.content_json.body}</p>
                {/if}
              </div>
            {:else}
              <!-- File/image content slide -->
              <div class="w-full flex flex-col items-center gap-4 max-h-[70vh]">
                {#if activeSlide.content_json?.title}
                  <h1 class="text-3xl font-heading font-bold text-white text-center">{activeSlide.content_json.title}</h1>
                {/if}
                {#key activeSlide.content_json?.file_page}
                  <img
                    alt={`Slide page ${activeSlide.content_json?.file_page || 1}`}
                    src={getPageImageUrl(session.id, activeSlide.id, activeSlide.content_json?.file_page || 1)}
                    class="max-w-full max-h-[65vh] w-auto rounded-2xl border border-white/10 object-contain shadow-2xl"
                    draggable="false"
                  />
                {/key}
                {#if activeSlide.content_json?.total_pages}
                  <p class="text-white/30 text-sm font-mono">
                    Page {activeSlide.content_json.file_page || 1} / {activeSlide.content_json.total_pages}
                  </p>
                {/if}
              </div>
            {/if}
          </div>
        {/if}

      </div>
    {/if}
  </main>
</div>

