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
  import { RadioTower, Plus, Trash2, LogOut, ExternalLink, Copy, Eye, EyeOff, Pencil } from 'lucide-svelte';
  import { onMount } from 'svelte';

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

  function handleLogout() {
    logout();
    goto('/');
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

<div class="min-h-screen flex flex-col">
  <!-- Top bar -->
  <nav class="flex items-center justify-between px-6 py-4 border-b border-surface-800">
    <a href="/" class="flex items-center gap-2">
      <RadioTower class="w-6 h-6 text-brand-500" />
      <span class="text-lg font-bold">Rforum</span>
    </a>
    <button on:click={handleLogout} class="btn-secondary text-sm flex items-center gap-2">
      <LogOut class="w-4 h-4" />
      Log out
    </button>
  </nav>

  <main class="flex-1 max-w-4xl mx-auto w-full px-6 py-10">
    <div class="flex items-center justify-between mb-8">
      <div>
        <h1 class="text-2xl font-bold">Current Events</h1>
        <p class="text-sm text-surface-500">Today’s schedule and live sessions</p>
      </div>
      <button class="btn-primary text-sm" on:click={() => showCreateEvent = true}>Create Event</button>
    </div>

    {#if loading}
      <div class="text-center text-surface-500 py-6">Loading events...</div>
    {:else if getTodayEvents().length === 0}
      <div class="card text-center text-surface-500 py-8 mb-10">
        <p class="text-lg mb-2">No event scheduled for today</p>
        <p class="text-sm">Create one to start planning sessions.</p>
      </div>
    {:else}
      <div class="space-y-3 mb-10">
        {#each getTodayEvents() as event (event.id)}
          <div class="card grid gap-4">
            <div class="flex items-start justify-between gap-4">
              <div class="flex-1">
                <div class="flex items-center gap-2 mb-1">
                  <h3 class="text-lg font-semibold">{event.title}</h3>
                  {#if event.is_published}
                    <span class="text-xs px-2 py-0.5 rounded-full bg-success/20 text-success font-medium">
                      Published
                    </span>
                  {:else}
                    <span class="text-xs px-2 py-0.5 rounded-full bg-surface-700 text-surface-400 font-medium">
                      Draft
                    </span>
                  {/if}
                </div>
                <p class="text-sm text-surface-500">
                  {new Date(event.event_date).toLocaleDateString()}
                </p>
                {#if event.description}
                  <p class="text-sm text-surface-400 mt-1">{event.description}</p>
                {/if}
              </div>
              <div class="flex items-center gap-2">
                <button
                  on:click={() => startEditEvent(event)}
                  class="btn-secondary text-sm p-2.5"
                  title="Edit"
                >
                  <Pencil class="w-4 h-4" />
                </button>
                <button
                  on:click={() => handleTogglePublish(event.id, event.is_published)}
                  class="btn-secondary text-sm p-2.5"
                  title={event.is_published ? 'Unpublish' : 'Publish'}
                >
                  {#if event.is_published}
                    <EyeOff class="w-4 h-4" />
                  {:else}
                    <Eye class="w-4 h-4" />
                  {/if}
                </button>
                <button on:click={() => handleDeleteEvent(event.id)} class="btn-danger text-sm p-2.5">
                  <Trash2 class="w-4 h-4" />
                </button>
              </div>
            </div>

            <div class="grid gap-3">
              <div class="text-sm text-surface-500">Sessions</div>
              {#if getSelectedSessions(event.id).length === 0}
                <p class="text-sm text-surface-500">No sessions assigned yet.</p>
              {:else}
                <div class="space-y-2">
                  {#each getSelectedSessions(event.id) as session (session.id)}
                    <div class="flex items-center justify-between gap-3 p-3 rounded-lg border border-surface-800">
                      <div class="min-w-0">
                        <div class="font-medium truncate">{session.title}</div>
                        <div class="text-xs text-surface-500 font-mono">{session.unique_code}</div>
                      </div>
                      <button
                        class="btn-secondary text-xs"
                        on:click={() => handleRemoveSession(event.id, session.id)}
                        disabled={savingEventId === event.id}
                      >
                        Remove
                      </button>
                    </div>
                  {/each}
                </div>
              {/if}
              <div class="flex items-center gap-2">
                <select
                  class="input-field flex-1"
                  value={addSessionSelections[event.id] || ''}
                  on:change={(e) => addSessionSelections = {
                    ...addSessionSelections,
                    [event.id]: (e.currentTarget as HTMLSelectElement).value
                  }}
                >
                  <option value="" disabled>Select session to add</option>
                  {#each getAvailableSessions(event.id) as session (session.id)}
                    <option value={session.id}>{session.title} ({session.unique_code})</option>
                  {/each}
                </select>
                <button
                  class="btn-secondary text-sm"
                  on:click={() => handleAddSession(event.id)}
                  disabled={savingEventId === event.id || !addSessionSelections[event.id]}
                >
                  {savingEventId === event.id ? 'Saving...' : 'Add'}
                </button>
              </div>
            </div>
          </div>
        {/each}
      </div>
    {/if}

    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-bold">Other Events</h2>
    </div>

    {#if !loading && getOtherEvents().length === 0}
      <div class="text-center text-surface-500 py-6 mb-10">No other events yet.</div>
    {:else if !loading}
      <div class="space-y-3 mb-12">
        {#each getOtherEvents() as event (event.id)}
          <div class="card grid gap-3 animate-fade-in">
            <div class="flex items-start justify-between gap-4">
              <div class="flex-1">
                <div class="flex items-center gap-2 mb-1">
                  <h3 class="font-semibold">{event.title}</h3>
                  {#if event.is_published}
                    <span class="text-xs px-2 py-0.5 rounded-full bg-success/20 text-success font-medium">
                      Published
                    </span>
                  {:else}
                    <span class="text-xs px-2 py-0.5 rounded-full bg-surface-700 text-surface-400 font-medium">
                      Draft
                    </span>
                  {/if}
                </div>
                <p class="text-sm text-surface-500">
                  {new Date(event.event_date).toLocaleDateString()}
                </p>
                {#if event.description}
                  <p class="text-sm text-surface-400 mt-1">{event.description}</p>
                {/if}
              </div>
              <div class="flex items-center gap-2">
                <button
                  on:click={() => startEditEvent(event)}
                  class="btn-secondary text-sm p-2.5"
                  title="Edit"
                >
                  <Pencil class="w-4 h-4" />
                </button>
                <button
                  on:click={() => handleTogglePublish(event.id, event.is_published)}
                  class="btn-secondary text-sm p-2.5"
                  title={event.is_published ? 'Unpublish' : 'Publish'}
                >
                  {#if event.is_published}
                    <EyeOff class="w-4 h-4" />
                  {:else}
                    <Eye class="w-4 h-4" />
                  {/if}
                </button>
                <button on:click={() => handleDeleteEvent(event.id)} class="btn-danger text-sm p-2.5">
                  <Trash2 class="w-4 h-4" />
                </button>
              </div>
            </div>

            <div class="grid gap-3">
              <div class="text-sm text-surface-500">Sessions</div>
              {#if getSelectedSessions(event.id).length === 0}
                <p class="text-sm text-surface-500">No sessions assigned yet.</p>
              {:else}
                <div class="space-y-2">
                  {#each getSelectedSessions(event.id) as session (session.id)}
                    <div class="flex items-center justify-between gap-3 p-3 rounded-lg border border-surface-800">
                      <div class="min-w-0">
                        <div class="font-medium truncate">{session.title}</div>
                        <div class="text-xs text-surface-500 font-mono">{session.unique_code}</div>
                      </div>
                      <button
                        class="btn-secondary text-xs"
                        on:click={() => handleRemoveSession(event.id, session.id)}
                        disabled={savingEventId === event.id}
                      >
                        Remove
                      </button>
                    </div>
                  {/each}
                </div>
              {/if}
              <div class="flex items-center gap-2">
                <select
                  class="input-field flex-1"
                  value={addSessionSelections[event.id] || ''}
                  on:change={(e) => addSessionSelections = {
                    ...addSessionSelections,
                    [event.id]: (e.currentTarget as HTMLSelectElement).value
                  }}
                >
                  <option value="" disabled>Select session to add</option>
                  {#each getAvailableSessions(event.id) as session (session.id)}
                    <option value={session.id}>{session.title} ({session.unique_code})</option>
                  {/each}
                </select>
                <button
                  class="btn-secondary text-sm"
                  on:click={() => handleAddSession(event.id)}
                  disabled={savingEventId === event.id || !addSessionSelections[event.id]}
                >
                  {savingEventId === event.id ? 'Saving...' : 'Add'}
                </button>
              </div>
            </div>
          </div>
        {/each}
      </div>
    {/if}

    <div class="flex items-center justify-between mb-8">
      <h1 class="text-2xl font-bold">Your Sessions</h1>
    </div>

    <!-- Create new session -->
    <form on:submit|preventDefault={handleCreate} class="card flex gap-3 mb-8">
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
        class="btn-primary flex items-center gap-2 whitespace-nowrap"
        disabled={creating || !newSessionEventId}
      >
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

  {#if showCreateEvent}
    <div class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center px-4 z-50">
      <div class="card w-full max-w-lg">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-lg font-semibold">Create Event</h2>
          <button class="btn-secondary text-sm" on:click={() => showCreateEvent = false}>Close</button>
        </div>
        <form on:submit|preventDefault={handleCreateEvent} class="grid gap-3">
          <div class="grid gap-3 md:grid-cols-2">
            <input
              type="text"
              bind:value={newEventTitle}
              placeholder="Event title..."
              class="input-field"
            />
            <input
              type="date"
              bind:value={newEventDate}
              class="input-field"
            />
          </div>
          <textarea
            rows="2"
            bind:value={newEventDescription}
            placeholder="Description (optional)"
            class="input-field"
          ></textarea>
          <div class="flex justify-end gap-2">
            <button type="button" class="btn-secondary" on:click={() => showCreateEvent = false}>
              Cancel
            </button>
            <button type="submit" class="btn-primary" disabled={creatingEvent}>
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
            <input
              type="text"
              bind:value={editEventTitle}
              placeholder="Event title..."
              class="input-field"
            />
            <input
              type="date"
              bind:value={editEventDate}
              class="input-field"
            />
          </div>
          <textarea
            rows="2"
            bind:value={editEventDescription}
            placeholder="Description (optional)"
            class="input-field"
          ></textarea>
          <div class="flex justify-end gap-2">
            <button type="button" class="btn-secondary" on:click={() => showEditEvent = false}>
              Cancel
            </button>
            <button type="submit" class="btn-primary" disabled={savingEditEvent}>
              {savingEditEvent ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  {/if}
</div>
