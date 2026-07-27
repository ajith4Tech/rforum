<script lang="ts">
  import Modal from '$lib/components/Modal.svelte';
  import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
  import PresentationPreviewDialog from './PresentationPreviewDialog.svelte';
  import { listPresentations, deletePresentation, getPresentationPageThumbnailUrl } from '$lib/api';
  import { Search, Trash2, Inbox } from 'lucide-svelte';

  let {
    eventId,
    onAttach,
    onClose
  }: {
    eventId: string | null | undefined;
    onAttach: (presentationId: string) => Promise<void>;
    onClose: () => void;
  } = $props();

  let presentations: any[] = $state([]);
  let loading = $state(true);
  let error = $state('');
  let search = $state('');
  let sort = $state<'recent' | 'last_used' | 'name'>('recent');
  let previewId: string | null = $state(null);
  let deleteTarget: any = $state(null);
  let deleting = $state(false);

  let searchDebounce: ReturnType<typeof setTimeout> | null = null;

  async function load() {
    loading = true;
    error = '';
    try {
      presentations = await listPresentations({ eventId: eventId ?? undefined, search: search || undefined, sort });
    } catch (e: any) {
      error = e?.message || 'Failed to load presentations';
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    void sort;
    load();
  });

  function handleSearchInput(value: string) {
    search = value;
    if (searchDebounce) clearTimeout(searchDebounce);
    searchDebounce = setTimeout(load, 300);
  }

  function formatDate(iso: string | null) {
    if (!iso) return 'Never';
    return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  }

  async function handleAttachFromPreview(presentationId: string) {
    await onAttach(presentationId);
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    deleting = true;
    try {
      await deletePresentation(deleteTarget.id);
      presentations = presentations.filter((p) => p.id !== deleteTarget.id);
      deleteTarget = null;
    } catch (e: any) {
      error = e?.message || 'Failed to delete presentation';
    } finally {
      deleting = false;
    }
  }
</script>

<Modal open={true} {onClose} maxWidth="max-w-3xl" ariaLabel="Choose an existing presentation">
  <div class="p-6">
    <div class="mb-4 pr-8">
      <h2 class="text-base font-heading font-bold">Choose Existing Presentation</h2>
    </div>

    <div class="flex flex-wrap gap-3 mb-5">
      <div class="relative flex-1 min-w-52">
        <Search class="absolute left-3 top-2.5 w-4 h-4 text-surface-400" />
        <input
          type="text"
          placeholder="Search by filename…"
          value={search}
          oninput={(e) => handleSearchInput((e.currentTarget as HTMLInputElement).value)}
          class="input-field pl-9 text-sm py-2"
        />
      </div>
      <select bind:value={sort} class="input-field text-sm py-2 w-40">
        <option value="recent">Most recent</option>
        <option value="last_used">Last used</option>
        <option value="name">Name (A–Z)</option>
      </select>
    </div>

    {#if error}
      <div class="mb-4 px-3 py-2 rounded-lg bg-danger/10 border border-danger/20 text-danger text-xs">{error}</div>
    {/if}

    {#if loading}
      <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {#each Array(6) as _}
          <div class="rounded-xl border border-surface-200 dark:border-surface-800 p-2 animate-pulse">
            <div class="aspect-video rounded-lg bg-surface-200 dark:bg-surface-800 mb-2"></div>
            <div class="h-3 rounded bg-surface-200 dark:bg-surface-800 w-3/4 mb-1"></div>
            <div class="h-3 rounded bg-surface-200 dark:bg-surface-800 w-1/2"></div>
          </div>
        {/each}
      </div>
    {:else if presentations.length === 0}
      <div class="flex flex-col items-center py-14 gap-3 text-surface-500">
        <Inbox class="w-9 h-9 opacity-30" />
        <p class="text-sm">No existing presentations yet.</p>
        <p class="text-xs text-surface-600 max-w-xs text-center">
          Decks you've uploaded — or that are already attached to a session in this event — will show up here.
        </p>
      </div>
    {:else}
      <div class="grid grid-cols-2 sm:grid-cols-3 gap-3 max-h-[55vh] overflow-y-auto pr-1">
        {#each presentations as p (p.id)}
          <div class="card-interactive group relative rounded-xl border border-surface-200 dark:border-surface-800 p-2 text-left">
            <button onclick={() => (previewId = p.id)} class="w-full text-left">
              <div class="aspect-video rounded-lg overflow-hidden bg-surface-100 dark:bg-surface-800 mb-2">
                <img
                  src={getPresentationPageThumbnailUrl(p.id, 1)}
                  alt={p.original_file_name}
                  loading="lazy"
                  decoding="async"
                  class="w-full h-full object-cover"
                />
              </div>
              <p class="text-xs font-medium truncate" title={p.original_file_name}>{p.original_file_name}</p>
              <p class="text-[11px] text-surface-500">
                {p.page_count} slide{p.page_count === 1 ? '' : 's'} &middot; {formatDate(p.last_used_at)}
              </p>
            </button>
            {#if p.storage_status === 'detached'}
              <button
                onclick={() => (deleteTarget = p)}
                class="absolute top-1.5 right-1.5 p-1.5 rounded-lg bg-surface-950/60 text-white opacity-0 group-hover:opacity-100 hover:bg-danger transition"
                title="Delete this unattached presentation"
                aria-label="Delete presentation"
              >
                <Trash2 class="w-3.5 h-3.5" />
              </button>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  </div>
</Modal>

{#if previewId}
  <PresentationPreviewDialog
    presentationId={previewId}
    onAttach={handleAttachFromPreview}
    onClose={() => (previewId = null)}
  />
{/if}

<ConfirmDialog
  open={!!deleteTarget}
  tone="danger"
  title="Delete this presentation?"
  description="This permanently removes the file and every rendered page. This cannot be undone."
  confirmLabel="Delete"
  loading={deleting}
  onConfirm={confirmDelete}
  onCancel={() => (deleteTarget = null)}
>
  {#if deleteTarget}
    <p class="text-xs text-surface-500 px-4 py-3 rounded-xl bg-surface-50 dark:bg-surface-800/60 break-all">
      {deleteTarget.original_file_name}
    </p>
  {/if}
</ConfirmDialog>
