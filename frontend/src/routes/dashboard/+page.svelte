<script lang="ts">
  import { goto } from '$app/navigation';
  import {
    createSession,
    createEvent,
    listAssets,
    getStorageUsage,
    formatBytes,
    isAuthenticated,
    isAuthFailure
  } from '$lib/api';
  import { getEvents, getSessions, invalidateEvents, invalidateSessions } from '$lib/dataCache';
  import { todayKey, isToday, parseEventDate } from '$lib/dates';
  import Modal from '$lib/components/Modal.svelte';
  import { Plus, ExternalLink, Copy, Check, Calendar, ArrowRight, CheckSquare, Square, Trash2, HardDrive, File, RefreshCw, Upload, AlertTriangle, X } from 'lucide-svelte';
  import { onMount, onDestroy } from 'svelte';

  const CHECKLIST_KEY = 'rforum_checklist';
  const DEFAULT_ITEMS = [
    { id: '1', label: 'Slides uploaded',     done: false },
    { id: '2', label: 'Poll questions added', done: false },
    { id: '3', label: 'Test session code',    done: false },
    { id: '4', label: 'Enable audience Q&A', done: false },
  ];

  function loadChecklist() {
    try {
      const raw = localStorage.getItem(CHECKLIST_KEY);
      return raw ? JSON.parse(raw) : DEFAULT_ITEMS.map(i => ({ ...i }));
    } catch { return DEFAULT_ITEMS.map(i => ({ ...i })); }
  }
  function saveChecklist(items: typeof checklist) {
    try { localStorage.setItem(CHECKLIST_KEY, JSON.stringify(items)); } catch { /* storage unavailable — keep in memory */ }
  }

  let checklist: { id: string; label: string; done: boolean }[] = $state([]);
  let newCheckItem = $state('');
  let doneCount = $derived(checklist.filter(i => i.done).length);

  function toggleItem(id: string) {
    checklist = checklist.map(i => i.id === id ? { ...i, done: !i.done } : i);
    saveChecklist(checklist);
  }
  function addItem() {
    const label = newCheckItem.trim();
    if (!label) return;
    checklist = [...checklist, { id: Date.now().toString(), label, done: false }];
    newCheckItem = '';
    saveChecklist(checklist);
  }
  function removeItem(id: string) {
    checklist = checklist.filter(i => i.id !== id);
    saveChecklist(checklist);
  }
  function resetChecklist() {
    checklist = DEFAULT_ITEMS.map(i => ({ ...i }));
    saveChecklist(checklist);
  }

  // This overview only needs "enough" events/sessions to summarize (live
  // sessions widget, upcoming events widget, quick-create dropdown) — not a
  // paginated view, so it fetches a bounded page (the backend's
  // MAX_PAGE_SIZE) rather than paging through everything.
  const OVERVIEW_LIMIT = 100;
  let sessions: any[] = $state([]);
  let events: any[] = $state([]);
  let recentAssets: any[] = $state([]);
  let storageBytes = $state(0);
  let loading = $state(true);
  // Events/sessions failure blocks the overview; assets are non-critical and
  // only mark their own card as unavailable.
  let loadError = $state('');
  let assetsError = $state(false);

  // Quick Create Event modal
  let showCreateEvent = $state(false);
  let newEventTitle = $state('');
  let newEventDate = $state('');
  let newEventDescription = $state('');
  let creatingEvent = $state(false);
  let createEventError = $state('');

  // Quick Create Session modal
  let showCreateSession = $state(false);
  let newSessionTitle = $state('');
  let newSessionEventId = $state('');
  let newSessionModerator = $state('');
  let newSessionSpeakerInput = $state('');
  let newSessionSpeakers = $state<string[]>([]);
  let creatingSession = $state(false);
  let createSessionError = $state('');

  // Per-event countdowns
  let countdowns: Record<string, { days: number; hours: number; minutes: number; seconds: number }> = $state({});
  let countdownInterval: ReturnType<typeof setInterval> | null = null;

  function computeCountdowns() {
    const now = new Date();
    const updated: typeof countdowns = {};
    for (const event of upcomingEvents) {
      const target = parseEventDate(event.event_date);
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

  async function loadDashboard() {
    loading = true;
    loadError = '';
    assetsError = false;
    try {
      const [sessionsResult, eventsResult] = await Promise.all([
        getSessions({ limit: OVERVIEW_LIMIT }), getEvents({ limit: OVERVIEW_LIMIT })
      ]);
      sessions = sessionsResult.items;
      events = eventsResult.items;
    } catch (e: any) {
      if (isAuthFailure(e)) { goto('/login'); return; }
      loadError = e?.message || 'Could not load your events and sessions.';
    }
    // Assets/storage are non-critical — fetch separately so failures don't block the dashboard
    try {
      const [assetsResult, storageResult] = await Promise.all([
        listAssets(), getStorageUsage()
      ]);
      recentAssets = (assetsResult as any[]).slice(0, 4);
      storageBytes = (storageResult as any).total_bytes ?? 0;
    } catch {
      assetsError = true;
    } finally {
      loading = false;
      computeCountdowns();
    }
  }

  onMount(async () => {
    checklist = loadChecklist();
    if (!isAuthenticated()) { goto('/login'); return; }
    await loadDashboard();
    countdownInterval = setInterval(computeCountdowns, 1000);
  });

  onDestroy(() => {
    if (countdownInterval) clearInterval(countdownInterval);
    if (copyTimer) clearTimeout(copyTimer);
  });

  function openCreateEvent() {
    createEventError = '';
    showCreateEvent = true;
  }

  function openCreateSession() {
    createSessionError = '';
    showCreateSession = true;
  }

  async function handleCreateEvent() {
    if (!newEventTitle.trim() || !newEventDate) return;
    creatingEvent = true;
    createEventError = '';
    try {
      const event = await createEvent({ title: newEventTitle.trim(), event_date: newEventDate, description: newEventDescription.trim() || null });
      events = [event, ...events];
      invalidateEvents();
      newEventTitle = ''; newEventDate = ''; newEventDescription = '';
      showCreateEvent = false;
      goto('/dashboard/events');
    } catch (e: any) {
      createEventError = e?.message || 'Could not create the event.';
    } finally { creatingEvent = false; }
  }

  async function handleCreateSession() {
    if (!newSessionTitle.trim() || !newSessionEventId) return;
    creatingSession = true;
    createSessionError = '';
    try {
      const session = await createSession(
        newSessionTitle.trim(),
        newSessionEventId,
        newSessionModerator.trim() || null,
        newSessionSpeakers
      );
      sessions = [session, ...sessions];
      invalidateSessions();
      newSessionTitle = '';
      newSessionEventId = '';
      newSessionModerator = '';
      newSessionSpeakerInput = '';
      newSessionSpeakers = [];
      showCreateSession = false;
      goto('/dashboard/sessions');
    } catch (e: any) {
      createSessionError = e?.message || 'Could not create the session.';
    } finally { creatingSession = false; }
  }

  function addNewSessionSpeaker() {
    const name = newSessionSpeakerInput.trim();
    if (!name) return;
    if (newSessionSpeakers.some((s) => s.toLowerCase() === name.toLowerCase())) {
      newSessionSpeakerInput = '';
      return;
    }
    newSessionSpeakers = [...newSessionSpeakers, name];
    newSessionSpeakerInput = '';
  }

  function removeNewSessionSpeaker(index: number) {
    newSessionSpeakers = newSessionSpeakers.filter((_, i) => i !== index);
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

  function formatEventDate(dateStr: string) {
    return parseEventDate(dateStr).toLocaleDateString();
  }

  const liveSessions = $derived(sessions.filter((s) => s.is_live));
  const upcomingEvents = $derived.by(() => {
    const today = todayKey();
    return events
      .filter((e) => e.event_date >= today)
      .sort((a, b) => a.event_date.localeCompare(b.event_date))
      .slice(0, 5);
  });
</script>

<svelte:head>
  <title>Dashboard – Rforum</title>
</svelte:head>

<main class="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-6 sm:py-8">

  <div class="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4 mb-6">
    <div>
      <h1 class="text-3xl font-heading font-bold tracking-wide">Dashboard</h1>
      <p class="text-surface-500 mt-1.5">Live sessions, upcoming events and quick actions</p>
    </div>
    <div class="flex gap-2">
      <button onclick={openCreateEvent} class="btn-secondary text-sm flex items-center justify-center gap-1.5 flex-1 sm:flex-none">
        <Plus class="w-4 h-4" /> Add Event
      </button>
      <button onclick={openCreateSession} class="btn-primary text-sm flex items-center justify-center gap-1.5 flex-1 sm:flex-none">
        <Plus class="w-4 h-4" /> Add Session
      </button>
    </div>
  </div>

  <!-- One shared live region for copy feedback (the visible feedback is on the button itself). -->
  <p class="sr-only" role="status" aria-live="polite">
    {#if copyState}{copyState.ok ? `Copied session code ${copyState.code}` : `Could not copy session code ${copyState.code}`}{/if}
  </p>

  {#if loading}
    <div class="grid gap-6 lg:grid-cols-3" aria-busy="true" aria-label="Loading dashboard">
      <div class="lg:col-span-2 card space-y-3">
        <div class="skeleton h-4 w-1/4 rounded"></div>
        {#each Array(3) as _}
          <div class="skeleton h-16 w-full rounded-xl"></div>
        {/each}
      </div>
      <div class="space-y-6">
        <div class="card space-y-3">
          <div class="skeleton h-4 w-1/3 rounded"></div>
          <div class="skeleton h-24 w-full rounded-xl"></div>
        </div>
        <div class="card space-y-3">
          <div class="skeleton h-4 w-1/3 rounded"></div>
          <div class="skeleton h-16 w-full rounded-xl"></div>
        </div>
      </div>
    </div>
  {:else}

    {#if loadError}
      <div class="card mb-6 flex flex-col sm:flex-row sm:items-center gap-3 border-danger/30" role="alert">
        <AlertTriangle class="w-5 h-5 text-danger flex-shrink-0" />
        <div class="flex-1 min-w-0">
          <p class="text-sm font-medium">Couldn't load your events and sessions</p>
          <p class="text-xs text-surface-500 mt-0.5 break-words">{loadError}</p>
        </div>
        <button onclick={loadDashboard} class="btn-secondary text-sm flex items-center justify-center gap-1.5">
          <RefreshCw class="w-4 h-4" /> Retry
        </button>
      </div>
    {/if}

    <!-- Live Sessions (if any) — most time-critical, so first -->
    {#if liveSessions.length > 0}
      <section class="card mb-6 border-live/30" aria-labelledby="live-heading">
        <div class="flex items-center justify-between gap-3 mb-3">
          <h2 id="live-heading" class="flex items-center gap-2 font-heading font-semibold text-sm uppercase tracking-widest text-surface-500">
            <span class="w-2 h-2 rounded-full bg-live animate-pulse-live"></span>
            Live Right Now
          </h2>
          <a href="/dashboard/sessions" class="text-xs text-brand-600 dark:text-brand-400 hover:underline flex items-center gap-1">
            All sessions <ArrowRight class="w-3 h-3" />
          </a>
        </div>
        <div class="space-y-2">
          {#each liveSessions.slice(0, 4) as session (session.id)}
            {@const copied = copyState?.id === session.id ? copyState : null}
            <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 px-4 py-3 rounded-xl border border-live/20 bg-live/5">
              <div class="flex items-center gap-3 flex-1 min-w-0 w-full">
                <span class="font-medium text-sm truncate">{session.title}</span>
                <button
                  onclick={() => copyCode(session.id, session.unique_code)}
                  class="font-mono text-xs px-1.5 py-0.5 rounded-md transition-colors flex items-center gap-1 flex-shrink-0
                         {copied && !copied.ok ? 'text-red-700 dark:text-red-300' : 'text-surface-600 dark:text-surface-400 hover:text-surface-900 dark:hover:text-surface-100 hover:bg-surface-100 dark:hover:bg-surface-800'}"
                  aria-label={`Copy session code ${session.unique_code}`}
                  title="Copy session code"
                >
                  {#if copied?.ok}
                    <Check class="w-3 h-3 text-emerald-600 dark:text-emerald-400" />Copied
                  {:else if copied}
                    <AlertTriangle class="w-3 h-3" />Copy failed · {session.unique_code}
                  {:else}
                    <Copy class="w-3 h-3" />{session.unique_code}
                  {/if}
                </button>
              </div>
              <a href="/dashboard/{session.id}" class="btn-secondary text-xs px-3 py-1.5 flex items-center justify-center gap-1 w-full sm:w-auto flex-shrink-0">
                <ExternalLink class="w-3 h-3" /> Manage
              </a>
            </div>
          {/each}
        </div>
        {#if liveSessions.length > 4}
          <p class="text-xs text-surface-500 mt-3">+{liveSessions.length - 4} more live — see all sessions.</p>
        {/if}
      </section>
    {/if}

    <div class="grid gap-6 lg:grid-cols-3 items-start">

      <!-- Upcoming Events -->
      <section class="card lg:col-span-2" aria-labelledby="upcoming-heading">
        <div class="flex items-center justify-between gap-3 mb-4">
          <h2 id="upcoming-heading" class="font-heading font-semibold text-sm uppercase tracking-widest text-surface-500">Upcoming Events</h2>
          <a href="/dashboard/events" class="text-xs text-brand-600 dark:text-brand-400 hover:underline flex items-center gap-1">
            All events <ArrowRight class="w-3 h-3" />
          </a>
        </div>

        {#if loadError}
          <p class="text-sm text-surface-500 py-6 text-center">Events are unavailable until they load.</p>
        {:else if upcomingEvents.length === 0}
          <div class="flex flex-col items-center py-8 gap-3 text-surface-500">
            <Calendar class="w-8 h-8 opacity-40" />
            <p class="text-sm">No upcoming events</p>
            <button onclick={openCreateEvent} class="text-xs text-brand-600 dark:text-brand-400 hover:underline">Create one →</button>
          </div>
        {:else}
          <div class="space-y-2">
            {#each upcomingEvents as event (event.id)}
              {@const cd = countdowns[event.id]}
              {@const today = isToday(event.event_date)}
              {@const eventDate = parseEventDate(event.event_date)}
              <a
                href="/dashboard/events?event={event.id}"
                class="flex items-center gap-4 px-4 py-3 rounded-xl border border-surface-200 dark:border-surface-800 hover:border-surface-300 dark:hover:border-surface-700 hover:bg-surface-50 dark:hover:bg-surface-800/40 transition-colors"
              >
                <!-- Date block -->
                <div class="flex-shrink-0 w-12 text-center">
                  <div class="text-2xl font-heading font-bold leading-none">{eventDate.getDate()}</div>
                  <div class="text-xs text-surface-500 uppercase tracking-wide mt-0.5">
                    {eventDate.toLocaleString('default', { month: 'short' })}
                  </div>
                </div>

                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2 mb-0.5 min-w-0">
                    {#if today}
                      <span class="text-live text-[10px] font-bold uppercase tracking-widest flex-shrink-0">Today</span>
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
                  <div class="hidden sm:flex flex-shrink-0 items-center gap-1.5 text-xs" aria-label={`Starts in ${cd.days} days ${cd.hours} hours ${cd.minutes} minutes`}>
                    {#each [{ v: cd.days, l: 'd' }, { v: cd.hours, l: 'h' }, { v: cd.minutes, l: 'm' }] as unit}
                      <div class="text-center" aria-hidden="true">
                        <span class="font-heading font-bold text-sm tabular-nums">{String(unit.v).padStart(2, '0')}</span>
                        <span class="text-surface-500">{unit.l}</span>
                      </div>
                      {#if unit.l !== 'm'}<span class="text-surface-500" aria-hidden="true">:</span>{/if}
                    {/each}
                  </div>
                {/if}

                <ArrowRight class="w-4 h-4 text-surface-400 flex-shrink-0" />
              </a>
            {/each}
          </div>
        {/if}
      </section>

      <div class="space-y-6">
        <!-- Checklist -->
        <section class="card" aria-labelledby="checklist-heading">
          <div class="flex items-center justify-between gap-3 mb-3">
            <h2 id="checklist-heading" class="font-heading font-semibold text-sm uppercase tracking-widest text-surface-500">Session Checklist</h2>
            <div class="flex items-center gap-3">
              <span class="text-xs text-surface-500">{doneCount}/{checklist.length} done</span>
              <button onclick={resetChecklist} class="text-xs text-surface-500 hover:text-surface-900 dark:hover:text-surface-200 transition-colors">Reset</button>
            </div>
          </div>
          <ul class="space-y-1 mb-3">
            {#each checklist as item (item.id)}
              <li class="flex items-center gap-3 group py-1">
                <button
                  onclick={() => toggleItem(item.id)}
                  class="flex-shrink-0 text-surface-500 hover:text-brand-600 dark:hover:text-brand-400 transition-colors"
                  role="checkbox"
                  aria-checked={item.done}
                  aria-label={item.label}
                >
                  {#if item.done}
                    <CheckSquare class="w-4 h-4 text-brand-600 dark:text-brand-400" />
                  {:else}
                    <Square class="w-4 h-4" />
                  {/if}
                </button>
                <span class="flex-1 text-sm {item.done ? 'line-through text-surface-500' : ''}">{item.label}</span>
                <button
                  onclick={() => removeItem(item.id)}
                  class="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity text-surface-500 hover:text-red-600 dark:hover:text-red-400"
                  aria-label={`Remove “${item.label}”`}
                >
                  <Trash2 class="w-3.5 h-3.5" />
                </button>
              </li>
            {/each}
          </ul>
          <form onsubmit={(e) => { e.preventDefault(); addItem(); }} class="flex gap-2">
            <input
              type="text"
              bind:value={newCheckItem}
              placeholder="Add item…"
              aria-label="New checklist item"
              class="input-field text-sm py-1.5 flex-1"
              maxlength="100"
            />
            <button type="submit" class="btn-secondary text-sm px-3 py-1.5 flex items-center gap-1" disabled={!newCheckItem.trim()}>
              <Plus class="w-3.5 h-3.5" /> Add
            </button>
          </form>
        </section>

        <!-- Session Assets: recent uploads -->
        <section class="card" aria-labelledby="assets-heading">
          <div class="flex items-center justify-between gap-3 mb-3">
            <h2 id="assets-heading" class="flex items-center gap-2 font-heading font-semibold text-sm uppercase tracking-widest text-surface-500">
              <HardDrive class="w-4 h-4 text-warning" /> Session Assets
            </h2>
            <a href="/dashboard/assets" class="text-xs text-brand-600 dark:text-brand-400 hover:underline flex items-center gap-1">
              Manage <ArrowRight class="w-3 h-3" />
            </a>
          </div>

          {#if assetsError}
            <p class="text-sm text-surface-500 py-4 flex items-center gap-2">
              <AlertTriangle class="w-4 h-4 text-warning flex-shrink-0" /> Couldn't load your files right now.
            </p>
          {:else}
            <p class="text-xs text-surface-500 mb-3">
              Storage used: <span class="font-semibold text-surface-800 dark:text-surface-200">{formatBytes(storageBytes)}</span>
            </p>
            {#if recentAssets.length === 0}
              <div class="flex flex-col items-center py-6 gap-2 text-surface-500 text-center">
                <Upload class="w-7 h-7 opacity-40" />
                <p class="text-sm">No files uploaded yet. Upload slides through a session to get started.</p>
              </div>
            {:else}
              <ul class="divide-y divide-surface-100 dark:divide-surface-800">
                {#each recentAssets as asset (asset.id)}
                  <li class="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0">
                    <File class="w-4 h-4 text-surface-500 flex-shrink-0" />
                    <div class="flex-1 min-w-0">
                      <p class="text-sm font-medium truncate" title={asset.file_name}>{asset.file_name}</p>
                      <p class="text-xs text-surface-500 mt-0.5 truncate">
                        {#if asset.session_title}Session: {asset.session_title}
                        {:else if asset.event_title}Event: {asset.event_title}
                        {:else}Unlinked{/if}
                      </p>
                    </div>
                    <div class="text-right flex-shrink-0">
                      <p class="text-xs text-surface-500">{formatBytes(asset.file_size)}</p>
                      <p class="text-xs text-surface-500 mt-0.5">{new Date(asset.uploaded_at).toLocaleDateString()}</p>
                    </div>
                  </li>
                {/each}
              </ul>
            {/if}
          {/if}
        </section>
      </div>
    </div>

  {/if}
</main>

<!-- Create Event Modal -->
<Modal open={showCreateEvent} onClose={() => showCreateEvent = false} labelledBy="create-event-title">
  <h2 id="create-event-title" class="text-xl font-heading font-bold tracking-wide mb-5 pr-8">Create Event</h2>
  <form onsubmit={(e) => { e.preventDefault(); handleCreateEvent(); }} class="grid gap-4">
    <div class="grid gap-4 md:grid-cols-2">
      <div>
        <label for="dash-event-title" class="block text-xs font-medium text-surface-500 uppercase tracking-wider mb-1.5">Title</label>
        <input id="dash-event-title" type="text" bind:value={newEventTitle} placeholder="e.g. Annual Conference" class="input-field" />
      </div>
      <div>
        <label for="dash-event-date" class="block text-xs font-medium text-surface-500 uppercase tracking-wider mb-1.5">Date</label>
        <input id="dash-event-date" type="date" bind:value={newEventDate} class="input-field" />
      </div>
    </div>
    <div>
      <label for="dash-event-description" class="block text-xs font-medium text-surface-500 uppercase tracking-wider mb-1.5">Description <span class="normal-case">(optional)</span></label>
      <textarea id="dash-event-description" rows="2" bind:value={newEventDescription} placeholder="Brief description…" class="input-field resize-none"></textarea>
    </div>
    {#if createEventError}
      <p class="text-sm text-red-700 dark:text-red-300 flex items-center gap-2" role="alert">
        <AlertTriangle class="w-4 h-4 flex-shrink-0" /> {createEventError}
      </p>
    {/if}
    <div class="flex flex-col-reverse sm:flex-row justify-end gap-2 pt-2">
      <button type="button" onclick={() => showCreateEvent = false} class="btn-secondary text-sm">Cancel</button>
      <button type="submit" class="btn-primary text-sm" aria-busy={creatingEvent} disabled={creatingEvent || !newEventTitle.trim() || !newEventDate}>
        {creatingEvent ? 'Creating…' : 'Create Event'}
      </button>
    </div>
  </form>
</Modal>

<!-- Create Session Modal -->
<Modal open={showCreateSession} onClose={() => showCreateSession = false} labelledBy="create-session-title">
  <h2 id="create-session-title" class="text-xl font-heading font-bold tracking-wide mb-5 pr-8">Create Session</h2>
  <form onsubmit={(e) => { e.preventDefault(); handleCreateSession(); }} class="grid gap-4">
    <div>
      <label for="dash-session-event" class="block text-xs font-medium text-surface-500 uppercase tracking-wider mb-1.5">Event</label>
      <select id="dash-session-event" class="input-field" bind:value={newSessionEventId}>
        <option value="" disabled>Select an event</option>
        {#each events as event (event.id)}
          <option value={event.id}>{event.title} · {formatEventDate(event.event_date)}</option>
        {/each}
      </select>
    </div>
    <div>
      <label for="dash-session-title" class="block text-xs font-medium text-surface-500 uppercase tracking-wider mb-1.5">Session Title</label>
      <input id="dash-session-title" type="text" bind:value={newSessionTitle} placeholder="e.g. Morning Keynote" class="input-field" />
    </div>
    <div>
      <label for="dash-session-moderator" class="block text-xs font-medium text-surface-500 uppercase tracking-wider mb-1.5">Moderator Name <span class="normal-case">(optional)</span></label>
      <input id="dash-session-moderator" type="text" bind:value={newSessionModerator} placeholder="e.g. Priya Nair" class="input-field" />
    </div>
    <div>
      <label for="dash-session-speaker" class="block text-xs font-medium text-surface-500 uppercase tracking-wider mb-1.5">Guest Speakers / Panelists</label>
      <div class="flex gap-2">
        <input
          id="dash-session-speaker"
          type="text"
          bind:value={newSessionSpeakerInput}
          placeholder="Add speaker name"
          class="input-field"
          onkeydown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              addNewSessionSpeaker();
            }
          }}
        />
        <button type="button" class="btn-secondary" onclick={addNewSessionSpeaker}>Add</button>
      </div>
    </div>
    {#if newSessionSpeakers.length > 0}
      <div class="flex flex-wrap gap-2">
        {#each newSessionSpeakers as speaker, index (speaker + index)}
          <span class="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-surface-200 dark:border-surface-700 text-xs">
            {speaker}
            <button type="button" class="text-surface-500 hover:text-danger transition-colors" onclick={() => removeNewSessionSpeaker(index)} aria-label={`Remove ${speaker}`}>
              <X class="w-3 h-3" />
            </button>
          </span>
        {/each}
      </div>
    {/if}
    {#if createSessionError}
      <p class="text-sm text-red-700 dark:text-red-300 flex items-center gap-2" role="alert">
        <AlertTriangle class="w-4 h-4 flex-shrink-0" /> {createSessionError}
      </p>
    {/if}
    <div class="flex flex-col-reverse sm:flex-row justify-end gap-2 pt-2">
      <button type="button" onclick={() => showCreateSession = false} class="btn-secondary text-sm">Cancel</button>
      <button type="submit" class="btn-primary text-sm" aria-busy={creatingSession} disabled={creatingSession || !newSessionTitle.trim() || !newSessionEventId}>
        {creatingSession ? 'Creating…' : 'Create Session'}
      </button>
    </div>
  </form>
</Modal>
