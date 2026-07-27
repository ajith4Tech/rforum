<script lang="ts">
  import { BarChart3, MessageSquare, Cloud, AlignLeft, Star, Plus } from 'lucide-svelte';

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
    { type: 'QNA', label: 'Q&A', icon: MessageSquare },
    { type: 'WORD_CLOUD', label: 'Word Cloud', icon: Cloud },
    { type: 'FEEDBACK', label: 'Feedback', icon: AlignLeft },
    { type: 'RATING', label: 'Rating', icon: Star }
  ];

  function pick(type: string) {
    open = false;
    onInsert(type, position);
  }
</script>

<div bind:this={rootEl} class="relative flex items-center py-1 group transition-all" class:my-2={highlighted}>
  <div class="flex-1 rounded-full transition-all duration-150 {highlighted ? 'h-1 bg-purple-500 shadow-[0_0_8px_rgba(168,85,247,0.6)]' : 'h-px bg-slate-200 dark:bg-slate-800 group-hover:bg-purple-300 dark:group-hover:bg-purple-700'}"></div>
  <button
    onclick={() => (open = !open)}
    aria-expanded={open}
    aria-label={`Insert an interaction at position ${position + 1}`}
    class="mx-2 flex items-center gap-1 px-2 py-1 rounded-full text-[11px] font-medium border border-slate-200 dark:border-slate-700 text-slate-400 dark:text-slate-500 opacity-0 group-hover:opacity-100 hover:border-purple-400 hover:text-purple-600 hover:bg-purple-50 dark:hover:bg-purple-500/10 transition-all {open ? 'opacity-100' : ''} {highlighted ? 'opacity-100 border-purple-400 text-purple-600' : ''}"
  >
    <Plus class="w-3 h-3" /> Add Interaction
  </button>
  <div class="flex-1 rounded-full transition-all duration-150 {highlighted ? 'h-1 bg-purple-500 shadow-[0_0_8px_rgba(168,85,247,0.6)]' : 'h-px bg-slate-200 dark:bg-slate-800 group-hover:bg-purple-300 dark:group-hover:bg-purple-700'}"></div>

  {#if open}
    <div class="absolute z-10 top-full mt-1 left-1/2 -translate-x-1/2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-lg p-1.5 flex gap-1 animate-fade-in">
      {#each options as opt}
        <button
          onclick={() => pick(opt.type)}
          class="flex flex-col items-center gap-1 px-2.5 py-2 rounded-lg hover:bg-purple-50 dark:hover:bg-purple-500/10 transition-colors"
          title={opt.label}
          aria-label={`Insert ${opt.label}`}
        >
          <opt.icon class="w-4 h-4 text-slate-400 group-hover:text-purple-500" />
          <span class="text-[10px] text-slate-500 dark:text-slate-400 whitespace-nowrap">{opt.label}</span>
        </button>
      {/each}
    </div>
  {/if}
</div>
