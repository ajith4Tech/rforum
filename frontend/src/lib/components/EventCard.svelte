<script lang="ts">
  import StatusBadge from './StatusBadge.svelte';
  import SessionItem from './SessionItem.svelte';
  import { Pencil, Eye, EyeOff, Trash2 } from 'lucide-svelte';

  let {
    event,
    sessions = [],
    availableSessions = [],
    saving = false,
    addSessionSelection = '',
    onEdit,
    onTogglePublish,
    onDelete,
    onAddSession,
    onRemoveSession,
    onAddSessionSelectionChange,
  }: {
    event: any;
    sessions?: any[];
    availableSessions?: any[];
    saving?: boolean;
    addSessionSelection?: string;
    onEdit?: (event: any) => void;
    onTogglePublish?: (eventId: string, current: boolean) => void;
    onDelete?: (eventId: string) => void;
    onAddSession?: (eventId: string) => void;
    onRemoveSession?: (eventId: string, sessionId: string) => void;
    onAddSessionSelectionChange?: (eventId: string, value: string) => void;
  } = $props();

  function formatDate(dateStr: string) {
    return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  }
</script>

<div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm hover:shadow-md transition-all duration-200 hover:scale-[1.01] p-6 space-y-4">
  <!-- Header -->
  <div class="flex justify-between items-start">
    <div class="flex-1 min-w-0">
      <div class="flex items-center gap-2 mb-1">
        <h3 class="text-lg font-semibold text-slate-900 dark:text-white truncate">{event.title}</h3>
        <StatusBadge published={event.is_published} />
      </div>
      <p class="text-xs text-slate-500">
        {event.is_published ? 'Published' : 'Draft'} &bull; {formatDate(event.event_date)}
      </p>
      {#if event.description}
        <p class="text-sm text-slate-400 mt-1">{event.description}</p>
      {/if}
    </div>
    <div class="flex items-center gap-1.5 ml-4 flex-shrink-0">
      {#if onEdit}
        <button
          onclick={() => onEdit(event)}
          class="border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 p-2 rounded-lg text-sm transition active:scale-95"
          title="Edit"
        >
          <Pencil class="w-4 h-4 text-slate-500 dark:text-slate-400" />
        </button>
      {/if}
      {#if onTogglePublish}
        <button
          onclick={() => onTogglePublish(event.id, event.is_published)}
          class="border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 p-2 rounded-lg text-sm transition active:scale-95"
          title={event.is_published ? 'Unpublish' : 'Publish'}
        >
          {#if event.is_published}
            <EyeOff class="w-4 h-4 text-slate-500 dark:text-slate-400" />
          {:else}
            <Eye class="w-4 h-4 text-slate-500 dark:text-slate-400" />
          {/if}
        </button>
      {/if}
      {#if onDelete}
        <button
          onclick={() => onDelete(event.id)}
          class="border border-red-200 dark:border-red-900/50 hover:bg-red-50 dark:hover:bg-red-900/20 p-2 rounded-lg text-sm transition active:scale-95"
        >
          <Trash2 class="w-4 h-4 text-red-400" />
        </button>
      {/if}
    </div>
  </div>

  <!-- Sessions -->
  <div class="space-y-2">
    <div class="text-base font-semibold text-slate-700 dark:text-slate-300">Sessions</div>
    {#if sessions.length === 0}
      <p class="text-sm text-slate-400">No sessions assigned yet.</p>
    {:else}
      <div class="space-y-1.5">
        {#each sessions as session (session.id)}
          <SessionItem
            {session}
            {saving}
            onRemove={(sid) => onRemoveSession?.(event.id, sid)}
          />
        {/each}
      </div>
    {/if}
    <div class="flex items-center gap-2 pt-1">
      <select
        class="input-field flex-1 !py-2 text-sm"
        value={addSessionSelection}
        onchange={(e) => onAddSessionSelectionChange?.(event.id, (e.currentTarget as HTMLSelectElement).value)}
      >
        <option value="" disabled>Select session to add</option>
        {#each availableSessions as s (s.id)}
          <option value={s.id}>{s.title} ({s.unique_code})</option>
        {/each}
      </select>
      <button
        class="border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 px-4 py-2 rounded-lg text-sm transition active:scale-95"
        onclick={() => onAddSession?.(event.id)}
        disabled={saving || !addSessionSelection}
      >
        {saving ? 'Saving...' : 'Add'}
      </button>
    </div>
  </div>
</div>
