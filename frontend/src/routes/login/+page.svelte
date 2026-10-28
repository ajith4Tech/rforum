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

<div class="min-h-screen flex flex-col">
  <main class="flex-1 flex items-center justify-center px-6 py-10">
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
              <KeyRound class="absolute left-3.5 top-3.5 w-4 h-4 text-surface-400 pointer-events-none" aria-hidden="true" />
              <input
                id="login-invite-code"
                type="text"
                bind:value={inviteCode}
                placeholder="Invite code"
                aria-label="Invite code"
                class="input-field pl-10 uppercase tracking-widest"
                maxlength="20"
                autocomplete="off"
              />
            </div>
          {/if}

          <div class="relative">
            <Mail class="absolute left-3.5 top-3.5 w-4 h-4 text-surface-400 pointer-events-none" aria-hidden="true" />
            <input
              id="login-email"
              type="email"
              autocomplete="email"
              bind:value={email}
              placeholder="Email"
              aria-label="Email"
              class="input-field pl-10"
              required
            />
          </div>

          <div class="relative">
            <Lock class="absolute left-3.5 top-3.5 w-4 h-4 text-surface-400 pointer-events-none" aria-hidden="true" />
            <input
              id="login-password"
              type={showPassword ? 'text' : 'password'}
              autocomplete={isRegister ? 'new-password' : 'current-password'}
              bind:value={password}
              placeholder="Password"
              aria-label="Password"
              class="input-field pl-10 pr-11"
              required
              minlength="6"
            />
            <button
              type="button"
              class="absolute right-3 top-1/2 -translate-y-1/2 text-surface-500 hover:text-surface-800 dark:text-surface-400 dark:hover:text-surface-200 transition-colors"
              onclick={() => showPassword = !showPassword}
              aria-label={showPassword ? 'Hide password' : 'Show password'}
              aria-pressed={showPassword}
            >
              {#if showPassword}
                <EyeOff class="w-4 h-4" />
              {:else}
                <Eye class="w-4 h-4" />
              {/if}
            </button>
          </div>

          {#if error}
            <p class="text-red-700 dark:text-red-300 text-sm" role="alert">{error}</p>
          {/if}

          <button type="submit" class="btn-primary w-full" disabled={loading} aria-busy={loading}>
            {loading ? (isRegister ? 'Creating account…' : 'Logging in…') : isRegister ? 'Create account' : 'Log in'}
          </button>
        </form>

        <div class="mt-6 text-center text-sm text-surface-500">
          {#if isRegister}
            Already have an account?
            <button type="button" onclick={() => { isRegister = false; error = ''; }} class="text-brand-600 dark:text-brand-400 hover:underline font-medium">Log in</button>
          {:else}
            Need an account?
            <button type="button" onclick={() => { isRegister = true; error = ''; }} class="text-brand-600 dark:text-brand-400 hover:underline font-medium">Sign up</button>
          {/if}
        </div>
      </div>
    </div>
  </main>

  <!-- In normal flow (was position: fixed, which covered the form on short
       mobile viewports and when the keyboard was open). -->
  <footer class="border-t">
    <div class="flex flex-col sm:flex-row items-center justify-center gap-3 px-4 md:px-8 py-3 text-surface-500 text-xs max-w-full">
      <span>Powered by <span class="font-semibold text-surface-600 dark:text-surface-300">Tech4Good Community</span></span>
      <span class="hidden sm:inline">•</span>
      <span>Built with <span class="text-red-500">❤</span> by Ajith</span>
      <span class="hidden sm:inline">•</span>
      <span>Rforum@2026</span>
    </div>
  </footer>
</div>
