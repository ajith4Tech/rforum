<script lang="ts">
  import { BarChart3, MessageSquare, Cloud, AlignLeft, Star, Plus, ListChecks, HelpCircle, Sliders, ClipboardList } from 'lucide-svelte';

  let {
    position,
    onInsert,
    highlighted = false
  }: { position: number; onInsert: (itemType: string, position: number) => void; highlighted?: boolean } = $props();

  let open = $state(false);
  let rootEl: HTMLDivElement | undefined = $state();

  $effect(() => {
    if (!open) return;
    function handlePointerDown(e: PointerEvent) {
      if (rootEl && !rootEl.contains(e.target as Node)) open = false;
    }
    function handleKeydown(e: KeyboardEvent) {
      if (e.key === 'Escape') open = false;
    }
    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('keydown', handleKeydown);
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('keydown', handleKeydown);
    };
  });

  const options = [
    { type: 'POLL', label: 'Poll', icon: BarChart3 },
    { type: 'MULTIPLE_CHOICE', label: 'Multiple Choice', icon: ListChecks },
    { type: 'QUIZ', label: 'Quiz', icon: HelpCircle },
    { type: 'QNA', label: 'Q&A', icon: MessageSquare },
    { type: 'RATING', label: 'Rating', icon: Star },
    { type: 'SCALE', label: 'Scale', icon: Sliders },
    { type: 'FEEDBACK', label: 'Feedback', icon: AlignLeft },
    { type: 'WORD_CLOUD', label: 'Word Cloud', icon: Cloud },
    { type: 'SURVEY', label: 'Survey', icon: ClipboardList }
  ];

  function pick(type: string) {
    open = false;
    onInsert(type, position);
  }
</script>

<div bind:this={rootEl} class="relative flex items-center py-1 group transition-[margin] duration-150" class:my-2={highlighted}>
  <div class="flex-1 rounded-full transition-[height,background-color] duration-150 {highlighted ? 'h-1 bg-brand-500 shadow-[0_0_8px_rgba(139,92,246,0.6)]' : 'h-px bg-surface-200 dark:bg-surface-800 group-hover:bg-brand-300 dark:group-hover:bg-brand-700'}"></div>
  <button
    onclick={() => (open = !open)}
    aria-expanded={open}
    aria-label={`Insert an interaction at position ${position + 1}`}
    class="mx-2 flex items-center gap-1 px-2 py-1 rounded-full text-[11px] font-medium border opacity-0 group-hover:opacity-100 focus-visible:opacity-100 hover:border-brand-400 hover:text-brand-600 hover:bg-brand-50 dark:hover:text-brand-300 dark:hover:bg-brand-500/10 transition {open ? 'opacity-100' : ''} {highlighted ? 'opacity-100 border-brand-400 text-brand-600 dark:text-brand-300' : 'border-surface-200 dark:border-surface-700 text-surface-600 dark:text-surface-400'}"
  >
    <Plus class="w-3 h-3" /> Add Interaction
  </button>
  <div class="flex-1 rounded-full transition-[height,background-color] duration-150 {highlighted ? 'h-1 bg-brand-500 shadow-[0_0_8px_rgba(139,92,246,0.6)]' : 'h-px bg-surface-200 dark:bg-surface-800 group-hover:bg-brand-300 dark:group-hover:bg-brand-700'}"></div>

  {#if open}
    <div class="absolute z-10 top-full mt-1 left-1/2 -translate-x-1/2 bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-800 rounded-xl shadow-lg p-1.5 flex gap-1 animate-fade-in">
      {#each options as opt}
        <button
          onclick={() => pick(opt.type)}
          class="group/opt flex flex-col items-center gap-1 px-2.5 py-2 rounded-lg hover:bg-brand-50 dark:hover:bg-brand-500/10 transition-colors"
          title={opt.label}
          aria-label={`Insert ${opt.label}`}
        >
          <opt.icon class="w-4 h-4 text-surface-500 dark:text-surface-400 group-hover/opt:text-brand-600 dark:group-hover/opt:text-brand-400" />
          <span class="text-[10px] text-surface-500 dark:text-surface-400 whitespace-nowrap">{opt.label}</span>
        </button>
      {/each}
    </div>
  {/if}
</div>
