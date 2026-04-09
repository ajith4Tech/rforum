<script lang="ts">
  import { goto } from '$app/navigation';
  import { logout, getMe, isAuthenticated } from '$lib/api';
  import { currentUser } from '$lib/stores';
  import Nav from '$lib/components/Nav.svelte';
  import { onMount } from 'svelte';

  function handleLogout() {
    logout();
    currentUser.set(null);
    goto('/');
  }

  onMount(async () => {
    if (!isAuthenticated()) { goto('/login'); return; }
    try {
      const me = await getMe();
      currentUser.set(me);
    } catch {
      logout();
      goto('/login');
    }
  });

  let { children } = $props();
</script>

<div class="min-h-screen flex flex-col overflow-x-hidden">
  <Nav authenticated onLogout={handleLogout} />
  <div class="pt-16 flex-1">
    {@render children()}
  </div>
  <footer class="border-t mt-auto">
    <div class="flex flex-col sm:flex-row items-center justify-center gap-3 px-4 md:px-8 py-3 text-surface-500 text-xs">
      <span>Powered by <span class="font-semibold text-surface-600 dark:text-surface-300">Tech4Good Community</span></span>
      <span class="hidden sm:inline">•</span>
      <span>Built with <span class="text-red-500">❤</span> by Ajith</span>
      <span class="hidden sm:inline">•</span>
      <span>Rforum@2026</span>
    </div>
  </footer>
</div>
