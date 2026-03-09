<script lang="ts">
  import { goto } from '$app/navigation';
  import {
    listSessions,
    listEvents,
    createEvent,
    updateEvent,
    deleteEvent,
    setEventSessions
  } from '$lib/api';
  import { Calendar, Plus } from 'lucide-svelte';
  import { onMount } from 'svelte';
  import EventCard from '$lib/components/EventCard.svelte';

  let sessions: any[] = $state([]);
  let events: any[] = $state([]);
  let loading = $state(true);
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

  onMount(async () => {
    try {
      const [sessionsResult, eventsResult] = await Promise.all([
        listSessions(),
        listEvents()
      ]);
      sessions = sessionsResult;
      events = eventsResult;
      eventSelections = Object.fromEntries(
        events.map((event) => [event.id, (event.sessions || []).map((s: any) => s.id)])
      );
    } catch {
      goto('/login');
    } finally {
      loading = false;
    }
  });

  async function handleCreateEvent() {
    if (!newEventTitle.trim() || !newEventDate) return;
    creatingEvent = true;
    try {
      const event = await createEvent({
        title: newEventTitle.trim(),
        event_date: newEventDate,
        description: newEventDescription.trim() || null
      });
      events = [event, ...events];
      eventSelections = { ...eventSelections, [event.id]: [] };
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
      const refreshed = await listEvents();
      events = refreshed;
      eventSelections = Object.fromEntries(
        refreshed.map((event: any) => [event.id, (event.sessions || []).map((s: any) => s.id)])
      );
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
    events = events.filter((event) => event.id !== id);
  }

  async function handleTogglePublish(eventId: string, currentStatus: boolean) {
    try {
      const updated = await updateEvent(eventId, { is_published: !currentStatus });
      events = events.map((event) => (event.id === eventId ? { ...event, is_published: updated.is_published } : event));
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
      const updated = await updateEvent(editingEventId, {
        title: editEventTitle.trim(),
        event_date: editEventDate,
        description: editEventDescription.trim() || null
      });
      events = events.map((event) =>
        event.id === editingEventId ? { ...event, ...updated } : event
      );
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
</script>

<svelte:head>
  <title>Events – Rforum</title>
</svelte:head>

<main class="flex-1 max-w-5xl mx-auto w-full px-8 py-8">
  <div class="flex items-center justify-between mb-8">
    <div>
      <h1 class="text-3xl font-heading font-bold tracking-wide">All Events</h1>
      <p class="text-sm text-surface-500 mt-1.5">Manage your events and their sessions</p>
    </div>
    <button class="btn-primary text-sm flex items-center gap-2" on:click={() => showCreateEvent = true}>
      <Plus class="w-4 h-4" />
      Create Event
    </button>
  </div>

  {#if loading}
    <div class="text-center text-surface-400 py-16">Loading events...</div>
  {:else if events.length === 0}
    <div class="flex flex-col items-center justify-center text-center gap-4 py-20">
      <div class="w-14 h-14 flex items-center justify-center rounded-2xl bg-brand-500/10">
        <Calendar class="w-7 h-7 text-brand-500" />
      </div>
      <div>
        <h3 class="text-lg font-semibold">No events yet</h3>
        <p class="text-sm text-surface-400 mt-1">Create your first event to get started</p>
      </div>
      <button class="btn-primary text-sm" on:click={() => showCreateEvent = true}>Create Event</button>
    </div>
  {:else}
    <div class="space-y-4">
      {#each events as event (event.id)}
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
      {/each}
    </div>
  {/if}
</main>

{#if showCreateEvent}
  <div class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center px-4 z-50">
    <div class="card w-full max-w-lg">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold">Create Event</h2>
        <button class="btn-secondary text-sm" on:click={() => showCreateEvent = false}>Close</button>
      </div>
      <form on:submit|preventDefault={handleCreateEvent} class="grid gap-3">
        <div class="grid gap-3 md:grid-cols-2">
          <input type="text" bind:value={newEventTitle} placeholder="Event title..." class="input-field" />
          <input type="date" bind:value={newEventDate} class="input-field" />
        </div>
        <textarea rows="2" bind:value={newEventDescription} placeholder="Description (optional)" class="input-field"></textarea>
        <div class="flex justify-end gap-2">
          <button type="button" class="btn-secondary" on:click={() => showCreateEvent = false}>Cancel</button>
          <button type="submit" class="btn-primary text-sm" disabled={creatingEvent}>
            {creatingEvent ? 'Creating...' : 'Create Event'}
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}

{#if showEditEvent}
  <div class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center px-4 z-50">
    <div class="card w-full max-w-lg">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold">Edit Event</h2>
        <button class="btn-secondary text-sm" on:click={() => showEditEvent = false}>Close</button>
      </div>
      <form on:submit|preventDefault={handleUpdateEvent} class="grid gap-3">
        <div class="grid gap-3 md:grid-cols-2">
          <input type="text" bind:value={editEventTitle} placeholder="Event title..." class="input-field" />
          <input type="date" bind:value={editEventDate} class="input-field" />
        </div>
        <textarea rows="2" bind:value={editEventDescription} placeholder="Description (optional)" class="input-field"></textarea>
        <div class="flex justify-end gap-2">
          <button type="button" class="btn-secondary" on:click={() => showEditEvent = false}>Cancel</button>
          <button type="submit" class="btn-primary text-sm" disabled={savingEditEvent}>
            {savingEditEvent ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}
