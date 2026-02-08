<script lang="ts">
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { RforumWebSocket } from '$lib/ws';
  import * as api from '$lib/api';
  import { onMount, onDestroy } from 'svelte';
  import {
    Radio, ArrowLeft, Plus, Trash2, Play, Square, BarChart3,
    MessageSquare, FileText, AlignLeft, ChevronUp
  } from 'lucide-svelte';

  const sessionId = $derived($page.params.sessionId);

  let session: any = $state(null);
  let slides: any[] = $state([]);
  let activeSlideId: string | null = $state(null);
  let slideResponses: any[] = $state([]);
  let ws: RforumWebSocket | null = $state(null);
  let loading = $state(true);
  let errorMessage = $state('');

  const slideIcons: Record<string, any> = {
    POLL: BarChart3,
    QNA: MessageSquare,
    FEEDBACK: AlignLeft,
    CONTENT: FileText
  };

  const slideLabels: Record<string, string> = {
    POLL: 'Poll',
    QNA: 'Q&A',
    FEEDBACK: 'Feedback',
    CONTENT: 'Content'
  };

  onMount(async () => {
    console.log('onMount triggered');
    try {
      console.log('Fetching session data for sessionId:', sessionId);
      session = await api.getSession(sessionId);
      console.log('Session data:', session);

      slides = session.slides || [];
      console.log('Slides:', slides);

      const active = slides.find((s: any) => s.is_active);
      if (active) {
        activeSlideId = active.id;
        console.log('Active slide ID:', activeSlideId);
        await loadResponses(active.id);
        console.log('Responses loaded for active slide');
      }

      // Connect WebSocket
      ws = new RforumWebSocket(session.unique_code);
      ws.connect();
      ws.onMessage(handleWsMessage);
      console.log('WebSocket connected');
    } catch (error) {
      console.error('Error in onMount:', error);
      errorMessage = error.message || 'Failed to load session. Please try again later.';
    } finally {
      loading = false;
      console.log('Loading complete');
    }
  });

  onDestroy(() => {
    ws?.disconnect();
  });

  function handleWsMessage(msg: any) {
    if (msg.event === 'new_response') {
      slideResponses = [...slideResponses, msg.data];
    } else if (msg.event === 'upvote') {
      slideResponses = slideResponses.map((r) =>
        r.id === msg.data.id ? { ...r, upvotes: msg.data.upvotes } : r
      );
    }
  }

  async function loadResponses(slideId: string) {
    slideResponses = await api.listResponses(slideId);
  }

  async function toggleLive() {
    session = await api.updateSession(sessionId, { is_live: !session.is_live });
    ws?.send('session_update', { is_live: session.is_live });
  }

  async function addSlide(type: string) {
    const slide = await api.createSlide(sessionId, {
      type,
      order: slides.length,
      content_json: getDefaultContent(type)
    });
    slides = [...slides, slide];
  }

  function getDefaultContent(type: string): object {
    switch (type) {
      case 'POLL':
        return { question: 'Your question?', options: ['Option A', 'Option B', 'Option C'] };
      case 'QNA':
        return { prompt: 'Ask me anything!' };
      case 'FEEDBACK':
        return { prompt: 'Share your thoughts...' };
      case 'CONTENT':
        return { title: 'Slide Title', body: 'Slide content goes here.' };
      default:
        return {};
    }
  }

  async function activateSlide(slideId: string) {
    const slide = await api.updateSlide(sessionId, slideId, { is_active: true });
    slides = slides.map((s) => ({ ...s, is_active: s.id === slideId }));
    activeSlideId = slideId;
    await loadResponses(slideId);
    ws?.send('slide_change', { slide_id: slideId });
  }

  async function removeSlide(slideId: string) {
    if (!confirm('Delete this slide?')) return;
    await api.deleteSlide(sessionId, slideId);
    slides = slides.filter((s) => s.id !== slideId);
    if (activeSlideId === slideId) {
      activeSlideId = null;
      slideResponses = [];
    }
  }

  function getActiveSlide() {
    return slides.find((s) => s.id === activeSlideId);
  }

  function getPollResults(slide: any) {
    const options: string[] = slide.content_json?.options || [];
    const counts: Record<string, number> = {};
    options.forEach((opt) => (counts[opt] = 0));
    slideResponses.forEach((r) => {
      if (counts[r.value] !== undefined) counts[r.value]++;
    });
    const total = slideResponses.length || 1;
    return options.map((opt) => ({
      label: opt,
      count: counts[opt],
      percent: Math.round((counts[opt] / total) * 100)
    }));
  }
