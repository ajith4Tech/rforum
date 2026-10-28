<script lang="ts">
  import { goto } from '$app/navigation';
  import { createSession, deleteSession, updateSession, getSession, isAuthFailure } from '$lib/api';
  import { getEvents, getSessions, invalidateSessions } from '$lib/dataCache';
  import { parseEventDate } from '$lib/dates';
  import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
  import { Plus, Trash2, Pencil, Check, X, Copy, Search, AlertTriangle, RefreshCw } from 'lucide-svelte';
  import { onMount, onDestroy, tick } from 'svelte';
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
  let createError = $state('');
  let loading = $state(true);
  // Initial-load failure (shown instead of the "No sessions yet" empty state)
  // and failures of per-card actions, shown in a dismissible banner.
  let loadError = $state('');
  let actionError = $state('');
  let deleteTarget = $state<any | null>(null);
  let deleting = $state(false);
  let deleteError = $state('');

  function reportError(e: any, fallback: string) {
    if (isAuthFailure(e)) { goto('/login'); return; }
    actionError = e?.message || fallback;
  }

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

  async function initialLoad() {
    loading = true;
    loadError = '';
    try {
      const [eventsResult] = await Promise.all([
        getEvents({ limit: DROPDOWN_LIMIT }),
        loadSessions()
      ]);
      events = eventsResult.items;
    } catch (e: any) {
      if (isAuthFailure(e)) { goto('/login'); return false; }
      loadError = e?.message || 'Could not load sessions.';
      return false;
    } finally {
      loading = false;
      didInit = true;
    }
    return true;
  }

  onMount(async () => {
    if (!(await initialLoad())) return;

    // Deep link from the Events page ("Edit Session") or global search: open
    // this specific session's inline edit form and scroll it into view.
    if (typeof window !== 'undefined') {
      const targetId = new URLSearchParams(window.location.search).get('edit');
      if (targetId) {
        let target = sessions.find((s) => s.id === targetId);
        if (!target) {
          // Not on page 1 — narrow the list to it by its (unique) code so the
          // "Edit Session" link never lands on a page without that session.
          try {
            const found = await getSession(targetId);
            // Keep the search $effect from issuing a competing fetch whose
            // newer requestId would make this one's result get dropped.
            didInit = false;
            searchQuery = found.unique_code;
            debouncedQuery = found.unique_code;
            offset = 0;
            try { await loadSessions(); } finally { didInit = true; }
            target = sessions.find((s) => s.id === targetId);
          } catch (e) {
            reportError(e, 'That session could not be found.');
          }
        }
        if (target) startEditing(target);
        await tick();
        document.getElementById(`session-${targetId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  });

  onDestroy(() => { if (copyTimer) clearTimeout(copyTimer); });

  $effect(() => { applyDebouncedQuery(searchQuery); });

  // Search changes reset to page 1 — the initial fetch is already handled
  // by onMount above, so this only reacts to LATER changes to debouncedQuery.
  $effect(() => {
    debouncedQuery;
    if (!didInit) return;
    offset = 0;
    loadSessions().catch((e) => reportError(e, 'Could not search sessions.'));
  });

  function clearSearch() {
    searchQuery = '';
    debouncedQuery = '';
    activeIndex = -1;
  }

  async function goToPrevPage() {
    if (offset <= 0) return;
    offset = Math.max(0, offset - PAGE_SIZE);
    try { await loadSessions(); } catch (e) { reportError(e, 'Could not load sessions.'); }
  }

  async function goToNextPage() {
    if (offset + sessions.length >= total) return;
    offset = offset + PAGE_SIZE;
    try { await loadSessions(); } catch (e) { reportError(e, 'Could not load sessions.'); }
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
    createError = '';
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
      if (isAuthFailure(e)) { goto('/login'); return; }
      createError = e?.message || 'Could not create the session.';
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
      reportError(e, 'Could not save the session.');
    } finally {
      isSaving = false;
    }
  }

  function handleDelete(session: any) {
    deleteError = '';
    deleteTarget = session;
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    deleting = true;
    deleteError = '';
    try {
      await deleteSession(deleteTarget.id);
    } catch (e: any) {
      if (isAuthFailure(e)) { goto('/login'); return; }
      deleteError = e?.message || 'Could not delete the session.';
      return;
    } finally {
      deleting = false;
    }
    deleteTarget = null;
    invalidateSessions();
    try {
      await loadSessions();
      // If deleting emptied this page (and it isn't page 1), step back a page.
      if (sessions.length === 0 && offset > 0) {
        offset = Math.max(0, offset - PAGE_SIZE);
        await loadSessions();
      }
    } catch (e) {
      reportError(e, 'Session deleted, but the list could not be refreshed.');
    }
  }

  // navigator.clipboard only exists in secure contexts — Rforum is often
  // served over plain HTTP on a local network, so fall back to the legacy
  // execCommand path before reporting failure.
  async function writeClipboard(text: string): Promise<boolean> {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch { /* fall through to the legacy path */ }
    try {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand('copy');
      ta.remove();
      return ok;
    } catch {
      return false;
    }
  }

  let copyState = $state<{ id: string; ok: boolean; code: string } | null>(null);
  let copyTimer: ReturnType<typeof setTimeout> | null = null;

  async function copyCode(id: string, code: string) {
    const ok = await writeClipboard(code);
    copyState = { id, ok, code };
    if (copyTimer) clearTimeout(copyTimer);
    copyTimer = setTimeout(() => { copyState = null; }, ok ? 1500 : 4000);
  }

</script>

<svelte:head>
  <title>Sessions – Rforum</title>
</svelte:head>

<main class="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-6 sm:py-8">
  <div class="mb-6">
    <h1 class="text-3xl font-heading font-bold tracking-wide">Sessions</h1>
    <p class="text-sm text-surface-500 mt-1.5">Manage your presentations and moderate sessions</p>
  </div>

  <!-- One shared live region for copy feedback (the visible feedback is on the button itself). -->
  <p class="sr-only" role="status" aria-live="polite">
    {#if copyState}{copyState.ok ? `Copied session code ${copyState.code}` : `Could not copy session code ${copyState.code}`}{/if}
  </p>

  <!-- Create Session Form -->
  <section class="card mb-6" aria-labelledby="create-session-heading">
    <h2 id="create-session-heading" class="text-lg font-heading font-semibold mb-4">Create New Session</h2>
    <form onsubmit={(e) => { e.preventDefault(); handleCreate(); }} class="space-y-4">
      <div class="grid gap-4 md:grid-cols-2">
        <div>
          <label for="new-session-event" class="block text-xs uppercase tracking-wider text-surface-500 font-medium mb-2">Event</label>
          <select id="new-session-event" class="input-field w-full" bind:value={newSessionEventId}>
            <option value="" disabled>Select event</option>
            {#each events as event (event.id)}
              <option value={event.id}>
                {event.title} · {parseEventDate(event.event_date).toLocaleDateString()}
              </option>
            {/each}
          </select>
        </div>
        <div>
          <label for="new-session-title" class="block text-xs uppercase tracking-wider text-surface-500 font-medium mb-2">Session Title</label>
          <input id="new-session-title" type="text" bind:value={newTitle} placeholder="Enter session title" class="input-field" />
        </div>
      </div>

      <div class="grid gap-4 md:grid-cols-2">
        <div>
          <label for="new-session-moderator" class="block text-xs uppercase tracking-wider text-surface-500 font-medium mb-2">Moderator (optional)</label>
          <input id="new-session-moderator" type="text" bind:value={moderatorName} placeholder="Enter moderator name" class="input-field" />
        </div>
        <div>
          <label for="new-session-speaker" class="block text-xs uppercase tracking-wider text-surface-500 font-medium mb-2">Add Speakers</label>
          <div class="flex gap-2">
            <input
              id="new-session-speaker"
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
              <button type="button" class="text-surface-500 hover:text-danger transition-colors" onclick={() => removeSpeaker(index)} aria-label={`Remove ${speaker}`}>
                <X class="w-3 h-3" />
              </button>
            </span>
          {/each}
        </div>
      {/if}

      {#if createError}
        <p class="text-sm text-red-700 dark:text-red-300 flex items-center gap-2" role="alert">
          <AlertTriangle class="w-4 h-4 flex-shrink-0" /> {createError}
        </p>
      {/if}

      <div class="flex justify-end pt-2">
        <button
          type="submit"
          class="btn-primary flex items-center justify-center gap-2 w-full sm:w-auto"
          aria-busy={creating}
          disabled={creating || !newSessionEventId || !newTitle.trim()}
        >
          <Plus class="w-4 h-4" />
          {creating ? 'Creating...' : 'Create Session'}
        </button>
      </div>
    </form>
  </section>

  {#if actionError}
    <div class="mb-4 px-4 py-3 rounded-xl bg-danger/10 border border-danger/20 text-red-700 dark:text-red-300 text-sm flex items-start gap-2" role="alert">
      <AlertTriangle class="w-4 h-4 flex-shrink-0 mt-0.5" />
      <span class="flex-1 min-w-0 break-words">{actionError}</span>
      <button onclick={() => actionError = ''} class="text-xs underline flex-shrink-0">Dismiss</button>
    </div>
  {/if}

  <!-- Sessions List -->
  {#if loading}
    <div class="space-y-3" aria-busy="true" aria-label="Loading sessions">
      {#each Array(3) as _}
        <div class="card space-y-3">
          <div class="skeleton h-5 w-1/3 rounded"></div>
          <div class="skeleton h-16 w-full rounded-lg"></div>
        </div>
      {/each}
    </div>
  {:else if loadError}
    <div class="card flex flex-col items-center text-center py-12 gap-3" role="alert">
      <AlertTriangle class="w-8 h-8 text-danger" />
      <p class="text-sm font-medium">Couldn't load your sessions</p>
      <p class="text-xs text-surface-500 max-w-sm break-words">{loadError}</p>
      <button onclick={initialLoad} class="btn-secondary text-sm flex items-center gap-2">
        <RefreshCw class="w-4 h-4" /> Try again
      </button>
    </div>
  {:else}
    {#if total > 0 || searchQuery}
      <div class="relative mb-5">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-surface-500 pointer-events-none" />
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
            class="absolute right-3 top-1/2 -translate-y-1/2 text-surface-500 hover:text-surface-900 dark:hover:text-surface-200 transition-colors"
            onclick={clearSearch}
            aria-label="Clear search"
          >
            <X class="w-4 h-4" />
          </button>
        {/if}
      </div>
    {/if}

    {#if total === 0 && !debouncedQuery}
    <div class="card p-10 text-center border-dashed border-surface-300 dark:border-surface-700">
      <svg class="w-12 h-12 mx-auto text-surface-400 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
      </svg>
      <h3 class="text-lg font-semibold text-surface-900 dark:text-surface-100 mt-2">No sessions yet</h3>
      <p class="text-sm text-surface-500 mt-1">Create your first session using the form above</p>
    </div>
    {:else if sessions.length === 0}
      <div class="flex flex-col items-center justify-center text-center gap-3 py-16">
        <Search class="w-8 h-8 text-surface-500" />
        <p class="text-sm text-surface-500">No sessions match "{searchQuery}"</p>
        <button class="btn-secondary text-sm" onclick={clearSearch}>Clear search</button>
      </div>
    {:else}
    <div class="space-y-3">
      {#each sessions as session, i (session.id)}
        {@const copied = copyState?.id === session.id ? copyState : null}
        <!-- Session Card -->
        <div
          id={`session-${session.id}`}
          class="card transition-shadow duration-300 {highlightedSessionId === session.id ? 'ring-2 ring-brand-500' : ''} {activeIndex === i ? 'ring-2 ring-brand-400/60' : ''}">
          {#if editingSessionId === session.id}
            <!-- Edit Mode -->
            <div class="space-y-4">
              <div class="grid gap-4 md:grid-cols-3">
                <div>
                  <label for="edit-title-{session.id}" class="block text-xs uppercase tracking-wider text-surface-500 font-medium mb-2">Title</label>
                  <input id="edit-title-{session.id}" type="text" bind:value={editTitle} class="input-field" placeholder="Session title" />
                </div>
                <div>
                  <label for="edit-moderator-{session.id}" class="block text-xs uppercase tracking-wider text-surface-500 font-medium mb-2">Moderator</label>
                  <input id="edit-moderator-{session.id}" type="text" bind:value={editModerator} class="input-field" placeholder="Moderator name" />
                </div>
                <div>
                  <label for="edit-speaker-{session.id}" class="block text-xs uppercase tracking-wider text-surface-500 font-medium mb-2">Add Speakers</label>
                  <div class="flex gap-2">
                    <input
                      id="edit-speaker-{session.id}"
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
                    <button type="button" class="btn-secondary px-3" onclick={addEditSpeaker} aria-label="Add speaker">
                      <Plus class="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>

              {#if editSpeakers.length > 0}
                <div class="flex flex-wrap gap-2">
                  {#each editSpeakers as speaker, index (speaker + index)}
                    <span class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-surface-100 dark:bg-surface-800 text-xs font-medium">
                      {speaker}
                      <button type="button" class="text-surface-500 hover:text-danger transition-colors" onclick={() => removeEditSpeaker(index)} aria-label={`Remove ${speaker}`}>
                        <X class="w-3 h-3" />
                      </button>
                    </span>
                  {/each}
                </div>
              {/if}

              <div class="flex justify-end gap-2 pt-2">
                <button type="button" class="btn-secondary flex items-center gap-2" onclick={cancelEditing} disabled={isSaving}>
                  <X class="w-4 h-4" />
                  Cancel
                </button>
                <button type="button" class="btn-primary flex items-center gap-2" onclick={() => saveEditing(session.id)} aria-busy={isSaving} disabled={isSaving || !editTitle.trim()}>
                  <Check class="w-4 h-4" />
                  {isSaving ? 'Saving...' : 'Save'}
                </button>
              </div>
            </div>
          {:else}
            <!-- View Mode -->
            <div class="flex flex-wrap items-center gap-x-3 gap-y-2 mb-3">
              <h3 class="text-xl font-heading font-semibold text-surface-900 dark:text-surface-100 truncate min-w-0">{session.title}</h3>
              {#if session.is_live}
                <span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-red-500/10 border border-red-500/30 text-xs font-semibold text-red-700 dark:text-red-400">
                  <span class="w-2 h-2 bg-red-500 rounded-full animate-pulse"></span>
                  LIVE
                </span>
              {:else}
                <span class="inline-flex items-center px-2.5 py-0.5 rounded-full bg-surface-100 dark:bg-surface-800 border border-surface-200 dark:border-surface-700 text-xs font-semibold text-surface-600 dark:text-surface-400">
                  Not live
                </span>
              {/if}
            </div>

            <!-- Session Info and Moderator/Speakers -->
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 py-3 border-y border-surface-200 dark:border-surface-800">
              <div>
                <p class="text-xs uppercase tracking-wider text-surface-500 font-medium mb-1">Session Code</p>
                <button
                  onclick={() => copyCode(session.id, session.unique_code)}
                  class="font-mono font-semibold transition-colors flex items-center gap-2
                         {copied && !copied.ok ? 'text-red-700 dark:text-red-300' : 'text-surface-900 dark:text-surface-100 hover:text-brand-600 dark:hover:text-brand-400'}"
                  aria-label={`Copy session code ${session.unique_code}`}
                  title="Copy session code"
                >
                  {session.unique_code}
                  {#if copied?.ok}
                    <Check class="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                    <span class="text-xs font-sans font-medium text-emerald-700 dark:text-emerald-400">Copied</span>
                  {:else if copied}
                    <AlertTriangle class="w-3.5 h-3.5" />
                    <span class="text-xs font-sans font-medium">Copy failed — select the code manually</span>
                  {:else}
                    <Copy class="w-3.5 h-3.5" />
                  {/if}
                </button>
                <p class="text-xs text-surface-500 mt-1">Created {new Date(session.created_at).toLocaleDateString()}</p>
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

            <!-- Action Buttons -->
            <div class="flex flex-wrap items-center justify-end gap-2 pt-3">
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
                onclick={() => handleDelete(session)}
                aria-label={`Delete session ${session.title}`}
              >
                <Trash2 class="w-3.5 h-3.5" />
                Delete
              </button>
            </div>
          {/if}
        </div>
      {/each}
    </div>
    <PaginationBar {total} limit={PAGE_SIZE} {offset} itemCount={sessions.length} onPrev={goToPrevPage} onNext={goToNextPage} />
    {/if}
  {/if}
</main>

<ConfirmDialog
  open={!!deleteTarget}
  tone="danger"
  title="Delete session?"
  description={deleteTarget ? `“${deleteTarget.title}” (code ${deleteTarget.unique_code}) and its slides and responses will be permanently deleted.` : ''}
  confirmLabel="Delete session"
  loading={deleting}
  onConfirm={confirmDelete}
  onCancel={() => { if (!deleting) deleteTarget = null; }}
>
  {#if deleteError}
    <p class="text-xs text-red-700 dark:text-red-300 flex items-center gap-1.5" role="alert">
      <AlertTriangle class="w-3.5 h-3.5 flex-shrink-0" /> {deleteError}
    </p>
  {/if}
</ConfirmDialog>
