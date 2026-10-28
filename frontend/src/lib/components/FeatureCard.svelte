<script lang="ts">
  import type { Component } from 'svelte';

  let { icon, title, description, color = 'brand' }: {
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
    brand: 'bg-brand-500/10 text-brand-500',
    purple: 'bg-brand-500/10 text-brand-500', // legacy alias
  };

  const iconClasses = $derived(colorMap[color] ?? colorMap.brand);
  const Icon = $derived(icon);
</script>

<div class="rounded-2xl border border-surface-200 dark:border-surface-800 bg-white dark:bg-surface-900 shadow-sm p-7">
  <div class="flex flex-col gap-4">
    <div class="w-14 h-14 flex items-center justify-center rounded-2xl {iconClasses}">
      <Icon class="w-7 h-7" />
    </div>
    <h3 class="text-lg font-heading font-semibold tracking-wide text-surface-900 dark:text-surface-100">{title}</h3>
    <p class="text-base text-surface-600 dark:text-surface-400 leading-relaxed">{description}</p>
  </div>
</div>
