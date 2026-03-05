<script lang="ts">
  import { goto } from '$app/navigation';
  import { logout } from '$lib/api';
  import Nav from '$lib/components/Nav.svelte';

  function handleLogout() {
    logout();
    goto('/');
  }

  let { children } = $props();
</script>

<div class="min-h-screen flex flex-col bg-slate-50 dark:bg-slate-950">
  <Nav authenticated onLogout={handleLogout} />
  {@render children()}
</div>
