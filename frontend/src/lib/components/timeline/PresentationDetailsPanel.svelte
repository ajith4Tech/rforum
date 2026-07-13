<script lang="ts">
  import {
    getPresentationDetails,
    downloadPresentationOriginal,
    formatBytes
  } from '$lib/api';
  import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
  import {
    FileText, Download, Link2Off, Trash2, Upload, RefreshCw,
    CheckCircle2, AlertTriangle, Clock, User, HardDrive
  } from 'lucide-svelte';

  let {
    presentationId,
    onReplaceClick,
    onDetach,
    onDelete,
    onDetachSuccess,
    onDeleteSuccess
  }: {
    presentationId: string;
    onReplaceClick: () => void;
    onDetach: () => Promise<void>;
    onDelete: (presentationId: string) => Promise<void>;
    onDetachSuccess?: () => void;
    onDeleteSuccess?: () => void;
  } = $props();

  let details: any = $state(null);
  let loading = $state(true);
  let error = $state('');
  let detaching = $state(false);
  let deleting = $state(false);
  let downloading = $state(false);
  let confirmingDetach = $state(false);
  let confirmingDelete = $state(false);

  async function load() {
    loading = true;
    error = '';
    try {
      details = await getPresentationDetails(presentationId);
    } catch (e: any) {
      error = e?.message || 'Failed to load presentation details';
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    void presentationId;
    load();
  });

  function formatDate(iso: string | null) {
    if (!iso) return 'Never';
    return new Date(iso).toLocaleString('en-GB', {
      day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'
    });
  }

  async function handleConfirmDetach() {
    detaching = true;
    try {
      await onDetach();
      confirmingDetach = false;
      // Re-fetch in place (rather than closing) so storage_status flips to
      // "detached" and Delete becomes actionable without leaving this view —
      // the parent only resets session state once this panel is closed.
      await load();
      onDetachSuccess?.();
    } catch (e: any) {
      error = e?.message || 'Failed to detach presentation';
    } finally {
      detaching = false;
    }
  }

  async function handleConfirmDelete() {
    deleting = true;
    try {
      await onDelete(presentationId);
      confirmingDelete = false;
      onDeleteSuccess?.();
    } catch (e: any) {
      error = e?.message || 'Failed to delete presentation';
      confirmingDelete = false;
    } finally {
      deleting = false;
    }
  }

  async function handleDownload() {
    if (!details) return;
    downloading = true;
    try {
      await downloadPresentationOriginal(presentationId, details.original_file_name);
    } catch (e: any) {
      error = e?.message || 'Failed to download original file';
    } finally {
      downloading = false;
    }
  }

  const conversionLabel = $derived(
    !details ? '' :
    details.status === 'FAILED' ? 'Conversion failed' :
    details.status === 'PENDING' || details.status === 'PROCESSING' ? 'Converting…' :
    details.conversion_warnings?.length ? 'Converted with warnings' : 'Converted cleanly'
  );

  const renderingLabel = $derived(
    !details ? '' : details.status === 'READY' ? 'Pages ready' : details.status === 'FAILED' ? 'Not rendered' : 'Rendering…'
  );
</script>

