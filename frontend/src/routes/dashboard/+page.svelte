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
  import { Radio, Plus, Trash2, LogOut, ExternalLink, Copy, Eye, EyeOff } from 'lucide-svelte';
  import { onMount } from 'svelte';

  let sessions: any[] = $state([]);
  let events: any[] = $state([]);
  let newTitle = $state('');
  let creating = $state(false);
  let loading = $state(true);
  let newEventTitle = $state('');
  let newEventDate = $state('');
  let newEventDescription = $state('');
  let newEventSessions: string[] = $state([]);
  let creatingEvent = $state(false);
  let savingEventId = $state<string | null>(null);
  let eventSelections: Record<string, string[]> = $state({});
  let showCreateEvent = $state(false);

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

  function handleNewEventSessionsChange(event: Event) {
    const selected = Array.from((event.currentTarget as HTMLSelectElement).selectedOptions)
      .map((option) => option.value);
    newEventSessions = selected;
  }

  function handleEventSessionsChange(eventId: string, event: Event) {
    const selected = Array.from((event.currentTarget as HTMLSelectElement).selectedOptions)
      .map((option) => option.value);
    eventSelections = { ...eventSelections, [eventId]: selected };
  }

  async function handleCreateEvent() {
    if (!newEventTitle.trim() || !newEventDate) return;
    creatingEvent = true;
    try {
      const event = await createEvent({
        title: newEventTitle.trim(),
        event_date: newEventDate,
        description: newEventDescription.trim() || null,
        session_ids: newEventSessions
      });
      events = [event, ...events];
      eventSelections = { ...eventSelections, [event.id]: [...newEventSessions] };
      newEventTitle = '';
      newEventDate = '';
      newEventDescription = '';
      newEventSessions = [];
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
      const updated = await setEventSessions(eventId, eventSelections[eventId] || []);
      events = events.map((event) => (event.id === eventId ? updated : event));
      eventSelections = {
        ...eventSelections,
        [eventId]: (updated.sessions || []).map((s: any) => s.id)
      };
    } catch (e: any) {
      alert(e.message);
    } finally {
      savingEventId = null;
    }
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

  function getCurrentEvent() {
    return events.find((event) => isTodayEvent(event)) || null;
  }

  function getOtherEvents() {
    return events.filter((event) => !isTodayEvent(event));
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
      <div>
        <h1 class="text-2xl font-bold">Current Event</h1>
        <p class="text-sm text-surface-500">Today’s schedule and live sessions</p>
      </div>
      <button class="btn-primary text-sm" on:click={() => showCreateEvent = true}>Create Event</button>
    </div>

    {#if loading}
      <div class="text-center text-surface-500 py-6">Loading events...</div>
    {:else if !getCurrentEvent()}
      <div class="card text-center text-surface-500 py-8 mb-10">
        <p class="text-lg mb-2">No event scheduled for today</p>
        <p class="text-sm">Create one to start planning sessions.</p>
      </div>
    {:else}
      {#key getCurrentEvent().id}
        <div class="card grid gap-4 mb-10">
          <div class="flex items-start justify-between gap-4">
            <div class="flex-1">
              <div class="flex items-center gap-2 mb-1">
                <h3 class="text-lg font-semibold">{getCurrentEvent().title}</h3>
                {#if getCurrentEvent().is_published}
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
                {new Date(getCurrentEvent().event_date).toLocaleDateString()}
              </p>
              {#if getCurrentEvent().description}
                <p class="text-sm text-surface-400 mt-1">{getCurrentEvent().description}</p>
              {/if}
            </div>
            <div class="flex items-center gap-2">
              <button
                on:click={() => handleTogglePublish(getCurrentEvent().id, getCurrentEvent().is_published)}
                class="btn-secondary text-sm p-2.5"
                title={getCurrentEvent().is_published ? 'Unpublish' : 'Publish'}
              >
                {#if getCurrentEvent().is_published}
                  <EyeOff class="w-4 h-4" />
                {:else}
                  <Eye class="w-4 h-4" />
                {/if}
              </button>
              <button on:click={() => handleDeleteEvent(getCurrentEvent().id)} class="btn-danger text-sm p-2.5">
                <Trash2 class="w-4 h-4" />
              </button>
            </div>
          </div>

          <div class="grid gap-2">
            <div class="text-sm text-surface-500">Sessions</div>
            <select
              class="input-field"
              multiple
              size="4"
              on:change={(e) => handleEventSessionsChange(getCurrentEvent().id, e)}
            >
              {#each sessions as session (session.id)}
                <option
                  value={session.id}
                  selected={(eventSelections[getCurrentEvent().id] || []).includes(session.id)}
                >
                  {session.title} ({session.unique_code})
                </option>
              {/each}
            </select>
            <div class="flex justify-end">
              <button
                class="btn-secondary text-sm"
                on:click={() => handleSaveEventSessions(getCurrentEvent().id)}
                disabled={savingEventId === getCurrentEvent().id}
              >
                {savingEventId === getCurrentEvent().id ? 'Saving...' : 'Save Sessions'}
              </button>
            </div>
          </div>
        </div>
      {/key}
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

            <div class="grid gap-2">
              <div class="text-sm text-surface-500">Sessions</div>
              <select
                class="input-field"
                multiple
                size="4"
                on:change={(e) => handleEventSessionsChange(event.id, e)}
              >
                {#each sessions as session (session.id)}
                  <option
                    value={session.id}
                    selected={(eventSelections[event.id] || []).includes(session.id)}
                  >
                    {session.title} ({session.unique_code})
                  </option>
                {/each}
              </select>
              <div class="flex justify-end">
                <button
                  class="btn-secondary text-sm"
                  on:click={() => handleSaveEventSessions(event.id)}
                  disabled={savingEventId === event.id}
                >
                  {savingEventId === event.id ? 'Saving...' : 'Save Sessions'}
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
          <select
            class="input-field"
            multiple
            size="4"
            on:change={handleNewEventSessionsChange}
          >
            {#each sessions as session (session.id)}
              <option value={session.id} selected={newEventSessions.includes(session.id)}>
                {session.title} ({session.unique_code})
              </option>
            {/each}
          </select>
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
</div>
