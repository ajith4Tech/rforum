<script lang="ts">
  import { Radio, Trash2, GripVertical, FileText, RefreshCw, Upload, Copy, ChevronUp, ChevronDown, Info } from 'lucide-svelte';
  import { flip } from 'svelte/animate';
  import { tick } from 'svelte';
  import ConnectionStatus from '$lib/components/ConnectionStatus.svelte';
  import { getPresentationPageThumbnailUrl } from '$lib/api';
  import TimelineInserter from './TimelineInserter.svelte';
  import { metaForItem } from '$lib/timelineTypes';
  import type { ConnectionStatus as WsStatus } from '$lib/ws';

  let {
    session,
    presentation,
    timeline,
    activeItemId = null,
    liveItemId = null,
    wsStatus = 'disconnected' as WsStatus,
    liveToggleBusy = false,
    onToggleLive,
    onSelect,
    onInsert,
    onDeleteItem,
    onDuplicateItem,
    onReorder,
    onReplaceClick,
    onRegenerate,
    onOpenDetails
  }: {
    session: any;
    presentation: any;
    timeline: { items: any[] };
    activeItemId: string | null;
    liveItemId?: string | null;
    wsStatus: WsStatus;
    /** True while a start/end-session request is in flight. */
    liveToggleBusy?: boolean;
    onToggleLive: () => void;
    onSelect: (itemId: string) => void;
    onInsert: (itemType: string, position: number) => void;
    onDeleteItem: (itemId: string) => void;
    onDuplicateItem: (itemId: string) => void;
    onReorder: (itemIds: string[]) => void;
    onReplaceClick: () => void;
    onRegenerate: () => void;
    onOpenDetails: () => void;
  } = $props();

  const items = $derived([...(timeline?.items || [])].sort((a, b) => a.order - b.order));

  const metaFor = metaForItem;

  let draggedItemId: string | null = $state(null);
  let dragOverIndex: number | null = $state(null);
  let confirmingDeleteId: string | null = $state(null);
  let reorderAnnouncement = $state('');
  let loadedThumbs: Record<string, boolean> = $state({});

  function handleDragStart(item: any) {
    if (item.item_type === 'PAGE') return;
    draggedItemId = item.id;
  }

  function handleDragEnd() {
    draggedItemId = null;
    dragOverIndex = null;
  }

  function handleDragOver(e: DragEvent, index: number) {
    if (!draggedItemId) return;
    e.preventDefault();
    dragOverIndex = index;
  }

  function handleDrop(e: DragEvent, targetIndex: number) {
    e.preventDefault();
    dragOverIndex = null;
    if (!draggedItemId) return;
    const currentIds = items.map((i) => i.id);
    const fromIndex = currentIds.indexOf(draggedItemId);
    if (fromIndex === -1) return;
    const reordered = currentIds.filter((id) => id !== draggedItemId);
    const adjustedTarget = fromIndex < targetIndex ? targetIndex - 1 : targetIndex;
    reordered.splice(adjustedTarget, 0, draggedItemId);
    draggedItemId = null;
    reorderAnnouncement = 'Timeline reordered';
    onReorder(reordered);
  }

  /** Keyboard-operable equivalent of dragging a row up/down one slot — swaps
   * with whatever is currently adjacent (page or interaction), matching what
   * native drag already allows since only PAGE-vs-PAGE relative order is fixed. */
  function moveItem(itemId: string, delta: number) {
    const ids = items.map((i) => i.id);
    const idx = ids.indexOf(itemId);
    const newIdx = idx + delta;
    if (idx === -1 || newIdx < 0 || newIdx >= ids.length) return;
    [ids[idx], ids[newIdx]] = [ids[newIdx], ids[idx]];
    reorderAnnouncement = delta < 0 ? 'Moved up' : 'Moved down';
    onReorder(ids);
  }

  function requestDelete(itemId: string) {
    confirmingDeleteId = itemId;
  }
  /** Closing the inline confirm row puts focus back on the row's delete
   * button (it was unmounted while the row was showing). */
  async function cancelDelete() {
    const itemId = confirmingDeleteId;
    confirmingDeleteId = null;
    if (!itemId) return;
    await tick();
    document.querySelector<HTMLButtonElement>(`[data-delete-item="${CSS.escape(itemId)}"]`)?.focus();
  }
  function focusOnMount(node: HTMLElement) {
    node.focus();
  }
  function confirmDelete(itemId: string) {
    confirmingDeleteId = null;
    onDeleteItem(itemId);
  }
</script>

