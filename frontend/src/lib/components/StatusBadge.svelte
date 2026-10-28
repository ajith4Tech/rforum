<script lang="ts" module>
  export type StatusTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral';

  // 700-step text on light tints / 300-400 on dark keeps every tone ≥ 4.5:1 in
  // both themes (the old green-400 / yellow-400 text was ~2:1 on white).
  const toneClasses: Record<StatusTone, string> = {
    success: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
    warning: 'bg-amber-500/10 text-amber-700 dark:text-amber-400',
    danger: 'bg-red-500/10 text-red-700 dark:text-red-300',
    info: 'bg-brand-500/10 text-brand-700 dark:text-brand-300',
    neutral: 'bg-surface-200 text-surface-700 dark:bg-surface-800 dark:text-surface-300'
  };
</script>

<script lang="ts">
  // Either pass `published` (event Published/Draft badge) or an explicit
  // `tone` + `label` for any other status.
  let {
    published = false,
    tone,
    label
  }: {
    published?: boolean;
    tone?: StatusTone;
    label?: string;
  } = $props();

  const resolvedTone = $derived<StatusTone>(tone ?? (published ? 'success' : 'warning'));
  const resolvedLabel = $derived(label ?? (published ? 'Published' : 'Draft'));
</script>

<span class="px-2 py-1 rounded-md text-xs font-medium {toneClasses[resolvedTone]}">
  {resolvedLabel}
</span>
