<script lang="ts">
  import { getPresentationPageImageUrl } from '$lib/api';
  import Modal from '$lib/components/Modal.svelte';
  import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
  import PresentationDetailsPanel from './PresentationDetailsPanel.svelte';
  import InteractionView from './InteractionView.svelte';
  import TimelineSidebar from './TimelineSidebar.svelte';
  import PresentationLiveView from './PresentationLiveView.svelte';
  import { metaForItem } from '$lib/timelineTypes';
  import { Eye, Pencil, Check, Loader2, Undo2, Redo2, Maximize, Minimize } from 'lucide-svelte';
  import type { ConnectionStatus as WsStatus } from '$lib/ws';
  import ZoomableImageViewer from '$lib/components/ZoomableImageViewer.svelte';

  let {
    session,
    presentation,
    timeline,
    responses = [],
    wsStatus = 'disconnected' as WsStatus,
    saveState = 'idle' as 'idle' | 'saving' | 'saved',
    canUndo = false,
    canRedo = false,
    onToggleLive,
    onActivateItem,
    onSelectItem,
    onNavigate,
    onInsertItem,
    onUpdateItemContent,
    onDeleteItem,
    onDuplicateItem,
    onReorderItems,
    onReplace,
    onRegenerate,
    onDetach,
    onDeletePresentation,
    onDetailsClosedAfterChange,
    onDirtyChange,
    onUndo,
    onRedo
  }: {
    session: any;
    presentation: any;
    timeline: any;
    responses?: any[];
    wsStatus?: WsStatus;
    saveState?: 'idle' | 'saving' | 'saved';
    canUndo?: boolean;
    canRedo?: boolean;
    onToggleLive: () => void;
    onActivateItem: (itemId: string) => void;
    onSelectItem?: (itemId: string) => void;
    onNavigate: (direction: 'prev' | 'next') => void;
    onInsertItem: (itemType: string, position: number) => void;
    onUpdateItemContent: (itemId: string, contentJson: Record<string, unknown>) => void;
    onDeleteItem: (itemId: string) => void;
    onDuplicateItem: (itemId: string) => void;
    onReorderItems: (itemIds: string[]) => void;
    onReplace: (file: File) => void;
    onRegenerate: () => void;
    onDetach: () => Promise<void>;
    onDeletePresentation: (presentationId: string) => Promise<void>;
    onDetailsClosedAfterChange: () => void;
    onDirtyChange?: (dirty: boolean) => void;
    onUndo?: () => void;
    onRedo?: () => void;
  } = $props();

  let workspaceEl: HTMLDivElement | null = $state(null);
  let isFullscreen = $state(false);

  function toggleFullscreen() {
    if (!workspaceEl) return;
    if (!document.fullscreenElement) {
      workspaceEl.requestFullscreen?.().catch(() => {});
    } else {
      document.exitFullscreen?.().catch(() => {});
    }
  }

  $effect(() => {
    function onFsChange() { isFullscreen = document.fullscreenElement === workspaceEl; }
    document.addEventListener('fullscreenchange', onFsChange);
    return () => document.removeEventListener('fullscreenchange', onFsChange);
  });

  const sortedItems = $derived([...(timeline?.items || [])].sort((a: any, b: any) => a.order - b.order));
  const liveItemId = $derived(timeline?.active_timeline_item_id ?? null);
  let selectedItemId = $state<string | null>(null);
  $effect(() => {
    if (!selectedItemId && (liveItemId || sortedItems[0]?.id)) {
      selectedItemId = liveItemId || sortedItems[0].id;
    }
  });
  $effect(() => {
    if (selectedItemId && !sortedItems.some((i: any) => i.id === selectedItemId)) {
      selectedItemId = liveItemId || sortedItems[0]?.id || null;
    }
  });
  const selectedItem = $derived(sortedItems.find((i: any) => i.id === selectedItemId) || null);
  const activeItem = $derived(selectedItem);
  const activeIndex = $derived(activeItem ? sortedItems.findIndex((i: any) => i.id === activeItem.id) : -1);
  const activeMeta = $derived(activeItem ? metaForItem(activeItem) : null);

  function selectItem(itemId: string) {
    selectedItemId = itemId;
    onSelectItem?.(itemId);
  }

  function presentSelected() {
    if (selectedItemId) onActivateItem(selectedItemId);
  }

  let editingItemId: string | null = $state(null);
  let replaceInputEl: HTMLInputElement | null = $state(null);
  let previewVariant: 'guest' | 'screen' | null = $state(null);
  let pageImageLoaded = $state(false);
  let pageImageErrored = $state(false);
  let detailsOpen = $state(false);
  let detachedWhileDetailsOpen = $state(false);
  let confirmingReplaceFile: File | null = $state(null);

  function handleReplaceFileChange(e: Event) {
    const files = (e.currentTarget as HTMLInputElement).files;
    if (files && files.length > 0) {
      confirmingReplaceFile = files[0];
    }
    (e.currentTarget as HTMLInputElement).value = '';
  }

  function confirmReplace() {
    if (confirmingReplaceFile) onReplace(confirmingReplaceFile);
    confirmingReplaceFile = null;
  }

  function openDetails() {
    detachedWhileDetailsOpen = false;
    detailsOpen = true;
  }

  function closeDetails() {
    detailsOpen = false;
    if (detachedWhileDetailsOpen) onDetailsClosedAfterChange();
  }

  function togglePreview(variant: 'guest' | 'screen') {
    previewVariant = previewVariant === variant ? null : variant;
  }

  function requestDeleteActive() {
    // Mirror the sidebar's confirm-before-delete gate — Delete/Backspace
    // must not remove an interaction with fewer steps than the mouse path.
    if (activeItem && activeItem.item_type !== 'PAGE' && confirm(`Delete this ${activeMeta?.label ?? 'interaction'}?`)) {
      onDeleteItem(activeItem.id);
    }
  }

  $effect(() => {
    void activeItem?.id; // re-run (and reset the skeleton) whenever the active item changes
    pageImageLoaded = false;
    pageImageErrored = false;
  });

  $effect(() => {
    const items = sortedItems;
    const currentId = selectedItemId;
    function onKeydown(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      const isTyping = target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable);
      if (isTyping || previewVariant) return;

      if (e.key === 'ArrowLeft') {
        e.preventDefault();
        const ids = items.map((i: any) => i.id);
        const idx = ids.indexOf(currentId || '');
        if (idx > 0) selectItem(ids[idx - 1]);
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        const ids = items.map((i: any) => i.id);
        const idx = ids.indexOf(currentId || '');
        if (idx >= 0 && idx < ids.length - 1) selectItem(ids[idx + 1]);
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        // Every mutation already persists immediately — this is pure feedback,
        // it doesn't trigger a new save. Preventing default just stops the
        // browser's "Save Page" dialog from popping up.
        e.preventDefault();
      } else if (e.key === 'Delete' || e.key === 'Backspace') {
        if (editingItemId) return;
        requestDeleteActive();
      }
    }
    window.addEventListener('keydown', onKeydown);
    return () => window.removeEventListener('keydown', onKeydown);
  });
