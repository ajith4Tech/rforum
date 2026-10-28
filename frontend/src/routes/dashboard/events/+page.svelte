<script lang="ts">
  import { goto } from '$app/navigation';
  import {
    createEvent,
    updateEvent,
    deleteEvent,
    setEventSessions,
    createSession,
    isAuthFailure
  } from '$lib/api';
  import { getEvents, getSessions, invalidateEvents, invalidateSessions } from '$lib/dataCache';
  import { Calendar, Plus, Search, X, AlertTriangle, RefreshCw } from 'lucide-svelte';
  import { onMount, tick } from 'svelte';
  import { debounce } from '$lib/debounce';
  import { cycleSearchIndex } from '$lib/search';
  import EventCard from '$lib/components/EventCard.svelte';
  import PaginationBar from '$lib/components/PaginationBar.svelte';
  import Modal from '$lib/components/Modal.svelte';
  import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';

  const PAGE_SIZE = 20;
  // Sessions here are only the "assign to event" dropdown source, not a
  // paginated view — 100 is the backend's MAX_PAGE_SIZE, a bounded stand-in
  // for "every session" that avoids ever fetching the whole table.
  const DROPDOWN_LIMIT = 100;

  let sessions: any[] = $state([]);
  let events: any[] = $state([]);
  let total = $state(0);
  let offset = $state(0);
  let loading = $state(true);
  let didInit = false;
  let requestId = 0;
  let searchQuery = $state('');
  let debouncedQuery = $state('');
  let activeIndex = $state(-1);
  let highlightedEventId: string | null = $state(null);
  const applyDebouncedQuery = debounce((value: string) => { debouncedQuery = value; activeIndex = -1; }, 250);
  let newEventTitle = $state('');
  let newEventDate = $state('');
  let newEventDescription = $state('');
  let creatingEvent = $state(false);
  let savingEventId = $state<string | null>(null);
  // Tracks which event's inline "create a new session" is in flight, so
  // only that event's card shows a loading state — separate from
  // savingEventId (which covers the existing select + Add flow).
  let creatingSessionForEventId = $state<string | null>(null);
  let eventSelections: Record<string, string[]> = $state({});
  let addSessionSelections: Record<string, string> = $state({});
  let showCreateEvent = $state(false);
  let showEditEvent = $state(false);
  let editingEventId = $state<string | null>(null);
  let editEventTitle = $state('');
  let editEventDate = $state('');
  let editEventDescription = $state('');
  let savingEditEvent = $state(false);
  let createEventError = $state('');
  let editEventError = $state('');
  // Initial-load failure (shown instead of the "No events yet" empty state)
  // and failures of per-card actions, shown in a dismissible banner.
  let loadError = $state('');
  let actionError = $state('');
  let deleteTarget = $state<any | null>(null);
  let deletingEvent = $state(false);
  let deleteError = $state('');

  function reportError(e: any, fallback: string) {
    if (isAuthFailure(e)) { goto('/login'); return; }
    actionError = e?.message || fallback;
  }

  async function loadEvents() {
    const myRequest = ++requestId;
    const result = await getEvents({ limit: PAGE_SIZE, offset, search: debouncedQuery || undefined });
    if (myRequest !== requestId) return; // a newer request already landed
    events = result.items;
    total = result.total;
    eventSelections = Object.fromEntries(
      events.map((event) => [event.id, (event.sessions || []).map((s: any) => s.id)])
    );
  }

  async function loadSessionsForDropdown() {
    const result = await getSessions({ limit: DROPDOWN_LIMIT });
    sessions = result.items;
  }

  async function initialLoad() {
    loading = true;
    loadError = '';
    try {
      await Promise.all([loadSessionsForDropdown(), loadEvents()]);
    } catch (e: any) {
      if (isAuthFailure(e)) { goto('/login'); return; }
      loadError = e?.message || 'Could not load events.';
    } finally {
      loading = false;
      didInit = true;
    }
  }

  onMount(async () => {
    await initialLoad();

    // Deep link from global search (?event=<id>): scroll to and briefly highlight that card
    if (typeof window !== 'undefined') {
      const targetId = new URLSearchParams(window.location.search).get('event');
      if (targetId) {
        await tick();
        const el = document.getElementById(`event-${targetId}`);
        el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        highlightedEventId = targetId;
        setTimeout(() => { highlightedEventId = null; }, 2000);
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
    loadEvents().catch((e) => reportError(e, 'Could not search events.'));
  });

  function clearSearch() {
    searchQuery = '';
    debouncedQuery = '';
    activeIndex = -1;
  }

  async function goToPrevPage() {
    if (offset <= 0) return;
    offset = Math.max(0, offset - PAGE_SIZE);
    try { await loadEvents(); } catch (e) { reportError(e, 'Could not load events.'); }
  }

  async function goToNextPage() {
    if (offset + events.length >= total) return;
    offset = offset + PAGE_SIZE;
    try { await loadEvents(); } catch (e) { reportError(e, 'Could not load events.'); }
  }

  function handleSearchKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      if (searchQuery) { e.stopPropagation(); clearSearch(); }
      return;
    }
    if (!events.length) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      activeIndex = cycleSearchIndex(e.key, activeIndex, events.length) ?? activeIndex;
    } else if (e.key === 'Enter' && activeIndex >= 0) {
      e.preventDefault();
      const target = events[activeIndex];
      document.getElementById(`event-${target.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      highlightedEventId = target.id;
      setTimeout(() => { highlightedEventId = null; }, 2000);
    }
  }

  async function handleCreateEvent() {
    if (!newEventTitle.trim() || !newEventDate) return;
    creatingEvent = true;
    createEventError = '';
    try {
      await createEvent({
        title: newEventTitle.trim(),
        event_date: newEventDate,
        description: newEventDescription.trim() || null
      });
      invalidateEvents();
      // New events sort newest-first, so they land on page 1.
      offset = 0;
      await loadEvents();
      newEventTitle = '';
      newEventDate = '';
      newEventDescription = '';
      showCreateEvent = false;
    } catch (e: any) {
      createEventError = e?.message || 'Could not create the event.';
    } finally {
      creatingEvent = false;
    }
  }

  async function handleSaveEventSessions(eventId: string) {
    savingEventId = eventId;
    try {
      await setEventSessions(eventId, eventSelections[eventId] || []);
      invalidateEvents();
      await loadEvents();
    } catch (e: any) {
      reportError(e, 'Could not update this event\'s sessions.');
    } finally {
      savingEventId = null;
    }
  }

  async function handleAddSession(eventId: string) {
    const selected = addSessionSelections[eventId];
    if (!selected) return;
    const current = eventSelections[eventId] || [];
    if (current.includes(selected)) return;
    eventSelections = { ...eventSelections, [eventId]: [...current, selected] };
    addSessionSelections = { ...addSessionSelections, [eventId]: '' };
    await handleSaveEventSessions(eventId);
  }

  async function handleRemoveSession(eventId: string, sessionId: string) {
    const current = eventSelections[eventId] || [];
    const next = current.filter((id) => id !== sessionId);
    if (next.length === current.length) return;
    eventSelections = { ...eventSelections, [eventId]: next };
    await handleSaveEventSessions(eventId);
  }

  /** Create a brand-new session and attach it to this event, without ever
      leaving the Events page — the flow the PM's feedback asked for. Reuses
      the existing createSession API (same one the Sessions page itself
      uses) and the existing handleSaveEventSessions attach step, so this is
      additive glue rather than a new attach mechanism. */
  async function handleCreateAndAddSession(eventId: string, title: string, moderatorName: string) {
    creatingSessionForEventId = eventId;
    try {
      const newSession = await createSession(title, eventId, moderatorName || null, []);
      const current = eventSelections[eventId] || [];
      eventSelections = { ...eventSelections, [eventId]: [...current, newSession.id] };
      // createSession() bypasses the cache layer entirely — without this,
      // loadSessionsForDropdown() below would serve the stale cached
      // sessions list (missing the one just created) until a hard reload
      // clears the in-memory cache Map. This was the actual "need a
      // refresh to see it" bug.
      invalidateSessions();
      await loadSessionsForDropdown();
      await handleSaveEventSessions(eventId);
    } catch (e: any) {
      reportError(e, 'Could not create the session.');
      // Rethrow so EventCard keeps the typed title/moderator for a retry.
      throw e;
    } finally {
      creatingSessionForEventId = null;
    }
  }

  function handleDeleteEvent(id: string) {
    deleteTarget = events.find((e) => e.id === id) ?? null;
    deleteError = '';
  }

  async function confirmDeleteEvent() {
    if (!deleteTarget) return;
    deletingEvent = true;
    deleteError = '';
    try {
      await deleteEvent(deleteTarget.id);
    } catch (e: any) {
      if (isAuthFailure(e)) { goto('/login'); return; }
      deleteError = e?.message || 'Could not delete the event.';
      return;
    } finally {
      deletingEvent = false;
    }
    deleteTarget = null;
    invalidateEvents();
    try {
      await loadEvents();
      // If deleting emptied this page (and it isn't page 1), step back a page.
      if (events.length === 0 && offset > 0) {
        offset = Math.max(0, offset - PAGE_SIZE);
        await loadEvents();
      }
    } catch (e) {
      reportError(e, 'Event deleted, but the list could not be refreshed.');
    }
  }

  async function handleTogglePublish(eventId: string, currentStatus: boolean) {
    try {
      await updateEvent(eventId, { is_published: !currentStatus });
      invalidateEvents();
      await loadEvents();
    } catch (e: any) {
      reportError(e, 'Could not change the event\'s visibility.');
    }
  }

  function startEditEvent(event: any) {
    editingEventId = event.id;
    editEventTitle = event.title || '';
    editEventDate = event.event_date || '';
    editEventDescription = event.description || '';
    editEventError = '';
    showEditEvent = true;
  }

  async function handleUpdateEvent() {
    if (!editingEventId || !editEventTitle.trim() || !editEventDate) return;
    savingEditEvent = true;
    editEventError = '';
    try {
      await updateEvent(editingEventId, {
        title: editEventTitle.trim(),
        event_date: editEventDate,
        description: editEventDescription.trim() || null
      });
      invalidateEvents();
      await loadEvents();
      showEditEvent = false;
      editingEventId = null;
    } catch (e: any) {
      editEventError = e?.message || 'Could not save the event.';
    } finally {
      savingEditEvent = false;
    }
  }

  function getSelectedSessions(eventId: string) {
    const ids = eventSelections[eventId] || [];
    return ids.map((id) => sessions.find((session) => session.id === id)).filter(Boolean);
  }

  function getAvailableSessions(eventId: string) {
    const selected = new Set(eventSelections[eventId] || []);
    return sessions.filter((session) => !selected.has(session.id));
  }

  function openCreateEvent() {
    createEventError = '';
    showCreateEvent = true;
  }
</script>

<svelte:head>
  <title>Events – Rforum</title>
</svelte:head>

<main class="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-6 sm:py-8">
  <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-6">
    <div>
      <h1 class="text-3xl font-heading font-bold tracking-wide">All Events</h1>
      <p class="text-sm text-surface-500 mt-1.5">Manage your events and their sessions</p>
    </div>
    <button class="btn-primary text-sm flex items-center justify-center gap-2 w-full sm:w-auto" onclick={openCreateEvent}>
      <Plus class="w-4 h-4" />
      Create Event
    </button>
  </div>

  {#if actionError}
    <div class="mb-4 px-4 py-3 rounded-xl bg-danger/10 border border-danger/20 text-red-700 dark:text-red-300 text-sm flex items-start gap-2" role="alert">
      <AlertTriangle class="w-4 h-4 flex-shrink-0 mt-0.5" />
      <span class="flex-1 min-w-0 break-words">{actionError}</span>
      <button onclick={() => actionError = ''} class="text-xs underline flex-shrink-0">Dismiss</button>
    </div>
  {/if}

  {#if loading}
    <div class="space-y-3" aria-busy="true" aria-label="Loading events">
      {#each Array(3) as _}
        <div class="card p-6 space-y-3">
          <div class="skeleton h-5 w-1/3 rounded"></div>
          <div class="skeleton h-3 w-2/3 rounded"></div>
          <div class="skeleton h-16 w-full rounded-lg"></div>
        </div>
      {/each}
    </div>
  {:else if loadError}
    <div class="card flex flex-col items-center text-center py-12 gap-3" role="alert">
      <AlertTriangle class="w-8 h-8 text-danger" />
      <p class="text-sm font-medium">Couldn't load your events</p>
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
          placeholder="Search events by name, description, or moderator…"
          bind:value={searchQuery}
          onkeydown={handleSearchKeydown}
          class="input-field pl-9 pr-9 text-sm py-2.5 w-full"
          aria-label="Search events"
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
      <div class="flex flex-col items-center justify-center text-center gap-4 py-16">
        <div class="w-14 h-14 flex items-center justify-center rounded-2xl bg-brand-500/10">
          <Calendar class="w-7 h-7 text-brand-500" />
        </div>
        <div>
          <h2 class="text-lg font-semibold">No events yet</h2>
          <p class="text-sm text-surface-500 mt-1">Create your first event to get started</p>
        </div>
        <button class="btn-primary text-sm" onclick={openCreateEvent}>Create Event</button>
      </div>
    {:else if events.length === 0}
      <div class="flex flex-col items-center justify-center text-center gap-3 py-16">
        <Search class="w-8 h-8 text-surface-500" />
        <p class="text-sm text-surface-500">No events match "{searchQuery}"</p>
        <button class="btn-secondary text-sm" onclick={clearSearch}>Clear search</button>
      </div>
    {:else}
      <div class="space-y-3">
        {#each events as event, i (event.id)}
          <div
            id={`event-${event.id}`}
            class="rounded-2xl transition-shadow duration-300 {highlightedEventId === event.id ? 'ring-2 ring-brand-500' : ''} {activeIndex === i ? 'ring-2 ring-brand-400/60' : ''}"
          >
            <EventCard
              {event}
              sessions={getSelectedSessions(event.id)}
              availableSessions={getAvailableSessions(event.id)}
              saving={savingEventId === event.id}
              creatingSession={creatingSessionForEventId === event.id}
              addSessionSelection={addSessionSelections[event.id] || ''}
              onEdit={startEditEvent}
              onTogglePublish={handleTogglePublish}
              onDelete={handleDeleteEvent}
              onAddSession={handleAddSession}
              onRemoveSession={handleRemoveSession}
              onAddSessionSelectionChange={(eid, val) => addSessionSelections = { ...addSessionSelections, [eid]: val }}
              onCreateAndAddSession={handleCreateAndAddSession}
            />
          </div>
        {/each}
      </div>
      <PaginationBar {total} limit={PAGE_SIZE} {offset} itemCount={events.length} onPrev={goToPrevPage} onNext={goToNextPage} />
    {/if}
  {/if}
</main>

<Modal open={showCreateEvent} onClose={() => showCreateEvent = false} labelledBy="create-event-title">
  <h2 id="create-event-title" class="text-lg font-semibold mb-4 pr-8">Create Event</h2>
  <form onsubmit={(e) => { e.preventDefault(); handleCreateEvent(); }} class="grid gap-3">
    <div class="grid gap-3 md:grid-cols-2">
      <input type="text" bind:value={newEventTitle} placeholder="Event title..." aria-label="Event title" class="input-field" />
      <input type="date" bind:value={newEventDate} aria-label="Event date" class="input-field" />
    </div>
    <textarea rows="2" bind:value={newEventDescription} placeholder="Description (optional)" aria-label="Description (optional)" class="input-field"></textarea>
    {#if createEventError}
      <p class="text-sm text-red-700 dark:text-red-300 flex items-center gap-2" role="alert">
        <AlertTriangle class="w-4 h-4 flex-shrink-0" /> {createEventError}
      </p>
    {/if}
    <div class="flex flex-col-reverse sm:flex-row justify-end gap-2">
      <button type="button" class="btn-secondary text-sm" onclick={() => showCreateEvent = false}>Cancel</button>
      <button type="submit" class="btn-primary text-sm" aria-busy={creatingEvent} disabled={creatingEvent || !newEventTitle.trim() || !newEventDate}>
        {creatingEvent ? 'Creating...' : 'Create Event'}
      </button>
    </div>
  </form>
</Modal>

<Modal open={showEditEvent} onClose={() => showEditEvent = false} labelledBy="edit-event-title">
  <h2 id="edit-event-title" class="text-lg font-semibold mb-4 pr-8">Edit Event</h2>
  <form onsubmit={(e) => { e.preventDefault(); handleUpdateEvent(); }} class="grid gap-3">
    <div class="grid gap-3 md:grid-cols-2">
      <input type="text" bind:value={editEventTitle} placeholder="Event title..." aria-label="Event title" class="input-field" />
      <input type="date" bind:value={editEventDate} aria-label="Event date" class="input-field" />
    </div>
    <textarea rows="2" bind:value={editEventDescription} placeholder="Description (optional)" aria-label="Description (optional)" class="input-field"></textarea>
    {#if editEventError}
      <p class="text-sm text-red-700 dark:text-red-300 flex items-center gap-2" role="alert">
        <AlertTriangle class="w-4 h-4 flex-shrink-0" /> {editEventError}
      </p>
    {/if}
    <div class="flex flex-col-reverse sm:flex-row justify-end gap-2">
      <button type="button" class="btn-secondary text-sm" onclick={() => showEditEvent = false}>Cancel</button>
      <button type="submit" class="btn-primary text-sm" aria-busy={savingEditEvent} disabled={savingEditEvent || !editEventTitle.trim() || !editEventDate}>
        {savingEditEvent ? 'Saving...' : 'Save Changes'}
      </button>
    </div>
  </form>
</Modal>

<ConfirmDialog
  open={!!deleteTarget}
  tone="danger"
  title="Delete event?"
  description={deleteTarget ? `“${deleteTarget.title}” will be permanently deleted. Its sessions are kept but no longer assigned to an event.` : ''}
  confirmLabel="Delete event"
  loading={deletingEvent}
  onConfirm={confirmDeleteEvent}
  onCancel={() => { if (!deletingEvent) deleteTarget = null; }}
>
  {#if deleteError}
    <p class="text-xs text-red-700 dark:text-red-300 flex items-center gap-1.5" role="alert">
      <AlertTriangle class="w-3.5 h-3.5 flex-shrink-0" /> {deleteError}
    </p>
  {/if}
</ConfirmDialog>
