<script lang="ts">
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import {
    listAssets,
    getStorageUsage,
    replaceAssetFile,
    deleteAsset,
    formatBytes,
    isAuthenticated
  } from '$lib/api';
  import {
    HardDrive,
    Search,
    File,
    Upload,
    Trash2,
    RefreshCw,
    ExternalLink,
    AlertTriangle
  } from 'lucide-svelte';

  interface Asset {
    id: string;
    user_id: string;
    session_id: string | null;
    event_id: string | null;
    slide_id: string | null;
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
  let deletingId = $state<string | null>(null);
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

  function fileTypeBadge(ct: string = ''): string {
    if (ct.includes('pdf')) return 'PDF';
    if (ct.includes('presentationml') || ct.includes('pptx')) return 'PPTX';
    if (ct.includes('powerpoint') || ct.includes('ppt')) return 'PPT';
    if (ct.includes('msword') || ct.includes('docx')) return 'DOCX';
    if (ct.includes('plain')) return 'TXT';
    return (ct.split('/').pop() ?? 'FILE').toUpperCase().slice(0, 6);
  }

  function fileTypeBadgeClass(ct: string = ''): string {
    if (ct.includes('pdf')) return 'bg-danger/10 text-danger';
    if (ct.includes('presentation') || ct.includes('ppt')) return 'bg-warning/10 text-warning';
    if (ct.includes('word') || ct.includes('doc')) return 'bg-accent-500/10 text-accent-500';
    return 'bg-surface-100 dark:bg-surface-800 text-surface-500';
  }

  async function handleReplace(asset: Asset) {
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

  async function confirmDelete() {
    if (!deleteTarget) return;
    deletingId = deleteTarget.id;
    actionError = '';
    try {
      await deleteAsset(deleteTarget.id);
      assets = assets.filter(a => a.id !== deleteTarget!.id);
      assetCount = Math.max(0, assetCount - 1);
      const s = await getStorageUsage();
      storageBytes = (s as any).total_bytes ?? 0;
      deleteTarget = null;
    } catch (e: any) {
      actionError = e?.message || 'Failed to delete asset';
    } finally {
      deletingId = null;
    }
  }

  function formatDate(iso: string) {
    return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  }

  const STORAGE_CAP_BYTES = 500 * 1024 * 1024;
  const storagePct = $derived(Math.min((storageBytes / STORAGE_CAP_BYTES) * 100, 100));
  const storageBarColor = $derived(
    storagePct > 80 ? 'bg-danger' : storagePct > 50 ? 'bg-warning' : 'bg-brand-500'
  );
</script>

<svelte:head>
  <title>Session Assets – Rforum</title>
</svelte:head>

<main class="flex-1 max-w-6xl mx-auto w-full px-8 py-10">

  <!-- Header -->
  <div class="flex items-center justify-between mb-8">
    <div>
      <div class="flex items-center gap-3 mb-1">
        <div class="w-10 h-10 flex items-center justify-center rounded-xl bg-warning/10">
          <HardDrive class="w-5 h-5 text-warning" />
        </div>
        <h1 class="text-3xl font-heading font-bold tracking-wide">Session Assets</h1>
      </div>
      <p class="text-surface-500 ml-13 mt-1">Manage all files uploaded across your sessions and events.</p>
    </div>
    <button onclick={load} disabled={loading} class="btn-secondary flex items-center gap-2 text-sm">
      <RefreshCw class="w-4 h-4 {loading ? 'animate-spin' : ''}" />
      Refresh
    </button>
  </div>

  <!-- Storage summary card -->
  <div class="card mb-8">
    <div class="flex items-center justify-between mb-3">
      <div>
        <p class="text-xs text-surface-500 uppercase tracking-widest font-semibold">Storage Used</p>
        <p class="text-2xl font-heading font-bold mt-1">{formatBytes(storageBytes)}</p>
      </div>
      <div class="text-right">
        <p class="text-sm font-semibold">{assetCount}</p>
        <p class="text-xs text-surface-500">file{assetCount !== 1 ? 's' : ''}</p>
      </div>
    </div>
    <div class="w-full h-2 rounded-full bg-surface-100 dark:bg-surface-800 overflow-hidden">
      <div class="h-full rounded-full transition-all duration-500 {storageBarColor}" style="width:{storagePct}%"></div>
    </div>
    <p class="text-xs text-surface-500 mt-2">Reference quota: 500 MB</p>
  </div>

  {#if actionError}
    <div class="mb-4 px-4 py-3 rounded-xl bg-danger/10 border border-danger/20 text-danger text-sm flex items-center gap-2">
      <AlertTriangle class="w-4 h-4 flex-shrink-0" />
      {actionError}
      <button onclick={() => actionError = ''} class="ml-auto text-xs underline">Dismiss</button>
    </div>
  {/if}

  <!-- Filters -->
  <div class="card mb-6 flex flex-wrap gap-3 items-center">
    <div class="relative flex-1 min-w-52">
      <Search class="absolute left-3 top-2.5 w-4 h-4 text-surface-400" />
      <input
        type="text"
        placeholder="Search by file or session name…"
        bind:value={searchQuery}
        class="input-field pl-9 text-sm py-2"
      />
    </div>
    <select bind:value={filterContext} class="input-field text-sm py-2 w-44">
      <option value="all">All files</option>
      <option value="session">Session files</option>
      <option value="event">Event files</option>
      <option value="unlinked">Unlinked</option>
    </select>
    {#if searchQuery || filterContext !== 'all'}
      <button onclick={() => { searchQuery = ''; filterContext = 'all'; }} class="text-xs text-surface-500 hover:text-surface-300 transition">
        Clear
      </button>
    {/if}
  </div>

  {#if loading}
    <div class="flex justify-center py-16">
      <RefreshCw class="w-8 h-8 text-surface-400 animate-spin" />
    </div>

  {:else if error}
    <div class="card text-center py-12 text-danger">{error}</div>

  {:else if assets.length === 0}
    <div class="card flex flex-col items-center py-16 gap-4 text-surface-500">
      <HardDrive class="w-10 h-10 opacity-30" />
      <p class="text-sm">No uploaded files yet.</p>
      <p class="text-xs text-surface-600 max-w-xs text-center">
        Files are tracked automatically when you upload a slide via a session.
      </p>
      <a href="/dashboard/sessions" class="btn-primary text-sm">Go to Sessions</a>
    </div>

  {:else if filteredAssets.length === 0}
    <div class="card text-center py-12 text-surface-500">No assets match your filters.</div>

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
              <th class="px-4 py-3 text-left font-semibold text-surface-500 text-xs uppercase tracking-wide">File Name</th>
              <th class="px-4 py-3 text-left font-semibold text-surface-500 text-xs uppercase tracking-wide">Event / Session</th>
              <th class="px-4 py-3 text-left font-semibold text-surface-500 text-xs uppercase tracking-wide">Type</th>
              <th class="px-4 py-3 text-left font-semibold text-surface-500 text-xs uppercase tracking-wide">Size</th>
              <th class="px-4 py-3 text-left font-semibold text-surface-500 text-xs uppercase tracking-wide">Uploaded</th>
              <th class="px-4 py-3 text-right font-semibold text-surface-500 text-xs uppercase tracking-wide">Actions</th>
            </tr>
          </thead>
          <tbody>
            {#each filteredAssets as asset (asset.id)}
              <tr class="border-b border-surface-100 dark:border-surface-800/60 hover:bg-surface-50 dark:hover:bg-surface-800/30 transition">

                <td class="px-4 py-3">
                  <div class="flex items-center gap-2">
                    <File class="w-4 h-4 text-surface-400 flex-shrink-0" />
                    <span class="font-medium truncate max-w-56 dark:text-surface-100" title={asset.file_name}>{asset.file_name}</span>
                  </div>
                </td>

                <td class="px-4 py-3 text-xs max-w-44 text-surface-500">
                  {#if asset.session_title}
                    <span class="text-[10px] px-1.5 py-0.5 rounded bg-accent-500/10 text-accent-500 font-bold mr-1">S</span>
                    <span class="truncate">{asset.session_title}</span>
                  {:else if asset.event_title}
                    <span class="text-[10px] px-1.5 py-0.5 rounded bg-brand-500/10 text-brand-500 font-bold mr-1">E</span>
                    <span class="truncate">{asset.event_title}</span>
                  {:else}
                    <span class="italic text-surface-600">Unlinked</span>
                  {/if}
                </td>

                <td class="px-4 py-3">
                  <span class="text-[11px] font-bold px-1.5 py-0.5 rounded {fileTypeBadgeClass(asset.file_type)}">
                    {fileTypeBadge(asset.file_type)}
                  </span>
                </td>

                <td class="px-4 py-3 text-surface-500 text-xs whitespace-nowrap">{formatBytes(asset.file_size)}</td>

                <td class="px-4 py-3 text-surface-500 text-xs whitespace-nowrap">{formatDate(asset.uploaded_at)}</td>

                <td class="px-4 py-3">
                  <div class="flex items-center justify-end gap-1.5">
                    {#if asset.session_id}
                      <a
                        href="/dashboard/{asset.session_id}"
                        class="p-1.5 rounded-lg text-surface-400 hover:text-brand-400 hover:bg-brand-500/10 transition"
                        title="Open session"
                      >
                        <ExternalLink class="w-3.5 h-3.5" />
                      </a>
                    {/if}
                    <button
                      onclick={() => handleReplace(asset)}
                      disabled={uploadingId === asset.id}
                      class="p-1.5 rounded-lg text-surface-400 hover:text-accent-400 hover:bg-accent-500/10 transition disabled:opacity-40"
                      title="Replace file"
                    >
                      {#if uploadingId === asset.id}
                        <RefreshCw class="w-3.5 h-3.5 animate-spin" />
                      {:else}
                        <Upload class="w-3.5 h-3.5" />
                      {/if}
                    </button>
                    <button
                      onclick={() => { deleteTarget = asset; actionError = ''; }}
                      class="p-1.5 rounded-lg text-surface-400 hover:text-danger hover:bg-danger/10 transition"
                      title="Delete"
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

<!-- Delete confirmation modal -->
{#if deleteTarget}
  <div
    class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center px-4 z-50"
    onclick={(e) => { if (e.target === e.currentTarget) deleteTarget = null; }}
    role="dialog"
    aria-modal="true"
  >
    <div class="card w-full max-w-sm shadow-2xl animate-fade-in p-6">
      <div class="flex items-center gap-3 mb-4">
        <div class="w-10 h-10 flex items-center justify-center rounded-xl bg-danger/10 flex-shrink-0">
          <AlertTriangle class="w-5 h-5 text-danger" />
        </div>
        <div>
          <h2 class="text-base font-heading font-bold">Delete Asset?</h2>
          <p class="text-xs text-surface-500">The file will be permanently removed from disk.</p>
        </div>
      </div>
      <div class="px-4 py-3 rounded-xl bg-surface-50 dark:bg-surface-800/60 mb-4">
        <p class="text-sm font-medium break-all">{deleteTarget.file_name}</p>
        <p class="text-xs text-surface-500 mt-1">{formatBytes(deleteTarget.file_size)}</p>
        {#if deleteTarget.session_title}
          <p class="text-xs text-surface-500">Session: {deleteTarget.session_title}</p>
        {/if}
      </div>
      {#if deleteTarget.slide_id}
        <p class="text-xs text-warning mb-4 flex items-center gap-1.5">
          <AlertTriangle class="w-3.5 h-3.5 flex-shrink-0" />
          The linked slide will also be removed from the session.
        </p>
      {/if}
      <div class="flex gap-3">
        <button onclick={() => deleteTarget = null} class="btn-secondary flex-1 text-sm">Cancel</button>
        <button
          onclick={confirmDelete}
          disabled={!!deletingId}
          class="flex-1 px-4 py-2 rounded-xl font-semibold text-sm bg-danger text-white hover:opacity-90 transition disabled:opacity-40"
        >
          {deletingId ? 'Deleting…' : 'Delete'}
        </button>
      </div>
    </div>
  </div>
{/if}
