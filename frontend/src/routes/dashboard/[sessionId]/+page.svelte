<script lang="ts">
  import {
    getSession, updateSession, createSlide, updateSlide, deleteSlide, listResponses, resolveFileUrl, getPageImageUrl
  } from '$lib/api';
  import { RforumWebSocket } from '$lib/ws';
  import type { ConnectionStatus as WsStatus } from '$lib/ws';
  import { onMount, onDestroy } from 'svelte';
  import {
    BarChart3,
    MessageSquare,
    AlignLeft,
    FileText,
    Pencil,
    Cloud
  } from 'lucide-svelte';
  import Sidebar from '$lib/components/Sidebar.svelte';

  let sessionId = $state('');

  let session: any = $state(null);
  let slides: any[] = $state([]);
  let activeSlideId: string | null = $state(null);
  let slideResponses: any[] = $state([]);
  let ws: RforumWebSocket | null = $state(null);
  let wsStatus: WsStatus = $state('disconnected');
  let loading = $state(true);
  let errorMessage = $state('');
  let slideTitle = $state('');
  let slideFile: FileList | null = $state(null);
  let currentSlideIndex = $state(0);
  let contentTitle = $state('');
  let contentBody = $state('');
  let contentFile: FileList | null = $state(null);
  let pollQuestion = $state('');
  let pollOptions = $state<string[]>([]);
  let qnaPrompt = $state('');
  let feedbackPrompt = $state('');
  let wordCloudPrompt = $state('');
  let editingSlideId = $state<string | null>(null);
  const activeSlide = $derived(getActiveSlide());
  const activeType = $derived(activeSlide?.type?.toUpperCase());

  const slideIcons: Record<string, any> = {
    POLL: BarChart3,
    QNA: MessageSquare,
    FEEDBACK: AlignLeft,
    CONTENT: FileText,
    WORD_CLOUD: Cloud
  };

  const slideLabels: Record<string, string> = {
    POLL: 'Poll',
    QNA: 'Q&A',
    FEEDBACK: 'Feedback',
    CONTENT: 'Content',
    WORD_CLOUD: 'Word Cloud'
  };

  $effect(() => {
    const active = getActiveSlide();
    if (active?.type?.toUpperCase() === 'CONTENT') {
      contentTitle = active.content_json?.title ?? '';
      contentBody = active.content_json?.body ?? '';
    }
    if (active?.type?.toUpperCase() === 'POLL') {
      pollQuestion = active.content_json?.question ?? '';
      pollOptions = active.content_json?.options ? [...active.content_json.options] : [];
    }
    if (active?.type?.toUpperCase() === 'QNA') {
      qnaPrompt = active.content_json?.prompt ?? '';
    }
    if (active?.type?.toUpperCase() === 'FEEDBACK') {
      feedbackPrompt = active.content_json?.prompt ?? '';
    }
    if (active?.type?.toUpperCase() === 'WORD_CLOUD') {
      wordCloudPrompt = active.content_json?.prompt ?? '';
    }
  });

  onMount(async () => {
    console.log('onMount triggered');
    try {
      sessionId = typeof window !== 'undefined'
        ? window.location.pathname.split('/').pop() || ''
        : '';
      console.log('Fetching session data for sessionId:', sessionId);
      session = await getSession(sessionId);
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
      ws.onStatusChange((s) => { wsStatus = s; });
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
    slideResponses = await listResponses(slideId);
  }

  async function toggleLive() {
    session = await updateSession(sessionId, { is_live: !session.is_live });
    ws?.send('session_update', { is_live: session.is_live });
  }

  async function addSlide(type: string) {
    // Optimistic: add a temporary slide immediately
    const tempId = `temp-${Date.now()}`;
    const tempSlide = { id: tempId, type, order: slides.length, content_json: getDefaultContent(type), is_active: false, _temp: true };
    slides = [...slides, tempSlide];
    try {
      const slide = await createSlide(sessionId, {
        type,
        order: tempSlide.order,
        content_json: tempSlide.content_json
      });
      slides = slides.map((s) => s.id === tempId ? slide : s);
      await activateSlide(slide.id);
    } catch {
      // Revert on failure
      slides = slides.filter((s) => s.id !== tempId);
    }
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
      case 'WORD_CLOUD':
        return { prompt: 'What comes to mind?' };
      default:
        return {};
    }
  }

  async function activateSlide(slideId: string) {
    const slide = await updateSlide(sessionId, slideId, { is_active: true });
    slides = slides.map((s) => ({ ...s, is_active: s.id === slideId }));
    activeSlideId = slideId;
    await loadResponses(slideId);
    ws?.send('slide_change', { slide_id: slideId });
  }

  function startEditing(slideId: string) {
    editingSlideId = slideId;
  }

  function stopEditing() {
    editingSlideId = null;
  }

  async function removeSlide(slideId: string) {
    if (!confirm('Delete this slide?')) return;
    // Optimistic removal
    const removedSlide = slides.find((s) => s.id === slideId);
    const removedIndex = slides.indexOf(removedSlide);
    slides = slides.filter((s) => s.id !== slideId);
    if (activeSlideId === slideId) {
      activeSlideId = null;
      slideResponses = [];
    }
    try {
      await deleteSlide(sessionId, slideId);
    } catch {
      // Revert on failure
      slides = [...slides.slice(0, removedIndex), removedSlide, ...slides.slice(removedIndex)];
    }
  }

  function getActiveSlide() {
    return slides.find((s) => s.id === activeSlideId);
  }

  function getSlideTypeKey(slide: any) {
    return slide?.type?.toUpperCase?.() || '';
  }

  function getContentSlideIds() {
    return slides
      .filter((s) => s.type?.toUpperCase() === 'CONTENT')
      .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
      .map((s) => s.id);
  }

  async function saveContentSlide() {
    const active = getActiveSlide();
    if (!active) return;
    const updated = await updateSlide(sessionId, active.id, {
      content_json: {
        ...active.content_json,
        title: contentTitle,
        body: contentBody
      }
    });
    slides = slides.map((s) => (s.id === active.id ? updated : s));
    ws?.send('slide_change', { slide_id: active.id });
  }

  async function uploadContentFile() {
    const active = getActiveSlide();
    if (!active || !contentFile || contentFile.length === 0) return;
    const token = typeof localStorage !== 'undefined' ? localStorage.getItem('rforum_token') : null;
    const formData = new FormData();
    formData.append('file', contentFile[0]);
    const response = await fetch(`/api/sessions/${sessionId}/slides/${active.id}/upload`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      body: formData
    });
    if (!response.ok) {
      alert('Failed to upload file');
      return;
    }
    const updated = await response.json();
    slides = slides.map((s) => (s.id === active.id ? updated : s));
    contentFile = null;
    ws?.send('slide_change', { slide_id: active.id });
  }

  async function changeContentPage(delta: number) {
    const active = getActiveSlide();
    if (!active) return;
    const current = active.content_json?.file_page || 1;
    const next = Math.max(1, current + delta);
    slides = slides.map((s) =>
      s.id === active.id
        ? { ...s, content_json: { ...s.content_json, file_page: next } }
        : s
    );
    try {
      const updated = await updateSlide(sessionId, active.id, {
        content_json: {
          ...active.content_json,
          file_page: next
        }
      });
      slides = slides.map((s) => (s.id === active.id ? updated : s));
      ws?.send('page_change', { slide_id: active.id, file_page: next, total_pages: updated.content_json?.total_pages });
    } catch {
      // Revert optimistic update on failure
      slides = slides.map((s) =>
        s.id === active.id
          ? { ...s, content_json: { ...s.content_json, file_page: current } }
          : s
      );
    }
  }

  function addPollOption() {
    pollOptions = [...pollOptions, ''];
  }

  function updatePollOption(index: number, value: string) {
    pollOptions = pollOptions.map((opt, i) => (i === index ? value : opt));
  }

  function removePollOption(index: number) {
    pollOptions = pollOptions.filter((_, i) => i !== index);
  }

  async function savePollSlide() {
    const active = getActiveSlide();
    if (!active) return;
    const cleanedOptions = pollOptions.map((opt) => opt.trim()).filter(Boolean);
    if (!pollQuestion.trim() || cleanedOptions.length < 2) {
      alert('Provide a question and at least two options.');
      return;
    }
    const updated = await updateSlide(sessionId, active.id, {
      content_json: {
        ...active.content_json,
        question: pollQuestion.trim(),
        options: cleanedOptions
      }
    });
    slides = slides.map((s) => (s.id === active.id ? updated : s));
    ws?.send('slide_change', { slide_id: active.id });
  }

  async function saveQnaSlide() {
    const active = getActiveSlide();
    if (!active) return;
    const updated = await updateSlide(sessionId, active.id, {
      content_json: {
        ...active.content_json,
        prompt: qnaPrompt.trim()
      }
    });
    slides = slides.map((s) => (s.id === active.id ? updated : s));
    ws?.send('slide_change', { slide_id: active.id });
  }

  async function saveFeedbackSlide() {
    const active = getActiveSlide();
    if (!active) return;
    const updated = await updateSlide(sessionId, active.id, {
      content_json: {
        ...active.content_json,
        prompt: feedbackPrompt.trim()
      }
    });
    slides = slides.map((s) => (s.id === active.id ? updated : s));
    ws?.send('slide_change', { slide_id: active.id });
  }

  async function saveWordCloudSlide() {
    const active = getActiveSlide();
    if (!active) return;
    const updated = await updateSlide(sessionId, active.id, {
      content_json: {
        ...active.content_json,
        prompt: wordCloudPrompt.trim()
      }
    });
    slides = slides.map((s) => (s.id === active.id ? updated : s));
    ws?.send('slide_change', { slide_id: active.id });
  }

  function getWordCloudData() {
    const freq: Record<string, number> = {};
    for (const r of slideResponses) {
      const word = r.value?.trim().toLowerCase();
      if (word) freq[word] = (freq[word] || 0) + 1;
    }
    const entries = Object.entries(freq).sort((a, b) => b[1] - a[1]);
    const maxCount = entries[0]?.[1] || 1;
    return entries.map(([word, count]) => ({
      word,
      count,
      size: Math.max(0.75, (count / maxCount) * 2.5)
    }));
  }

  async function goToContentSlide(direction: 'next' | 'prev') {
    const ids = getContentSlideIds();
    if (ids.length === 0) return;
    const currentIndex = Math.max(ids.indexOf(activeSlideId || ''), 0);
    const nextIndex = direction === 'next'
      ? Math.min(currentIndex + 1, ids.length - 1)
      : Math.max(currentIndex - 1, 0);
    const nextId = ids[nextIndex];
    if (nextId && nextId !== activeSlideId) {
      await activateSlide(nextId);
    }
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

  async function uploadSlide() {
    if (!slideTitle || !slideFile || slideFile.length === 0) {
      alert('Please provide a title and select a file.');
      return;
    }

    const formData = new FormData();
    formData.append('session_id', session.id);
    formData.append('title', slideTitle);
    formData.append('file', slideFile[0]);

    try {
      const response = await fetch('/slides/upload', {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        throw new Error('Failed to upload slide');
      }

      const newSlide = await response.json();
      slides = [...slides, newSlide];
      alert('Slide uploaded successfully!');
      slideTitle = '';
      slideFile = null;
    } catch (error) {
      console.error('Error uploading slide:', error);
      alert('Failed to upload slide. Please try again.');
    }
  }

  function nextSlide() {
    if (currentSlideIndex < slides.length - 1) {
      currentSlideIndex++;
    }
  }

  function previousSlide() {
    if (currentSlideIndex > 0) {
      currentSlideIndex--;
    }
  }
</script>

<svelte:head>
  <title>Manage Session – Rforum</title>
</svelte:head>

<div>
  <!-- Sub-header with session actions -->
  <div class="flex items-center justify-between px-8 py-3 border-b border-slate-200 dark:border-slate-800 bg-white/60 dark:bg-slate-900/60 backdrop-blur-sm">
    <button onclick={() => { window.location.href = '/dashboard'; }} class="text-sm font-medium text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition">&larr; Back to dashboard</button>
    <div class="flex items-center gap-3">
      {#if session?.unique_code}
        <a class="border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 px-3 py-1.5 rounded-lg text-sm font-medium text-slate-600 dark:text-slate-300 transition" href={`/screen/${session.unique_code}`} target="_blank" rel="noreferrer">Open screen</a>
      {/if}
      <span class="text-sm text-slate-400 font-mono">{session?.unique_code}</span>
    </div>
  </div>

  <main class="flex-1 px-6 py-8">
    {#if loading}
      <div class="text-center text-slate-400 py-20">Loading...</div>
    {:else if errorMessage}
      <div class="rounded-2xl border border-red-200 dark:border-red-900/50 bg-white dark:bg-slate-900 text-center text-red-500 py-10 px-6">{errorMessage}</div>
    {:else}
      <div class="grid grid-cols-12 gap-6">
        <Sidebar
          {session}
          {slides}
          {activeSlideId}
          {slideIcons}
          {slideLabels}
          {wsStatus}
          onToggleLive={toggleLive}
          onAddSlide={addSlide}
          onActivateSlide={activateSlide}
          onStartEditing={startEditing}
          onRemoveSlide={removeSlide}
        />

        <section class="col-span-12 lg:col-span-9">
          {#if !activeSlide}
            <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-center text-slate-400 py-20">Select a slide to get started.</div>
          {:else}
            {#if activeType === 'POLL'}
              <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 space-y-4">
                <div class="text-lg font-semibold text-slate-900 dark:text-white">Poll</div>
                {#if editingSlideId === activeSlideId}
                  <input class="input-field" type="text" bind:value={pollQuestion} placeholder="Poll question" />
                  <div class="space-y-2">
                    {#each pollOptions as option, index (index)}
                      <div class="flex items-center gap-2">
                        <input
                          class="input-field flex-1"
                          type="text"
                          value={option}
                          oninput={(event) => updatePollOption(index, event.currentTarget.value)}
                          placeholder={`Option ${index + 1}`}
                        />
                        <button onclick={() => removePollOption(index)} class="border border-red-200 dark:border-red-900/50 hover:bg-red-50 dark:hover:bg-red-900/20 text-red-500 text-xs font-medium px-3 py-1.5 rounded-lg transition">Remove</button>
                      </div>
                    {/each}
                  </div>
                  <div class="flex items-center gap-2">
                    <button onclick={addPollOption} class="border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 px-3 py-1.5 rounded-lg text-sm font-medium text-slate-600 dark:text-slate-300 transition">Add option</button>
                    <button onclick={savePollSlide} class="bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-medium px-3 py-1.5 rounded-lg shadow-lg shadow-purple-500/20 transition active:scale-95 text-sm">Save</button>
                    <button onclick={stopEditing} class="border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 px-3 py-1.5 rounded-lg text-sm font-medium text-slate-600 dark:text-slate-300 transition">Done</button>
                  </div>
                {/if}
                <div class="border border-slate-200 dark:border-slate-800 rounded-xl p-4">
                  <div class="text-sm font-semibold text-slate-900 dark:text-white mb-3">Live results</div>
                  <div class="flex items-end gap-4">
                    {#each getPollResults(activeSlide) as row}
                      <div class="flex flex-col items-center gap-2 flex-1">
                        <div class="relative w-full h-28 bg-slate-100 dark:bg-slate-800 rounded-lg overflow-hidden">
                          <div
                            class="absolute bottom-0 left-0 right-0 bg-purple-500 rounded-lg transition-all duration-500"
                            style={`height: ${row.percent}%; min-height: ${row.percent > 0 ? '6px' : '0px'}`}
                          ></div>
                        </div>
                        <div class="text-xs text-slate-500 dark:text-slate-400">{row.label}</div>
                        <div class="text-xs text-slate-400 dark:text-slate-500">{row.percent}%</div>
                      </div>
                    {/each}
                  </div>
                </div>
              </div>
            {:else if activeType === 'QNA'}
              <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 space-y-4">
                <div class="text-lg font-semibold text-slate-900 dark:text-white">Questions</div>
                {#if editingSlideId === activeSlideId}
                  <input class="input-field" type="text" bind:value={qnaPrompt} placeholder="Prompt" />
                  <div class="flex items-center gap-2">
                    <button onclick={saveQnaSlide} class="bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-medium px-3 py-1.5 rounded-lg shadow-lg shadow-purple-500/20 transition active:scale-95 text-sm">Save prompt</button>
                    <button onclick={stopEditing} class="border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 px-3 py-1.5 rounded-lg text-sm font-medium text-slate-600 dark:text-slate-300 transition">Done</button>
                  </div>
                {/if}
                {#if slideResponses.length === 0}
                  <div class="text-sm text-slate-400">No questions yet.</div>
                {:else}
                  <div class="space-y-3">
                    {#each slideResponses as response (response.id)}
                      <div class="p-3 rounded-xl border border-slate-200 dark:border-slate-800">
                        <div class="text-xs text-slate-500 mb-1">{response.name || response.guest_identifier}</div>
                        <div class="text-sm text-slate-900 dark:text-slate-100">{response.value}</div>
                      </div>
                    {/each}
                  </div>
                {/if}
              </div>
            {:else if activeType === 'FEEDBACK'}
              <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 space-y-4">
                <div class="text-lg font-semibold text-slate-900 dark:text-white">Feedback</div>
                {#if editingSlideId === activeSlideId}
                  <input class="input-field" type="text" bind:value={feedbackPrompt} placeholder="Prompt" />
                  <div class="flex items-center gap-2">
                    <button onclick={saveFeedbackSlide} class="bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-medium px-3 py-1.5 rounded-lg shadow-lg shadow-purple-500/20 transition active:scale-95 text-sm">Save prompt</button>
                    <button onclick={stopEditing} class="border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 px-3 py-1.5 rounded-lg text-sm font-medium text-slate-600 dark:text-slate-300 transition">Done</button>
                  </div>
                {/if}
                {#if slideResponses.length === 0}
                  <div class="text-sm text-slate-400">No feedback yet.</div>
                {:else}
                  <div class="space-y-3">
                    {#each slideResponses as response (response.id)}
                      <div class="p-3 rounded-xl border border-slate-200 dark:border-slate-800">
                        <div class="flex items-center justify-between text-xs text-slate-500 mb-1">
                          <span>{response.name || response.guest_identifier}</span>
                          {#if response.rating}
                            <span class="font-medium">Rating: {response.rating}</span>
                          {/if}
                        </div>
                        <div class="text-sm text-slate-900 dark:text-slate-100">{response.value}</div>
                      </div>
                    {/each}
                  </div>
                {/if}
              </div>
            {:else if activeType === 'CONTENT'}
              <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 space-y-4">
                <div class="text-lg font-semibold text-slate-900 dark:text-white">Content slide</div>
                {#if editingSlideId === activeSlideId}
                  <input class="input-field" type="text" bind:value={contentTitle} placeholder="Slide title" />
                  <textarea class="input-field" rows="6" bind:value={contentBody} placeholder="Slide content"></textarea>
                  <div class="flex items-center gap-2">
                    <button onclick={saveContentSlide} class="bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-medium px-3 py-1.5 rounded-lg shadow-lg shadow-purple-500/20 transition active:scale-95 text-sm">Save</button>
                    <button onclick={stopEditing} class="border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 px-3 py-1.5 rounded-lg text-sm font-medium text-slate-600 dark:text-slate-300 transition">Done</button>
                  </div>
                  <div class="flex items-center gap-3">
                    <input type="file" bind:files={contentFile} accept=".pdf,.ppt,.pptx" class="input-field" />
                    <button onclick={uploadContentFile} class="border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 px-3 py-1.5 rounded-lg text-sm font-medium text-slate-600 dark:text-slate-300 transition">Upload file</button>
                  </div>
                {/if}
                <div class="flex items-center gap-2">
                  <button onclick={() => goToContentSlide('prev')} class="border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 px-3 py-1.5 rounded-lg text-sm font-medium text-slate-600 dark:text-slate-300 transition">Previous</button>
                  <button onclick={() => goToContentSlide('next')} class="border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 px-3 py-1.5 rounded-lg text-sm font-medium text-slate-600 dark:text-slate-300 transition">Next</button>
                </div>
                {#if activeSlide.content_json?.file_url}
                    <div class="flex items-center gap-2">
                      <button onclick={() => changeContentPage(-1)} class="border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 px-3 py-1.5 rounded-lg text-sm font-medium text-slate-600 dark:text-slate-300 transition" disabled={(activeSlide.content_json?.file_page || 1) <= 1}>Prev page</button>
                      <button onclick={() => changeContentPage(1)} class="border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 px-3 py-1.5 rounded-lg text-sm font-medium text-slate-600 dark:text-slate-300 transition">Next page</button>
                      <div class="text-xs text-slate-400">Page {activeSlide.content_json?.file_page || 1}{activeSlide.content_json?.total_pages ? ` / ${activeSlide.content_json.total_pages}` : ''}</div>
                    </div>
                    <div class="overflow-x-auto">
                      {#key activeSlide.content_json?.file_page}
                        <img
                          alt={`Page ${activeSlide.content_json?.file_page || 1}`}
                          src={getPageImageUrl(sessionId, activeSlide.id, activeSlide.content_json?.file_page || 1)}
                          class="max-h-[500px] rounded-xl border border-slate-200 dark:border-slate-800 mx-auto"
                        />
                      {/key}
                    </div>
                {/if}
                <div class="border border-slate-200 dark:border-slate-800 rounded-xl p-6 bg-slate-50 dark:bg-slate-900">
                  <div class="text-xl font-semibold text-slate-900 dark:text-white mb-3">{contentTitle || 'Untitled slide'}</div>
                  <div class="text-sm text-slate-700 dark:text-slate-200 whitespace-pre-wrap">{contentBody || 'Add your slide content...'}</div>
                </div>
              </div>
            {:else if activeType === 'WORD_CLOUD'}
              <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 space-y-4">
                <div class="text-lg font-semibold text-slate-900 dark:text-white">Word Cloud</div>
                {#if editingSlideId === activeSlideId}
                  <input class="input-field" type="text" bind:value={wordCloudPrompt} placeholder="Prompt" />
                  <div class="flex items-center gap-2">
                    <button onclick={saveWordCloudSlide} class="bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-medium px-3 py-1.5 rounded-lg shadow-lg shadow-purple-500/20 transition active:scale-95 text-sm">Save prompt</button>
                    <button onclick={stopEditing} class="border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 px-3 py-1.5 rounded-lg text-sm font-medium text-slate-600 dark:text-slate-300 transition">Done</button>
                  </div>
                {/if}
                {#if slideResponses.length === 0}
                  <div class="text-sm text-slate-400">No responses yet.</div>
                {:else}
                  <div class="border border-slate-200 dark:border-slate-800 rounded-xl p-6 flex flex-wrap items-center justify-center gap-3 min-h-[200px]">
                    {#each getWordCloudData() as item}
                      <span
                        class="text-purple-600 dark:text-purple-400 font-semibold transition-all"
                        style={`font-size: ${item.size}rem; opacity: ${0.5 + (item.count / (slideResponses.length || 1)) * 0.5}`}
                      >{item.word}</span>
                    {/each}
                  </div>
                  <div class="text-xs text-slate-400">{slideResponses.length} response{slideResponses.length === 1 ? '' : 's'}</div>
                {/if}
              </div>
            {:else}
              <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-center text-slate-400 py-20">Unsupported slide type.</div>
            {/if}
          {/if}
        </section>
      </div>
    {/if}
  </main>
</div>
