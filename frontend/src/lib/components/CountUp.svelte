<script lang="ts">
  import { tweened } from 'svelte/motion';
  import { cubicOut } from 'svelte/easing';

  let { value, decimals = 0, suffix = '', duration = 700 }: {
    value: number;
    decimals?: number;
    suffix?: string;
    duration?: number;
  } = $props();

  const display = tweened(0, { duration, easing: cubicOut });

  $effect(() => {
    display.set(value ?? 0);
  });
</script>

<span>{$display.toFixed(decimals)}{suffix}</span>
