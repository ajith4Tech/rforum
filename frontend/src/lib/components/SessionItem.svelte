<script lang="ts">
  let { session, onRemove, saving = false, showRemove = true }: {
    session: any;
    onRemove?: (sessionId: string) => void;
    saving?: boolean;
    showRemove?: boolean;
  } = $props();
</script>

<div class="flex justify-between items-center p-3 rounded-lg bg-slate-100 dark:bg-slate-800/40 hover:bg-slate-200 dark:hover:bg-slate-700/40 transition">
  <div class="min-w-0">
    <div class="text-sm font-medium text-slate-900 dark:text-white truncate">{session.title}</div>
    <div class="text-xs text-slate-500 dark:text-slate-400 font-mono">{session.unique_code}</div>
  </div>
  {#if showRemove && onRemove}
    <button
      class="text-red-400 hover:text-red-300 text-xs font-medium transition"
      onclick={() => onRemove(session.id)}
      disabled={saving}
    >
      Remove
    </button>
  {/if}
</div>