</script>

<svelte:head>
  <title>{session?.title || 'Session'} – Rforum</title>
</svelte:head>

{#if loading}
  <div class="min-h-screen flex items-center justify-center text-surface-500">Loading...</div>
{:else if session}
  <div class="min-h-screen flex">
    <!-- Sidebar -->
    <aside class="w-72 border-r border-surface-800 flex flex-col bg-surface-950">
      <div class="p-4 border-b border-surface-800">
        <a href="/dashboard" class="flex items-center gap-2 text-surface-400 hover:text-surface-200 text-sm mb-4 transition-colors">
          <ArrowLeft class="w-4 h-4" />
          Back to dashboard
        </a>
        <h2 class="font-bold text-lg truncate">{session.title}</h2>
        <p class="font-mono text-sm text-surface-500 mt-1">{session.unique_code}</p>
      </div>

      <!-- Live Toggle -->
      <div class="p-4 border-b border-surface-800">
        <button
          onclick={toggleLive}
          class={session.is_live ? 'btn-live w-full flex items-center justify-center gap-2' : 'btn-primary w-full flex items-center justify-center gap-2'}
        >
          {#if session.is_live}
            <Square class="w-4 h-4" />
            Stop Session
          {:else}
            <Play class="w-4 h-4" />
            Go Live
          {/if}
        </button>
      </div>

      <!-- Slide list -->
      <div class="flex-1 overflow-y-auto p-3 space-y-1">
        {#each slides as slide, i (slide.id)}
          {@const Icon = slideIcons[slide.type] || FileText}
          <button
            onclick={() => activateSlide(slide.id)}
            class="sidebar-item w-full text-left group"
            class:active={slide.id === activeSlideId}
          >
            <span class="flex items-center justify-center w-7 h-7 rounded-lg bg-surface-800 text-xs font-bold text-surface-400 shrink-0">
              {i + 1}
            </span>
            <Icon class="w-4 h-4 shrink-0" />
            <span class="flex-1 text-sm truncate">{slideLabels[slide.type]}</span>
            <span
              onclick={() => removeSlide(slide.id)}
              role="button"
              tabindex="0"
              onkeydown={(e) => e.key === 'Enter' && removeSlide(slide.id)}
              class="opacity-0 group-hover:opacity-100 text-surface-500 hover:text-danger transition-all cursor-pointer p-1"
            >
              <Trash2 class="w-3.5 h-3.5" />
            </span>
          </button>
        {/each}
      </div>

      <!-- Add slide buttons -->
      <div class="p-3 border-t border-surface-800 grid grid-cols-2 gap-2">
        <button onclick={() => addSlide('POLL')} class="btn-secondary text-xs flex items-center justify-center gap-1.5 py-2">
          <BarChart3 class="w-3.5 h-3.5" /> Poll
        </button>
        <button onclick={() => addSlide('QNA')} class="btn-secondary text-xs flex items-center justify-center gap-1.5 py-2">
          <MessageSquare class="w-3.5 h-3.5" /> Q&A
        </button>
        <button onclick={() => addSlide('FEEDBACK')} class="btn-secondary text-xs flex items-center justify-center gap-1.5 py-2">
          <AlignLeft class="w-3.5 h-3.5" /> Feedback
        </button>
        <button onclick={() => addSlide('CONTENT')} class="btn-secondary text-xs flex items-center justify-center gap-1.5 py-2">
          <FileText class="w-3.5 h-3.5" /> Content
        </button>
      </div>
    </aside>

    <!-- Main content area -->
    <main class="flex-1 p-8 overflow-y-auto">
      {#if !activeSlideId}
        <div class="flex flex-col items-center justify-center h-full text-surface-500">
          <Radio class="w-16 h-16 mb-4 text-surface-700" />
          <p class="text-lg">Select a slide or create one to get started</p>
        </div>
      {:else}
        {@const slide = getActiveSlide()}
        {#if slide}
          <div class="max-w-3xl mx-auto animate-fade-in">
            <div class="flex items-center gap-3 mb-6">
              <span class="badge-live" class:opacity-0={!session.is_live}>
                <span class="w-1.5 h-1.5 bg-live rounded-full"></span>
                Live
              </span>
              <h2 class="text-xl font-bold">{slideLabels[slide.type]} Slide</h2>
              <span class="text-surface-500 text-sm">{slideResponses.length} responses</span>
            </div>

            <!-- Poll Results -->
            {#if slide.type === 'POLL'}
              <div class="card mb-6">
                <h3 class="text-lg font-semibold mb-6">{slide.content_json?.question}</h3>
                <div class="space-y-4">
                  {#each getPollResults(slide) as result}
                    <div>
                      <div class="flex justify-between text-sm mb-1.5">
                        <span class="font-medium">{result.label}</span>
                        <span class="text-surface-400">{result.count} ({result.percent}%)</span>
                      </div>
                      <div class="h-8 bg-surface-800 rounded-lg overflow-hidden">
                        <div
                          class="h-full bg-gradient-to-r from-brand-500 to-brand-400 rounded-lg transition-all duration-500 ease-out flex items-center px-3"
                          style="width: {result.percent}%"
                        >
                        </div>
                      </div>
                    </div>
                  {/each}
                </div>
              </div>
            {/if}

            <!-- Q&A Results -->
            {#if slide.type === 'QNA'}
              <div class="card mb-6">
                <h3 class="text-lg font-semibold mb-4">{slide.content_json?.prompt}</h3>
              </div>
              <div class="space-y-3">
                {#each slideResponses.sort((a, b) => b.upvotes - a.upvotes) as response (response.id)}
                  <div class="card flex items-start gap-4 animate-slide-up">
                    <button class="flex flex-col items-center gap-1 text-surface-400 hover:text-brand-400 transition-colors">
                      <ChevronUp class="w-5 h-5" />
                      <span class="text-sm font-bold">{response.upvotes}</span>
                    </button>
                    <div>
                      <p class="text-surface-200">{response.value}</p>
                      <span class="text-xs text-surface-600 mt-1">
                        {new Date(response.created_at).toLocaleTimeString()}
                      </span>
                    </div>
                  </div>
                {/each}
                {#if slideResponses.length === 0}
                  <p class="text-surface-500 text-center py-8">Waiting for questions...</p>
                {/if}
              </div>
            {/if}

            <!-- Feedback Results -->
            {#if slide.type === 'FEEDBACK'}
              <div class="card mb-6">
                <h3 class="text-lg font-semibold mb-4">{slide.content_json?.prompt}</h3>
              </div>
              <div class="space-y-3">
                {#each slideResponses as response (response.id)}
                  <div class="card animate-slide-up">
                    <p class="text-surface-200">{response.value}</p>
                    <span class="text-xs text-surface-600 mt-2 block">
                      {new Date(response.created_at).toLocaleTimeString()}
                    </span>
                  </div>
                {/each}
                {#if slideResponses.length === 0}
                  <p class="text-surface-500 text-center py-8">Waiting for feedback...</p>
                {/if}
              </div>
            {/if}

            <!-- Content Slide -->
            {#if slide.type === 'CONTENT'}
              <div class="card">
                <h3 class="text-2xl font-bold mb-4">{slide.content_json?.title}</h3>
                <p class="text-surface-300 leading-relaxed">{slide.content_json?.body}</p>
              </div>
            {/if}
          </div>
        {/if}
      {/if}
    </main>
  </div>

  {#if slides.length === 0 && !loading}
    <div class="no-slides-message">
      <p>No slides are available for this session. Please create a slide to get started.</p>
    </div>
  {/if}
{/if}

{#if errorMessage}
  <div class="error-message">
    <p>{errorMessage}</p>
  </div>
{/if}
