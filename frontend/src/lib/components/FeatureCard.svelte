<script lang="ts">
  import type { Component } from 'svelte';

  let { icon, title, description, color = 'purple' }: {
    icon: Component;
    title: string;
    description: string;
    color?: string;
  } = $props();

  const colorMap: Record<string, string> = {
    amber: 'bg-amber-500/10 text-amber-500',
    cyan: 'bg-cyan-500/10 text-cyan-500',
    emerald: 'bg-emerald-500/10 text-emerald-500',
    rose: 'bg-rose-500/10 text-rose-500',
    purple: 'bg-purple-500/10 text-purple-500',
  };

  const iconClasses = colorMap[color] ?? colorMap.purple;
</script>

<div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm hover:shadow-md transition-all duration-200 hover:scale-[1.01] p-6">
  <div class="flex flex-col gap-3">
    <div class="w-10 h-10 flex items-center justify-center rounded-lg {iconClasses}">
      <svelte:component this={icon} class="w-5 h-5" />
    </div>
    <h3 class="text-base font-semibold text-slate-900 dark:text-white">{title}</h3>
    <p class="text-sm text-slate-500 dark:text-slate-400">{description}</p>
  </div>
</div>
