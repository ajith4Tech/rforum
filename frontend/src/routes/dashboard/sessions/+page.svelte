<script lang="ts">
  import { goto } from '$app/navigation';
  import {
    listSessions,
    createSession,
    deleteSession,
    listEvents
  } from '$lib/api';
  import { Plus, Trash2, ExternalLink, Copy, Presentation } from 'lucide-svelte';
  import { onMount } from 'svelte';

  let sessions: any[] = $state([]);
  let events: any[] = $state([]);
  let newTitle = $state('');
  let newSessionEventId = $state('');
  let creating = $state(false);
  let loading = $state(true);

  onMount(async () => {
    try {
      const [sessionsResult, eventsResult] = await Promise.all([
        listSessions(),
        listEvents()
      ]);
      sessions = sessionsResult;
      events = eventsResult;
    } catch {
      goto('/login');
    } finally {
      loading = false;
    }
  });

  async function handleCreate() {
    if (!newTitle.trim() || !newSessionEventId) return;
    creating = true;
    try {
      const session = await createSession(newTitle.trim(), newSessionEventId);
      sessions = [session, ...sessions];
      newTitle = '';
      newSessionEventId = '';
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

  function copyCode(code: string) {
    navigator.clipboard.writeText(code);
  }
</script>

<svelte:head>
  <title>Sessions – Rforum</title>
</svelte:head>

<main class="flex-1 max-w-5xl mx-auto w-full px-8 py-8">
  <div class="flex items-center justify-between mb-8">
    <div>
      <h1 class="text-3xl font-heading font-bold tracking-wide">All Sessions</h1>
      <p class="text-sm text-surface-500 mt-1.5">Manage your presentation sessions</p>
    </div>
  </div>

  <!-- Create new session -->
  <form onsubmit={(e) => { e.preventDefault(); handleCreate(); }} class="card p-6 flex gap-3 mb-8">
    <select class="input-field w-52" bind:value={newSessionEventId}>
      <option value="" disabled>Select event</option>
      {#each events as event (event.id)}
        <option value={event.id}>
          {event.title} · {new Date(event.event_date).toLocaleDateString()}
        </option>
      {/each}
    </select>
    <input type="text" bind:value={newTitle} placeholder="New session title..." class="input-field flex-1" />
    <button
      type="submit"
      class="btn-primary flex items-center gap-2 whitespace-nowrap text-sm"
      disabled={creating || !newSessionEventId}
    >
      <Plus class="w-4 h-4" />
      Create
    </button>
  </form>

  {#if loading}
    <div class="text-center text-surface-400 py-20">Loading...</div>
  {:else if sessions.length === 0}
    <div class="flex flex-col items-center justify-center text-center gap-4 py-16">
      <div class="w-14 h-14 flex items-center justify-center rounded-2xl bg-cyan-500/10">
        <Presentation class="w-7 h-7 text-cyan-500" />
      </div>
      <div>
        <h3 class="text-lg font-semibold">No sessions yet</h3>
        <p class="text-sm text-surface-400 mt-1">Create your first session to get started</p>
      </div>
    </div>
  {:else}
    <div class="space-y-3">
      {#each sessions as session (session.id)}
        <div class="card p-6 hover:shadow-md transition-all duration-200 hover:scale-[1.01] flex items-center justify-between gap-4">
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-3 mb-1">
              <h3 class="text-lg font-semibold truncate">{session.title}</h3>
              {#if session.is_live}
                <span class="badge-live">
                  <span class="w-1.5 h-1.5 bg-live rounded-full animate-pulse-live"></span>
                  Live
                </span>
              {/if}
            </div>
            <div class="flex items-center gap-3 text-sm text-surface-500">
              <button
                onclick={() => copyCode(session.unique_code)}
                class="flex items-center gap-1 font-mono hover:text-surface-300 transition-colors"
              >
                <Copy class="w-3 h-3" />
                {session.unique_code}
              </button>
              <span>&middot;</span>
              <span class="text-xs text-surface-500">{new Date(session.created_at).toLocaleDateString()}</span>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <a href="/dashboard/{session.id}" class="btn-secondary flex items-center gap-1.5">
              <ExternalLink class="w-3.5 h-3.5" />
              Manage
            </a>
            <button onclick={() => handleDelete(session.id)} class="btn-danger p-2.5">
              <Trash2 class="w-4 h-4" />
            </button>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</main>
