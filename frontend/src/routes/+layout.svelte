<script>
  import '../app.css';
  import { theme, toggleTheme } from '$lib/theme';
  import { Moon, Sun } from 'lucide-svelte';
  import { onMount } from 'svelte';

  let mounted = $state(false);

  onMount(() => {
    // Apply theme on mount
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-theme', $theme);
    }
    mounted = true;
  });

  let { children } = $props();
</script>

<div data-theme={$theme} class="min-h-screen flex flex-col">
  {@render children()}
</div>

