<script>
  import '../app.css';
  import { theme, toggleTheme } from '$lib/theme';
  import { Moon, Sun } from 'lucide-svelte';
  import { onMount } from 'svelte';

  let mounted = $state(false);

  onMount(() => {
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-theme', $theme);
      document.documentElement.classList.toggle('dark', $theme === 'dark');
    }
    mounted = true;
  });

  // Keep the dark class in sync with theme changes
  $effect(() => {
    if (typeof document !== 'undefined') {
      document.documentElement.classList.toggle('dark', $theme === 'dark');
    }
  });

  let { children } = $props();
</script>

<div data-theme={$theme} class="min-h-screen flex flex-col {$theme === 'dark' ? 'dark' : ''}">
  {@render children()}
</div>

