<script lang="ts">
  import { goto } from '$app/navigation';
  import {
    listSessions,
    createSession,
    deleteSession,
    logout,
    listEvents,
    createEvent,
    updateEvent,
    deleteEvent,
    setEventSessions
  } from '$lib/api';
  import { RadioTower, Plus, Trash2, LogOut, ExternalLink, Copy, Eye, EyeOff, Pencil, Calendar, LayoutDashboard, CalendarDays, Presentation, BarChart3 } from 'lucide-svelte';
  import { onMount } from 'svelte';
  import { theme, toggleTheme } from '$lib/theme';
  import { Moon, Sun } from 'lucide-svelte';
  import EventCard from '$lib/components/EventCard.svelte';

  let sessions: any[] = $state([]);
  let events: any[] = $state([]);
  let newTitle = $state('');
  let newSessionEventId = $state('');
  let creating = $state(false);
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

  async function handleCreate() {
    if (!newTitle.trim() || !newSessionEventId) return;
    creating = true;
    try {
      const session = await createSession(newTitle.trim(), newSessionEventId);
      sessions = [session, ...sessions];
      eventSelections = {
        ...eventSelections,
        [newSessionEventId]: [...(eventSelections[newSessionEventId] || []), session.id]
      };
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

  function copyCode(code: string) {
    navigator.clipboard.writeText(code);
  }

  function isTodayEvent(event: any) {
    const today = new Date().toISOString().slice(0, 10);
    return event?.event_date === today;
  }

  function getTodayEvents() {
    return events.filter((event) => isTodayEvent(event));
  }

  function getOtherEvents() {
    return events.filter((event) => !isTodayEvent(event));
  }

  function getSelectedSessions(eventId: string) {
    const ids = eventSelections[eventId] || [];
    return ids
      .map((id) => sessions.find((session) => session.id === id))
      .filter(Boolean);
  }

  function getAvailableSessions(eventId: string) {
    const selected = new Set(eventSelections[eventId] || []);
    return sessions.filter((session) => !selected.has(session.id));
  }
</script>

<svelte:head>
  <title>Dashboard – Rforum</title>
</svelte:head>

<div>
  <main class="flex-1 max-w-5xl mx-auto w-full px-8 py-8">
    <div class="flex items-center justify-between mb-8">
      <div>
        <h1 class="text-2xl font-bold text-slate-900 dark:text-white">Current Events</h1>
        <p class="text-sm text-slate-500 dark:text-slate-400 mt-1">Today's schedule and live sessions</p>
      </div>
      <button class="bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-medium px-4 py-2 rounded-lg shadow-lg shadow-purple-500/20 transition active:scale-95 text-sm" on:click={() => showCreateEvent = true}>Create Event</button>
    </div>

    {#if loading}
      <div class="text-center text-slate-400 py-6">Loading events...</div>
    {:else if getTodayEvents().length === 0}
      <div class="flex flex-col items-center justify-center text-center gap-4 py-16 mb-10">
        <div class="w-14 h-14 flex items-center justify-center rounded-2xl bg-purple-500/10">
          <Calendar class="w-7 h-7 text-purple-500" />
        </div>
        <div>
          <h3 class="text-lg font-semibold text-slate-900 dark:text-white">No events scheduled today</h3>
          <p class="text-sm text-slate-400 mt-1">Create an event to start engaging your audience</p>
        </div>
        <button class="bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-medium px-4 py-2 rounded-lg shadow-lg shadow-purple-500/20 transition active:scale-95 text-sm" on:click={() => showCreateEvent = true}>Create Event</button>
      </div>
    {:else}
      <div class="space-y-4 mb-10">
        {#each getTodayEvents() as event (event.id)}
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

    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-bold text-slate-900 dark:text-white">Other Events</h2>
    </div>

    {#if !loading && getOtherEvents().length === 0}
      <div class="text-center text-slate-400 py-6 mb-10">No other events yet.</div>
    {:else if !loading}
      <div class="space-y-4 mb-12">
        {#each getOtherEvents() as event (event.id)}
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

    <div class="flex items-center justify-between mb-8">
      <h1 class="text-2xl font-bold text-slate-900 dark:text-white">Your Sessions</h1>
    </div>

    <!-- Create new session -->
    <form on:submit|preventDefault={handleCreate} class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm p-6 flex gap-3 mb-8">
      <select
        class="input-field w-52"
        bind:value={newSessionEventId}
      >
        <option value="" disabled>Select event</option>
        {#each events as event (event.id)}
          <option value={event.id}>
            {event.title} · {new Date(event.event_date).toLocaleDateString()}
          </option>
        {/each}
      </select>
      <input
        type="text"
        bind:value={newTitle}
        placeholder="New session title..."
        class="input-field flex-1"
      />
      <button
        type="submit"
        class="bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-medium px-4 py-2 rounded-lg shadow-lg shadow-purple-500/20 transition active:scale-95 flex items-center gap-2 whitespace-nowrap text-sm"
        disabled={creating || !newSessionEventId}
      >
        <Plus class="w-4 h-4" />
        Create
      </button>
    </form>

    <!-- Sessions list -->
    {#if loading}
      <div class="text-center text-slate-400 py-20">Loading...</div>
    {:else if sessions.length === 0}
      <div class="flex flex-col items-center justify-center text-center gap-4 py-16">
        <div class="w-14 h-14 flex items-center justify-center rounded-2xl bg-cyan-500/10">
          <Presentation class="w-7 h-7 text-cyan-500" />
        </div>
        <div>
          <h3 class="text-lg font-semibold text-slate-900 dark:text-white">No sessions yet</h3>
          <p class="text-sm text-slate-400 mt-1">Create your first session to get started</p>
        </div>
      </div>
    {:else}
      <div class="space-y-3">
        {#each sessions as session (session.id)}
          <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm hover:shadow-md transition-all duration-200 hover:scale-[1.01] p-6 flex items-center justify-between gap-4">
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-3 mb-1">
                <h3 class="text-lg font-semibold text-slate-900 dark:text-white truncate">{session.title}</h3>
                {#if session.is_live}
                  <span class="badge-live">
                    <span class="w-1.5 h-1.5 bg-live rounded-full animate-pulse-live"></span>
                    Live
                  </span>
                {/if}
              </div>
              <div class="flex items-center gap-3 text-sm text-slate-500 dark:text-slate-400">
                <button
                  on:click={() => copyCode(session.unique_code)}
                  class="flex items-center gap-1 font-mono hover:text-slate-700 dark:hover:text-slate-300 transition-colors"
                >
                  <Copy class="w-3 h-3" />
                  {session.unique_code}
                </button>
                <span>&middot;</span>
                <span class="text-xs text-slate-500">{new Date(session.created_at).toLocaleDateString()}</span>
              </div>
            </div>

            <div class="flex items-center gap-2">
              <a href="/dashboard/{session.id}" class="border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 px-4 py-2 rounded-lg text-sm font-medium text-slate-600 dark:text-slate-300 transition active:scale-95 flex items-center gap-1.5">
                <ExternalLink class="w-3.5 h-3.5" />
                Manage
              </a>
              <button on:click={() => handleDelete(session.id)} class="border border-red-200 dark:border-red-900/50 hover:bg-red-50 dark:hover:bg-red-900/20 p-2.5 rounded-lg transition active:scale-95">
                <Trash2 class="w-4 h-4 text-red-400" />
              </button>
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </main>

  {#if showCreateEvent}
    <div class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center px-4 z-50">
      <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-xl w-full max-w-lg p-6">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-lg font-semibold text-slate-900 dark:text-white">Create Event</h2>
          <button class="border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 px-3 py-1.5 rounded-lg text-sm transition" on:click={() => showCreateEvent = false}>Close</button>
        </div>
        <form on:submit|preventDefault={handleCreateEvent} class="grid gap-3">
          <div class="grid gap-3 md:grid-cols-2">
            <input type="text" bind:value={newEventTitle} placeholder="Event title..." class="input-field" />
            <input type="date" bind:value={newEventDate} class="input-field" />
          </div>
          <textarea rows="2" bind:value={newEventDescription} placeholder="Description (optional)" class="input-field"></textarea>
          <div class="flex justify-end gap-2">
            <button type="button" class="border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 px-4 py-2 rounded-lg text-sm transition" on:click={() => showCreateEvent = false}>Cancel</button>
            <button type="submit" class="bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-medium px-4 py-2 rounded-lg shadow-lg shadow-purple-500/20 transition active:scale-95 text-sm" disabled={creatingEvent}>
              {creatingEvent ? 'Creating...' : 'Create Event'}
            </button>
          </div>
        </form>
      </div>
    </div>
  {/if}

  {#if showEditEvent}
    <div class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center px-4 z-50">
      <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-xl w-full max-w-lg p-6">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-lg font-semibold text-slate-900 dark:text-white">Edit Event</h2>
          <button class="border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 px-3 py-1.5 rounded-lg text-sm transition" on:click={() => showEditEvent = false}>Close</button>
        </div>
        <form on:submit|preventDefault={handleUpdateEvent} class="grid gap-3">
          <div class="grid gap-3 md:grid-cols-2">
            <input type="text" bind:value={editEventTitle} placeholder="Event title..." class="input-field" />
            <input type="date" bind:value={editEventDate} class="input-field" />
          </div>
          <textarea rows="2" bind:value={editEventDescription} placeholder="Description (optional)" class="input-field"></textarea>
          <div class="flex justify-end gap-2">
            <button type="button" class="border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 px-4 py-2 rounded-lg text-sm transition" on:click={() => showEditEvent = false}>Cancel</button>
            <button type="submit" class="bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-medium px-4 py-2 rounded-lg shadow-lg shadow-purple-500/20 transition active:scale-95 text-sm" disabled={savingEditEvent}>
              {savingEditEvent ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  {/if}
</div>
