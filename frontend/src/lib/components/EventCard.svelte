<script lang="ts">
  import StatusBadge from './StatusBadge.svelte';
  import SessionItem from './SessionItem.svelte';
  import { Pencil, Eye, EyeOff, Trash2 } from 'lucide-svelte';
  import { parseEventDate } from '$lib/dates';

  let {
    event,
    sessions = [],
    availableSessions = [],
    saving = false,
    creatingSession = false,
    addSessionSelection = '',
    onEdit,
    onTogglePublish,
    onDelete,
    onAddSession,
    onRemoveSession,
    onAddSessionSelectionChange,
    onCreateAndAddSession,
  }: {
    event: any;
    sessions?: any[];
    availableSessions?: any[];
    saving?: boolean;
    /** True while a new session created inline (see below) is being created + attached. */
    creatingSession?: boolean;
    addSessionSelection?: string;
    onEdit?: (event: any) => void;
    onTogglePublish?: (eventId: string, current: boolean) => void;
    onDelete?: (eventId: string) => void;
    onAddSession?: (eventId: string) => void;
    onRemoveSession?: (eventId: string, sessionId: string) => void;
    onAddSessionSelectionChange?: (eventId: string, value: string) => void;
    /** Create a brand-new session and attach it to this event in one step —
        lets the moderator skip the separate Sessions page entirely. */
    onCreateAndAddSession?: (eventId: string, title: string, moderatorName: string) => void | Promise<void>;
  } = $props();

  function formatDate(dateStr: string) {
    // event_date is a local calendar date — new Date('YYYY-MM-DD') would parse
    // it as UTC midnight and show the previous day west of UTC.
    return parseEventDate(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  }

  // ── Inline "create a new session" — self-contained, doesn't touch the
  // existing select/Add flow above it at all. ──
  let showCreateSessionForm = $state(false);
  let newSessionTitle = $state('');
  let newSessionModerator = $state('');

  function cancelCreateSession() {
    showCreateSessionForm = false;
    newSessionTitle = '';
    newSessionModerator = '';
  }

  async function submitCreateSession() {
    if (!newSessionTitle.trim() || creatingSession) return;
    try {
      await onCreateAndAddSession?.(event.id, newSessionTitle.trim(), newSessionModerator.trim());
    } catch {
      // Only clear the form on success — the caller reports the error itself
      // and rethrows, so the moderator's typed title/moderator aren't lost.
      return;
    }
    showCreateSessionForm = false;
    newSessionTitle = '';
    newSessionModerator = '';
  }
</script>

<div class="card p-5 sm:p-6 space-y-4">
  <!-- Header -->
  <div class="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-3">
    <div class="flex-1 min-w-0">
      <div class="flex items-center gap-2 mb-1">
        <h3 class="text-lg font-semibold truncate">{event.title}</h3>
        <StatusBadge published={event.is_published} />
      </div>
      <p class="text-xs text-surface-500">{formatDate(event.event_date)}</p>
      {#if event.description}
        <p class="text-sm text-surface-600 dark:text-surface-400 mt-1 break-words">{event.description}</p>
      {/if}
    </div>
    <div class="flex items-center gap-1.5 sm:ml-4 flex-shrink-0 self-start sm:self-auto">
      {#if onEdit}
        <button
          onclick={() => onEdit(event)}
          class="btn-secondary p-2"
          title="Edit"
          aria-label={`Edit event ${event.title}`}
        >
          <Pencil class="w-4 h-4 text-surface-500" />
        </button>
      {/if}
      {#if onTogglePublish}
        <button
          onclick={() => onTogglePublish(event.id, event.is_published)}
          class="btn-secondary p-2"
          title={event.is_published ? 'Unpublish' : 'Publish'}
          aria-label={`${event.is_published ? 'Unpublish' : 'Publish'} event ${event.title}`}
        >
          {#if event.is_published}
            <EyeOff class="w-4 h-4 text-surface-500" />
          {:else}
            <Eye class="w-4 h-4 text-surface-500" />
          {/if}
        </button>
      {/if}
      {#if onDelete}
        <button
          onclick={() => onDelete(event.id)}
          class="btn-danger p-2"
          title="Delete"
          aria-label={`Delete event ${event.title}`}
        >
          <Trash2 class="w-4 h-4" />
        </button>
      {/if}
    </div>
  </div>

  <!-- Sessions -->
  <div class="space-y-2">
    <h4 class="text-sm font-semibold text-surface-700 dark:text-surface-300">Sessions ({sessions.length})</h4>
    {#if sessions.length === 0}
      <p class="text-sm text-surface-500">No sessions assigned yet.</p>
    {:else}
      <div class="space-y-1.5">
        {#each sessions as session (session.id)}
          <SessionItem
            {session}
            eventId={event.id}
            {saving}
            onRemove={(sid) => onRemoveSession?.(event.id, sid)}
          />
        {/each}
      </div>
    {/if}
    <div class="flex flex-col sm:flex-row sm:items-center gap-2 pt-1">
      <select
        class="input-field flex-1 !py-2 text-sm"
        value={addSessionSelection}
        aria-label={`Add an existing session to ${event.title}`}
        onchange={(e) => onAddSessionSelectionChange?.(event.id, (e.currentTarget as HTMLSelectElement).value)}
      >
        <option value="" disabled>Select session to add</option>
        {#each availableSessions as s (s.id)}
          <option value={s.id}>{s.title} ({s.unique_code})</option>
        {/each}
      </select>
      <button
        class="btn-secondary w-full sm:w-auto"
        onclick={() => onAddSession?.(event.id)}
        disabled={saving || !addSessionSelection}
      >
        {saving ? 'Saving...' : 'Add'}
      </button>
    </div>

    {#if onCreateAndAddSession}
      {#if !showCreateSessionForm}
        <button
          type="button"
          class="text-xs text-brand-600 hover:text-brand-700 dark:text-brand-400 dark:hover:text-brand-300 font-medium pt-0.5 transition-colors"
          onclick={() => (showCreateSessionForm = true)}
        >
          + Create a new session for this event
        </button>
      {:else}
        <div class="rounded-xl border border-surface-200 dark:border-surface-800 p-3 space-y-2">
          <input
            type="text"
            class="input-field !py-2 text-sm w-full"
            placeholder="Session title"
            aria-label="New session title"
            bind:value={newSessionTitle}
            onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); submitCreateSession(); } }}
          />
          <input
            type="text"
            class="input-field !py-2 text-sm w-full"
            placeholder="Moderator name (optional)"
            aria-label="Moderator name (optional)"
            bind:value={newSessionModerator}
            onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); submitCreateSession(); } }}
          />
          <div class="flex flex-col-reverse sm:flex-row gap-2 justify-end">
            <button type="button" class="btn-secondary text-xs" onclick={cancelCreateSession} disabled={creatingSession}>
              Cancel
            </button>
            <button
              type="button"
              class="btn-primary text-xs"
              disabled={creatingSession || !newSessionTitle.trim()}
              onclick={submitCreateSession}
            >
              {creatingSession ? 'Creating…' : 'Create & add'}
            </button>
          </div>
        </div>
      {/if}
    {/if}
  </div>
</div>