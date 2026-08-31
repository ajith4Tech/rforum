<script lang="ts">
  import { FileText, Maximize2, MonitorPlay, Pencil, Radio, RefreshCw, Users, BarChart3, Cloud, MessageSquare } from 'lucide-svelte';
  import { getPresentationPageImageUrl } from '$lib/api';
  import PageImageViewer from '$lib/components/PageImageViewer.svelte';
  import PresentationLiveView from '$lib/components/timeline/PresentationLiveView.svelte';
  import InteractionView from '$lib/components/timeline/InteractionView.svelte';
  import ConnectionStatus from '$lib/components/ConnectionStatus.svelte';
  import ContentSlideCanvas from '$lib/components/ContentSlideCanvas.svelte';
  import { getFitTitleStyle, responsesForSlide } from '$lib/fitTitle';
  import type { ConnectionStatus as WsStatus } from '$lib/ws';

  let {
    session, presentation = null, timeline = null, slides = [], activeSlideId = null,
    responses = [], wsStatus = 'disconnected' as WsStatus, onSelect, onEdit, onPresent, onToggleLive,
    onRefreshPresentation = undefined, onMaximizeQr = undefined
  }: {
    session: any; presentation?: any; timeline?: any; slides?: any[]; activeSlideId?: string | null;
    responses?: any[]; wsStatus?: WsStatus; onSelect: (id: string) => void; onEdit: () => void;
    onPresent: (itemId: string | null) => void; onToggleLive: () => void; onRefreshPresentation?: () => void; onMaximizeQr?: () => void;
  } = $props();

  const items = $derived(timeline ? [...(timeline.items || [])].sort((a: any, b: any) => a.order - b.order) : [...slides].sort((a: any, b: any) => (a.order ?? 0) - (b.order ?? 0)));
  const liveId = $derived(timeline?.active_timeline_item_id || activeSlideId || null);
  let selectedItemId = $state<string | null>(null);
  $effect(() => { if (!selectedItemId && items[0]?.id) selectedItemId = items[0].id; });
  const selectedId = $derived(selectedItemId || items[0]?.id || null);
  const selected = $derived(items.find((item: any) => item.id === selectedId) || items[0] || null);
  const selectedSlide = $derived(selected?.slide || selected);
  const isTimeline = $derived(!!timeline);
  const isInteractive = $derived(selectedSlide && selectedSlide.type?.toUpperCase() !== 'CONTENT' && selected?.item_type !== 'PAGE');
  const visibleResponses = $derived(responsesForSlide(responses, selectedSlide?.id));
  const promptText = $derived(selectedSlide?.content_json?.question || selectedSlide?.content_json?.prompt || 'Audience responses');

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

  function selectItem(id: string) {
    selectedItemId = id;
    onSelect(id);
  }
</script>

