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
  <div class="pt-16">
    {@render children()}
  </div>
</div>