<aside class="col-span-12 lg:col-span-4 order-2 lg:order-1 space-y-4">
  <div class="rounded-2xl border border-surface-200 dark:border-surface-800 bg-white dark:bg-surface-900 p-5">
    <div class="flex items-center justify-between mb-3">
      <div class="text-lg font-semibold text-surface-900 dark:text-white truncate">{session?.title}</div>
      <ConnectionStatus status={wsStatus} />
    </div>
    <div class="text-xs text-surface-500 font-mono mb-4">{session?.unique_code}</div>
    <button
      onclick={onToggleLive}
      disabled={liveToggleBusy}
      aria-busy={liveToggleBusy}
      class="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed disabled:active:scale-100 {session?.is_live
        ? 'bg-red-500/10 text-red-700 dark:text-red-300 border border-red-500/20 hover:bg-red-500/20'
        : 'bg-gradient-to-r from-brand-600 to-brand-500 hover:from-brand-700 hover:to-brand-600 text-white shadow-lg shadow-brand-500/20'}"
    >
      <Radio class="w-4 h-4" />
      {#if liveToggleBusy}{session?.is_live ? 'Stopping…' : 'Starting…'}{:else}{session?.is_live ? 'Stop session' : 'Start session'}{/if}
    </button>
  </div>

  <div class="rounded-2xl border border-surface-200 dark:border-surface-800 bg-white dark:bg-surface-900 p-5">
    <div class="flex items-center justify-between mb-3">
      <div class="text-sm font-semibold text-surface-900 dark:text-white truncate" title={presentation?.original_file_name}>
        {presentation?.original_file_name || 'Presentation'}
      </div>
      <span class="text-xs text-surface-400">{presentation?.page_count} page{presentation?.page_count === 1 ? '' : 's'}</span>
    </div>
    <div class="flex gap-2">
      <button onclick={onOpenDetails} class="btn-secondary text-xs flex-1 flex items-center justify-center gap-1.5 py-2">
        <Info class="w-3.5 h-3.5" /> Details
      </button>
      <button onclick={onReplaceClick} class="btn-secondary text-xs flex-1 flex items-center justify-center gap-1.5 py-2">
        <Upload class="w-3.5 h-3.5" /> Replace
      </button>
      <button onclick={onRegenerate} class="btn-secondary text-xs flex-1 flex items-center justify-center gap-1.5 py-2">
        <RefreshCw class="w-3.5 h-3.5" /> Regenerate
      </button>
    </div>
  </div>

  <div class="rounded-2xl border border-surface-200 dark:border-surface-800 bg-white dark:bg-surface-900 p-5">
    <div class="flex items-center justify-between mb-3">
      <div class="text-sm font-semibold text-surface-900 dark:text-white">Timeline</div>
      <span class="text-xs text-surface-400">{items.length}</span>
    </div>

    <span class="sr-only" role="status" aria-live="polite">{reorderAnnouncement}</span>

    <div>
      <TimelineInserter position={0} {onInsert} />
      {#each items as item, index (item.id)}
        <div animate:flip={{ duration: 200 }} class="transition-opacity {draggedItemId === item.id ? 'opacity-40' : ''}">
          {#if item.item_type === 'PAGE'}
            <button
              onclick={() => onSelect(item.id)}
              ondragover={(e) => handleDragOver(e, index)}
              ondrop={(e) => handleDrop(e, index)}
              aria-current={item.id === activeItemId ? 'true' : undefined}
              class="w-full flex items-center gap-2.5 p-2 rounded-xl border transition text-left {item.id === activeItemId
                ? 'border-brand-500/60 bg-brand-500/5 dark:bg-brand-500/10 shadow-sm'
                : 'border-surface-200 dark:border-surface-800 hover:border-surface-300 dark:hover:border-surface-700'} {dragOverIndex === index ? 'ring-2 ring-brand-400' : ''}"
            >
              <span class="relative w-16 h-11 flex-shrink-0 rounded-md overflow-hidden border border-surface-200 dark:border-surface-700 bg-surface-100 dark:bg-surface-800">
                {#if !loadedThumbs[item.id]}
                  <span class="absolute inset-0 animate-pulse-live bg-surface-200 dark:bg-surface-700"></span>
                {/if}
                <img
                  src={getPresentationPageThumbnailUrl(presentation.id, item.page.page_number)}
                  alt={`Page ${item.page.page_number}`}
                  loading="lazy"
                  decoding="async"
                  onload={() => (loadedThumbs = { ...loadedThumbs, [item.id]: true })}
                  onerror={() => (loadedThumbs = { ...loadedThumbs, [item.id]: true })}
                  class="w-full h-full object-cover transition-opacity duration-200 {loadedThumbs[item.id] ? 'opacity-100' : 'opacity-0'}"
                />
              </span>
              <span class="text-xs font-medium {item.id === activeItemId ? 'text-brand-700 dark:text-brand-300' : 'text-surface-600 dark:text-surface-400'}">
                Page {item.page.page_number}
              </span>
              {#if item.id === liveItemId}<span class="ml-auto text-[10px] font-semibold uppercase tracking-wider text-brand-600 dark:text-brand-400">Live</span>{/if}
            </button>
          {:else if confirmingDeleteId === item.id}
            <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
            <div
              role="group"
              aria-label="Confirm delete"
              onkeydown={(e) => { if (e.key === 'Escape') { e.stopPropagation(); void cancelDelete(); } }}
              class="flex items-center gap-2 p-2 rounded-xl border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-500/10"
            >
              <span class="text-xs font-medium text-red-700 dark:text-red-300 flex-1">Delete this interaction?</span>
              <button onclick={() => confirmDelete(item.id)} class="text-xs font-semibold px-2 py-1 rounded-lg bg-red-600 text-white hover:bg-red-700 transition-colors">Delete</button>
              <button use:focusOnMount onclick={cancelDelete} class="text-xs font-semibold px-2 py-1 rounded-lg border border-surface-300 dark:border-surface-700 text-surface-600 dark:text-surface-300 hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors">Cancel</button>
            </div>
          {:else}
            {@const meta = metaFor(item)}
            <div
              draggable={true}
              ondragstart={() => handleDragStart(item)}
              ondragend={handleDragEnd}
              ondragover={(e) => handleDragOver(e, index)}
              ondrop={(e) => handleDrop(e, index)}
              aria-current={item.id === activeItemId ? 'true' : undefined}
              class="group flex items-center gap-1 p-2 rounded-xl border transition duration-150 cursor-grab active:cursor-grabbing {item.id === activeItemId
                ? 'border-brand-500/60 shadow-sm ' + meta.ring
                : 'border-surface-200 dark:border-surface-800 hover:border-surface-300 dark:hover:border-surface-700'} {dragOverIndex === index ? 'ring-2 ring-brand-400 scale-[1.01]' : ''}"
            >
              <span class="w-4 h-4 flex items-center justify-center opacity-40 group-hover:opacity-100 transition-opacity text-surface-400 flex-shrink-0">
                <GripVertical class="w-3.5 h-3.5" />
              </span>
              <button onclick={() => onSelect(item.id)} class="flex items-center gap-2 flex-1 min-w-0 text-left rounded-lg">
                <span class="w-2 h-2 rounded-full flex-shrink-0 {meta.dot}"></span>
                <meta.icon class="w-3.5 h-3.5 flex-shrink-0 text-surface-500 dark:text-surface-400" />
                <span class="text-xs font-medium truncate {item.id === activeItemId ? 'text-surface-900 dark:text-white' : 'text-surface-600 dark:text-surface-400'}">
                  {meta.label}
                </span>
                {#if item.id === liveItemId}<span class="text-[10px] font-semibold uppercase tracking-wider text-brand-600 dark:text-brand-400">Live</span>{/if}
              </button>
              <div class="flex items-center opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity flex-shrink-0">
                <button onclick={() => moveItem(item.id, -1)} disabled={index === 0} class="p-1 rounded-md hover:bg-surface-100 dark:hover:bg-surface-800 transition disabled:opacity-30 disabled:pointer-events-none" aria-label="Move up" title="Move up">
                  <ChevronUp class="w-3 h-3 text-surface-400" />
                </button>
                <button onclick={() => moveItem(item.id, 1)} disabled={index === items.length - 1} class="p-1 rounded-md hover:bg-surface-100 dark:hover:bg-surface-800 transition disabled:opacity-30 disabled:pointer-events-none" aria-label="Move down" title="Move down">
                  <ChevronDown class="w-3 h-3 text-surface-400" />
                </button>
                <button onclick={() => onDuplicateItem(item.id)} class="p-1 rounded-md hover:bg-surface-100 dark:hover:bg-surface-800 transition" aria-label="Duplicate interaction" title="Duplicate">
                  <Copy class="w-3 h-3 text-surface-400" />
                </button>
                <button onclick={() => requestDelete(item.id)} data-delete-item={item.id} class="p-1 rounded-md hover:bg-red-50 dark:hover:bg-red-900/20 transition" aria-label="Delete interaction" title="Delete">
                  <Trash2 class="w-3 h-3 text-red-600 dark:text-red-400" />
                </button>
              </div>
            </div>
          {/if}
          <TimelineInserter position={index + 1} {onInsert} highlighted={dragOverIndex === index} />
        </div>
      {/each}
      {#if items.length === 0}
        <div class="flex flex-col items-center gap-2 py-8 text-center">
          <FileText class="w-9 h-9 text-surface-300 dark:text-surface-700" />
          <p class="text-sm font-medium text-surface-500 dark:text-surface-400">No pages yet</p>
          <p class="text-xs text-surface-400 dark:text-surface-500 max-w-[16rem]">Use "Add Interaction" above to insert a Poll, Q&amp;A, Word Cloud, Feedback or Rating item.</p>
        </div>
      {/if}
    </div>
  </div>
</aside>
