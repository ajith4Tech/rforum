<script lang="ts">
  import { goto } from '$app/navigation';
  import {
    adminListUsers,
    adminDeleteUser,
    adminUpdateUserRole,
    adminToggleUserActive,
    adminGetStorage,
    formatBytes,
    isAuthenticated
  } from '$lib/api';
  import { isSuperAdmin } from '$lib/stores';
  import { onMount } from 'svelte';
  import { Shield, User, Trash2, ToggleLeft, ToggleRight, ChevronDown, Search, RefreshCw, AlertTriangle, HardDrive } from 'lucide-svelte';

  type UserRecord = {
    id: string;
    email: string;
    role: 'USER' | 'SUPER_ADMIN';
    is_active: boolean;
    created_at: string;
    sessions_count: number;
    events_count: number;
  };

  let users: UserRecord[] = $state([]);
  let loading = $state(true);
  let error = $state('');
  let searchQuery = $state('');
  let roleFilter = $state<'all' | 'USER' | 'SUPER_ADMIN'>('all');
  let statusFilter = $state<'all' | 'active' | 'disabled'>('all');

  // Storage stats
  let storageTotalBytes = $state(0);
  let storageTotalAssets = $state(0);
  let storageTopUsers: { user_id: string; email: string; total_bytes: number; asset_count: number }[] = $state([]);
  let loadingStorage = $state(false);

  // Confirm delete modal
  let deleteTarget = $state<UserRecord | null>(null);
  let deleteConfirmEmail = $state('');
  let deletingId = $state<string | null>(null);

  // Inline action states
  let togglingId = $state<string | null>(null);
  let promotingId = $state<string | null>(null);
  let actionError = $state('');

  async function load() {
    loading = true;
    error = '';
    try {
      users = await adminListUsers() as UserRecord[];
    } catch (e: any) {
      error = e?.message || 'Failed to load users';
    } finally {
      loading = false;
    }
  }

  async function loadStorage() {
    loadingStorage = true;
    try {
      const s = await adminGetStorage();
      storageTotalBytes = s.total_bytes;
      storageTotalAssets = s.asset_count;
      storageTopUsers = s.top_users;
    } catch {
      // non-critical, keep defaults
    } finally {
      loadingStorage = false;
    }
  }

  onMount(async () => {
    if (!isAuthenticated()) { goto('/login'); return; }
    if (!$isSuperAdmin) { goto('/dashboard'); return; }
    await Promise.all([load(), loadStorage()]);
  });

  let filteredUsers = $derived(users.filter(u => {
    const matchSearch = !searchQuery || u.email.toLowerCase().includes(searchQuery.toLowerCase());
    const matchRole = roleFilter === 'all' || u.role === roleFilter;
    const matchStatus = statusFilter === 'all'
      || (statusFilter === 'active' && u.is_active)
      || (statusFilter === 'disabled' && !u.is_active);
    return matchSearch && matchRole && matchStatus;
  }));

  async function handleToggleActive(u: UserRecord) {
    togglingId = u.id;
    actionError = '';
    try {
      const updated = await adminToggleUserActive(u.id, !u.is_active) as UserRecord;
      users = users.map(x => x.id === u.id ? { ...x, is_active: updated.is_active } : x);
    } catch (e: any) {
      actionError = e?.message || 'Failed to update status';
    } finally {
      togglingId = null;
    }
  }

  async function handleRoleChange(u: UserRecord, newRole: 'USER' | 'SUPER_ADMIN') {
    if (u.role === newRole) return;
    promotingId = u.id;
    actionError = '';
    try {
      const updated = await adminUpdateUserRole(u.id, newRole) as UserRecord;
      users = users.map(x => x.id === u.id ? { ...x, role: updated.role } : x);
    } catch (e: any) {
      actionError = e?.message || 'Failed to update role';
    } finally {
      promotingId = null;
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    if (deleteConfirmEmail.trim().toLowerCase() !== deleteTarget.email.toLowerCase()) return;
    deletingId = deleteTarget.id;
    try {
      await adminDeleteUser(deleteTarget.id);
      users = users.filter(u => u.id !== deleteTarget!.id);
      deleteTarget = null;
      deleteConfirmEmail = '';
    } catch (e: any) {
      actionError = e?.message || 'Failed to delete user';
    } finally {
      deletingId = null;
    }
  }

  function formatDate(iso: string) {
    return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  }
</script>

<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

  <!-- Header -->
  <div class="flex items-center justify-between mb-8">
    <div class="flex items-center gap-3">
      <div class="w-10 h-10 flex items-center justify-center rounded-xl bg-rose-500/10">
        <Shield class="w-5 h-5 text-rose-500" />
      </div>
      <div>
        <h1 class="text-2xl font-heading font-bold text-surface-900 dark:text-surface-100">User Management</h1>
        <p class="text-sm text-surface-500">{users.length} total user{users.length !== 1 ? 's' : ''}</p>
      </div>
    </div>
    <button onclick={load} class="btn-secondary flex items-center gap-2 text-sm" disabled={loading}>
      <RefreshCw class="w-4 h-4 {loading ? 'animate-spin' : ''}" />
      Refresh
    </button>
  </div>

  {#if actionError}
    <div class="mb-4 px-4 py-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-600 dark:text-rose-400 text-sm flex items-center gap-2">
      <AlertTriangle class="w-4 h-4 flex-shrink-0" />
      {actionError}
      <button onclick={() => actionError = ''} class="ml-auto text-xs underline">Dismiss</button>
    </div>
  {/if}

  <!-- Filters -->
  <div class="card mb-6 flex flex-wrap gap-3 items-center">
    <div class="relative flex-1 min-w-48">
      <Search class="absolute left-3 top-2.5 w-4 h-4 text-surface-400" />
      <input
        type="text"
        placeholder="Search by email…"
        bind:value={searchQuery}
        class="input-field pl-9 text-sm py-2"
      />
    </div>
    <select bind:value={roleFilter} class="input-field text-sm py-2 w-40">
      <option value="all">All roles</option>
      <option value="USER">Moderator</option>
      <option value="SUPER_ADMIN">Super Admin</option>
    </select>
    <select bind:value={statusFilter} class="input-field text-sm py-2 w-40">
      <option value="all">All status</option>
      <option value="active">Active</option>
      <option value="disabled">Disabled</option>
    </select>
  </div>

  <!-- Table -->
  {#if loading}
    <div class="flex justify-center py-16">
      <RefreshCw class="w-8 h-8 text-surface-400 animate-spin" />
    </div>
  {:else if error}
    <div class="card text-center py-12 text-rose-500">{error}</div>
  {:else if filteredUsers.length === 0}
    <div class="card text-center py-12 text-surface-400">No users match your filters.</div>
  {:else}
    <div class="card overflow-hidden p-0">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-surface-200 dark:border-surface-800">
              <th class="px-4 py-3 text-left font-semibold text-surface-500 text-xs uppercase tracking-wide">User</th>
              <th class="px-4 py-3 text-left font-semibold text-surface-500 text-xs uppercase tracking-wide">Role</th>
              <th class="px-4 py-3 text-left font-semibold text-surface-500 text-xs uppercase tracking-wide">Status</th>
              <th class="px-4 py-3 text-left font-semibold text-surface-500 text-xs uppercase tracking-wide">Content</th>
              <th class="px-4 py-3 text-left font-semibold text-surface-500 text-xs uppercase tracking-wide">Joined</th>
              <th class="px-4 py-3 text-right font-semibold text-surface-500 text-xs uppercase tracking-wide">Actions</th>
            </tr>
          </thead>
          <tbody>
            {#each filteredUsers as u (u.id)}
              <tr class="border-b border-surface-100 dark:border-surface-800/60 hover:bg-surface-50 dark:hover:bg-surface-800/40 transition">
                <!-- Email -->
                <td class="px-4 py-3">
                  <div class="flex items-center gap-2">
                    <div class="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0
                      {u.role === 'SUPER_ADMIN' ? 'bg-rose-500/10 text-rose-500' : 'bg-brand-500/10 text-brand-500'}">
                      {u.email[0].toUpperCase()}
                    </div>
                    <span class="font-medium text-surface-900 dark:text-surface-100 truncate max-w-56">{u.email}</span>
                  </div>
                </td>

                <!-- Role selector -->
                <td class="px-4 py-3">
                  <div class="relative inline-block">
                    <select
                      value={u.role}
                      onchange={(e) => handleRoleChange(u, (e.target as HTMLSelectElement).value as 'USER' | 'SUPER_ADMIN')}
                      disabled={promotingId === u.id}
                      class="appearance-none pl-2 pr-6 py-1 rounded-lg text-xs font-bold border transition cursor-pointer
                        {u.role === 'SUPER_ADMIN'
                          ? 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20'
                          : 'bg-brand-500/10 text-brand-600 dark:text-brand-400 border-brand-500/20'}
                        disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <option value="USER">Moderator</option>
                      <option value="SUPER_ADMIN">Super Admin</option>
                    </select>
                    <ChevronDown class="absolute right-1 top-1.5 w-3 h-3 pointer-events-none
                      {u.role === 'SUPER_ADMIN' ? 'text-rose-500' : 'text-brand-500'}" />
                  </div>
                </td>

                <!-- Active toggle -->
                <td class="px-4 py-3">
                  <button
                    onclick={() => handleToggleActive(u)}
                    disabled={togglingId === u.id}
                    class="flex items-center gap-1.5 text-xs font-semibold transition disabled:opacity-50
                      {u.is_active ? 'text-emerald-600 dark:text-emerald-400' : 'text-surface-400'}"
                    title="{u.is_active ? 'Click to disable' : 'Click to enable'}"
                  >
                    {#if u.is_active}
                      <ToggleRight class="w-5 h-5" />
                      Active
                    {:else}
                      <ToggleLeft class="w-5 h-5" />
                      Disabled
                    {/if}
                  </button>
                </td>

                <!-- Content counts -->
                <td class="px-4 py-3 text-surface-500">
                  <div class="flex gap-3 text-xs">
                    <span>{u.events_count} event{u.events_count !== 1 ? 's' : ''}</span>
                    <span class="text-surface-300 dark:text-surface-700">·</span>
                    <span>{u.sessions_count} session{u.sessions_count !== 1 ? 's' : ''}</span>
                  </div>
                </td>

                <!-- Joined date -->
                <td class="px-4 py-3 text-surface-500 text-xs whitespace-nowrap">
                  {formatDate(u.created_at)}
                </td>

                <!-- Delete -->
                <td class="px-4 py-3 text-right">
                  <button
                    onclick={() => { deleteTarget = u; deleteConfirmEmail = ''; actionError = ''; }}
                    class="p-1.5 rounded-lg text-surface-400 hover:text-rose-500 hover:bg-rose-500/10 transition"
                    title="Delete user"
                  >
                    <Trash2 class="w-4 h-4" />
                  </button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  {/if}

  <!-- ── Storage section ─────────────────────────────────────────────── -->
  <div class="mt-10">
    <div class="flex items-center justify-between mb-5">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 flex items-center justify-center rounded-xl bg-warning/10">
          <HardDrive class="w-5 h-5 text-warning" />
        </div>
        <div>
          <h2 class="text-xl font-heading font-bold tracking-wide text-surface-900 dark:text-surface-100">Platform Storage</h2>
          <p class="text-sm text-surface-500">Total storage used across all users</p>
        </div>
      </div>
      <button onclick={loadStorage} disabled={loadingStorage} class="btn-secondary flex items-center gap-2 text-sm">
        <RefreshCw class="w-4 h-4 {loadingStorage ? 'animate-spin' : ''}" />
        Refresh
      </button>
    </div>

    <!-- Total summary -->
    <div class="grid grid-cols-2 gap-4 mb-6">
      <div class="card">
        <p class="text-xs text-surface-500 uppercase tracking-widest font-semibold mb-1">Total Storage Used</p>
        <p class="text-3xl font-heading font-bold">{formatBytes(storageTotalBytes)}</p>
        <div class="mt-3 w-full h-1.5 rounded-full bg-surface-100 dark:bg-surface-800 overflow-hidden">
          <div
            class="h-full rounded-full transition-all duration-500 {Math.min((storageTotalBytes / (10 * 1024 * 1024 * 1024)) * 100, 100) > 80 ? 'bg-danger' : Math.min((storageTotalBytes / (10 * 1024 * 1024 * 1024)) * 100, 100) > 50 ? 'bg-warning' : 'bg-brand-500'}"
            style="width:{Math.min((storageTotalBytes / (10 * 1024 * 1024 * 1024)) * 100, 100)}%"
          ></div>
        </div>
        <p class="text-xs text-surface-500 mt-1.5">Reference: 10 GB platform cap</p>
      </div>
      <div class="card">
        <p class="text-xs text-surface-500 uppercase tracking-widest font-semibold mb-1">Total Files</p>
        <p class="text-3xl font-heading font-bold">{storageTotalAssets}</p>
        <p class="text-xs text-surface-500 mt-1.5">Across all users and sessions</p>
      </div>
    </div>

    <!-- Top users by storage -->
    {#if loadingStorage}
      <div class="flex justify-center py-8"><RefreshCw class="w-6 h-6 text-surface-400 animate-spin" /></div>
    {:else if storageTopUsers.length === 0}
      <div class="card text-center py-10 text-surface-500 text-sm">No file uploads recorded yet.</div>
    {:else}
      <div class="card overflow-hidden p-0">
        <div class="px-4 py-3 border-b border-surface-200 dark:border-surface-800 bg-surface-50 dark:bg-surface-900/50">
          <h3 class="text-xs font-semibold text-surface-500 uppercase tracking-widest">Top Users by Storage</h3>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-surface-200 dark:border-surface-800">
                <th class="px-4 py-2 text-left font-semibold text-surface-500 text-xs uppercase tracking-wide">#</th>
                <th class="px-4 py-2 text-left font-semibold text-surface-500 text-xs uppercase tracking-wide">User</th>
                <th class="px-4 py-2 text-left font-semibold text-surface-500 text-xs uppercase tracking-wide">Files</th>
                <th class="px-4 py-2 text-left font-semibold text-surface-500 text-xs uppercase tracking-wide">Storage</th>
                <th class="px-4 py-2 text-left font-semibold text-surface-500 text-xs uppercase tracking-wide w-48">Usage</th>
              </tr>
            </thead>
            <tbody>
              {#each storageTopUsers as u, i (u.user_id)}
                {@const pct = storageTotalBytes > 0 ? (u.total_bytes / storageTotalBytes) * 100 : 0}
                <tr class="border-b border-surface-100 dark:border-surface-800/60 hover:bg-surface-50 dark:hover:bg-surface-800/30 transition">
                  <td class="px-4 py-3 text-surface-500 text-xs font-mono">{i + 1}</td>
                  <td class="px-4 py-3">
                    <div class="flex items-center gap-2">
                      <div class="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold bg-brand-500/10 text-brand-500 flex-shrink-0">
                        {u.email[0].toUpperCase()}
                      </div>
                      <span class="text-sm font-medium truncate max-w-60">{u.email}</span>
                    </div>
                  </td>
                  <td class="px-4 py-3 text-surface-500 text-xs">{u.asset_count} file{u.asset_count !== 1 ? 's' : ''}</td>
                  <td class="px-4 py-3 text-sm font-semibold">{formatBytes(u.total_bytes)}</td>
                  <td class="px-4 py-3">
                    <div class="flex items-center gap-2">
                      <div class="flex-1 h-2 rounded-full bg-surface-100 dark:bg-surface-800 overflow-hidden">
                        <div class="h-full rounded-full bg-brand-500 transition-all duration-500" style="width:{pct.toFixed(1)}%"></div>
                      </div>
                      <span class="text-xs text-surface-500 w-10 text-right">{pct.toFixed(0)}%</span>
                    </div>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>
    {/if}
  </div>

</div>

<!-- Delete confirmation modal -->
{#if deleteTarget}
  <div
    class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center px-4 z-50"
    onclick={(e) => { if (e.target === e.currentTarget) { deleteTarget = null; } }}
    role="dialog"
    aria-modal="true"
  >
    <div class="card w-full max-w-md shadow-2xl animate-fade-in p-6">
      <div class="flex items-center gap-3 mb-4">
        <div class="w-10 h-10 flex items-center justify-center rounded-xl bg-rose-500/10 flex-shrink-0">
          <AlertTriangle class="w-5 h-5 text-rose-500" />
        </div>
        <div>
          <h2 class="text-base font-heading font-bold text-surface-900 dark:text-surface-100">Delete User</h2>
          <p class="text-xs text-surface-500">This permanently deletes the account and all their data.</p>
        </div>
      </div>

      <div class="rounded-xl bg-surface-50 dark:bg-surface-800/60 px-4 py-3 mb-4">
        <p class="text-sm font-semibold text-surface-900 dark:text-surface-100 break-all">{deleteTarget.email}</p>
        <p class="text-xs text-surface-500 mt-0.5">
          {deleteTarget.events_count} event{deleteTarget.events_count !== 1 ? 's' : ''} &nbsp;·&nbsp;
          {deleteTarget.sessions_count} session{deleteTarget.sessions_count !== 1 ? 's' : ''} will be removed
        </p>
      </div>

      <div class="mb-4">
        <label class="block text-xs font-medium text-surface-500 mb-1.5">
          Type the email address to confirm:
        </label>
        <input
          type="email"
          bind:value={deleteConfirmEmail}
          placeholder={deleteTarget.email}
          class="input-field text-sm"
          autocomplete="off"
        />
      </div>

      <div class="flex gap-3">
        <button
          onclick={() => { deleteTarget = null; deleteConfirmEmail = ''; }}
          class="btn-secondary flex-1"
        >
          Cancel
        </button>
        <button
          onclick={confirmDelete}
          disabled={deleteConfirmEmail.trim().toLowerCase() !== deleteTarget.email.toLowerCase() || deletingId === deleteTarget.id}
          class="flex-1 px-4 py-2 rounded-xl font-semibold text-sm bg-rose-500 text-white hover:bg-rose-600 transition disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {deletingId === deleteTarget.id ? 'Deleting…' : 'Delete permanently'}
        </button>
      </div>
    </div>
  </div>
{/if}

<!-- ─────────────────────────────────────────────────────────────── -->
<!-- Storage section (outside the modal, inside the page container  -->
<!-- is imported from outside the {#if deleteTarget} block)         -->
<!-- ─────────────────────────────────────────────────────────────── -->