<div class="p-6">
  <div class="flex items-center gap-3 mb-5">
    <div class="w-10 h-10 flex items-center justify-center rounded-xl bg-brand-500/10 flex-shrink-0">
      <FileText class="w-5 h-5 text-brand-500" />
    </div>
    <div class="min-w-0">
      <h2 class="text-base font-heading font-bold">Presentation Details</h2>
      <p class="text-xs text-surface-500 truncate" title={details?.original_file_name}>
        {details?.original_file_name || '—'}
      </p>
    </div>
  </div>

  {#if loading}
    <div class="space-y-3 animate-pulse" aria-busy="true">
      <div class="h-4 rounded bg-surface-200 dark:bg-surface-800 w-3/4"></div>
      <div class="h-4 rounded bg-surface-200 dark:bg-surface-800 w-1/2"></div>
      <div class="h-4 rounded bg-surface-200 dark:bg-surface-800 w-2/3"></div>
      <div class="h-20 rounded bg-surface-200 dark:bg-surface-800"></div>
    </div>
  {:else if error && !details}
    <div class="text-center py-8 text-danger text-sm">{error}</div>
  {:else if details}
    {#if error}
      <div class="mb-4 px-3 py-2 rounded-lg bg-danger/10 border border-danger/20 text-danger text-xs">{error}</div>
    {/if}

    <div class="grid grid-cols-2 gap-x-4 gap-y-3 mb-5 text-sm">
      <div>
        <p class="text-xs text-surface-500">Slides</p>
        <p class="font-medium">{details.page_count}</p>
      </div>
      <div>
        <p class="text-xs text-surface-500">File size</p>
        <p class="font-medium">{formatBytes(details.original_file_size)}</p>
      </div>
      <div>
        <p class="text-xs text-surface-500 flex items-center gap-1"><Clock class="w-3 h-3" /> Uploaded</p>
        <p class="font-medium">{formatDate(details.created_at)}</p>
      </div>
      <div>
        <p class="text-xs text-surface-500 flex items-center gap-1"><Clock class="w-3 h-3" /> Last used</p>
        <p class="font-medium">{formatDate(details.last_used_at)}</p>
      </div>
      <div>
        <p class="text-xs text-surface-500 flex items-center gap-1"><User class="w-3 h-3" /> Uploaded by</p>
        <p class="font-medium truncate" title={details.owner_email}>{details.owner_email}</p>
      </div>
      <div>
        <p class="text-xs text-surface-500 flex items-center gap-1"><HardDrive class="w-3 h-3" /> Storage status</p>
        <span class="inline-flex items-center gap-1 text-xs font-bold px-2 py-0.5 rounded-full {details.storage_status === 'active' ? 'bg-emerald-500/10 text-emerald-500' : 'bg-surface-200 dark:bg-surface-800 text-surface-500'}">
          {details.storage_status === 'active' ? 'Active' : 'Detached'}
        </span>
      </div>
      <div>
        <p class="text-xs text-surface-500">Conversion status</p>
        <span class="inline-flex items-center gap-1 text-xs font-medium {details.status === 'FAILED' ? 'text-danger' : details.conversion_warnings?.length ? 'text-warning' : 'text-emerald-500'}">
          {#if details.status === 'FAILED'}
            <AlertTriangle class="w-3 h-3" />
          {:else}
            <CheckCircle2 class="w-3 h-3" />
          {/if}
          {conversionLabel}
        </span>
      </div>
      <div>
        <p class="text-xs text-surface-500">Rendering status</p>
        <p class="font-medium">{renderingLabel}</p>
      </div>
    </div>

    {#if details.attached_sessions?.length}
      <div class="mb-5">
        <p class="text-xs text-surface-500 uppercase tracking-widest font-semibold mb-2">
          Used in {details.attached_sessions.length} session{details.attached_sessions.length === 1 ? '' : 's'}
        </p>
        <ul class="space-y-1">
          {#each details.attached_sessions as s (s.id)}
            <li class="text-xs text-surface-500 flex items-center gap-1.5">
              <span class="w-1.5 h-1.5 rounded-full bg-brand-500 flex-shrink-0"></span>
              {s.title} <span class="font-mono text-surface-600">({s.unique_code})</span>
            </li>
          {/each}
        </ul>
      </div>
    {/if}

    <div class="grid grid-cols-2 gap-2">
      <button onclick={onReplaceClick} class="btn-secondary text-xs flex items-center justify-center gap-1.5 py-2">
        <Upload class="w-3.5 h-3.5" /> Replace
      </button>
      <button
        onclick={handleDownload}
        disabled={downloading}
        class="btn-secondary text-xs flex items-center justify-center gap-1.5 py-2 disabled:opacity-50"
      >
        {#if downloading}
          <RefreshCw class="w-3.5 h-3.5 animate-spin" />
        {:else}
          <Download class="w-3.5 h-3.5" />
        {/if}
        Download Original
      </button>
      <button
        onclick={() => (confirmingDetach = true)}
        class="btn-secondary text-xs flex items-center justify-center gap-1.5 py-2"
      >
        <Link2Off class="w-3.5 h-3.5" /> Detach
      </button>
      <button
        onclick={() => (confirmingDelete = true)}
        disabled={details.storage_status === 'active'}
        title={details.storage_status === 'active' ? 'This presentation is still attached to a session — detach it first' : 'Delete permanently'}
        class="text-xs flex items-center justify-center gap-1.5 py-2 rounded-xl font-medium border border-danger/20 bg-danger/10 text-danger transition disabled:opacity-40"
      >
        <Trash2 class="w-3.5 h-3.5" /> Delete
      </button>
    </div>
  {/if}
</div>

<ConfirmDialog
  open={confirmingDetach}
  tone="warning"
  title="Detach this presentation?"
  description="It will be removed from this session, but the file and its rendered pages are kept for reuse."
  confirmLabel="Detach"
  loading={detaching}
  onConfirm={handleConfirmDetach}
  onCancel={() => (confirmingDetach = false)}
>
  <p class="text-xs text-surface-500 px-4 py-3 rounded-xl bg-surface-50 dark:bg-surface-800/60">
    Detaching does not delete any assets and does not affect existing analytics or responses. You can reattach this
    presentation to any session later via "Choose Existing Presentation."
  </p>
</ConfirmDialog>

<ConfirmDialog
  open={confirmingDelete}
  tone="danger"
  title="Delete this presentation?"
  description="This permanently removes the file and every rendered page. This cannot be undone."
  confirmLabel="Delete"
  loading={deleting}
  onConfirm={handleConfirmDelete}
  onCancel={() => (confirmingDelete = false)}
/>
