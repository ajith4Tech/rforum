<script lang="ts">
  import { Upload, FileCog, Image, CheckCircle2, AlertTriangle, RefreshCw } from 'lucide-svelte';

  let {
    stage,
    errorMessage = '',
    firstPageThumbnailUrl = '',
    slideCount = 0,
    reusedExisting = false,
    onRetry,
    onChooseDifferent
  }: {
    stage: 'uploading' | 'converting' | 'generating_preview' | 'ready' | 'error';
    errorMessage?: string;
    firstPageThumbnailUrl?: string;
    slideCount?: number;
    reusedExisting?: boolean;
    onRetry?: () => void;
    onChooseDifferent?: () => void;
  } = $props();

  const steps = [
    { key: 'uploading', label: 'Uploading', icon: Upload },
    { key: 'converting', label: 'Converting', icon: FileCog },
    { key: 'generating_preview', label: 'Generating Preview', icon: Image },
    { key: 'ready', label: 'Ready', icon: CheckCircle2 }
  ];

  const stepOrder = ['uploading', 'converting', 'generating_preview', 'ready'];
  const currentIndex = $derived(stepOrder.indexOf(stage));
</script>

<div class="card p-5">
  {#if stage === 'error'}
    <div class="flex items-start gap-3">
      <div class="w-9 h-9 flex items-center justify-center rounded-xl bg-danger/10 flex-shrink-0">
        <AlertTriangle class="w-4.5 h-4.5 text-danger" />
      </div>
      <div class="flex-1 min-w-0">
        <p class="text-sm font-semibold text-danger">Upload failed</p>
        <p class="text-xs text-surface-500 mt-1">{errorMessage || 'Something went wrong while processing this file.'}</p>
        <div class="flex items-center gap-3 mt-3">
          {#if onRetry}
            <button onclick={onRetry} class="btn-secondary text-xs flex items-center gap-1.5">
              <RefreshCw class="w-3.5 h-3.5" /> Retry
            </button>
          {/if}
          {#if onChooseDifferent}
            <button onclick={onChooseDifferent} class="text-xs text-surface-500 hover:text-surface-300 transition underline">
              Choose a different file
            </button>
          {/if}
        </div>
      </div>
    </div>
  {:else}
    <div class="flex items-center justify-between mb-4">
      {#each steps as step, i}
        <div class="flex items-center flex-1 last:flex-none">
          <div class="flex flex-col items-center gap-1.5">
            <div
              class="w-8 h-8 flex items-center justify-center rounded-full border-2 transition-colors
                {i < currentIndex ? 'bg-emerald-500 border-emerald-500 text-white' :
                 i === currentIndex ? 'border-brand-500 text-brand-500' :
                 'border-surface-200 dark:border-surface-800 text-surface-400'}"
            >
              {#if i < currentIndex}
                <CheckCircle2 class="w-4 h-4" />
              {:else if i === currentIndex && stage !== 'ready'}
                <RefreshCw class="w-4 h-4 animate-spin" />
              {:else}
                <step.icon class="w-4 h-4" />
              {/if}
            </div>
            <span class="text-[10px] font-medium {i <= currentIndex ? 'text-surface-100 dark:text-surface-100' : 'text-surface-500'} whitespace-nowrap">
              {step.label}
            </span>
          </div>
          {#if i < steps.length - 1}
            <div class="flex-1 h-0.5 mx-1 mb-4 rounded {i < currentIndex ? 'bg-emerald-500' : 'bg-surface-200 dark:bg-surface-800'}"></div>
          {/if}
        </div>
      {/each}
    </div>

    {#if stage === 'ready'}
      <div class="flex items-center gap-3 pt-1">
        {#if firstPageThumbnailUrl}
          <img
            src={firstPageThumbnailUrl}
            alt="First slide preview"
            class="w-20 h-14 object-cover rounded-lg border border-surface-200 dark:border-surface-800 flex-shrink-0 bg-surface-100 dark:bg-surface-800"
          />
        {/if}
        <div>
          <p class="text-sm font-semibold text-emerald-500 flex items-center gap-1.5">
            <CheckCircle2 class="w-4 h-4" /> Ready — {slideCount} slide{slideCount === 1 ? '' : 's'}
          </p>
          {#if reusedExisting}
            <p class="text-xs text-surface-500 mt-0.5">This presentation already exists. Reusing existing assets.</p>
          {/if}
        </div>
      </div>
    {/if}
  {/if}
</div>
