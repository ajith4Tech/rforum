<script lang="ts">
  import { goto } from '$app/navigation';
  import { listSessions, createSession, deleteSession, logout } from '$lib/api';
  import { Radio, Plus, Trash2, LogOut, ExternalLink, Copy } from 'lucide-svelte';
  import { onMount } from 'svelte';

  let sessions: any[] = $state([]);
  let newTitle = $state('');
  let creating = $state(false);
  let loading = $state(true);

  onMount(async () => {
    try {
      sessions = await listSessions();
    } catch {
      goto('/login');
    } finally {
      loading = false;
    }
  });

  async function handleCreate() {
    if (!newTitle.trim()) return;
    creating = true;
    try {
      const session = await createSession(newTitle.trim());
      sessions = [session, ...sessions];
      newTitle = '';
    } catch (e: any) {
      alert(e.message);
    } finally {
      creating = false;
    }
  }

  async function handleDelete(id: string) {
    if (!confirm('Delete this session?')) return;
    await deleteSession(id);
    sessions = sessions.filter((s) => s.id !== id);
  }

  function handleLogout() {
    logout();
    goto('/');
  }

  function copyCode(code: string) {
    navigator.clipboard.writeText(code);
  }
</script>

<svelte:head>
  <title>Dashboard – Rforum</title>
</svelte:head>

<div class="min-h-screen flex flex-col">
  <!-- Top bar -->
  <nav class="flex items-center justify-between px-6 py-4 border-b border-surface-800">
    <a href="/" class="flex items-center gap-2">
      <Radio class="w-6 h-6 text-brand-400" />
      <span class="text-lg font-bold">Rforum</span>
    </a>
    <button on:click={handleLogout} class="btn-secondary text-sm flex items-center gap-2">
      <LogOut class="w-4 h-4" />
      Log out
    </button>
  </nav>

  <main class="flex-1 max-w-4xl mx-auto w-full px-6 py-10">
    <div class="flex items-center justify-between mb-8">
      <h1 class="text-2xl font-bold">Your Sessions</h1>
    </div>

    <!-- Create new session -->
    <form on:submit|preventDefault={handleCreate} class="card flex gap-3 mb-8">
      <input
        type="text"
        bind:value={newTitle}
        placeholder="New session title..."
        class="input-field flex-1"
      />
      <button type="submit" class="btn-primary flex items-center gap-2 whitespace-nowrap" disabled={creating}>
        <Plus class="w-4 h-4" />
        Create
      </button>
    </form>

    <!-- Sessions list -->
    {#if loading}
      <div class="text-center text-surface-500 py-20">Loading...</div>
    {:else if sessions.length === 0}
      <div class="text-center text-surface-500 py-20">
        <p class="text-lg mb-2">No sessions yet</p>
        <p class="text-sm">Create your first session to get started</p>
      </div>
    {:else}
      <div class="space-y-3">
        {#each sessions as session (session.id)}
          <div class="card flex items-center justify-between gap-4 animate-fade-in">
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-3 mb-1">
                <h3 class="font-semibold truncate">{session.title}</h3>
                {#if session.is_live}
                  <span class="badge-live">
                    <span class="w-1.5 h-1.5 bg-live rounded-full animate-pulse-live"></span>
                    Live
                  </span>
                {/if}
              </div>
              <div class="flex items-center gap-3 text-sm text-surface-500">
                <button
                  on:click={() => copyCode(session.unique_code)}
                  class="flex items-center gap-1 font-mono hover:text-surface-300 transition-colors"
                >
                  <Copy class="w-3 h-3" />
                  {session.unique_code}
                </button>
                <span>·</span>
                <span>{new Date(session.created_at).toLocaleDateString()}</span>
              </div>
            </div>

            <div class="flex items-center gap-2">
              <a href="/dashboard/{session.id}" class="btn-secondary text-sm flex items-center gap-1.5">
                <ExternalLink class="w-3.5 h-3.5" />
                Manage
              </a>
              <button on:click={() => handleDelete(session.id)} class="btn-danger text-sm p-2.5">
                <Trash2 class="w-4 h-4" />
              </button>
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </main>
</div>
