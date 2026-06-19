<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { login, register } from '$lib/api';
  import { branding, loadBranding, resetBrandingCache } from '$lib/branding';
  import { Orbit, Mail, Lock, KeyRound, Eye, EyeOff, ShieldCheck } from 'lucide-svelte';

  let isRegister = $state(false);
  let email = $state('');
  let password = $state('');
  let inviteCode = $state('');
  let showPassword = $state(false);
  let error = $state('');
  let loading = $state(false);
  let settingsLoaded = $state(false);

  // Check URL params for mode
  $effect(() => {
    const mode = $page.url.searchParams.get('mode');
    if (mode === 'register') isRegister = true;
  });

  onMount(async () => {
    // Ensure fresh check — onboarding_locked may have changed since layout loaded
    resetBrandingCache();
    await loadBranding();
    settingsLoaded = true;
  });

  // When in onboarding mode (setup), we're always in "register" mode
  $effect(() => {
    if (settingsLoaded && !$branding.onboarding_locked) {
      isRegister = true;
    }
  });

  async function handleSubmit() {
    error = '';
    loading = true;
    try {
      if (isRegister) {
        const code = $branding.invite_required && $branding.onboarding_locked
          ? inviteCode.trim()
          : '';
        if ($branding.invite_required && $branding.onboarding_locked && !code) {
          error = 'Invite code is required';
          loading = false;
          return;
        }
        await register(email, password, code);
      }
      await login(email, password);
      goto('/dashboard');
    } catch (e: any) {
      error = e.message || 'Something went wrong';
    } finally {
      loading = false;
    }
  }

  const isSetupMode = $derived(settingsLoaded && !$branding.onboarding_locked);
</script>

<svelte:head>
  <title>{isSetupMode ? 'First-time Setup' : isRegister ? 'Sign up' : 'Log in'} – Rforum</title>
</svelte:head>

<div class="min-h-screen flex items-center justify-center px-6">
  <div class="w-full max-w-sm animate-fade-in">
    <a href="/" class="flex items-center gap-2 justify-center mb-10">
      <Orbit class="w-8 h-8 text-brand-500" />
      <span class="text-2xl font-heading font-bold tracking-wide">Rforum</span>
    </a>

    {#if !settingsLoaded}
      <div class="card p-8 flex items-center justify-center">
        <div class="w-6 h-6 border-2 border-brand-500 border-t-transparent rounded-full animate-spin"></div>
      </div>

    {:else if isSetupMode}
      <!-- ── First-time setup: create super admin ── -->
      <div class="card p-6">
        <div class="flex items-center gap-2 mb-1">
          <ShieldCheck class="w-5 h-5 text-brand-500" />
          <h1 class="text-xl font-heading font-bold">Create Admin Account</h1>
        </div>
        <p class="text-xs text-surface-500 mb-6">
          No users found. The first account becomes the super admin for this Rforum installation.
        </p>

        <form onsubmit={(e) => { e.preventDefault(); handleSubmit(); }} class="space-y-4">
          <div class="relative">
            <Mail class="absolute left-3.5 top-3.5 w-4 h-4 text-surface-400" />
            <input
              type="email"
              bind:value={email}
              placeholder="Admin email"
              class="input-field pl-10"
              required
            />
          </div>

          <div class="relative">
            <Lock class="absolute left-3.5 top-3.5 w-4 h-4 text-surface-400" />
            <input
              type={showPassword ? 'text' : 'password'}
              bind:value={password}
              placeholder="Password (min. 8 characters)"
              class="input-field pl-10 pr-11"
              required
              minlength="8"
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
            {loading ? 'Creating account…' : 'Create Admin Account'}
          </button>
        </form>
      </div>

    {:else}
      <!-- ── Normal login / register ── -->
      <div class="card p-6">
        <h1 class="text-xl font-heading font-bold mb-1">
          {isRegister ? 'Create an account' : 'Welcome back'}
        </h1>
        {#if isRegister}
          <p class="text-xs text-surface-500 mb-6">
            {$branding.invite_required ? 'You need an invite code to register.' : 'Fill in your details to register.'}
          </p>
        {:else}
          <p class="text-xs text-surface-500 mb-6">Sign in to manage your events and sessions.</p>
        {/if}

        <form onsubmit={(e) => { e.preventDefault(); handleSubmit(); }} class="space-y-4">
          {#if isRegister && $branding.invite_required}
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

          {#if !isRegister}
            <div class="text-right -mt-1">
              <a href="/forgot-password" class="text-xs text-surface-400 hover:text-brand-500 transition">Forgot password?</a>
            </div>
          {/if}

          {#if error}
            <p class="text-danger text-sm">{error}</p>
          {/if}

          <button type="submit" class="btn-primary w-full" disabled={loading}>
            {loading ? 'Please wait…' : isRegister ? 'Create account' : 'Log in'}
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
    {/if}
  </div>

  <footer class="fixed bottom-0 left-0 right-0 border-t bg-white dark:bg-surface-950">
    <div class="flex flex-col sm:flex-row items-center justify-center gap-3 px-4 md:px-8 py-3 text-surface-500 text-xs max-w-full">
      <span>Powered by <span class="font-semibold text-surface-600 dark:text-surface-300">Tech4Good Community</span></span>
      <span class="hidden sm:inline">•</span>
      <span>Built with <span class="text-red-500">❤</span> by Ajith</span>
      <span class="hidden sm:inline">•</span>
      <span>Rforum@2026</span>
    </div>
  </footer>
</div>
