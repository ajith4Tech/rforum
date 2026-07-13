<script lang="ts">
  import Modal from '$lib/components/Modal.svelte';
  import { getPresentationDetails, getPresentationPageThumbnailUrl, formatBytes } from '$lib/api';
  import { FileText, Clock, User } from 'lucide-svelte';

  let {
    presentationId,
    onAttach,
    onClose
  }: {
    presentationId: string;
    onAttach: (presentationId: string) => Promise<void>;
    onClose: () => void;
  } = $props();

  let details: any = $state(null);
  let loading = $state(true);
  let error = $state('');
  let attaching = $state(false);

  $effect(() => {
    const id = presentationId;
    loading = true;
    error = '';
    getPresentationDetails(id)
      .then((d) => { details = d; })
      .catch((e: any) => { error = e?.message || 'Failed to load presentation'; })
      .finally(() => { loading = false; });
  });

  function formatDate(iso: string | null) {
    if (!iso) return 'Never';
    return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  }

  async function handleUse() {
    attaching = true;
    error = '';
    try {
      await onAttach(presentationId);
    } catch (e: any) {
      error = e?.message || 'Failed to attach presentation';
    } finally {
      attaching = false;
    }
  }
</script>

<Modal open={true} {onClose} maxWidth="max-w-xl" ariaLabel="Preview presentation">
  <div class="p-6">
    {#if loading}
      <div class="space-y-3 animate-pulse" aria-busy="true">
        <div class="h-24 rounded bg-surface-200 dark:bg-surface-800"></div>
        <div class="h-4 rounded bg-surface-200 dark:bg-surface-800 w-2/3"></div>
        <div class="h-4 rounded bg-surface-200 dark:bg-surface-800 w-1/2"></div>
      </div>
    {:else if error && !details}
      <div class="text-center py-8 text-danger text-sm">{error}</div>
    {:else if details}
      <div class="flex items-center gap-3 mb-4">
        <div class="w-10 h-10 flex items-center justify-center rounded-xl bg-brand-500/10 flex-shrink-0">
          <FileText class="w-5 h-5 text-brand-500" />
        </div>
        <div class="min-w-0">
          <h2 class="text-base font-heading font-bold truncate" title={details.original_file_name}>{details.original_file_name}</h2>
          <p class="text-xs text-surface-500">{details.page_count} slide{details.page_count === 1 ? '' : 's'} &middot; {formatBytes(details.original_file_size)}</p>
        </div>
      </div>

      {#if details.page_count > 0}
        <div class="flex gap-2 overflow-x-auto pb-2 mb-4 -mx-1 px-1">
          {#each Array(details.page_count) as _, i}
            <img
              src={getPresentationPageThumbnailUrl(details.id, i + 1)}
              alt={`Slide ${i + 1}`}
              loading="lazy"
              decoding="async"
              class="w-24 h-16 object-cover rounded-lg border border-surface-200 dark:border-surface-800 flex-shrink-0 bg-surface-100 dark:bg-surface-800"
            />
          {/each}
        </div>
      {/if}

      <div class="grid grid-cols-2 gap-x-4 gap-y-2 text-xs mb-5">
        <div class="flex items-center gap-1.5 text-surface-500"><Clock class="w-3 h-3" /> Uploaded {formatDate(details.created_at)}</div>
        <div class="flex items-center gap-1.5 text-surface-500"><Clock class="w-3 h-3" /> Last used {formatDate(details.last_used_at)}</div>
        <div class="flex items-center gap-1.5 text-surface-500 col-span-2"><User class="w-3 h-3" /> {details.owner_email}</div>
      </div>

      {#if error}
        <p class="text-xs text-danger mb-3" role="alert">{error}</p>
      {/if}

      <div class="flex gap-3">
        <button onclick={onClose} class="btn-secondary flex-1 text-sm">Cancel</button>
        <button onclick={handleUse} disabled={attaching} class="btn-primary flex-1 text-sm disabled:opacity-50">
          {attaching ? 'Attaching…' : 'Use this presentation'}
        </button>
      </div>
    {/if}
  </div>
</Modal>
