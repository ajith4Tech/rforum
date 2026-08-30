<script lang="ts">
  import { BarChart3, Cloud, FileText, Maximize2, MessageSquare, MonitorPlay, Pencil, Radio, RefreshCw, Users } from 'lucide-svelte';
  import { getPageImageUrl, getPresentationPageImageUrl } from '$lib/api';
  import PageImageViewer from '$lib/components/PageImageViewer.svelte';
  import PresentationLiveView from '$lib/components/timeline/PresentationLiveView.svelte';
  import InteractionView from '$lib/components/timeline/InteractionView.svelte';
  import ConnectionStatus from '$lib/components/ConnectionStatus.svelte';
  import ContentSlideCanvas from '$lib/components/ContentSlideCanvas.svelte';
  import type { ConnectionStatus as WsStatus } from '$lib/ws';

  let {
    session, presentation = null, timeline = null, slides = [], activeSlideId = null,
    responses = [], wsStatus = 'disconnected' as WsStatus, onAddSlide = undefined, onSelect, onEdit, onPresent, onToggleLive,
    onRefreshPresentation = undefined, onMaximizeQr = undefined
  }: {
    session: any; presentation?: any; timeline?: any; slides?: any[]; activeSlideId?: string | null;
    responses?: any[]; wsStatus?: WsStatus; onAddSlide?: (type: string) => void; onSelect: (id: string) => void; onEdit: () => void;
    onPresent: () => void; onToggleLive: () => void; onRefreshPresentation?: () => void; onMaximizeQr?: () => void;
  } = $props();

  const items = $derived(timeline ? [...(timeline.items || [])].sort((a: any, b: any) => a.order - b.order) : [...slides].sort((a: any, b: any) => (a.order ?? 0) - (b.order ?? 0)));
  const activeId = $derived(timeline?.active_timeline_item_id || activeSlideId || items[0]?.id || null);
  let selectedItemId = $state<string | null>(null);
  $effect(() => { if (!selectedItemId) selectedItemId = activeId; });
  const selectedId = $derived(selectedItemId || activeId);
  const selected = $derived(items.find((item: any) => item.id === selectedId) || items[0] || null);
  const selectedSlide = $derived(selected?.slide || selected);
  const isTimeline = $derived(!!timeline);
  const isInteractive = $derived(selectedSlide && selectedSlide.type?.toUpperCase() !== 'CONTENT');
  const quickSlideTypes = [
    { type: 'POLL', label: 'Poll', icon: BarChart3 },
    { type: 'QNA', label: 'Q&A', icon: MessageSquare },
    { type: 'FEEDBACK', label: 'Feedback', icon: FileText },
    { type: 'CONTENT', label: 'Content', icon: FileText },
    { type: 'WORD_CLOUD', label: 'Word Cloud', icon: Cloud }
  ];
  const label = (item: any) => {
    const slide = item.slide || item;
    if (item.item_type === 'PAGE') return `Page ${item.page?.page_number ?? ''}`;
    const c = slide?.content_json || {};
    return c.title || c.question || c.prompt || slide?.type || 'Slide';
  };
  const icon = (item: any) => {
    const type = (item.slide || item)?.type?.toUpperCase();
    return type === 'POLL' ? BarChart3 : type === 'WORD_CLOUD' ? Cloud : type === 'QNA' ? MessageSquare : FileText;
  };
</script>

