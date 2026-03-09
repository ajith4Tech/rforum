<script lang="ts">
  import { goto } from '$app/navigation';
  import {
    listSessions,
    createSession,
    listEvents,
    createEvent,
    isAuthenticated
  } from '$lib/api';
  import { Plus, ExternalLink, Copy, Calendar, Presentation, Radio, ArrowRight } from 'lucide-svelte';
  import { onMount, onDestroy } from 'svelte';

  let sessions: any[] = $state([]);
  let events: any[] = $state([]);
  let loading = $state(true);

  // Quick Create Event modal
  let showCreateEvent = $state(false);
  let newEventTitle = $state('');
  let newEventDate = $state('');
  let newEventDescription = $state('');
  let creatingEvent = $state(false);

  // Quick Create Session modal
  let showCreateSession = $state(false);
  let newSessionTitle = $state('');
  let newSessionEventId = $state('');
  let creatingSession = $state(false);

  // Per-event countdowns
  let countdowns: Record<string, { days: number; hours: number; minutes: number; seconds: number }> = $state({});
  let countdownInterval: ReturnType<typeof setInterval> | null = null;

  function computeCountdowns() {
    const now = new Date();
    const updated: typeof countdowns = {};
    for (const event of upcomingEvents) {
      const target = new Date(event.event_date + 'T00:00:00');
      const diff = target.getTime() - now.getTime();
      updated[event.id] = diff <= 0
        ? { days: 0, hours: 0, minutes: 0, seconds: 0 }
        : {
            days: Math.floor(diff / 86400000),
            hours: Math.floor((diff % 86400000) / 3600000),
            minutes: Math.floor((diff % 3600000) / 60000),
            seconds: Math.floor((diff % 60000) / 1000)
          };
    }
    countdowns = updated;
  }

  onMount(async () => {
    if (!isAuthenticated()) { goto('/login'); return; }
    try {
      const [sessionsResult, eventsResult] = await Promise.all([listSessions(), listEvents()]);
      sessions = sessionsResult;
      events = eventsResult;
    } catch {
      goto('/login');
    } finally {
      loading = false;
      computeCountdowns();
      countdownInterval = setInterval(computeCountdowns, 1000);
    }
  });

  onDestroy(() => { if (countdownInterval) clearInterval(countdownInterval); });

  async function handleCreateEvent() {
    if (!newEventTitle.trim() || !newEventDate) return;
    creatingEvent = true;
    try {
      const event = await createEvent({ title: newEventTitle.trim(), event_date: newEventDate, description: newEventDescription.trim() || null });
      events = [event, ...events];
      newEventTitle = ''; newEventDate = ''; newEventDescription = '';
      showCreateEvent = false;
      goto('/dashboard/events');
    } catch (e: any) { alert(e.message); } finally { creatingEvent = false; }
  }

  async function handleCreateSession() {
    if (!newSessionTitle.trim() || !newSessionEventId) return;
    creatingSession = true;
    try {
      const session = await createSession(newSessionTitle.trim(), newSessionEventId);
      sessions = [session, ...sessions];
      newSessionTitle = ''; newSessionEventId = '';
      showCreateSession = false;
      goto('/dashboard/sessions');
    } catch (e: any) { alert(e.message); } finally { creatingSession = false; }
  }

  function copyCode(code: string) { navigator.clipboard.writeText(code); }
  function isToday(dateStr: string) { return dateStr === new Date().toISOString().slice(0, 10); }

  const liveSessions = $derived(sessions.filter((s) => s.is_live));
  const upcomingEvents = $derived(
    events
      .filter((e) => e.event_date >= new Date().toISOString().slice(0, 10))
      .sort((a, b) => a.event_date.localeCompare(b.event_date))
      .slice(0, 5)
  );
</script>

<svelte:head>
  <title>Dashboard – Rforum</title>
</svelte:head>

