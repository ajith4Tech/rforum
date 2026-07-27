<script lang="ts">
  import { ChevronLeft, ChevronRight } from 'lucide-svelte';

  let {
    total,
    limit,
    offset,
    itemCount,
    onPrev,
    onNext
  }: {
    total: number;
    limit: number;
    offset: number;
    itemCount: number;
    onPrev: () => void;
    onNext: () => void;
  } = $props();

  const from = $derived(total === 0 ? 0 : offset + 1);
  const to = $derived(offset + itemCount);
  const canPrev = $derived(offset > 0);
  const canNext = $derived(offset + itemCount < total);
</script>

<div class="flex items-center justify-between gap-3 pt-2">
  <p class="text-xs text-surface-500 dark:text-surface-400">
    Displaying {from}–{to} of {total}
  </p>
  <div class="flex items-center gap-2">
    <button
      type="button"
      class="btn-secondary text-sm flex items-center gap-1.5 px-3 py-1.5 disabled:opacity-40 disabled:cursor-not-allowed"
      onclick={onPrev}
      disabled={!canPrev}
      aria-label="Previous page"
    >
      <ChevronLeft class="w-3.5 h-3.5" />
      Previous
    </button>
    <button
      type="button"
      class="btn-secondary text-sm flex items-center gap-1.5 px-3 py-1.5 disabled:opacity-40 disabled:cursor-not-allowed"
      onclick={onNext}
      disabled={!canNext}
      aria-label="Next page"
    >
      Next
      <ChevronRight class="w-3.5 h-3.5" />
    </button>
  </div>
</div>
