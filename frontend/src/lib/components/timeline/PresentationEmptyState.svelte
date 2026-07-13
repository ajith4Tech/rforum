<script lang="ts">
  import { getPresentationPageThumbnailUrl } from '$lib/api';
  import UploadProgress from './UploadProgress.svelte';
  import PresentationPickerDialog from './PresentationPickerDialog.svelte';
  import { UploadCloud, FolderOpen } from 'lucide-svelte';

  let {
    eventId,
    onUpload,
    onAttach,
    onUploadDone
  }: {
    eventId: string | null | undefined;
    onUpload: (file: File) => Promise<{ presentation: any; timeline: any; reused_existing: boolean }>;
    onAttach: (presentationId: string) => Promise<void>;
    onUploadDone: (result: { presentation: any; timeline: any }) => void;
  } = $props();

  let dragOver = $state(false);
  let pickerOpen = $state(false);
  let pendingFile: File | null = $state(null);

  type Stage = 'uploading' | 'converting' | 'generating_preview' | 'ready' | 'error';
  let stage: Stage | null = $state(null);
  let errorMessage = $state('');
  let slideCount = $state(0);
  let firstPageThumbnailUrl = $state('');
  let reusedExisting = $state(false);

  let fakeStageTimers: ReturnType<typeof setTimeout>[] = [];

  function clearFakeStageTimers() {
    fakeStageTimers.forEach(clearTimeout);
    fakeStageTimers = [];
  }

  async function startUpload(file: File) {
    pendingFile = file;
    stage = 'uploading';
    errorMessage = '';
    clearFakeStageTimers();

    // The backend does upload+convert+render in one synchronous call — there's
    // no real per-stage signal to key off, so we simulate the visual
    // progression while the real request is in flight, then reconcile to the
    // actual outcome (ready/error) once it resolves.
    fakeStageTimers.push(setTimeout(() => { if (stage !== 'error') stage = 'converting'; }, 400));
    fakeStageTimers.push(setTimeout(() => { if (stage !== 'error') stage = 'generating_preview'; }, 1100));

    try {
      const result = await onUpload(file);
      clearFakeStageTimers();
      stage = 'ready';
      slideCount = result.presentation.page_count;
      firstPageThumbnailUrl = getPresentationPageThumbnailUrl(result.presentation.id, 1);
      reusedExisting = result.reused_existing;

      // Briefly show the Ready state (slide count + preview) before revealing
      // the full workspace, so the moderator actually sees the result of the
      // upload rather than an instant jump-cut.
      setTimeout(() => onUploadDone(result), 900);
    } catch (err: any) {
      clearFakeStageTimers();
      stage = 'error';
      errorMessage = err?.message || 'Failed to upload presentation';
    }
  }

  function handleFileChosen(file: File | undefined | null) {
    if (!file) return;
    startUpload(file);
  }

  function handleInputChange(e: Event) {
    const input = e.currentTarget as HTMLInputElement;
    handleFileChosen(input.files?.[0]);
    input.value = '';
  }

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    dragOver = false;
    handleFileChosen(e.dataTransfer?.files?.[0]);
  }

  function handleRetry() {
    if (pendingFile) startUpload(pendingFile);
  }

  function handleChooseDifferent() {
    stage = null;
    pendingFile = null;
    errorMessage = '';
  }

  async function handleAttachFromPicker(presentationId: string) {
    await onAttach(presentationId);
    pickerOpen = false;
  }
</script>

<div class="card mb-5 p-5">
  <div class="mb-4">
    <div class="text-sm font-semibold">Presentation Timeline</div>
    <div class="text-xs text-surface-500 max-w-xl mt-0.5">
      Upload a PPT/PPTX/PDF deck to build an interactive presentation — polls, Q&amp;A, word clouds and more woven
      directly between your slide pages.
    </div>
  </div>

  {#if stage}
    <UploadProgress
      {stage}
      {errorMessage}
      {firstPageThumbnailUrl}
      {slideCount}
      {reusedExisting}
      onRetry={handleRetry}
      onChooseDifferent={handleChooseDifferent}
    />
  {:else}
    <div
      role="button"
      tabindex="0"
      ondragover={(e) => { e.preventDefault(); dragOver = true; }}
      ondragleave={() => (dragOver = false)}
      ondrop={handleDrop}
      onclick={() => document.getElementById('presentation-file-input')?.click()}
      onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); document.getElementById('presentation-file-input')?.click(); } }}
      class="flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed py-8 px-4 text-center cursor-pointer transition-colors
        {dragOver ? 'border-brand-500 bg-brand-500/5' : 'border-surface-200 dark:border-surface-800 hover:border-surface-300 dark:hover:border-surface-700'}"
    >
      <UploadCloud class="w-7 h-7 {dragOver ? 'text-brand-500' : 'text-surface-400'}" />
      <p class="text-sm font-medium">Drag &amp; drop a file here, or click to browse</p>
      <p class="text-xs text-surface-500">PDF, PPT, or PPTX</p>
      <input
        id="presentation-file-input"
        type="file"
        accept=".pdf,.ppt,.pptx"
        class="hidden"
        onchange={handleInputChange}
      />
    </div>

    <div class="flex items-center gap-3 my-4">
      <div class="flex-1 h-px bg-surface-200 dark:bg-surface-800"></div>
      <span class="text-xs text-surface-500 font-medium">OR</span>
      <div class="flex-1 h-px bg-surface-200 dark:bg-surface-800"></div>
    </div>

    <button onclick={() => (pickerOpen = true)} class="btn-secondary w-full text-sm flex items-center justify-center gap-2">
      <FolderOpen class="w-4 h-4" /> Choose Existing Presentation
    </button>
  {/if}
</div>

{#if pickerOpen}
  <PresentationPickerDialog {eventId} onAttach={handleAttachFromPicker} onClose={() => (pickerOpen = false)} />
{/if}
