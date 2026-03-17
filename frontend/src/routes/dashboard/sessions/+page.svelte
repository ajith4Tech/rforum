<script lang="ts">
  import { goto } from '$app/navigation';
  import {
    listSessions,
    createSession,
    deleteSession,
    updateSession,
    listEvents
  } from '$lib/api';
  import { Plus, Trash2, Pencil, Check, X, Copy } from 'lucide-svelte';
  import { onMount } from 'svelte';

  let sessions: any[] = $state([]);
  let events: any[] = $state([]);
  let newTitle = $state('');
  let newSessionEventId = $state('');
  let moderatorName = $state('');
  let speakerInput = $state('');
  let speakerNames = $state<string[]>([]);
  let creating = $state(false);
  let loading = $state(true);

  // Inline editing state
  let editingSessionId: string | null = $state(null);
  let editTitle = $state('');
  let editModerator = $state('');
  let editSpeakers = $state<string[]>([]);
  let editSpeakerInput = $state('');
  let isSaving = $state(false);

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
      const session = await createSession(
        newTitle.trim(),
        newSessionEventId,
        moderatorName.trim() || null,
        speakerNames
      );
      sessions = [session, ...sessions];
      newTitle = '';
      newSessionEventId = '';
      moderatorName = '';
      speakerInput = '';
      speakerNames = [];
    } catch (e: any) {
      alert(e.message);
    } finally {
      creating = false;
    }
  }

  function addSpeaker() {
    const name = speakerInput.trim();
    if (!name) return;
    if (speakerNames.some((s) => s.toLowerCase() === name.toLowerCase())) {
      speakerInput = '';
      return;
    }
    speakerNames = [...speakerNames, name];
    speakerInput = '';
  }

  function removeSpeaker(index: number) {
    speakerNames = speakerNames.filter((_, i) => i !== index);
  }

  function addEditSpeaker() {
    const name = editSpeakerInput.trim();
    if (!name) return;
    if (editSpeakers.some((s) => s.toLowerCase() === name.toLowerCase())) {
      editSpeakerInput = '';
      return;
    }
    editSpeakers = [...editSpeakers, name];
    editSpeakerInput = '';
  }

  function removeEditSpeaker(index: number) {
    editSpeakers = editSpeakers.filter((_, i) => i !== index);
  }

  function startEditing(session: any) {
    editingSessionId = session.id;
    editTitle = session.title;
    editModerator = session.moderator_name || '';
    editSpeakers = Array.isArray(session.speaker_names) ? [...session.speaker_names] : [];
    editSpeakerInput = '';
  }

  function cancelEditing() {
    editingSessionId = null;
    editTitle = '';
    editModerator = '';
    editSpeakers = [];
    editSpeakerInput = '';
  }

  async function saveEditing(sessionId: string) {
    if (!editTitle.trim()) return;
    isSaving = true;
    try {
      const updated = await updateSession(sessionId, {
        title: editTitle.trim(),
        moderator_name: editModerator.trim() || null,
        speaker_names: editSpeakers
      });
      sessions = sessions.map((s) => s.id === sessionId ? updated : s);
      cancelEditing();
    } catch (e: any) {
      alert(e.message);
    } finally {
      isSaving = false;
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

<main class="flex-1 max-w-6xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8">
  <div class="mb-8">
    <h1 class="text-3xl sm:text-4xl font-heading font-semibold tracking-wide">Sessions</h1>
    <p class="text-surface-500 mt-2">Manage your presentations and moderate sessions</p>
  </div>

  <!-- Create Session Form -->
  <div class="card p-6 sm:p-8 mb-8 border border-surface-200 dark:border-surface-800">
    <h2 class="text-lg font-heading font-semibold mb-5">Create New Session</h2>
    <form onsubmit={(e) => { e.preventDefault(); handleCreate(); }} class="space-y-4">
      <div class="grid gap-4 md:grid-cols-2">
        <div>
          <label class="block text-xs uppercase tracking-wider text-surface-500 font-medium mb-2">Event</label>
          <select class="input-field w-full" bind:value={newSessionEventId}>
            <option value="" disabled>Select event</option>
            {#each events as event (event.id)}
              <option value={event.id}>
                {event.title} · {new Date(event.event_date).toLocaleDateString()}
              </option>
            {/each}
          </select>
        </div>
        <div>
          <label class="block text-xs uppercase tracking-wider text-surface-500 font-medium mb-2">Session Title</label>
          <input type="text" bind:value={newTitle} placeholder="Enter session title" class="input-field" />
        </div>
      </div>

      <div class="grid gap-4 md:grid-cols-2">
        <div>
          <label class="block text-xs uppercase tracking-wider text-surface-500 font-medium mb-2">Moderator (optional)</label>
          <input type="text" bind:value={moderatorName} placeholder="Enter moderator name" class="input-field" />
        </div>
        <div>
          <label class="block text-xs uppercase tracking-wider text-surface-500 font-medium mb-2">Add Speakers</label>
          <div class="flex gap-2">
            <input
              type="text"
              bind:value={speakerInput}
              placeholder="Enter speaker name"
              class="input-field flex-1"
              onkeydown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                  addSpeaker();
                }
              }}
            />
            <button type="button" class="btn-secondary px-4" onclick={addSpeaker}>Add</button>
          </div>
        </div>
      </div>

      {#if speakerNames.length > 0}
        <div class="flex flex-wrap gap-2 pt-2">
          {#each speakerNames as speaker, index (speaker + index)}
            <span class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-surface-300 dark:border-surface-700 text-xs font-medium">
              {speaker}
              <button type="button" class="text-surface-500 hover:text-danger transition-colors" onclick={() => removeSpeaker(index)}>×</button>
            </span>
          {/each}
        </div>
      {/if}

      <div class="flex justify-end pt-2">
        <button
          type="submit"
          class="btn-primary flex items-center justify-center gap-2"
          disabled={creating || !newSessionEventId || !newTitle.trim()}
        >
          <Plus class="w-4 h-4" />
          {creating ? 'Creating...' : 'Create Session'}
        </button>
      </div>
    </form>
  </div>

  <!-- Sessions List -->
  {#if loading}
    <div class="text-center text-surface-400 py-20">Loading sessions...</div>
  {:else if sessions.length === 0}
    <div class="card p-12 text-center border border-dashed border-surface-300 dark:border-surface-700">
      <svg class="w-12 h-12 mx-auto text-surface-400 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
      </svg>
      <h3 class="text-lg font-semibold text-surface-900 dark:text-surface-100 mt-2">No sessions yet</h3>
      <p class="text-sm text-surface-500 mt-1">Create your first session to get started</p>
    </div>
  {:else}
    <div class="space-y-3">
      {#each sessions as session (session.id)}
        <!-- Session Card -->
        <div class="card border border-surface-200 dark:border-surface-800 hover:border-surface-300 dark:hover:border-surface-700 transition-all duration-200">
          {#if editingSessionId === session.id}
            <!-- Edit Mode -->
            <div class="p-6 space-y-4">
              <div class="grid gap-4 md:grid-cols-3">
                <div>
                  <label class="block text-xs uppercase tracking-wider text-surface-500 font-medium mb-2">Title</label>
                  <input type="text" bind:value={editTitle} class="input-field" placeholder="Session title" />
                </div>
                <div>
                  <label class="block text-xs uppercase tracking-wider text-surface-500 font-medium mb-2">Moderator</label>
                  <input type="text" bind:value={editModerator} class="input-field" placeholder="Moderator name" />
                </div>
                <div>
                  <label class="block text-xs uppercase tracking-wider text-surface-500 font-medium mb-2">Add Speakers</label>
                  <div class="flex gap-2">
                    <input
                      type="text"
                      bind:value={editSpeakerInput}
                      class="input-field flex-1"
                      placeholder="Speaker name"
                      onkeydown={(event) => {
                        if (event.key === 'Enter') {
                          event.preventDefault();
                          addEditSpeaker();
                        }
                      }}
                    />
                    <button type="button" class="btn-secondary px-3" onclick={addEditSpeaker}>+</button>
                  </div>
                </div>
              </div>

              {#if editSpeakers.length > 0}
                <div class="flex flex-wrap gap-2">
                  {#each editSpeakers as speaker, index (speaker + index)}
                    <span class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-surface-100 dark:bg-surface-800 text-xs font-medium">
                      {speaker}
                      <button type="button" class="text-surface-500 hover:text-danger transition-colors" onclick={() => removeEditSpeaker(index)}>×</button>
                    </span>
                  {/each}
                </div>
              {/if}

              <div class="flex justify-end gap-2 pt-2">
                <button type="button" class="btn-secondary flex items-center gap-2" onclick={cancelEditing} disabled={isSaving}>
                  <X class="w-4 h-4" />
                  Cancel
                </button>
                <button type="button" class="btn-primary flex items-center gap-2" onclick={() => saveEditing(session.id)} disabled={isSaving}>
                  <Check class="w-4 h-4" />
                  {isSaving ? 'Saving...' : 'Save'}
                </button>
              </div>
            </div>
          {:else}
            <!-- View Mode -->
            <div class="p-6">
              <!-- Top Row: Title and Status -->
              <div class="flex items-start justify-between gap-4 mb-4">
                <div class="flex-1 min-w-0">
                  <h3 class="text-xl font-heading font-semibold text-surface-900 dark:text-surface-100 truncate">{session.title}</h3>
                  <div class="flex items-center gap-3 mt-2">
                    {#if session.is_live}
                      <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-red-500/10 border border-red-500/30 text-xs font-semibold text-red-600 dark:text-red-400">
                        <span class="w-2 h-2 bg-red-500 rounded-full animate-pulse"></span>
                        LIVE
                      </span>
                    {:else}
                      <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-surface-100 dark:bg-surface-800 border border-surface-200 dark:border-surface-700 text-xs font-semibold text-surface-600 dark:text-surface-400">
                        Scheduled
                      </span>
                    {/if}
                  </div>
                </div>
              </div>

              <!-- Middle: Session Info and Moderator/Speakers -->
              <div class="grid grid-cols-1 md:grid-cols-3 gap-6 py-4 border-y border-surface-200 dark:border-surface-800">
                <div>
                  <p class="text-xs uppercase tracking-wider text-surface-500 font-medium mb-1">Session Code</p>
                  <button
                    onclick={() => copyCode(session.unique_code)}
                    class="font-mono font-semibold text-surface-900 dark:text-surface-100 hover:text-brand-600 dark:hover:text-brand-400 transition-colors flex items-center gap-2"
                  >
                    {session.unique_code}
                    <Copy class="w-3.5 h-3.5" />
                  </button>
                  <p class="text-xs text-surface-500 mt-2">{new Date(session.created_at).toLocaleDateString()}</p>
                </div>

                <div>
                  {#if session.moderator_name}
                    <p class="text-xs uppercase tracking-wider text-surface-500 font-medium mb-1">Moderator</p>
                    <p class="font-medium text-surface-900 dark:text-surface-100">{session.moderator_name}</p>
                  {/if}
                </div>

                <div>
                  {#if session.speaker_names && session.speaker_names.length > 0}
                    <p class="text-xs uppercase tracking-wider text-surface-500 font-medium mb-1">Speakers</p>
                    <p class="text-sm text-surface-900 dark:text-surface-100">{session.speaker_names.join(', ')}</p>
                  {/if}
                </div>
              </div>

              <!-- Bottom: Action Buttons -->
              <div class="flex flex-wrap items-center justify-end gap-2 pt-4">
                <a href="/dashboard/{session.id}" class="btn-secondary text-sm flex items-center gap-1.5">
                  Manage
                </a>
                <button
                  type="button"
                  class="btn-secondary text-sm flex items-center gap-1.5"
                  onclick={() => startEditing(session)}
                >
                  <Pencil class="w-3.5 h-3.5" />
                  Edit
                </button>
                <button
                  type="button"
                  class="btn-danger text-sm flex items-center gap-1.5"
                  onclick={() => handleDelete(session.id)}
                >
                  <Trash2 class="w-3.5 h-3.5" />
                  Delete
                </button>
              </div>
            </div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</main>

<style>
  :global(body) {
    font-family: var(--font-body);
  }

  :global(h1, h2, h3, h4, h5, h6) {
    font-family: var(--font-heading);
    font-weight: 600;
  }
</style>
