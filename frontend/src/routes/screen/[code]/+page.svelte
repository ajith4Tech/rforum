<script lang="ts">
  import { joinSession, listResponses, getPageImageUrl } from '$lib/api';
  import { RforumWebSocket } from '$lib/ws';
  import { onMount, onDestroy } from 'svelte';
  import { BarChart3, MessageSquare, AlignLeft, FileText, RadioTower, Cloud } from 'lucide-svelte';

  let code = $state('');
  let session: any = $state(null);
  let activeSlide: any = $state(null);
  let responses: any[] = $state([]);
  let ws: RforumWebSocket | null = $state(null);
  let loading = $state(true);
  let error = $state('');
  let guestUrl = $state('');

  onMount(async () => {
    code = typeof window !== 'undefined'
      ? window.location.pathname.split('/').pop() || ''
      : '';
    guestUrl = typeof window !== 'undefined' ? `${window.location.origin}/session/${code}` : '';

    try {
      session = await joinSession(code);
      const active = session.slides?.find((s: any) => s.is_active);
      if (active) {
        activeSlide = { ...active, type: active.type?.toUpperCase() };
        responses = await listResponses(active.id);
      }

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
      session = await joinSession(code);
      const active = session.slides?.find((s: any) => s.is_active);
      activeSlide = active ? { ...active, type: active.type?.toUpperCase() } : null;
      if (active) responses = await listResponses(active.id);
    } else if (msg.event === 'new_response') {
      responses = [...responses, msg.data];
    } else if (msg.event === 'upvote') {
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

<div class="min-h-screen flex flex-col bg-surface-950">
  <header class="flex items-center justify-between px-6 py-4 border-b border-surface-800">
    <div class="flex items-center gap-2">
      <RadioTower class="w-5 h-5 text-brand-500" />
      <span class="font-bold text-sm">Rforum</span>
    </div>
    <div class="flex items-center gap-4">
      {#if guestUrl}
        <div class="text-xs text-surface-500">Scan to join</div>
        <img
          src={`https://api.qrserver.com/v1/create-qr-code/?size=140x140&data=${encodeURIComponent(guestUrl)}`}
          alt="Join QR"
          class="rounded-lg border border-surface-800"
        />
      {/if}
      <span class="font-mono text-xs text-surface-500 bg-surface-900 px-3 py-1 rounded-lg">{code}</span>
    </div>
  </header>

  <main class="flex-1 flex items-center justify-center px-6 py-8">
    {#if loading}
      <p class="text-surface-500">Connecting...</p>
    {:else if error}
      <div class="text-center">
        <p class="text-danger text-lg mb-2">{error}</p>
      </div>
    {:else if !activeSlide}
      <div class="text-center text-surface-500 animate-fade-in">
        <RadioTower class="w-16 h-16 mx-auto mb-4 text-brand-400 animate-pulse-live" />
        <p class="text-lg font-medium">Waiting for the presenter...</p>
      </div>
    {:else}
      <div class="w-full max-w-4xl">
        {#if activeSlide.type === 'POLL'}
          <div class="card space-y-6">
            <div class="text-center">
              <BarChart3 class="w-10 h-10 text-brand-600 mx-auto mb-3" />
              <h1 class="text-2xl font-bold">{activeSlide.content_json?.question}</h1>
            </div>
            <div class="flex items-end gap-4">
              {#each getPollResults(activeSlide) as row}
                <div class="flex flex-col items-center gap-2 flex-1">
                  <div class="relative w-full h-40 bg-surface-800 rounded-lg overflow-hidden">
                    <div
                      class="absolute bottom-0 left-0 right-0 bg-brand-500 rounded-lg"
                      style={`height: ${row.percent}%; min-height: ${row.percent > 0 ? '6px' : '0px'}`}
                    ></div>
                  </div>
                  <div class="text-xs text-surface-400">{row.label}</div>
                  <div class="text-xs text-surface-500">{row.percent}%</div>
                </div>
              {/each}
            </div>
          </div>
        {:else if activeSlide.type === 'QNA'}
          <div class="card">
            <div class="text-center mb-6">
              <MessageSquare class="w-10 h-10 text-brand-600 mx-auto mb-3" />
              <h1 class="text-2xl font-bold">{activeSlide.content_json?.prompt}</h1>
            </div>
            <div class="space-y-3 max-h-[60vh] overflow-y-auto">
              {#each [...responses].sort((a, b) => b.upvotes - a.upvotes) as response (response.id)}
                <div class="p-3 rounded-lg border border-surface-800">
                  <div class="text-xs text-surface-500 mb-1">{response.name || response.guest_identifier}</div>
                  <div class="text-sm">{response.value}</div>
                </div>
              {/each}
            </div>
          </div>
        {:else if activeSlide.type === 'FEEDBACK'}
          <div class="card">
            <div class="text-center mb-6">
              <AlignLeft class="w-10 h-10 text-brand-600 mx-auto mb-3" />
              <h1 class="text-2xl font-bold">{activeSlide.content_json?.prompt}</h1>
            </div>
            <div class="space-y-3 max-h-[60vh] overflow-y-auto">
              {#each responses as response (response.id)}
                <div class="p-3 rounded-lg border border-surface-800">
                  <div class="flex items-center justify-between text-xs text-surface-500 mb-1">
                    <span>{response.name || response.guest_identifier}</span>
                    {#if response.rating}
                      <span>Rating: {response.rating}</span>
                    {/if}
                  </div>
                  <div class="text-sm">{response.value}</div>
                </div>
              {/each}
            </div>
          </div>
        {:else if activeSlide.type === 'WORD_CLOUD'}
          <div class="card text-center">
            <Cloud class="w-10 h-10 text-brand-600 mx-auto mb-4" />
            <h1 class="text-2xl font-bold mb-6">{activeSlide.content_json?.prompt}</h1>
            {#if responses.length === 0}
              <p class="text-surface-500">Waiting for responses...</p>
            {:else}
              <div class="flex flex-wrap items-center justify-center gap-4 min-h-[200px] p-6">
                {#each getWordCloudData() as item}
                  <span
                    class="text-brand-600 font-bold transition-all"
                    style={`font-size: ${item.size}rem; opacity: ${0.5 + (item.count / (responses.length || 1)) * 0.5}`}
                  >{item.word}</span>
                {/each}
              </div>
              <div class="text-xs text-surface-500 mt-4">{responses.length} response{responses.length === 1 ? '' : 's'}</div>
            {/if}
          </div>
        {:else if activeSlide.type === 'CONTENT'}
          <div class="card text-center">
            <FileText class="w-10 h-10 text-brand-600 mx-auto mb-4" />
            <h1 class="text-2xl font-bold mb-4">{activeSlide.content_json?.title}</h1>
            <p class="text-surface-300 leading-relaxed">{activeSlide.content_json?.body}</p>
            {#if (activeSlide.content_json?.file_url || activeSlide.content_json?.has_file) && session?.id}
              {#key activeSlide.content_json?.file_page}
                <img
                  alt={`Slide page ${activeSlide.content_json?.file_page || 1}`}
                  src={getPageImageUrl(session.id, activeSlide.id, activeSlide.content_json?.file_page || 1)}
                  class="w-full max-h-[75vh] mt-6 rounded-xl border border-surface-800 object-contain pointer-events-none select-none"
                  draggable="false"
                  style="-webkit-touch-callout: none;"
                />
              {/key}
              <div class="text-xs text-surface-500 mt-3">Page {activeSlide.content_json?.file_page || 1}{activeSlide.content_json?.total_pages ? ` / ${activeSlide.content_json.total_pages}` : ''}</div>
            {/if}
          </div>
        {/if}
      </div>
    {/if}
  </main>
</div>
