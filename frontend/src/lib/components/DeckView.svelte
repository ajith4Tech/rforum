<script lang="ts">
  import { FileText, Maximize2, MonitorPlay, Pencil, Radio, RefreshCw, Users, BarChart3, Cloud, MessageSquare, Eye, EyeOff, Trash2 } from 'lucide-svelte';
  import { getPresentationPageImageUrl } from '$lib/api';
  import PageImageViewer from '$lib/components/PageImageViewer.svelte';
  import PresentationLiveView from '$lib/components/timeline/PresentationLiveView.svelte';
  import InteractionView from '$lib/components/timeline/InteractionView.svelte';
  import ConnectionStatus from '$lib/components/ConnectionStatus.svelte';
  import ContentSlideCanvas from '$lib/components/ContentSlideCanvas.svelte';
  import type { VideoControlPayload } from '$lib/components/ContentSlideCanvas.svelte';
  import { getFitTitleStyle, responsesForSlide } from '$lib/fitTitle';
  import { metaForItem } from '$lib/timelineTypes';
  import { validQuizAnswer } from '$lib/quiz';
  import type { ConnectionStatus as WsStatus } from '$lib/ws';

  let {
    session, presentation = null, timeline = null, slides = [], activeSlideId = null,
    responses = [], wsStatus = 'disconnected' as WsStatus, onSelect, onEdit, onPresent, onToggleLive,
    onRefreshPresentation = undefined, onMaximizeQr = undefined, onToggleRevealAnswer = undefined,
    onVideoControl = undefined, liveToggleBusy = false, onSetResponseHidden = undefined, onClearResponses = undefined,
  }: {
    session: any; presentation?: any; timeline?: any; slides?: any[]; activeSlideId?: string | null;
    responses?: any[]; wsStatus?: WsStatus; onSelect: (id: string) => void; onEdit: () => void;
    onPresent: (itemId: string | null) => void; onToggleLive: () => void; onRefreshPresentation?: () => void; onMaximizeQr?: () => void;
    /** Toggle a Quiz slide's reveal_answer from the normal moderator view —
        not just the Editor. Only shown when the currently selected slide is
        a Quiz (see isQuizSelected below). */
    onToggleRevealAnswer?: (itemId: string) => void;
    /** Called when the moderator interacts with an embedded video player so
     *  the action can be broadcast to the main screen. */
    onVideoControl?: (payload: VideoControlPayload) => void;
    /** True while a start/end-session request is in flight. */
    liveToggleBusy?: boolean;
    /** Moderation: hide/unhide one response, or clear every response of a slide. */
    onSetResponseHidden?: (slideId: string, responseId: string, hidden: boolean) => void;
    onClearResponses?: (slideId: string) => void;
  } = $props();

  const items = $derived(timeline ? [...(timeline.items || [])].sort((a: any, b: any) => a.order - b.order) : [...slides].sort((a: any, b: any) => (a.order ?? 0) - (b.order ?? 0)));
  const liveId = $derived(timeline?.active_timeline_item_id || activeSlideId || null);
  let selectedItemId = $state<string | null>(null);
  // Follow the on-screen item whenever it changes (initial load, keyboard /
  // editor navigation, another tab), so this view — and the Present button,
  // which presents the selected item — never sits on a different slide than
  // the audience sees. Manual selection still works between live changes.
  let lastLiveId: string | null = null;
  $effect(() => {
    if (liveId && liveId !== lastLiveId) {
      lastLiveId = liveId;
      selectedItemId = liveId;
    }
  });
  // Fall back to the live item, then the first item, when nothing is selected
  // or the selected item was deleted.
  const selectedId = $derived(
    (selectedItemId && items.some((item: any) => item.id === selectedItemId) ? selectedItemId : null)
      || (liveId && items.some((item: any) => item.id === liveId) ? liveId : null)
      || items[0]?.id
      || null
  );
  const selected = $derived(items.find((item: any) => item.id === selectedId) || items[0] || null);
  const selectedSlide = $derived(selected?.slide || selected);
  const isTimeline = $derived(!!timeline);
  const isInteractive = $derived(selectedSlide && selectedSlide.type?.toUpperCase() !== 'CONTENT' && selected?.item_type !== 'PAGE');
  // The moderator also receives hidden responses (so they can be unhidden);
  // the preview and counts show only what the audience sees.
  const slideResponses = $derived(responsesForSlide(responses, selectedSlide?.id));
  const visibleResponses = $derived(slideResponses.filter((r: any) => !r.is_hidden));
  const hiddenCount = $derived(slideResponses.length - visibleResponses.length);
  const promptText = $derived(selectedSlide?.content_json?.question || selectedSlide?.content_json?.prompt || 'Audience responses');

  // Same detection InteractionView.svelte itself uses — a Quiz slide is a
  // POLL-type slide (legacy) or POLL-family timeline item (presentation)
  // whose content_json carries interaction_type/mode "QUIZ"/"quiz".
  const isQuizSelected = $derived(Boolean(
    selectedSlide?.content_json &&
    (selectedSlide.content_json.interaction_type === 'QUIZ' || selectedSlide.content_json.mode === 'quiz')
  ));
  const quizRevealed = $derived(Boolean(selectedSlide?.content_json?.reveal_answer));
  // Revealing a quiz without a valid answer would tell every guest they were
  // wrong — only allow it once one is set. Hiding is always allowed.
  const quizHasAnswer = $derived(validQuizAnswer(selectedSlide?.content_json) !== '');

  const label = (item: any) => {
    const slide = item.slide || item;
    if (item.item_type === 'PAGE') return `Page ${item.page?.page_number ?? ''}`;
    const c = slide?.content_json || {};
    return c.title || c.question || c.prompt || metaForItem(item).label || slide?.type || 'Slide';
  };
  const icon = (item: any) => metaForItem(item).icon;

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
      <button class="flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed {session?.is_live ? 'rounded-xl px-4 py-2.5 text-sm font-semibold border border-red-200 bg-red-50 text-red-600 hover:bg-red-100 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-400 dark:hover:bg-red-950/50' : 'btn-secondary'}" onclick={onToggleLive} disabled={liveToggleBusy} aria-busy={liveToggleBusy}><Radio class="w-4 h-4" />{#if liveToggleBusy}{session?.is_live ? 'Ending…' : 'Starting…'}{:else}{session?.is_live ? 'End session' : 'Go live'}{/if}</button>
      <button class="btn-secondary flex items-center gap-2" onclick={onEdit}><Pencil class="w-4 h-4" />Edit</button>
      <button class="btn-primary flex items-center gap-2" onclick={() => onPresent(selectedId)}><MonitorPlay class="w-4 h-4" />Present</button>
      {#if isQuizSelected && onToggleRevealAnswer}
        <button
          class="btn-secondary flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          onclick={() => selectedId && onToggleRevealAnswer?.(selectedId)}
          disabled={!quizRevealed && !quizHasAnswer}
          aria-label={quizRevealed ? 'Hide quiz answer' : 'Reveal quiz answer'}
          title={quizRevealed ? 'Hide quiz answer' : quizHasAnswer ? 'Reveal quiz answer' : 'Mark a correct answer in Edit before revealing'}
        >
          {#if quizRevealed}<EyeOff class="w-4 h-4" />Hide Answer{:else}<Eye class="w-4 h-4" />Reveal Answer{/if}
        </button>
      {/if}
      {#if onRefreshPresentation}
        <button class="btn-secondary flex items-center justify-center" onclick={onRefreshPresentation} aria-label="Refresh presentation screen" title="Refresh presentation screen"><RefreshCw class="h-4 w-4" /></button>
      {/if}
      {#if onMaximizeQr}
        <button class="btn-secondary flex items-center justify-center" onclick={onMaximizeQr} aria-label="Toggle enlarged QR" title="Toggle enlarged QR"><Maximize2 class="h-4 w-4" /></button>
      {/if}
    </div>
  </header>

  {#if wsStatus === 'offline' || wsStatus === 'reconnecting'}
    <div class="mt-3 rounded-xl border px-4 py-2.5 text-sm {wsStatus === 'offline' ? 'border-red-300 bg-red-50 text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300' : 'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800/60 dark:bg-amber-950/30 dark:text-amber-300'}" role="status" aria-live="polite">
      {#if wsStatus === 'offline'}
        You're offline. Slide changes and other actions can't reach the audience or projector until you reconnect; live responses are paused.
      {:else}
        Reconnecting… actions made now may not reach the audience or projector, and live responses may be delayed.
      {/if}
    </div>
  {/if}

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

    <div class="flex min-h-0 min-w-0 flex-1 items-center justify-center overflow-hidden px-0 py-4 lg:px-5">
  <div class="relative w-full max-w-full aspect-video max-h-full overflow-hidden rounded-xl bg-white shadow-lg ring-1 ring-surface-200 dark:bg-surface-900 dark:ring-surface-800">
    {#if !selected}
      <div class="flex h-full items-center justify-center px-6 text-center text-sm text-surface-500">
        This session has no slides yet. Open Edit to add a deck.
      </div>

    {:else if selected?.item_type === 'PAGE'}
      <PageImageViewer
        src={getPresentationPageImageUrl(presentation.id, selected.page.page_number)}
        page={selected.page.page_number}
        alt={label(selected)}
        imgClass="h-full w-full object-contain"
      />

    {:else if selectedSlide?.type?.toUpperCase() === 'CONTENT'}
      <div class="h-full w-full overflow-hidden p-4 sm:p-6">
        <ContentSlideCanvas
          slide={selectedSlide}
          sessionId={session?.id}
          sessionCode={session?.unique_code || ''}
          variant="deck"
          {onVideoControl}
        />
      </div>

    {:else if isTimeline && selected?.slide}
      <div class="h-full w-full overflow-auto p-4 sm:p-6">
        <PresentationLiveView
          activeItem={selected}
          presentationId={presentation.id}
          sessionId={session?.id}
          sessionCode={session?.unique_code || ''}
          responses={visibleResponses}
          variant="screen"
          readOnly
          {onVideoControl}
        />
      </div>

    {:else if selectedSlide}
      <div class="h-full w-full overflow-auto p-4 sm:p-6">
        <InteractionView
          slide={selectedSlide}
          responses={visibleResponses}
          variant="screen"
          readOnly
        />
      </div>
    {/if}
  </div>
</div>

    <aside class="max-h-[min(78vh,52rem)] overflow-y-auto border-surface-200 py-4 pl-0 dark:border-surface-800 xl:border-l xl:pl-5">
      <div class="flex items-center justify-between">
        <p class="text-[11px] font-semibold uppercase tracking-widest text-surface-500">Live activity</p>
        <Users class="h-4 w-4 text-brand-500" />
      </div>
      {#if isInteractive}
        <h2 class="mt-3 font-heading font-semibold text-surface-900 dark:text-white" style={getFitTitleStyle(promptText, 'question')}>{promptText}</h2>
        <div class="mt-2 flex items-end justify-between gap-2">
          <p class="text-2xl font-bold text-brand-500">{visibleResponses.length}<span class="ml-1 text-sm font-medium text-surface-500">responses{#if hiddenCount} · {hiddenCount} hidden{/if}</span></p>
          {#if onClearResponses && slideResponses.length && selectedSlide?.id}
            <button
              class="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-red-600 transition hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/30"
              onclick={() => onClearResponses?.(selectedSlide.id)}
            ><Trash2 class="h-3.5 w-3.5" />Clear</button>
          {/if}
        </div>
        <div class="mt-4 space-y-2">
          {#if slideResponses.length}
            {#each [...slideResponses].reverse() as response (response.id)}
              <div class="flex items-start gap-2 rounded-lg px-3 py-2 text-sm {response.is_hidden ? 'border border-dashed border-surface-300 text-surface-400 dark:border-surface-700 dark:text-surface-500' : 'bg-surface-100 text-surface-700 dark:bg-surface-900 dark:text-surface-200'}">
                <div class="min-w-0 flex-1 break-words">
                  {#if response.is_hidden}<span class="mb-0.5 block text-[10px] font-semibold uppercase tracking-wider">Hidden from audience</span>{/if}
                  {response.value || (response.rating ? `${response.rating} stars` : 'Response')} {#if response.name}<span class="block pt-1 text-xs text-surface-500">{response.name}</span>{/if}
                </div>
                {#if onSetResponseHidden && selectedSlide?.id}
                  <button
                    class="shrink-0 rounded-md p-1 text-surface-500 transition hover:bg-surface-200 hover:text-surface-900 dark:hover:bg-surface-800 dark:hover:text-white"
                    onclick={() => onSetResponseHidden?.(selectedSlide.id, response.id, !response.is_hidden)}
                    aria-label={response.is_hidden ? 'Show this response to the audience again' : 'Hide this response from the audience'}
                    title={response.is_hidden ? 'Unhide' : 'Hide from audience'}
                  >
                    {#if response.is_hidden}<Eye class="h-3.5 w-3.5" />{:else}<EyeOff class="h-3.5 w-3.5" />{/if}
                  </button>
                {/if}
              </div>
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