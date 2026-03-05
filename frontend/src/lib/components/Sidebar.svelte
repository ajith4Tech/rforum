<script lang="ts">
  import { Radio, Layers } from 'lucide-svelte';
  import SlideCard from './SlideCard.svelte';
  import ConnectionStatus from './ConnectionStatus.svelte';
  import type { ConnectionStatus as WsStatus } from '$lib/ws';

  let {
    session,
    slides = [],
    activeSlideId = null,
    slideIcons = {},
    slideLabels = {},
    wsStatus = 'disconnected' as WsStatus,
    onToggleLive,
    onAddSlide,
    onActivateSlide,
    onStartEditing,
    onRemoveSlide
  }: {
    session: any;
    slides: any[];
    activeSlideId: string | null;
    slideIcons: Record<string, any>;
    slideLabels: Record<string, string>;
    wsStatus: WsStatus;
    onToggleLive: () => void;
    onAddSlide: (type: string) => void;
    onActivateSlide: (id: string) => void;
    onStartEditing: (id: string) => void;
    onRemoveSlide: (id: string) => void;
  } = $props();

  function getSlideTypeKey(slide: any) {
    return slide?.type?.toUpperCase?.() || '';
  }
</script>

<aside class="col-span-12 lg:col-span-3 space-y-4">
  <!-- Session info card -->
  <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
    <div class="flex items-center justify-between mb-3">
      <div class="text-lg font-semibold text-slate-900 dark:text-white truncate">{session?.title}</div>
      <ConnectionStatus status={wsStatus} />
    </div>
    <div class="text-xs text-slate-500 font-mono mb-4">{session?.unique_code}</div>
    <button
      onclick={onToggleLive}
      class="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition-all active:scale-95 {session?.is_live
        ? 'bg-red-500/10 text-red-500 border border-red-500/20 hover:bg-red-500/20'
        : 'bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white shadow-lg shadow-purple-500/20'}"
    >
      <Radio class="w-4 h-4" />
      {session?.is_live ? 'Stop session' : 'Start session'}
    </button>
  </div>

  <!-- Add slide grid -->
  <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
    <div class="text-sm font-semibold text-slate-900 dark:text-white mb-3">Add slide</div>
    <div class="grid grid-cols-3 gap-2">
      {#each Object.keys(slideLabels) as key}
        {@const Icon = slideIcons[key]}
        <button
          onclick={() => onAddSlide(key)}
          class="flex flex-col items-center gap-1.5 p-3 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-purple-500/40 hover:bg-purple-50 dark:hover:bg-purple-500/5 transition-all group"
          title={slideLabels[key]}
        >
          {#if Icon}
            <Icon class="w-5 h-5 text-slate-400 group-hover:text-purple-500 transition-colors" />
          {/if}
          <span class="text-[10px] font-medium text-slate-500 dark:text-slate-400 group-hover:text-purple-600 dark:group-hover:text-purple-400 transition-colors">{slideLabels[key]}</span>
        </button>
      {/each}
    </div>
  </div>

  <!-- Slides list -->
  <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
    <div class="flex items-center justify-between mb-3">
      <div class="text-sm font-semibold text-slate-900 dark:text-white">Slides</div>
      <span class="text-xs text-slate-400">{slides.length}</span>
    </div>
    {#if slides.length === 0}
      <div class="flex flex-col items-center gap-2 py-6 text-center">
        <Layers class="w-8 h-8 text-slate-300 dark:text-slate-700" />
        <p class="text-xs text-slate-400">No slides yet. Add one above.</p>
      </div>
    {:else}
      <div class="space-y-1.5">
        {#each slides as slide (slide.id)}
          <SlideCard
            {slide}
            active={slide.id === activeSlideId}
            icon={slideIcons[getSlideTypeKey(slide)]}
            label={slideLabels[getSlideTypeKey(slide)] || getSlideTypeKey(slide) || 'Slide'}
            onActivate={onActivateSlide}
            onEdit={onStartEditing}
            onRemove={onRemoveSlide}
          />
        {/each}
      </div>
    {/if}
  </div>
</aside>
