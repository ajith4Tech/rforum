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

<div class="min-h-screen flex flex-col">
  <Nav authenticated onLogout={handleLogout} />
  <div class="pt-16">
    {@render children()}
  </div>
</div>
