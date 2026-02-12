<script lang="ts">
  import {
    getSession, updateSession, createSlide, updateSlide, deleteSlide, listResponses, resolveFileUrl
  } from '$lib/api';
  import { RforumWebSocket } from '$lib/ws';
  import { onMount, onDestroy } from 'svelte';
  import {
    BarChart3,
    MessageSquare,
    AlignLeft,
    FileText,
    Pencil
  } from 'lucide-svelte';

  let sessionId = $state('');

  let session: any = $state(null);
  let slides: any[] = $state([]);
  let activeSlideId: string | null = $state(null);
  let slideResponses: any[] = $state([]);
  let ws: RforumWebSocket | null = $state(null);
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
  let editingSlideId = $state<string | null>(null);
  const activeSlide = $derived(getActiveSlide());
  const activeType = $derived(activeSlide?.type?.toUpperCase());

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
    const slide = await createSlide(sessionId, {
      type,
      order: slides.length,
      content_json: getDefaultContent(type)
    });
    slides = [...slides, slide];
    await activateSlide(slide.id);
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
    await deleteSlide(sessionId, slideId);
    slides = slides.filter((s) => s.id !== slideId);
    if (activeSlideId === slideId) {
      activeSlideId = null;
      slideResponses = [];
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
    const updated = await updateSlide(sessionId, active.id, {
      content_json: {
        ...active.content_json,
        file_page: next
      }
    });
    slides = slides.map((s) => (s.id === active.id ? updated : s));
    ws?.send('slide_change', { slide_id: active.id });
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

<div class="min-h-screen flex flex-col">
  <header class="flex items-center justify-between px-6 py-4 border-b border-surface-800">
    <button onclick={() => { window.location.href = '/dashboard'; }} class="btn-secondary text-sm">Back to dashboard</button>
    <div class="flex items-center gap-3">
      {#if session?.unique_code}
        <a class="btn-secondary text-sm" href={`/screen/${session.unique_code}`} target="_blank" rel="noreferrer">Open screen</a>
      {/if}
      <div class="text-sm text-surface-400 font-mono">{session?.unique_code}</div>
    </div>
  </header>

  <main class="flex-1 px-6 py-8">
    {#if loading}
      <div class="text-center text-surface-500 py-20">Loading...</div>
    {:else if errorMessage}
      <div class="card text-center text-danger py-10">{errorMessage}</div>
    {:else}
      <div class="grid grid-cols-12 gap-6">
        <aside class="col-span-12 lg:col-span-3 space-y-4">
          <div class="card">
            <div class="text-lg font-semibold">{session?.title}</div>
            <div class="text-xs text-surface-500 mt-1">{session?.unique_code}</div>
            <button onclick={toggleLive} class={session?.is_live ? 'btn-danger w-full mt-4' : 'btn-primary w-full mt-4'}>
              {session?.is_live ? 'Stop session' : 'Start session'}
            </button>
          </div>

          <div class="card">
            <div class="text-sm font-semibold mb-3">Add slide</div>
            <div class="grid grid-cols-2 gap-2">
              {#each Object.keys(slideLabels) as key}
                <button onclick={() => addSlide(key)} class="btn-secondary text-xs">
                  {slideLabels[key]}
                </button>
              {/each}
            </div>
          </div>

          <div class="card">
            <div class="text-sm font-semibold mb-3">Slides</div>
            {#if slides.length === 0}
              <div class="text-xs text-surface-500">No slides yet.</div>
            {:else}
              <div class="space-y-2">
                {#each slides as slide (slide.id)}
                  {@const Icon = slideIcons[getSlideTypeKey(slide)]}
                  <div class={`flex items-center justify-between gap-2 p-2 rounded-lg border ${slide.id === activeSlideId ? 'border-brand-500/60 bg-surface-900' : 'border-surface-800'}`}>
                    <button class="flex items-center gap-2 text-left flex-1" onclick={() => activateSlide(slide.id)}>
                      {#if Icon}
                        <Icon class="w-4 h-4 text-brand-400" />
                      {/if}
                      <span class="text-xs">{slideLabels[getSlideTypeKey(slide)] || getSlideTypeKey(slide) || 'Slide'}</span>
                    </button>
                    <button onclick={() => startEditing(slide.id)} class="text-xs text-surface-400">
                      <Pencil class="w-3.5 h-3.5" />
                    </button>
                    <button onclick={() => removeSlide(slide.id)} class="text-danger text-xs">Delete</button>
                  </div>
                {/each}
              </div>
            {/if}
          </div>
        </aside>

        <section class="col-span-12 lg:col-span-9">
          {#if !activeSlide}
            <div class="card text-center text-surface-500 py-20">Select a slide to get started.</div>
          {:else}
            {#if activeType === 'POLL'}
              <div class="card space-y-4">
                <div class="text-lg font-semibold">Poll</div>
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
                        <button onclick={() => removePollOption(index)} class="btn-danger text-xs">Remove</button>
                      </div>
                    {/each}
                  </div>
                  <div class="flex items-center gap-2">
                    <button onclick={addPollOption} class="btn-secondary text-sm">Add option</button>
                    <button onclick={savePollSlide} class="btn-primary text-sm">Save</button>
                    <button onclick={stopEditing} class="btn-secondary text-sm">Done</button>
                  </div>
                {/if}
                <div class="border border-surface-800 rounded-xl p-4">
                  <div class="text-sm font-semibold mb-3">Live results</div>
                  <div class="flex items-end gap-4">
                    {#each getPollResults(activeSlide) as row}
                      <div class="flex flex-col items-center gap-2 flex-1">
                        <div class="relative w-full h-28 bg-surface-800 rounded-lg overflow-hidden">
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
              </div>
            {:else if activeType === 'QNA'}
              <div class="card space-y-4">
                <div class="text-lg font-semibold">Questions</div>
                {#if editingSlideId === activeSlideId}
                  <input class="input-field" type="text" bind:value={qnaPrompt} placeholder="Prompt" />
                  <div class="flex items-center gap-2">
                    <button onclick={saveQnaSlide} class="btn-primary text-sm">Save prompt</button>
                    <button onclick={stopEditing} class="btn-secondary text-sm">Done</button>
                  </div>
                {/if}
                {#if slideResponses.length === 0}
                  <div class="text-sm text-surface-500">No questions yet.</div>
                {:else}
                  <div class="space-y-3">
                    {#each slideResponses as response (response.id)}
                      <div class="p-3 rounded-lg border border-surface-800">
                        <div class="text-xs text-surface-500 mb-1">{response.name || response.guest_identifier}</div>
                        <div class="text-sm">{response.value}</div>
                      </div>
                    {/each}
                  </div>
                {/if}
              </div>
            {:else if activeType === 'FEEDBACK'}
              <div class="card space-y-4">
                <div class="text-lg font-semibold">Feedback</div>
                {#if editingSlideId === activeSlideId}
                  <input class="input-field" type="text" bind:value={feedbackPrompt} placeholder="Prompt" />
                  <div class="flex items-center gap-2">
                    <button onclick={saveFeedbackSlide} class="btn-primary text-sm">Save prompt</button>
                    <button onclick={stopEditing} class="btn-secondary text-sm">Done</button>
                  </div>
                {/if}
                {#if slideResponses.length === 0}
                  <div class="text-sm text-surface-500">No feedback yet.</div>
                {:else}
                  <div class="space-y-3">
                    {#each slideResponses as response (response.id)}
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
                {/if}
              </div>
            {:else if activeType === 'CONTENT'}
              <div class="card space-y-4">
                <div class="text-lg font-semibold">Content slide</div>
                {#if editingSlideId === activeSlideId}
                  <input class="input-field" type="text" bind:value={contentTitle} placeholder="Slide title" />
                  <textarea class="input-field" rows="6" bind:value={contentBody} placeholder="Slide content"></textarea>
                  <div class="flex items-center gap-2">
                    <button onclick={saveContentSlide} class="btn-primary text-sm">Save</button>
                    <button onclick={stopEditing} class="btn-secondary text-sm">Done</button>
                  </div>
                  <div class="flex items-center gap-3">
                    <input type="file" bind:files={contentFile} accept=".pdf,.ppt,.pptx" class="input-field" />
                    <button onclick={uploadContentFile} class="btn-secondary text-sm">Upload file</button>
                  </div>
                {/if}
                <div class="flex items-center gap-2">
                  <button onclick={() => goToContentSlide('prev')} class="btn-secondary text-sm">Previous</button>
                  <button onclick={() => goToContentSlide('next')} class="btn-secondary text-sm">Next</button>
                </div>
                {#if activeSlide.content_json?.file_url}
                  {#if activeSlide.content_json?.file_type?.includes('pdf')}
                    <div class="flex items-center gap-2">
                      <button onclick={() => changeContentPage(-1)} class="btn-secondary text-sm">Prev page</button>
                      <button onclick={() => changeContentPage(1)} class="btn-secondary text-sm">Next page</button>
                      <div class="text-xs text-surface-500">Page {activeSlide.content_json?.file_page || 1}</div>
                    </div>
                    <div class="overflow-x-auto">
                      {#key activeSlide.content_json?.file_page}
                        <iframe
                          title="Content file"
                          src={`${resolveFileUrl(activeSlide.content_json.file_url)}?v=${activeSlide.content_json?.file_page || 1}#page=${activeSlide.content_json?.file_page || 1}`}
                          class="h-[420px] rounded-xl border border-surface-800 min-w-[900px]"
                        ></iframe>
                      {/key}
                    </div>
                  {:else}
                    <div class="text-sm text-surface-500">
                      File uploaded: {activeSlide.content_json.file_name || 'file'}
                    </div>
                  {/if}
                {/if}
                <div class="border border-surface-800 rounded-xl p-6 bg-surface-900">
                  <div class="text-xl font-semibold mb-3">{contentTitle || 'Untitled slide'}</div>
                  <div class="text-sm text-surface-200 whitespace-pre-wrap">{contentBody || 'Add your slide content...'}</div>
                </div>
              </div>
            {:else}
              <div class="card text-center text-surface-500 py-20">Unsupported slide type.</div>
            {/if}
          {/if}
        </section>
      </div>
    {/if}
  </main>
</div>
