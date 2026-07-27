<script lang="ts">
  import { goto } from '$app/navigation';
  import { createSession, deleteSession, updateSession } from '$lib/api';
  import { getEvents, getSessions, invalidateSessions } from '$lib/dataCache';
  import { Plus, Trash2, Pencil, Check, X, Copy, Search } from 'lucide-svelte';
  import { onMount, tick } from 'svelte';
  import { debounce } from '$lib/debounce';
  import { cycleSearchIndex } from '$lib/search';
  import PaginationBar from '$lib/components/PaginationBar.svelte';

  const PAGE_SIZE = 20;
  // Events here are only the "create session" dropdown source, not a
  // paginated view — 100 is the backend's MAX_PAGE_SIZE, a bounded stand-in
  // for "every event" that avoids ever fetching the whole table.
  const DROPDOWN_LIMIT = 100;

  let sessions: any[] = $state([]);
  let total = $state(0);
  let offset = $state(0);
  let didInit = false;
  let requestId = 0;
  let events: any[] = $state([]);
  let searchQuery = $state('');
  let debouncedQuery = $state('');
  let activeIndex = $state(-1);
  let highlightedSessionId: string | null = $state(null);
  const applyDebouncedQuery = debounce((value: string) => { debouncedQuery = value; activeIndex = -1; }, 250);
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

  async function loadSessions() {
    const myRequest = ++requestId;
    const result = await getSessions({ limit: PAGE_SIZE, offset, search: debouncedQuery || undefined });
    if (myRequest !== requestId) return; // a newer request already landed
    sessions = result.items;
    total = result.total;
  }

  onMount(async () => {
    try {
      const [eventsResult] = await Promise.all([
        getEvents({ limit: DROPDOWN_LIMIT }),
        loadSessions()
      ]);
      events = eventsResult.items;
    } catch {
      goto('/login');
    } finally {
      loading = false;
      didInit = true;
    }

    // Deep link from the Events page ("Edit Session") or global search: open
    // this specific session's inline edit form and scroll it into view.
    if (typeof window !== 'undefined') {
      const targetId = new URLSearchParams(window.location.search).get('edit');
      if (targetId) {
        const target = sessions.find((s) => s.id === targetId);
        if (target) startEditing(target);
        await tick();
        document.getElementById(`session-${targetId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  });

  $effect(() => { applyDebouncedQuery(searchQuery); });

  // Search changes reset to page 1 — the initial fetch is already handled
  // by onMount above, so this only reacts to LATER changes to debouncedQuery.
  $effect(() => {
    debouncedQuery;
    if (!didInit) return;
    offset = 0;
    loadSessions();
  });

  function clearSearch() {
    searchQuery = '';
    debouncedQuery = '';
    activeIndex = -1;
  }

  async function goToPrevPage() {
    if (offset <= 0) return;
    offset = Math.max(0, offset - PAGE_SIZE);
    await loadSessions();
  }

  async function goToNextPage() {
    if (offset + sessions.length >= total) return;
    offset = offset + PAGE_SIZE;
    await loadSessions();
  }

  function handleSearchKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      if (searchQuery) { e.stopPropagation(); clearSearch(); }
      return;
    }
    if (!sessions.length) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      activeIndex = cycleSearchIndex(e.key, activeIndex, sessions.length) ?? activeIndex;
    } else if (e.key === 'Enter' && activeIndex >= 0) {
      e.preventDefault();
      const target = sessions[activeIndex];
      document.getElementById(`session-${target.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      highlightedSessionId = target.id;
      setTimeout(() => { highlightedSessionId = null; }, 2000);
    }
  }

  async function handleCreate() {
    if (!newTitle.trim() || !newSessionEventId) return;
    creating = true;
    try {
      await createSession(
        newTitle.trim(),
        newSessionEventId,
        moderatorName.trim() || null,
        speakerNames
      );
      invalidateSessions();
      // New sessions sort newest-first, so they land on page 1.
      offset = 0;
      await loadSessions();
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
      await updateSession(sessionId, {
        title: editTitle.trim(),
        moderator_name: editModerator.trim() || null,
        speaker_names: editSpeakers
      });
      invalidateSessions();
      await loadSessions();
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
    invalidateSessions();
    await loadSessions();
    // If deleting emptied this page (and it isn't page 1), step back a page.
    if (sessions.length === 0 && offset > 0) {
      offset = Math.max(0, offset - PAGE_SIZE);
      await loadSessions();
    }
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
    <div class="space-y-3" aria-hidden="true">
      {#each Array(3) as _}
        <div class="card p-6 space-y-3 border border-surface-200 dark:border-surface-800">
          <div class="skeleton h-5 w-1/3 rounded"></div>
          <div class="skeleton h-16 w-full rounded-lg"></div>
        </div>
      {/each}
    </div>
  {:else}
    {#if total > 0 || searchQuery}
      <div class="relative mb-5">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-surface-400" />
        <input
          type="search"
          placeholder="Search sessions by name, moderator, code, or file…"
          bind:value={searchQuery}
          onkeydown={handleSearchKeydown}
          class="input-field pl-9 pr-9 text-sm py-2.5 w-full"
          aria-label="Search sessions"
        />
        {#if searchQuery}
          <button
            class="absolute right-3 top-1/2 -translate-y-1/2 text-surface-400 hover:text-surface-200"
            onclick={clearSearch}
            aria-label="Clear search"
          >
            <X class="w-4 h-4" />
          </button>
        {/if}
      </div>
    {/if}

    {#if total === 0 && !debouncedQuery}
    <div class="card p-12 text-center border border-dashed border-surface-300 dark:border-surface-700">
      <svg class="w-12 h-12 mx-auto text-surface-400 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
      </svg>
      <h3 class="text-lg font-semibold text-surface-900 dark:text-surface-100 mt-2">No sessions yet</h3>
      <p class="text-sm text-surface-500 mt-1">Create your first session to get started</p>
    </div>
    {:else if sessions.length === 0}
      <div class="flex flex-col items-center justify-center text-center gap-3 py-16">
        <Search class="w-8 h-8 text-surface-400" />
        <p class="text-sm text-surface-400">No sessions match "{searchQuery}"</p>
        <button class="btn-secondary text-sm" onclick={clearSearch}>Clear search</button>
      </div>
    {:else}
    <div class="space-y-3">
      {#each sessions as session, i (session.id)}
        <!-- Session Card -->
        <div
          id={`session-${session.id}`}
          class="card border border-surface-200 dark:border-surface-800 hover:border-surface-300 dark:hover:border-surface-700 transition-all duration-200 {highlightedSessionId === session.id ? 'ring-2 ring-brand-500' : ''} {activeIndex === i ? 'ring-2 ring-brand-400/60' : ''}">
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
    <PaginationBar {total} limit={PAGE_SIZE} {offset} itemCount={sessions.length} onPrev={goToPrevPage} onNext={goToNextPage} />
    {/if}
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
