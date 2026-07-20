<script lang="ts">
  import { Pencil, Trash2, GripVertical, Copy, ChevronUp, ChevronDown } from 'lucide-svelte';

  let {
    slide,
    active = false,
    icon: Icon,
    label = 'Slide',
    isFirst = false,
    isLast = false,
    onActivate,
    onEdit,
    onRemove,
    onDuplicate,
    onMove,
    onReorder
  }: {
    slide: any;
    active?: boolean;
    icon?: any;
    label?: string;
    isFirst?: boolean;
    isLast?: boolean;
    onActivate: (id: string) => void;
    onEdit: (id: string) => void;
    onRemove: (id: string) => void;
    onDuplicate?: (id: string) => void;
    onMove?: (id: string, delta: number) => void;
    onReorder?: (slideId: string, direction: 'up' | 'down') => void;
  } = $props();

  let isDragging = $state(false);
</script>

<div
  draggable={true}
  ondragstart={() => { isDragging = true; }}
  ondragend={() => { isDragging = false; }}
  aria-current={active ? 'true' : undefined}
  class="group flex items-center justify-between gap-2 p-2.5 rounded-xl border transition-all duration-200 cursor-grab active:cursor-grabbing {isDragging ? 'opacity-40 scale-[0.98]' : ''} {active
    ? 'border-purple-500/60 bg-purple-500/5 dark:bg-purple-500/10 shadow-sm'
    : 'border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800/50'}"
>
  <button class="flex items-center gap-2.5 text-left flex-1 min-w-0" onclick={() => onActivate(slide.id)}>
    <span class="flex-shrink-0 w-5 h-5 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity text-slate-400 dark:text-slate-600">
      <GripVertical class="w-4 h-4" />
    </span>
    {#if Icon}
      <span class="flex-shrink-0 w-7 h-7 flex items-center justify-center rounded-lg {active ? 'bg-purple-500/10 text-purple-600 dark:text-purple-400' : 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400'}">
        <Icon class="w-3.5 h-3.5" />
      </span>
    {/if}
    <span class="text-xs font-medium truncate {active ? 'text-purple-700 dark:text-purple-300' : 'text-slate-700 dark:text-slate-300'}">{label}</span>
  </button>

  <div class="flex items-center opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity flex-shrink-0">
    {#if onMove}
      <button onclick={() => onMove(slide.id, -1)} disabled={isFirst} class="p-1 rounded-md hover:bg-slate-200 dark:hover:bg-slate-700 transition disabled:opacity-30 disabled:pointer-events-none" aria-label="Move up" title="Move up">
        <ChevronUp class="w-3 h-3 text-slate-400 dark:text-slate-500" />
      </button>
      <button onclick={() => onMove(slide.id, 1)} disabled={isLast} class="p-1 rounded-md hover:bg-slate-200 dark:hover:bg-slate-700 transition disabled:opacity-30 disabled:pointer-events-none" aria-label="Move down" title="Move down">
        <ChevronDown class="w-3 h-3 text-slate-400 dark:text-slate-500" />
      </button>
    {/if}
    <button
      onclick={() => onEdit(slide.id)}
      class="p-1 rounded-md hover:bg-slate-200 dark:hover:bg-slate-700 transition"
      aria-label="Edit"
      title="Edit"
    >
      <Pencil class="w-3 h-3 text-slate-400 dark:text-slate-500" />
    </button>
    {#if onDuplicate}
      <button
        onclick={() => onDuplicate(slide.id)}
        class="p-1 rounded-md hover:bg-slate-200 dark:hover:bg-slate-700 transition"
        aria-label="Duplicate slide"
        title="Duplicate"
      >
        <Copy class="w-3 h-3 text-slate-400 dark:text-slate-500" />
      </button>
    {/if}
    <button
      onclick={() => onRemove(slide.id)}
      class="p-1 rounded-md hover:bg-red-50 dark:hover:bg-red-900/20 transition"
      aria-label="Delete slide"
      title="Delete"
    >
      <Trash2 class="w-3 h-3 text-red-400" />
    </button>
  </div>
</div>
