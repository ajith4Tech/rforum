<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { login, register } from '$lib/api';
  import { RadioTower, Mail, Lock } from 'lucide-svelte';

  let isRegister = $state(false);
  let email = $state('');
  let password = $state('');
  let error = $state('');
  let loading = $state(false);

  // Check URL params for mode
  $effect(() => {
    const mode = $page.url.searchParams.get('mode');
    if (mode === 'register') isRegister = true;
  });

  async function handleSubmit() {
    error = '';
    loading = true;
    try {
      if (isRegister) {
        await register(email, password);
        // Auto-login after registration
      }
      await login(email, password);
      goto('/dashboard');
    } catch (e: any) {
      error = e.message || 'Something went wrong';
    } finally {
      loading = false;
    }
  }
</script>

<svelte:head>
  <title>{isRegister ? 'Sign up' : 'Log in'} – Rforum</title>
</svelte:head>

<div class="min-h-screen flex items-center justify-center px-6">
  <div class="w-full max-w-sm animate-fade-in">
    <a href="/" class="flex items-center gap-2 justify-center mb-10">
      <RadioTower class="w-8 h-8 text-brand-500" />
      <span class="text-2xl font-bold">Rforum</span>
    </a>

    <div class="card">
      <h1 class="text-xl font-bold mb-6">{isRegister ? 'Create an account' : 'Welcome back'}</h1>

      <form on:submit|preventDefault={handleSubmit} class="space-y-4">
        <div class="relative">
          <Mail class="absolute left-3.5 top-3.5 w-4 h-4 text-surface-500" />
          <input
            type="email"
            bind:value={email}
            placeholder="Email"
            class="input-field pl-10"
            required
          />
        </div>

        <div class="relative">
          <Lock class="absolute left-3.5 top-3.5 w-4 h-4 text-surface-500" />
          <input
            type="password"
            bind:value={password}
            placeholder="Password"
            class="input-field pl-10"
            required
            minlength="6"
          />
        </div>

        {#if error}
          <p class="text-danger text-sm">{error}</p>
        {/if}

        <button type="submit" class="btn-primary w-full" disabled={loading}>
          {loading ? 'Please wait...' : isRegister ? 'Create account' : 'Log in'}
        </button>
      </form>

      <div class="mt-6 text-center text-sm text-surface-500">
        {#if isRegister}
          Already have an account?
          <button on:click={() => isRegister = false} class="text-brand-600 hover:underline">Log in</button>
        {:else}
          Don't have an account?
          <button on:click={() => isRegister = true} class="text-brand-600 hover:underline">Sign up</button>
        {/if}
      </div>
    </div>
  </div>
</div>
