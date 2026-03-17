<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { login, register } from '$lib/api';
  import { Orbit, Mail, Lock, KeyRound, Eye, EyeOff } from 'lucide-svelte';

  let isRegister = $state(false);
  let email = $state('');
  let password = $state('');
  let inviteCode = $state('');
  let showPassword = $state(false);
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
        if (!inviteCode.trim()) {
          error = 'Invite code is required';
          loading = false;
          return;
        }
        await register(email, password, inviteCode.trim());
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
      <Orbit class="w-8 h-8 text-brand-500" />
      <span class="text-2xl font-heading font-bold tracking-wide">Rforum</span>
    </a>

    <div class="card p-6">
      <h1 class="text-xl font-heading font-bold mb-1">{isRegister ? 'Create an account' : 'Welcome back'}</h1>
      {#if isRegister}
        <p class="text-xs text-surface-500 mb-6">You need an invite code to register.</p>
      {:else}
        <p class="text-xs text-surface-500 mb-6">Sign in to manage your events and sessions.</p>
      {/if}

      <form onsubmit={(e) => { e.preventDefault(); handleSubmit(); }} class="space-y-4">
        {#if isRegister}
          <div class="relative">
            <KeyRound class="absolute left-3.5 top-3.5 w-4 h-4 text-surface-400" />
            <input
              type="text"
              bind:value={inviteCode}
              placeholder="Invite code"
              class="input-field pl-10 uppercase tracking-widest"
              maxlength="20"
              autocomplete="off"
            />
          </div>
        {/if}

        <div class="relative">
          <Mail class="absolute left-3.5 top-3.5 w-4 h-4 text-surface-400" />
          <input
            type="email"
            bind:value={email}
            placeholder="Email"
            class="input-field pl-10"
            required
          />
        </div>

        <div class="relative">
          <Lock class="absolute left-3.5 top-3.5 w-4 h-4 text-surface-400" />
          <input
            type={showPassword ? 'text' : 'password'}
            bind:value={password}
            placeholder="Password"
            class="input-field pl-10 pr-11"
            required
            minlength="6"
          />
          <button
            type="button"
            class="absolute right-3 top-1/2 -translate-y-1/2 text-surface-400 hover:text-surface-200 transition"
            onclick={() => showPassword = !showPassword}
            aria-label={showPassword ? 'Hide password' : 'Show password'}
          >
            {#if showPassword}
              <EyeOff class="w-4 h-4" />
            {:else}
              <Eye class="w-4 h-4" />
            {/if}
          </button>
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
          <button onclick={() => { isRegister = false; error = ''; }} class="text-brand-500 hover:underline font-medium">Log in</button>
        {:else}
          Need an account?
          <button onclick={() => { isRegister = true; error = ''; }} class="text-brand-500 hover:underline font-medium">Sign up</button>
        {/if}
      </div>
    </div>
  </div>
</div>
