<script>
  // Only the weights the UI actually uses (font-medium…font-extrabold; mono
  // 400/500). Each @font-face carries a unicode-range and font-display: swap,
  // so the browser fetches just the subsets a page renders and shows
  // fallback text meanwhile.
  import '@fontsource/inter/400.css';
  import '@fontsource/inter/500.css';
  import '@fontsource/inter/600.css';
  import '@fontsource/inter/700.css';
  import '@fontsource/inter/800.css';
  import '@fontsource/jetbrains-mono/400.css';
  import '@fontsource/jetbrains-mono/500.css';
  import '../app.css';
  import { theme, toggleTheme } from '$lib/theme';
  import { Moon, Sun } from 'lucide-svelte';
  import { onMount } from 'svelte';
  import { getOrgSettings } from '$lib/api';
  import { orgSettings } from '$lib/stores';

  let mounted = $state(false);

  onMount(() => {
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-theme', $theme);
      document.documentElement.classList.toggle('dark', $theme === 'dark');
    }
    mounted = true;

    // Public, unauthenticated — every guest-facing page needs the org's
    // favicon/name before any login happens. Swaps the static default
    // <link> hrefs in place; never triggers a reload.
    getOrgSettings().then((settings) => {
      orgSettings.set(settings);
      if (typeof document !== 'undefined') {
        document.querySelectorAll('link[rel="icon"], link[rel="alternate icon"]').forEach((link) => {
          link.setAttribute('href', settings.favicon_url);
        });
      }
    }).catch(() => {
      // Non-critical — keep the bundled default favicon/name.
    });
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