<section class="deck-view space-y-5">
  <header class="flex flex-col gap-4 border-b border-surface-200 dark:border-surface-800 pb-5 lg:flex-row lg:items-end lg:justify-between">
    <div>
      <p class="text-xs font-semibold uppercase tracking-[0.18em] text-brand-500">Presentation deck</p>
      <div class="mt-1 flex flex-wrap items-center gap-3"><h1 class="font-heading text-2xl font-bold text-surface-900 dark:text-white">{presentation?.title || session?.title}</h1><ConnectionStatus status={wsStatus} /></div>
      <p class="mt-1 text-sm text-surface-500">Session {session?.unique_code} · {items.length} {items.length === 1 ? 'slide' : 'slides'} · {session?.is_live ? 'Live now' : 'Not live'}</p>
    </div>
    <div class="flex flex-wrap gap-2">
      <button class="flex items-center gap-2 {session?.is_live ? 'rounded-xl px-4 py-2.5 text-sm font-semibold border border-red-200 bg-red-50 text-red-600 hover:bg-red-100 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-400 dark:hover:bg-red-950/50' : 'btn-secondary'}" onclick={onToggleLive}><Radio class="w-4 h-4" />{session?.is_live ? 'End session' : 'Go live'}</button>
      <button class="btn-secondary flex items-center gap-2" onclick={onEdit}><Pencil class="w-4 h-4" />Edit deck</button>
      <button class="btn-primary flex items-center gap-2" onclick={onPresent}><MonitorPlay class="w-4 h-4" />Present</button>
      {#if onRefreshPresentation}
        <button class="btn-secondary flex items-center justify-center" onclick={onRefreshPresentation} aria-label="Refresh presentation screen" title="Refresh presentation screen"><RefreshCw class="h-4 w-4" /></button>
      {/if}
      {#if onMaximizeQr}
        <button class="btn-secondary flex items-center justify-center" onclick={onMaximizeQr} aria-label="Toggle enlarged QR" title="Toggle enlarged QR"><Maximize2 class="h-4 w-4" /></button>
      {/if}
    </div>
  </header>

  <div class="grid min-h-[min(70vh,46rem)] gap-5 xl:grid-cols-[13rem_minmax(42rem,1fr)_17rem]">
    <aside class="max-h-[min(70vh,46rem)] overflow-y-auto pr-1">
      {#if !session?.presentation_id && onAddSlide}
        <div class="mb-5 rounded-xl border border-surface-200 bg-white p-4 shadow-sm dark:border-surface-800 dark:bg-surface-900">
          <p class="mb-3 text-xs font-semibold uppercase tracking-widest text-surface-500">Add slide</p>
          <div class="grid grid-cols-2 gap-2">
            {#each quickSlideTypes as option}
              {@const QuickIcon = option.icon}
              <button onclick={() => onAddSlide?.(option.type)} class="flex min-h-20 flex-col items-center justify-center gap-1.5 rounded-lg border border-surface-200 text-xs font-medium text-surface-600 transition hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700 dark:border-surface-800 dark:text-surface-300 dark:hover:border-brand-500/50 dark:hover:bg-brand-500/10 dark:hover:text-brand-300">
                <QuickIcon class="h-5 w-5 text-brand-500" />
                {option.label}
              </button>
            {/each}
          </div>
        </div>
      {/if}
      <p class="mb-2 text-xs font-semibold uppercase tracking-widest text-surface-500">Slides</p>
      <div class="space-y-2">
        {#each items as item, index (item.id)}
          {@const Icon = icon(item)}
          <button onclick={() => { selectedItemId = item.id; onSelect(item.id); }} class="w-full rounded-xl border p-3 text-left transition {item.id === selectedId ? 'border-brand-500 bg-brand-500/10 shadow-sm' : 'border-surface-200 bg-white hover:border-surface-300 dark:border-surface-800 dark:bg-surface-900 dark:hover:border-surface-700'}">
            <div class="flex items-start gap-2">
              <span class="mt-0.5 text-xs font-mono text-surface-400">{index + 1}</span>
              <Icon class="mt-0.5 h-4 w-4 shrink-0 text-brand-500" />
              <span class="line-clamp-2 text-sm font-medium text-surface-700 dark:text-surface-200">{label(item)}</span>
            </div>
            {#if (item.slide || item)?.type?.toUpperCase() !== 'CONTENT' && item.item_type !== 'PAGE'}<span class="mt-2 inline-block text-[10px] font-semibold uppercase tracking-wider text-brand-500">Interactive</span>{/if}
          </button>
        {/each}
      </div>
    </aside>

    <div class="min-w-0 flex flex-col">
      <p class="mb-2 text-xs font-semibold uppercase tracking-widest text-surface-500">Selected slide</p>
      <div class="aspect-video max-h-[min(65vh,42rem)] flex-1 overflow-hidden rounded-2xl border border-surface-200 bg-white shadow-lg dark:border-surface-800 dark:bg-surface-900">
        {#if selected?.item_type === 'PAGE'}
          <PageImageViewer src={getPresentationPageImageUrl(presentation.id, selected.page.page_number)} page={selected.page.page_number} alt={label(selected)} imgClass="w-full h-full object-contain" />
        {:else if isTimeline && selected?.slide}
          <div class="h-full overflow-auto p-5 sm:p-8"><PresentationLiveView activeItem={selected} presentationId={presentation.id} {responses} variant="screen" readOnly /></div>
        {:else if selectedSlide?.type?.toUpperCase() === 'CONTENT'}
          <div class="h-full overflow-hidden p-5 sm:p-8">
            <ContentSlideCanvas slide={selectedSlide} sessionId={session?.id} sessionCode={session?.unique_code || ''} variant="deck" />
          </div>
        {:else if selectedSlide}
          <div class="h-full overflow-auto p-5 sm:p-8"><InteractionView slide={selectedSlide} {responses} variant="screen" readOnly /></div>
        {/if}
      </div>
    </div>

    <aside class="max-h-[min(70vh,46rem)] overflow-hidden rounded-2xl border border-surface-200 bg-white p-5 dark:border-surface-800 dark:bg-surface-900">
      <div class="flex items-center justify-between"><p class="text-xs font-semibold uppercase tracking-widest text-surface-500">Live activity</p><Users class="h-4 w-4 text-brand-500" /></div>
      {#if isInteractive}
        <p class="mt-4 text-sm font-semibold text-surface-800 dark:text-white">{selectedSlide?.content_json?.question || selectedSlide?.content_json?.prompt || 'Audience responses'}</p>
        <p class="mt-2 text-2xl font-bold text-brand-500">{responses.length}<span class="ml-1 text-sm font-medium text-surface-500">responses</span></p>
        <div class="mt-4 max-h-[26rem] space-y-2 overflow-y-auto">
          {#if responses.length}
            {#each [...responses].slice().reverse().slice(0, 12) as response (response.id)}
              <div class="rounded-lg bg-surface-100 px-3 py-2 text-sm text-surface-700 dark:bg-surface-800 dark:text-surface-200">{response.value || (response.rating ? `${response.rating} stars` : 'Response')} {#if response.name}<span class="block pt-1 text-xs text-surface-500">{response.name}</span>{/if}</div>
            {/each}
          {:else}<p class="pt-8 text-sm text-surface-500">Responses will appear here as your audience participates.</p>{/if}
        </div>
      {:else}<div class="flex h-52 flex-col items-center justify-center text-center"><FileText class="mb-3 h-7 w-7 text-surface-300 dark:text-surface-700" /><p class="text-sm font-medium text-surface-500">Content slide</p><p class="mt-1 text-xs leading-relaxed text-surface-400">Live responses appear when an interactive slide is selected.</p></div>{/if}
    </aside>
  </div>
</section>
