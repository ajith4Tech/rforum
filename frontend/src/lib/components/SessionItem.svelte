<script lang="ts">
  let { session, eventId, onRemove, saving = false, showRemove = true }: {
    session: any;
    /** When set, renders an "Analytics" link into that event's drill-down analytics route. */
    eventId?: string;
    onRemove?: (sessionId: string) => void;
    saving?: boolean;
    showRemove?: boolean;
  } = $props();
</script>

<div class="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-2 p-3 rounded-lg bg-surface-100 dark:bg-surface-800/40">
  <div class="min-w-0">
    <div class="text-sm font-medium text-surface-900 dark:text-white truncate">{session.title}</div>
    <div class="text-xs text-surface-600 dark:text-surface-400 font-mono">{session.unique_code}</div>
  </div>
  <div class="flex items-center gap-3 flex-shrink-0 flex-wrap">
    <a
      href={`/dashboard/${session.id}`}
      class="text-xs font-medium text-brand-600 dark:text-brand-400 hover:underline"
    >
      Open Session
    </a>
    <a
      href={`/dashboard/sessions?edit=${session.id}`}
      class="text-xs font-medium text-surface-700 dark:text-surface-300 hover:text-surface-900 dark:hover:text-surface-100 hover:underline"
    >
      Edit Session
    </a>
    {#if eventId}
      <a
        href={`/dashboard/analytics/${eventId}/${session.id}`}
        class="text-xs font-medium text-surface-700 dark:text-surface-300 hover:text-surface-900 dark:hover:text-surface-100 hover:underline"
      >
        Analytics
      </a>
    {/if}
    {#if showRemove && onRemove}
      <button
        class="text-red-700 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300 text-xs font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        onclick={() => onRemove(session.id)}
        disabled={saving}
        aria-label={`Remove ${session.title} from this event`}
        title="Remove from this event (the session itself is kept)"
      >
        Remove
      </button>
    {/if}
  </div>
</div>