</script>

<input
  bind:this={replaceInputEl}
  type="file"
  accept=".pdf,.ppt,.pptx"
  class="hidden"
  onchange={handleReplaceFileChange}
/>

<div
  bind:this={workspaceEl}
  class="grid grid-cols-12 gap-5 {isFullscreen ? 'h-screen overflow-y-auto bg-surface-50 dark:bg-surface-950 p-4 sm:p-6' : ''}"
>
  <TimelineSidebar
    {session}
    {presentation}
    {timeline}
    activeItemId={selectedItemId}
    liveItemId={liveItemId}
    {wsStatus}
    {onToggleLive}
    onSelect={selectItem}
    onInsert={onInsertItem}
    {onDeleteItem}
    {onDuplicateItem}
    onReorder={onReorderItems}
    onReplaceClick={() => replaceInputEl?.click()}
    {onRegenerate}
    onOpenDetails={openDetails}
  />

  <section class="col-span-12 lg:col-span-8 order-1 lg:order-2">
    {#if !activeItem}
      <div class="card text-center text-surface-400 py-20">Select a page or interaction to get started.</div>
    {:else}
      <div class="sticky top-0 z-10 -mx-1 px-1 py-2 mb-3 flex flex-wrap items-center gap-2 bg-surface-50/90 dark:bg-surface-950/90 backdrop-blur supports-[backdrop-filter]:bg-surface-50/70 dark:supports-[backdrop-filter]:bg-surface-950/70">
        <button onclick={() => { const ids = sortedItems.map((i: any) => i.id); const idx = ids.indexOf(selectedItemId || ''); if (idx > 0) selectItem(ids[idx - 1]); }} class="btn-secondary text-sm" aria-label="Previous item">Previous</button>
        <button onclick={() => { const ids = sortedItems.map((i: any) => i.id); const idx = ids.indexOf(selectedItemId || ''); if (idx >= 0 && idx < ids.length - 1) selectItem(ids[idx + 1]); }} class="btn-secondary text-sm" aria-label="Next item">Next</button>
        <button onclick={presentSelected} class="btn-primary text-sm" disabled={!selectedItemId}>Present</button>

        {#if activeMeta}
          <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold {activeMeta.ring}">
            <activeMeta.icon class="w-3.5 h-3.5" />
            {activeItem.item_type === 'PAGE' ? `Page ${activeItem.page.page_number}` : activeMeta.label}
          </span>
        {/if}

        <span class="text-xs text-surface-400 tabular-nums">{activeIndex + 1} of {sortedItems.length}</span>

        <div class="ml-auto flex items-center gap-2">
          {#if saveState !== 'idle'}
            <span class="flex items-center gap-1.5 text-xs text-surface-400" role="status" aria-live="polite">
              {#if saveState === 'saving'}
                <Loader2 class="w-3.5 h-3.5 animate-spin" /> Saving…
              {:else}
                <Check class="w-3.5 h-3.5 text-emerald-500" /> Saved
              {/if}
            </span>
          {/if}

          {#if onUndo && onRedo}
            <div class="flex items-center rounded-lg border border-surface-200 dark:border-surface-800 overflow-hidden">
              <button onclick={onUndo} disabled={!canUndo} class="p-1.5 text-surface-500 hover:bg-surface-100 dark:hover:bg-surface-800 transition disabled:opacity-30 disabled:pointer-events-none" aria-label="Undo" title="Undo (Ctrl+Z)">
                <Undo2 class="w-3.5 h-3.5" />
              </button>
              <button onclick={onRedo} disabled={!canRedo} class="p-1.5 border-l border-surface-200 dark:border-surface-800 text-surface-500 hover:bg-surface-100 dark:hover:bg-surface-800 transition disabled:opacity-30 disabled:pointer-events-none" aria-label="Redo" title="Redo (Ctrl+Shift+Z)">
                <Redo2 class="w-3.5 h-3.5" />
              </button>
            </div>
          {/if}

          <button
            onclick={toggleFullscreen}
            class="p-1.5 rounded-lg border border-surface-200 dark:border-surface-800 text-surface-500 hover:bg-surface-100 dark:hover:bg-surface-800 transition"
            aria-label={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
            title={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
          >
            {#if isFullscreen}<Minimize class="w-3.5 h-3.5" />{:else}<Maximize class="w-3.5 h-3.5" />{/if}
          </button>

          <div class="flex items-center rounded-lg border border-surface-200 dark:border-surface-800 overflow-hidden text-xs font-medium">
            <button
              onclick={() => (previewVariant = null)}
              aria-pressed={previewVariant === null}
              class="px-2.5 py-1.5 flex items-center gap-1 transition {previewVariant === null ? 'bg-brand-500 text-white' : 'text-surface-500 hover:bg-surface-100 dark:hover:bg-surface-800'}"
            >
              <Pencil class="w-3.5 h-3.5" /> Editor
            </button>
            <button
              onclick={() => togglePreview('guest')}
              aria-pressed={previewVariant === 'guest'}
              class="px-2.5 py-1.5 flex items-center gap-1 border-l border-surface-200 dark:border-surface-800 transition {previewVariant === 'guest' ? 'bg-brand-500 text-white' : 'text-surface-500 hover:bg-surface-100 dark:hover:bg-surface-800'}"
            >
              <Eye class="w-3.5 h-3.5" /> Guest
            </button>
            <button
              onclick={() => togglePreview('screen')}
              aria-pressed={previewVariant === 'screen'}
              class="px-2.5 py-1.5 flex items-center gap-1 border-l border-surface-200 dark:border-surface-800 transition {previewVariant === 'screen' ? 'bg-brand-500 text-white' : 'text-surface-500 hover:bg-surface-100 dark:hover:bg-surface-800'}"
            >
              <Eye class="w-3.5 h-3.5" /> Screen
            </button>
          </div>
        </div>
      </div>

      {#if previewVariant}
        <div class="card p-4 sm:p-5">
          <PresentationLiveView
            {activeItem}
            presentationId={presentation.id}
            sessionId={session?.id}
            sessionCode={session?.unique_code || ''}
            {responses}
            variant={previewVariant}
            readOnly
          />
        </div>
      {:else if activeItem.item_type === 'PAGE'}
        <div class="card p-4 sm:p-5">
          <div class="text-lg font-semibold mb-3">Page {activeItem.page.page_number}</div>
          <div class="overflow-x-auto relative">
            {#if pageImageErrored}
              <div class="max-h-[500px] aspect-[4/3] rounded-xl bg-surface-100 dark:bg-surface-900 border border-surface-200 dark:border-surface-800 mx-auto flex flex-col items-center justify-center gap-2 text-sm text-surface-500 dark:text-surface-400">
                <span>Couldn't load this page.</span>
                <button
                  type="button"
                  class="text-brand-600 dark:text-brand-400 font-medium hover:underline"
                  onclick={() => { pageImageLoaded = false; pageImageErrored = false; }}
                >
                  Retry
                </button>
              </div>
            {:else}
              {#if !pageImageLoaded}
                <div class="max-h-[500px] aspect-[4/3] rounded-xl bg-surface-200 dark:bg-surface-800 animate-pulse-live mx-auto"></div>
              {/if}
              <div class={pageImageLoaded ? '' : 'hidden'}>
                <ZoomableImageViewer
                  src={getPresentationPageImageUrl(presentation.id, activeItem.page.page_number)}
                  page={activeItem.page.page_number}
                  alt={`Page ${activeItem.page.page_number}`}
                  imgClass="rounded-xl border border-surface-200 mx-auto"
                  onLoad={() => (pageImageLoaded = true)}
                  onError={() => { pageImageErrored = true; }}
                />
              </div>
            {/if}
          </div>
        </div>
      {:else}
        {#key activeItem.id}
          <InteractionView
            slide={activeItem.slide}
            {responses}
            variant="moderator"
            editing={editingItemId === activeItem.id}
            onToggleEdit={() => (editingItemId = editingItemId === activeItem.id ? null : activeItem.id)}
            onSaveContent={(cj) => onUpdateItemContent(activeItem.id, cj)}
            {onDirtyChange}
          />
        {/key}
      {/if}
    {/if}
  </section>
</div>

<Modal open={detailsOpen} onClose={closeDetails} ariaLabel="Presentation details" maxWidth="max-w-lg">
  <PresentationDetailsPanel
    presentationId={presentation.id}
    onReplaceClick={() => { detailsOpen = false; replaceInputEl?.click(); }}
    {onDetach}
    onDelete={onDeletePresentation}
    onDetachSuccess={() => (detachedWhileDetailsOpen = true)}
    onDeleteSuccess={() => { detailsOpen = false; onDetailsClosedAfterChange(); }}
  />
</Modal>

<ConfirmDialog
  open={!!confirmingReplaceFile}
  tone="warning"
  title="Replace this presentation?"
  description="All pages are regenerated from the new file. Your existing interactions are kept and repositioned."
  confirmLabel="Replace"
  onConfirm={confirmReplace}
  onCancel={() => (confirmingReplaceFile = null)}
/>
