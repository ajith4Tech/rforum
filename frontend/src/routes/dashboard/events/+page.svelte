<script lang="ts">
  import { goto } from '$app/navigation';
  import {
    createEvent,
    updateEvent,
    deleteEvent,
    setEventSessions
  } from '$lib/api';
  import { getEvents, getSessions, invalidateEvents } from '$lib/dataCache';
  import { Calendar, Plus, Search, X } from 'lucide-svelte';
  import { onMount, tick } from 'svelte';
  import { debounce } from '$lib/debounce';
  import { cycleSearchIndex } from '$lib/search';
  import EventCard from '$lib/components/EventCard.svelte';
  import PaginationBar from '$lib/components/PaginationBar.svelte';

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
  let eventSelections: Record<string, string[]> = $state({});
  let addSessionSelections: Record<string, string> = $state({});
  let showCreateEvent = $state(false);
  let showEditEvent = $state(false);
  let editingEventId = $state<string | null>(null);
  let editEventTitle = $state('');
  let editEventDate = $state('');
  let editEventDescription = $state('');
  let savingEditEvent = $state(false);

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

  onMount(async () => {
    try {
      const [sessionsResult] = await Promise.all([
        getSessions({ limit: DROPDOWN_LIMIT }),
        loadEvents()
      ]);
      sessions = sessionsResult.items;
    } catch {
      goto('/login');
    } finally {
      loading = false;
      didInit = true;
    }

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
    loadEvents();
  });

  function clearSearch() {
    searchQuery = '';
    debouncedQuery = '';
    activeIndex = -1;
  }

  async function goToPrevPage() {
    if (offset <= 0) return;
    offset = Math.max(0, offset - PAGE_SIZE);
    await loadEvents();
  }

  async function goToNextPage() {
    if (offset + events.length >= total) return;
    offset = offset + PAGE_SIZE;
    await loadEvents();
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
      alert(e.message);
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
      alert(e.message);
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

  async function handleDeleteEvent(id: string) {
    if (!confirm('Delete this event?')) return;
    await deleteEvent(id);
    invalidateEvents();
    await loadEvents();
    // If deleting emptied this page (and it isn't page 1), step back a page.
    if (events.length === 0 && offset > 0) {
      offset = Math.max(0, offset - PAGE_SIZE);
      await loadEvents();
    }
  }

  async function handleTogglePublish(eventId: string, currentStatus: boolean) {
    try {
      await updateEvent(eventId, { is_published: !currentStatus });
      invalidateEvents();
      await loadEvents();
    } catch (e: any) {
      alert(e.message);
    }
  }

  function startEditEvent(event: any) {
    editingEventId = event.id;
    editEventTitle = event.title || '';
    editEventDate = event.event_date || '';
    editEventDescription = event.description || '';
    showEditEvent = true;
  }

  async function handleUpdateEvent() {
    if (!editingEventId || !editEventTitle.trim() || !editEventDate) return;
    savingEditEvent = true;
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
      alert(e.message);
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

  function handleGlobalKeydown(e: KeyboardEvent) {
    if (e.key !== 'Escape') return;
    if (showCreateEvent) showCreateEvent = false;
    else if (showEditEvent) showEditEvent = false;
  }
</script>

<svelte:window onkeydown={handleGlobalKeydown} />

<svelte:head>
  <title>Events – Rforum</title>
</svelte:head>

<main class="flex-1 max-w-5xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-6 sm:py-7">
  <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-6">
    <div>
      <h1 class="text-3xl font-heading font-bold tracking-wide">All Events</h1>
      <p class="text-sm text-surface-500 mt-1.5">Manage your events and their sessions</p>
    </div>
    <button class="btn-primary text-sm flex items-center justify-center gap-2 w-full sm:w-auto" onclick={() => showCreateEvent = true}>
      <Plus class="w-4 h-4" />
      Create Event
    </button>
  </div>

  {#if loading}
    <div class="space-y-3" aria-hidden="true">
      {#each Array(3) as _}
        <div class="card p-6 space-y-3">
          <div class="skeleton h-5 w-1/3 rounded"></div>
          <div class="skeleton h-3 w-2/3 rounded"></div>
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
          placeholder="Search events by name, description, or moderator…"
          bind:value={searchQuery}
          onkeydown={handleSearchKeydown}
          class="input-field pl-9 pr-9 text-sm py-2.5 w-full"
          aria-label="Search events"
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
      <div class="flex flex-col items-center justify-center text-center gap-4 py-20">
        <div class="w-14 h-14 flex items-center justify-center rounded-2xl bg-brand-500/10">
          <Calendar class="w-7 h-7 text-brand-500" />
        </div>
        <div>
          <h3 class="text-lg font-semibold">No events yet</h3>
          <p class="text-sm text-surface-400 mt-1">Create your first event to get started</p>
        </div>
        <button class="btn-primary text-sm" onclick={() => showCreateEvent = true}>Create Event</button>
      </div>
    {:else if events.length === 0}
      <div class="flex flex-col items-center justify-center text-center gap-3 py-16">
        <Search class="w-8 h-8 text-surface-400" />
        <p class="text-sm text-surface-400">No events match "{searchQuery}"</p>
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
              addSessionSelection={addSessionSelections[event.id] || ''}
              onEdit={startEditEvent}
              onTogglePublish={handleTogglePublish}
              onDelete={handleDeleteEvent}
              onAddSession={handleAddSession}
              onRemoveSession={handleRemoveSession}
              onAddSessionSelectionChange={(eid, val) => addSessionSelections = { ...addSessionSelections, [eid]: val }}
            />
          </div>
        {/each}
      </div>
      <PaginationBar {total} limit={PAGE_SIZE} {offset} itemCount={events.length} onPrev={goToPrevPage} onNext={goToNextPage} />
    {/if}
  {/if}
</main>

{#if showCreateEvent}
  <div class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center px-4 z-50"
       onclick={(e) => { if (e.target === e.currentTarget) showCreateEvent = false; }}
       role="dialog" aria-modal="true" aria-label="Create Event">
    <div class="card w-full max-w-lg max-h-[90vh] overflow-y-auto">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold">Create Event</h2>
        <button class="btn-secondary text-sm" onclick={() => showCreateEvent = false}>Close</button>
      </div>
      <form onsubmit={(e) => { e.preventDefault(); handleCreateEvent(); }} class="grid gap-3">
        <div class="grid gap-3 md:grid-cols-2">
          <input type="text" bind:value={newEventTitle} placeholder="Event title..." class="input-field" />
          <input type="date" bind:value={newEventDate} class="input-field" />
        </div>
        <textarea rows="2" bind:value={newEventDescription} placeholder="Description (optional)" class="input-field"></textarea>
        <div class="flex flex-col-reverse sm:flex-row justify-end gap-2">
          <button type="button" class="btn-secondary" onclick={() => showCreateEvent = false}>Cancel</button>
          <button type="submit" class="btn-primary text-sm" disabled={creatingEvent}>
            {creatingEvent ? 'Creating...' : 'Create Event'}
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}

{#if showEditEvent}
  <div class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center px-4 z-50"
       onclick={(e) => { if (e.target === e.currentTarget) showEditEvent = false; }}
       role="dialog" aria-modal="true" aria-label="Edit Event">
    <div class="card w-full max-w-lg max-h-[90vh] overflow-y-auto">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold">Edit Event</h2>
        <button class="btn-secondary text-sm" onclick={() => showEditEvent = false}>Close</button>
      </div>
      <form onsubmit={(e) => { e.preventDefault(); handleUpdateEvent(); }} class="grid gap-3">
        <div class="grid gap-3 md:grid-cols-2">
          <input type="text" bind:value={editEventTitle} placeholder="Event title..." class="input-field" />
          <input type="date" bind:value={editEventDate} class="input-field" />
        </div>
        <textarea rows="2" bind:value={editEventDescription} placeholder="Description (optional)" class="input-field"></textarea>
        <div class="flex flex-col-reverse sm:flex-row justify-end gap-2">
          <button type="button" class="btn-secondary" onclick={() => showEditEvent = false}>Cancel</button>
          <button type="submit" class="btn-primary text-sm" disabled={savingEditEvent}>
            {savingEditEvent ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}
