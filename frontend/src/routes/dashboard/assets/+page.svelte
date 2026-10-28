<script lang="ts">
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import {
    listAssets,
    getStorageUsage,
    replaceAssetFile,
    deleteAsset,
    downloadPresentationOriginal,
    formatBytes,
    isAuthenticated,
    isAuthFailure
  } from '$lib/api';
  import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
  import {
    HardDrive,
    Search,
    Upload,
    Trash2,
    RefreshCw,
    Download,
    AlertTriangle,
    X,
    Layers
  } from 'lucide-svelte';

  interface Asset {
    id: string;
    user_id: string;
    session_id: string | null;
    event_id: string | null;
    slide_id: string | null;
    presentation_id: string | null;
    file_name: string;
    file_url: string;
    file_type: string;
    file_size: number;
    uploaded_at: string;
    session_title: string | null;
    event_title: string | null;
  }

  let assets: Asset[] = $state([]);
  let loading = $state(true);
  let error = $state('');
  let storageBytes = $state(0);
  let assetCount = $state(0);

  let searchQuery = $state('');
  let filterContext = $state<'all' | 'session' | 'event' | 'unlinked'>('all');

  let uploadingId = $state<string | null>(null);
  let downloadingId = $state<string | null>(null);
  let deleting = $state(false);
  let deleteError = $state('');
  let actionError = $state('');
  let deleteTarget = $state<Asset | null>(null);

  async function load() {
    loading = true;
    error = '';
    try {
      const [assetsResult, storageResult] = await Promise.all([listAssets(), getStorageUsage()]);
      assets = assetsResult as Asset[];
      storageBytes = (storageResult as any).total_bytes ?? 0;
      assetCount = (storageResult as any).asset_count ?? 0;
    } catch (e: any) {
      if (isAuthFailure(e)) { goto('/login'); return; }
      error = e?.message || 'Failed to load assets';
    } finally {
      loading = false;
    }
  }

  onMount(async () => {
    if (!isAuthenticated()) { goto('/login'); return; }
    await load();
  });

  const filteredAssets = $derived(assets.filter(a => {
    const matchSearch = !searchQuery
      || a.file_name.toLowerCase().includes(searchQuery.toLowerCase())
      || (a.session_title ?? '').toLowerCase().includes(searchQuery.toLowerCase())
      || (a.event_title ?? '').toLowerCase().includes(searchQuery.toLowerCase());
    const matchContext = filterContext === 'all'
      || (filterContext === 'session' && a.session_id !== null)
      || (filterContext === 'event' && a.event_id !== null && a.session_id === null)
      || (filterContext === 'unlinked' && !a.session_id && !a.event_id);
    return matchSearch && matchContext;
  }));

  // Rows that look like duplicates are usually not: a Presentation's original
  // file gets one asset record per session it is attached to (and another on
  // every re-attach), all pointing at the same stored file (same file_url).
  // Different uploads of a same-named file have different file_urls. Count
  // records per stored file so shared ones can be labelled — never merged or
  // deleted based on appearance.
  const usesByFile = $derived.by(() => {
    const counts = new Map<string, number>();
    for (const a of assets) counts.set(a.file_url, (counts.get(a.file_url) ?? 0) + 1);
    return counts;
  });
  const namesSeen = $derived.by(() => {
    const counts = new Map<string, number>();
    for (const a of assets) counts.set(a.file_name, (counts.get(a.file_name) ?? 0) + 1);
    return counts;
  });

  function fileTypeBadge(ct: string = ''): string {
    if (ct.includes('pdf')) return 'PDF';
    if (ct.includes('presentationml') || ct.includes('pptx')) return 'PPTX';
    if (ct.includes('powerpoint') || ct.includes('ppt')) return 'PPT';
    if (ct.includes('msword') || ct.includes('docx')) return 'DOCX';
    if (ct.includes('plain')) return 'TXT';
    return (ct.split('/').pop() ?? 'FILE').toUpperCase().slice(0, 6) || 'FILE';
  }

  function fileTypeBadgeClass(ct: string = ''): string {
    if (ct.includes('pdf')) return 'bg-red-500/10 text-red-700 dark:text-red-300';
    if (ct.includes('presentation') || ct.includes('ppt')) return 'bg-amber-500/10 text-amber-700 dark:text-amber-300';
    if (ct.includes('word') || ct.includes('doc')) return 'bg-accent-500/10 text-accent-600 dark:text-accent-400';
    return 'bg-surface-100 dark:bg-surface-800 text-surface-600 dark:text-surface-400';
  }

  async function handleReplace(asset: Asset) {
    if (asset.presentation_id) {
      actionError = 'This file is a Presentation original — use "Replace" inside the Presentation Builder instead.';
      return;
    }
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.pdf,.ppt,.pptx,.doc,.docx,.txt,.odp,.odt';
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      uploadingId = asset.id;
      actionError = '';
      try {
        const updated = await replaceAssetFile(asset.id, file);
        assets = assets.map(a => a.id === asset.id ? { ...a, ...updated } : a);
        const s = await getStorageUsage();
        storageBytes = (s as any).total_bytes ?? 0;
      } catch (e: any) {
        actionError = e?.message || 'Failed to replace file';
      } finally {
        uploadingId = null;
      }
    };
    input.click();
  }

  async function handleDownload(asset: Asset) {
    if (!asset.presentation_id) return;
    downloadingId = asset.id;
    actionError = '';
    try {
      await downloadPresentationOriginal(asset.presentation_id, asset.file_name);
    } catch (e: any) {
      actionError = e?.message || 'Failed to download file';
    } finally {
      downloadingId = null;
    }
  }

  function requestDelete(asset: Asset) {
    if (asset.presentation_id) return;
    deleteError = '';
    actionError = '';
    deleteTarget = asset;
  }

  async function confirmDelete() {
    const target = deleteTarget;
    if (!target || target.presentation_id) return;
    deleting = true;
    deleteError = '';
    try {
      await deleteAsset(target.id);
      assets = assets.filter(a => a.id !== target.id);
      assetCount = Math.max(0, assetCount - 1);
      deleteTarget = null;
    } catch (e: any) {
      deleteError = e?.message || 'Failed to delete asset';
      return;
    } finally {
      deleting = false;
    }
    // The delete succeeded — a failed storage refresh shouldn't read as a failed delete.
    try {
      const s = await getStorageUsage();
      storageBytes = (s as any).total_bytes ?? 0;
    } catch { /* keep the previous figure */ }
  }

  function formatDate(iso: string) {
    return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  }

  function formatTime(iso: string) {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  const STORAGE_CAP_BYTES = 500 * 1024 * 1024;
  const storagePct = $derived(Math.min((storageBytes / STORAGE_CAP_BYTES) * 100, 100));
  const storageBarColor = $derived(
    storagePct > 80 ? 'bg-danger' : storagePct > 50 ? 'bg-warning' : 'bg-brand-500'
  );

  const iconButton = 'p-1.5 rounded-lg text-surface-500 transition-colors disabled:opacity-40 disabled:cursor-not-allowed';
</script>

<svelte:head>
  <title>Session Assets – Rforum</title>
</svelte:head>

<main class="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-6 sm:py-8">

  <!-- Header -->
  <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
    <div class="flex items-center gap-3">
      <div class="w-10 h-10 flex items-center justify-center rounded-xl bg-warning/10 flex-shrink-0">
        <HardDrive class="w-5 h-5 text-warning" />
      </div>
      <div>
        <h1 class="text-3xl font-heading font-bold tracking-wide">Session Assets</h1>
        <p class="text-sm text-surface-500 mt-1">Manage all files uploaded across your sessions and events.</p>
      </div>
    </div>
    <button onclick={load} disabled={loading} aria-busy={loading} class="btn-secondary flex items-center justify-center gap-2 text-sm">
      <RefreshCw class="w-4 h-4 {loading ? 'animate-spin' : ''}" />
      Refresh
    </button>
  </div>

  <!-- Storage summary card -->
  <div class="card mb-6">
    <div class="flex items-center justify-between mb-3">
      <div>
        <p class="text-xs text-surface-500 uppercase tracking-widest font-semibold">Storage Used</p>
        <p class="text-2xl font-heading font-bold mt-1">{loading && !assets.length ? '—' : formatBytes(storageBytes)}</p>
      </div>
      <div class="text-right">
        <p class="text-sm font-semibold">{assetCount}</p>
        <p class="text-xs text-surface-500">file record{assetCount !== 1 ? 's' : ''}</p>
      </div>
    </div>
    <div
      class="w-full h-2 rounded-full bg-surface-100 dark:bg-surface-800 overflow-hidden"
      role="progressbar"
      aria-label="Storage used of 500 MB reference quota"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(storagePct)}
    >
      <div class="h-full rounded-full transition-[width] duration-500 {storageBarColor}" style="width:{storagePct}%"></div>
    </div>
    <p class="text-xs text-surface-500 mt-2">Reference quota: 500 MB</p>
  </div>

  {#if actionError}
    <div class="mb-4 px-4 py-3 rounded-xl bg-danger/10 border border-danger/20 text-red-700 dark:text-red-300 text-sm flex items-start gap-2" role="alert">
      <AlertTriangle class="w-4 h-4 flex-shrink-0 mt-0.5" />
      <span class="flex-1 min-w-0 break-words">{actionError}</span>
      <button onclick={() => actionError = ''} class="text-xs underline flex-shrink-0">Dismiss</button>
    </div>
  {/if}

  <!-- Filters -->
  <div class="flex flex-col sm:flex-row gap-3 sm:items-center mb-4">
    <div class="relative flex-1">
      <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-surface-500 pointer-events-none" />
      <input
        type="search"
        placeholder="Search by file, session or event name…"
        aria-label="Search assets"
        bind:value={searchQuery}
        class="input-field pl-9 text-sm py-2"
      />
    </div>
    <div class="flex items-center gap-3">
      <select bind:value={filterContext} aria-label="Filter by where the file is used" class="input-field text-sm py-2 sm:w-44">
        <option value="all">All files</option>
        <option value="session">Session files</option>
        <option value="event">Event files</option>
        <option value="unlinked">Unlinked</option>
      </select>
      {#if searchQuery || filterContext !== 'all'}
        <button onclick={() => { searchQuery = ''; filterContext = 'all'; }} class="btn-ghost text-xs flex items-center gap-1 flex-shrink-0">
          <X class="w-3.5 h-3.5" /> Clear
        </button>
      {/if}
    </div>
  </div>

  {#if loading && !assets.length}
    <div class="card p-0 overflow-hidden" aria-busy="true" aria-label="Loading assets">
      {#each Array(4) as _}
        <div class="flex items-center gap-3 px-4 py-3 border-b last:border-b-0 border-surface-100 dark:border-surface-800">
          <div class="skeleton h-6 w-12 rounded"></div>
          <div class="flex-1 space-y-2">
            <div class="skeleton h-3.5 w-1/3 rounded"></div>
            <div class="skeleton h-3 w-1/4 rounded"></div>
          </div>
        </div>
      {/each}
    </div>

  {:else if error}
    <div class="card flex flex-col items-center text-center py-12 gap-3" role="alert">
      <AlertTriangle class="w-8 h-8 text-danger" />
      <p class="text-sm font-medium">Couldn't load your files</p>
      <p class="text-xs text-surface-500 max-w-sm break-words">{error}</p>
      <button onclick={load} class="btn-secondary text-sm flex items-center gap-2">
        <RefreshCw class="w-4 h-4" /> Try again
      </button>
    </div>

  {:else if assets.length === 0}
    <div class="card flex flex-col items-center py-12 gap-3 text-surface-500 text-center">
      <HardDrive class="w-10 h-10 opacity-40" />
      <p class="text-sm">No uploaded files yet.</p>
      <p class="text-xs max-w-xs">
        Files are tracked automatically when you upload a slide via a session.
      </p>
      <a href="/dashboard/sessions" class="btn-primary text-sm mt-1">Go to Sessions</a>
    </div>

  {:else if filteredAssets.length === 0}
    <div class="card text-center py-12 text-sm text-surface-500">No assets match your filters.</div>

  {:else}
    <p class="text-xs text-surface-500 uppercase tracking-widest font-semibold mb-3">
      {filteredAssets.length} file{filteredAssets.length !== 1 ? 's' : ''}
      {#if filteredAssets.length !== assets.length}· filtered from {assets.length}{/if}
    </p>

    <div class="card overflow-hidden p-0">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-surface-200 dark:border-surface-800 bg-surface-50 dark:bg-surface-900/50">
              <th scope="col" class="px-4 py-3 text-left font-semibold text-surface-500 text-xs uppercase tracking-wide">File</th>
              <th scope="col" class="px-4 py-3 text-left font-semibold text-surface-500 text-xs uppercase tracking-wide hidden md:table-cell">Used in</th>
              <th scope="col" class="px-4 py-3 text-left font-semibold text-surface-500 text-xs uppercase tracking-wide hidden sm:table-cell">Size</th>
              <th scope="col" class="px-4 py-3 text-left font-semibold text-surface-500 text-xs uppercase tracking-wide hidden sm:table-cell">Uploaded</th>
              <th scope="col" class="px-4 py-3 text-right font-semibold text-surface-500 text-xs uppercase tracking-wide"><span class="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            {#each filteredAssets as asset (asset.id)}
              {@const uses = usesByFile.get(asset.file_url) ?? 1}
              {@const sameName = (namesSeen.get(asset.file_name) ?? 1) > 1}
              <tr class="border-b last:border-b-0 border-surface-100 dark:border-surface-800/60 hover:bg-surface-50 dark:hover:bg-surface-800/30 transition-colors">

                <td class="px-4 py-3 align-top">
                  <div class="flex items-start gap-3 min-w-0">
                    <span class="text-[11px] font-bold px-1.5 py-0.5 rounded flex-shrink-0 mt-0.5 min-w-[2.75rem] text-center {fileTypeBadgeClass(asset.file_type)}" title={asset.file_type || 'Unknown type'}>
                      {fileTypeBadge(asset.file_type)}
                    </span>
                    <div class="min-w-0">
                      <div class="flex items-center gap-2 flex-wrap">
                        <span class="font-medium break-all sm:break-normal sm:truncate sm:max-w-72" title={asset.file_name}>{asset.file_name}</span>
                        {#if asset.presentation_id}
                          <span class="text-[10px] px-1.5 py-0.5 rounded bg-brand-500/10 text-brand-700 dark:text-brand-300 font-bold flex-shrink-0" title="Presentation original — replace or delete it from the Presentation Builder">Presentation</span>
                        {/if}
                        {#if uses > 1}
                          <span
                            class="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-surface-100 dark:bg-surface-800 text-surface-600 dark:text-surface-400 font-semibold flex-shrink-0"
                            title="The same stored file is recorded once per session it was attached to. These rows are not separate copies."
                          >
                            <Layers class="w-3 h-3" /> Same file · {uses} records
                          </span>
                        {/if}
                      </div>
                      <!-- Context + metadata repeated here on narrow screens where those columns are hidden -->
                      <p class="text-xs text-surface-500 mt-0.5 md:hidden truncate">
                        {#if asset.session_id && asset.session_title}
                          Session: <a href="/dashboard/{asset.session_id}" class="text-brand-600 dark:text-brand-400 hover:underline">{asset.session_title}</a>
                        {:else if asset.event_id && asset.event_title}
                          Event: <a href="/dashboard/events?event={asset.event_id}" class="text-brand-600 dark:text-brand-400 hover:underline">{asset.event_title}</a>
                        {:else}Unlinked{/if}
                      </p>
                      <p class="text-xs text-surface-500 mt-0.5 sm:hidden">
                        {formatBytes(asset.file_size)} · {formatDate(asset.uploaded_at)}{sameName ? `, ${formatTime(asset.uploaded_at)}` : ''}
                      </p>
                    </div>
                  </div>
                </td>

                <td class="px-4 py-3 align-top text-xs max-w-56 hidden md:table-cell">
                  {#if asset.session_id && asset.session_title}
                    <a href="/dashboard/{asset.session_id}" class="inline-flex items-center gap-1.5 max-w-full text-surface-700 dark:text-surface-300 hover:text-brand-600 dark:hover:text-brand-400 hover:underline" title="Open session “{asset.session_title}”">
                      <span class="text-[10px] px-1.5 py-0.5 rounded bg-accent-500/10 text-accent-600 dark:text-accent-400 font-bold flex-shrink-0">Session</span>
                      <span class="truncate">{asset.session_title}</span>
                    </a>
                  {:else if asset.event_id && asset.event_title}
                    <a href="/dashboard/events?event={asset.event_id}" class="inline-flex items-center gap-1.5 max-w-full text-surface-700 dark:text-surface-300 hover:text-brand-600 dark:hover:text-brand-400 hover:underline" title="Show event “{asset.event_title}”">
                      <span class="text-[10px] px-1.5 py-0.5 rounded bg-brand-500/10 text-brand-700 dark:text-brand-300 font-bold flex-shrink-0">Event</span>
                      <span class="truncate">{asset.event_title}</span>
                    </a>
                  {:else}
                    <span class="italic text-surface-500">Unlinked</span>
                  {/if}
                </td>

                <td class="px-4 py-3 align-top text-surface-500 text-xs whitespace-nowrap hidden sm:table-cell">{formatBytes(asset.file_size)}</td>

                <td class="px-4 py-3 align-top text-surface-500 text-xs whitespace-nowrap hidden sm:table-cell" title={new Date(asset.uploaded_at).toLocaleString()}>
                  {formatDate(asset.uploaded_at)}
                  {#if sameName}<span class="block text-surface-500">{formatTime(asset.uploaded_at)}</span>{/if}
                </td>

                <td class="px-4 py-3 align-top">
                  <div class="flex items-center justify-end gap-1">
                    {#if asset.presentation_id}
                      <button
                        onclick={() => handleDownload(asset)}
                        disabled={downloadingId === asset.id}
                        aria-busy={downloadingId === asset.id}
                        class="{iconButton} hover:text-brand-600 dark:hover:text-brand-400 hover:bg-brand-500/10"
                        title="Download original"
                        aria-label={`Download ${asset.file_name}`}
                      >
                        {#if downloadingId === asset.id}
                          <RefreshCw class="w-3.5 h-3.5 animate-spin" />
                        {:else}
                          <Download class="w-3.5 h-3.5" />
                        {/if}
                      </button>
                    {:else}
                      <button
                        onclick={() => handleReplace(asset)}
                        disabled={uploadingId === asset.id}
                        aria-busy={uploadingId === asset.id}
                        class="{iconButton} hover:text-accent-600 dark:hover:text-accent-400 hover:bg-accent-500/10"
                        title="Replace file"
                        aria-label={`Replace ${asset.file_name}`}
                      >
                        {#if uploadingId === asset.id}
                          <RefreshCw class="w-3.5 h-3.5 animate-spin" />
                        {:else}
                          <Upload class="w-3.5 h-3.5" />
                        {/if}
                      </button>
                    {/if}
                    <button
                      onclick={() => requestDelete(asset)}
                      disabled={!!asset.presentation_id}
                      class="{iconButton} enabled:hover:text-red-600 dark:enabled:hover:text-red-400 enabled:hover:bg-danger/10"
                      title={asset.presentation_id ? 'Presentation originals cannot be deleted from here' : 'Delete'}
                      aria-label={asset.presentation_id ? `${asset.file_name} can only be deleted from the Presentation Builder` : `Delete ${asset.file_name}`}
                    >
                      <Trash2 class="w-3.5 h-3.5" />
                    </button>
                  </div>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  {/if}

</main>

<!-- Delete confirmation -->
<ConfirmDialog
  open={!!deleteTarget}
  tone="danger"
  title="Delete asset?"
  description="The file will be permanently removed from disk."
  confirmLabel="Delete"
  loading={deleting}
  onConfirm={confirmDelete}
  onCancel={() => { if (!deleting) deleteTarget = null; }}
>
  {#if deleteTarget}
    <div class="px-4 py-3 rounded-xl bg-surface-50 dark:bg-surface-800/60">
      <p class="text-sm font-medium break-all">{deleteTarget.file_name}</p>
      <p class="text-xs text-surface-500 mt-1">{formatBytes(deleteTarget.file_size)} · uploaded {new Date(deleteTarget.uploaded_at).toLocaleString()}</p>
      {#if deleteTarget.session_title}
        <p class="text-xs text-surface-500">Session: {deleteTarget.session_title}</p>
      {:else if deleteTarget.event_title}
        <p class="text-xs text-surface-500">Event: {deleteTarget.event_title}</p>
      {/if}
    </div>
    {#if deleteTarget.slide_id}
      <p class="text-xs text-amber-700 dark:text-amber-300 mt-3 flex items-center gap-1.5">
        <AlertTriangle class="w-3.5 h-3.5 flex-shrink-0" />
        The linked slide will also be removed from the session.
      </p>
    {/if}
    {#if deleteError}
      <p class="text-xs text-red-700 dark:text-red-300 mt-3 flex items-center gap-1.5" role="alert">
        <AlertTriangle class="w-3.5 h-3.5 flex-shrink-0" />
        {deleteError}
      </p>
    {/if}
  {/if}
</ConfirmDialog>