<main class="flex-1 max-w-5xl mx-auto w-full px-8 py-10">

  <div class="mb-10">
    <h1 class="text-3xl font-heading font-bold tracking-wide">Dashboard</h1>
    <p class="text-surface-500 mt-1.5">Quick actions and upcoming schedule</p>
  </div>

  {#if loading}
    <div class="text-center text-surface-400 py-20">Loading…</div>
  {:else}

    <!-- 3 Minimal Shortcuts -->
    <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-10">

      <!-- Add Event -->
      <button
        onclick={() => showCreateEvent = true}
        class="card card-interactive group flex items-center gap-5 text-left"
      >
        <div class="w-14 h-14 flex items-center justify-center rounded-2xl bg-brand-500/10 group-hover:bg-brand-500/20 transition flex-shrink-0">
          <Plus class="w-7 h-7 text-brand-500" />
        </div>
        <div>
          <h3 class="font-heading font-bold text-lg tracking-wide">Add Event</h3>
          <p class="text-sm text-surface-500 mt-0.5">Create a new event</p>
        </div>
      </button>

      <!-- Add Session -->
      <button
        onclick={() => showCreateSession = true}
        class="card card-interactive group flex items-center gap-5 text-left"
      >
        <div class="w-14 h-14 flex items-center justify-center rounded-2xl bg-accent-500/10 group-hover:bg-accent-500/20 transition flex-shrink-0">
          <Plus class="w-7 h-7 text-accent-500" />
        </div>
        <div>
          <h3 class="font-heading font-bold text-lg tracking-wide">Add Session</h3>
          <p class="text-sm text-surface-500 mt-0.5">Start a new session</p>
        </div>
      </button>

      <!-- Manage Live Sessions -->
      <a
        href="/dashboard/sessions"
        class="card card-interactive group flex items-center gap-5"
      >
        <div class="w-14 h-14 flex items-center justify-center rounded-2xl bg-live/10 group-hover:bg-live/20 transition flex-shrink-0">
          <Radio class="w-7 h-7 text-live" />
        </div>
        <div class="flex-1 min-w-0">
          <h3 class="font-heading font-bold text-lg tracking-wide">Live Sessions</h3>
          <p class="text-sm text-surface-500 mt-0.5">
            {#if liveSessions.length > 0}
              <span class="text-live font-semibold">{liveSessions.length} live</span> right now
            {:else}
              Manage sessions
            {/if}
          </p>
        </div>
        <ArrowRight class="w-5 h-5 text-surface-500 group-hover:text-live transition flex-shrink-0" />
      </a>
    </div>

    <!-- Live Sessions (if any) -->
    {#if liveSessions.length > 0}
      <div class="card mb-8">
        <div class="flex items-center justify-between mb-4">
          <h2 class="font-heading font-semibold text-sm uppercase tracking-widest text-surface-500">Live Right Now</h2>
          <a href="/dashboard/sessions" class="text-xs text-brand-500 hover:underline flex items-center gap-1">
            All sessions <ArrowRight class="w-3 h-3" />
          </a>
        </div>
        <div class="space-y-2">
          {#each liveSessions.slice(0, 4) as session (session.id)}
            <div class="flex items-center justify-between gap-3 px-4 py-3 rounded-xl border border-live/20 bg-live/5">
              <div class="flex items-center gap-3 flex-1 min-w-0">
                <span class="w-2 h-2 rounded-full bg-live animate-pulse-live flex-shrink-0"></span>
                <span class="font-medium text-sm truncate">{session.title}</span>
                <button onclick={() => copyCode(session.unique_code)} class="font-mono text-xs text-surface-500 hover:text-surface-700 dark:hover:text-surface-300 transition flex items-center gap-1 flex-shrink-0">
                  <Copy class="w-3 h-3" />{session.unique_code}
                </button>
              </div>
              <a href="/dashboard/{session.id}" class="btn-secondary text-xs px-3 py-1.5 flex items-center gap-1 flex-shrink-0">
                <ExternalLink class="w-3 h-3" /> Manage
              </a>
            </div>
          {/each}
        </div>
      </div>
    {/if}

    <!-- Upcoming Events -->
    <div class="card">
      <div class="flex items-center justify-between mb-5">
        <h2 class="font-heading font-semibold text-sm uppercase tracking-widest text-surface-500">Upcoming Events</h2>
        <a href="/dashboard/events" class="text-xs text-brand-500 hover:underline flex items-center gap-1">
          All events <ArrowRight class="w-3 h-3" />
        </a>
      </div>

      {#if upcomingEvents.length === 0}
        <div class="flex flex-col items-center py-10 gap-3 text-surface-500">
          <Calendar class="w-8 h-8 opacity-40" />
          <p class="text-sm">No upcoming events</p>
          <button onclick={() => showCreateEvent = true} class="text-xs text-brand-500 hover:underline">Create one →</button>
        </div>
      {:else}
        <div class="space-y-3">
          {#each upcomingEvents as event (event.id)}
            {@const cd = countdowns[event.id]}
            {@const today = isToday(event.event_date)}
            <div class="flex items-center gap-4 px-4 py-4 rounded-xl border border-surface-200 dark:border-surface-800 hover:border-surface-300 dark:hover:border-surface-700 transition">
              <!-- Date block -->
              <div class="flex-shrink-0 w-14 text-center">
                <div class="text-2xl font-heading font-bold leading-none">
                  {new Date(event.event_date + 'T00:00:00').getDate()}
                </div>
                <div class="text-xs text-surface-500 uppercase tracking-wide mt-0.5">
                  {new Date(event.event_date + 'T00:00:00').toLocaleString('default', { month: 'short' })}
                </div>
              </div>

              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 mb-0.5">
                  {#if today}
                    <span class="text-live text-[10px] font-bold uppercase tracking-widest">Today</span>
                  {/if}
                  <span class="font-heading font-semibold text-base truncate">{event.title}</span>
                </div>
                <span class="text-xs text-surface-500">
                  {(event.sessions || []).length} session{(event.sessions || []).length !== 1 ? 's' : ''}
                  {event.is_published ? ' · Published' : ' · Draft'}
                </span>
              </div>

              <!-- Mini countdown -->
              {#if cd && !today}
                <div class="flex-shrink-0 flex items-center gap-1.5 text-xs">
                  {#each [{ v: cd.days, l: 'd' }, { v: cd.hours, l: 'h' }, { v: cd.minutes, l: 'm' }] as unit}
                    <div class="text-center">
                      <span class="font-heading font-bold text-sm tabular-nums">{String(unit.v).padStart(2, '0')}</span>
                      <span class="text-surface-500">{unit.l}</span>
                    </div>
                    {#if unit.l !== 'm'}<span class="text-surface-600">:</span>{/if}
                  {/each}
                </div>
              {:else if today}
                <span class="text-live text-xs font-bold uppercase tracking-wider flex-shrink-0">Live</span>
              {/if}

              <a href="/dashboard/events" class="btn-secondary text-xs px-3 py-1.5 flex items-center gap-1 flex-shrink-0">
                <ExternalLink class="w-3 h-3" /> View
              </a>
            </div>
          {/each}
        </div>
      {/if}
    </div>

  {/if}
</main>

<!-- Create Event Modal -->
{#if showCreateEvent}
  <div class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center px-4 z-50"
       onclick={(e) => { if (e.target === e.currentTarget) showCreateEvent = false; }}>
    <div class="card w-full max-w-lg shadow-2xl">
      <div class="flex items-center justify-between mb-6">
        <h2 class="text-xl font-heading font-bold tracking-wide">Create Event</h2>
        <button onclick={() => showCreateEvent = false} class="btn-secondary px-3 py-1.5 text-xs">Close</button>
      </div>
      <form onsubmit={(e) => { e.preventDefault(); handleCreateEvent(); }} class="grid gap-4">
        <div class="grid gap-4 md:grid-cols-2">
          <div>
            <label class="block text-xs font-medium text-surface-500 uppercase tracking-wider mb-1.5">Title</label>
            <input type="text" bind:value={newEventTitle} placeholder="e.g. Annual Conference" class="input-field" />
          </div>
          <div>
            <label class="block text-xs font-medium text-surface-500 uppercase tracking-wider mb-1.5">Date</label>
            <input type="date" bind:value={newEventDate} class="input-field" />
          </div>
        </div>
        <div>
          <label class="block text-xs font-medium text-surface-500 uppercase tracking-wider mb-1.5">Description <span class="normal-case text-surface-600">(optional)</span></label>
          <textarea rows="2" bind:value={newEventDescription} placeholder="Brief description…" class="input-field resize-none"></textarea>
        </div>
        <div class="flex justify-end gap-2 pt-2">
          <button type="button" onclick={() => showCreateEvent = false} class="btn-secondary text-sm">Cancel</button>
          <button type="submit" class="btn-primary text-sm" disabled={creatingEvent || !newEventTitle.trim() || !newEventDate}>
            {creatingEvent ? 'Creating…' : 'Create Event'}
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}

<!-- Create Session Modal -->
{#if showCreateSession}
  <div class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center px-4 z-50"
       onclick={(e) => { if (e.target === e.currentTarget) showCreateSession = false; }}>
    <div class="card w-full max-w-lg shadow-2xl">
      <div class="flex items-center justify-between mb-6">
        <h2 class="text-xl font-heading font-bold tracking-wide">Create Session</h2>
        <button onclick={() => showCreateSession = false} class="btn-secondary px-3 py-1.5 text-xs">Close</button>
      </div>
      <form onsubmit={(e) => { e.preventDefault(); handleCreateSession(); }} class="grid gap-4">
        <div>
          <label class="block text-xs font-medium text-surface-500 uppercase tracking-wider mb-1.5">Event</label>
          <select class="input-field" bind:value={newSessionEventId}>
            <option value="" disabled>Select an event</option>
            {#each events as event (event.id)}
              <option value={event.id}>{event.title} · {new Date(event.event_date).toLocaleDateString()}</option>
            {/each}
          </select>
        </div>
        <div>
          <label class="block text-xs font-medium text-surface-500 uppercase tracking-wider mb-1.5">Session Title</label>
          <input type="text" bind:value={newSessionTitle} placeholder="e.g. Morning Keynote" class="input-field" />
        </div>
        <div class="flex justify-end gap-2 pt-2">
          <button type="button" onclick={() => showCreateSession = false} class="btn-secondary text-sm">Cancel</button>
          <button type="submit" class="btn-primary text-sm" disabled={creatingSession || !newSessionTitle.trim() || !newSessionEventId}>
            {creatingSession ? 'Creating…' : 'Create Session'}
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}