<section class="deck-console flex min-h-[calc(100vh-9rem)] flex-col bg-surface-50 dark:bg-surface-950">
  <header class="flex flex-col gap-3 border-b border-surface-200 px-1 py-3 dark:border-surface-800 sm:flex-row sm:items-center sm:justify-between">
    <div class="min-w-0">
      <p class="text-xs font-semibold uppercase tracking-[0.16em] text-brand-500">{session?.unique_code}</p>
      <div class="mt-0.5 flex min-w-0 flex-wrap items-center gap-3">
        <h1 class="font-heading truncate text-xl font-bold text-surface-900 dark:text-white">{presentation?.title || session?.title}</h1>
        <ConnectionStatus status={wsStatus} />
      </div>
      <p class="mt-0.5 text-sm text-surface-500">{items.length} {items.length === 1 ? 'slide' : 'slides'} · {session?.is_live ? 'Live' : 'Not live'}</p>
    </div>
    <div class="flex flex-wrap gap-2">
      <button class="flex items-center gap-2 {session?.is_live ? 'rounded-xl px-4 py-2.5 text-sm font-semibold border border-red-200 bg-red-50 text-red-600 hover:bg-red-100 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-400 dark:hover:bg-red-950/50' : 'btn-secondary'}" onclick={onToggleLive}><Radio class="w-4 h-4" />{session?.is_live ? 'End session' : 'Go live'}</button>
      <button class="btn-secondary flex items-center gap-2" onclick={onEdit}><Pencil class="w-4 h-4" />Edit</button>
      <button class="btn-primary flex items-center gap-2" onclick={() => onPresent(selectedId)}><MonitorPlay class="w-4 h-4" />Present</button>
      {#if onRefreshPresentation}
        <button class="btn-secondary flex items-center justify-center" onclick={onRefreshPresentation} aria-label="Refresh presentation screen" title="Refresh presentation screen"><RefreshCw class="h-4 w-4" /></button>
      {/if}
      {#if onMaximizeQr}
        <button class="btn-secondary flex items-center justify-center" onclick={onMaximizeQr} aria-label="Toggle enlarged QR" title="Toggle enlarged QR"><Maximize2 class="h-4 w-4" /></button>
      {/if}
    </div>
  </header>

  <div class="grid min-h-0 flex-1 gap-0 xl:grid-cols-[13.5rem_minmax(0,1fr)_18rem]">
    <aside class="max-h-[min(78vh,52rem)] overflow-y-auto border-surface-200 py-4 pr-3 dark:border-surface-800 xl:border-r">
      <p class="mb-2 text-[11px] font-semibold uppercase tracking-widest text-surface-500">Slides</p>
      {#if items.length === 0}
        <p class="text-sm text-surface-500">No slides yet. Use Edit to create or upload a deck.</p>
      {:else}
        <div class="space-y-1.5">
          {#each items as item, index (item.id)}
            {@const Icon = icon(item)}
            <button onclick={() => selectItem(item.id)} class="w-full rounded-lg px-2.5 py-2 text-left transition {item.id === selectedId ? 'bg-brand-500/10 ring-1 ring-brand-500' : 'hover:bg-surface-100 dark:hover:bg-surface-900'}">
              <div class="flex items-start gap-2">
                <span class="mt-0.5 w-4 text-right text-[11px] font-mono text-surface-400">{index + 1}</span>
                <Icon class="mt-0.5 h-4 w-4 shrink-0 text-brand-500" />
                <span class="line-clamp-2 text-sm font-medium text-surface-800 dark:text-surface-100">{label(item)}</span>
              </div>
              {#if item.id === liveId}<span class="ml-6 mt-1 inline-block text-[10px] font-semibold uppercase tracking-wider text-brand-500">On screen</span>{/if}
            </button>
          {/each}
        </div>
      {/if}
    </aside>

    <div class="flex min-h-0 min-w-0 flex-col px-0 py-4 xl:px-5">
      <div class="flex min-h-0 flex-1 items-center justify-center" style="container-type: size;">
        <div class="overflow-hidden rounded-xl bg-white shadow-lg ring-1 ring-surface-200 dark:bg-surface-900 dark:ring-surface-800" style="width: min(100cqw, calc(100cqh * 16 / 9)); height: min(100cqh, calc(100cqw * 9 / 16)); min-height: 14rem;">
          {#if !selected}
            <div class="flex h-full items-center justify-center px-6 text-center text-sm text-surface-500">This session has no slides yet. Open Edit to add a deck.</div>
          {:else if selected?.item_type === 'PAGE'}
            <PageImageViewer src={getPresentationPageImageUrl(presentation.id, selected.page.page_number)} page={selected.page.page_number} alt={label(selected)} imgClass="h-full w-full object-contain" />
          {:else if selectedSlide?.type?.toUpperCase() === 'CONTENT'}
            <div class="h-full overflow-hidden p-4 sm:p-6">
              <ContentSlideCanvas slide={selectedSlide} sessionId={session?.id} sessionCode={session?.unique_code || ''} variant="deck" />
            </div>
          {:else if isTimeline && selected?.slide}
            <div class="h-full overflow-auto p-4 sm:p-6"><PresentationLiveView activeItem={selected} presentationId={presentation.id} sessionId={session?.id} sessionCode={session?.unique_code || ''} responses={visibleResponses} variant="screen" readOnly /></div>
          {:else if selectedSlide}
            <div class="h-full overflow-auto p-4 sm:p-6"><InteractionView slide={selectedSlide} responses={visibleResponses} variant="screen" readOnly /></div>
          {/if}
        </div>
      </div>
    </div>

    <aside class="max-h-[min(78vh,52rem)] overflow-y-auto border-surface-200 py-4 pl-0 dark:border-surface-800 xl:border-l xl:pl-5">
      <div class="flex items-center justify-between">
        <p class="text-[11px] font-semibold uppercase tracking-widest text-surface-500">Live activity</p>
        <Users class="h-4 w-4 text-brand-500" />
      </div>
      {#if isInteractive}
        <h2 class="mt-3 font-heading font-semibold text-surface-900 dark:text-white" style={getFitTitleStyle(promptText, 'question')}>{promptText}</h2>
        <p class="mt-2 text-2xl font-bold text-brand-500">{visibleResponses.length}<span class="ml-1 text-sm font-medium text-surface-500">responses</span></p>
        <div class="mt-4 space-y-2">
          {#if visibleResponses.length}
            {#each [...visibleResponses].slice().reverse().slice(0, 12) as response (response.id)}
              <div class="rounded-lg bg-surface-100 px-3 py-2 text-sm text-surface-700 dark:bg-surface-900 dark:text-surface-200">{response.value || (response.rating ? `${response.rating} stars` : 'Response')} {#if response.name}<span class="block pt-1 text-xs text-surface-500">{response.name}</span>{/if}</div>
            {/each}
          {:else}
            <p class="pt-6 text-sm text-surface-500">Responses appear here for this slide when the audience participates.</p>
          {/if}
        </div>
      {:else}
        <div class="flex h-40 flex-col items-center justify-center text-center">
          <FileText class="mb-2 h-6 w-6 text-surface-300 dark:text-surface-700" />
          <p class="text-sm text-surface-500">Select an interactive slide to see live responses.</p>
        </div>
      {/if}
    </aside>
  </div>
</section>
