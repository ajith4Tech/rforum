<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { resetPassword } from '$lib/api';
  import { Orbit, Lock, Eye, EyeOff, CheckCircle } from 'lucide-svelte';

  let token = $state('');
  let newPassword = $state('');
  let confirmPassword = $state('');
  let showPassword = $state(false);
  let error = $state('');
  let loading = $state(false);
  let success = $state(false);

  onMount(() => {
    const param = $page.url.searchParams.get('token');
    if (param) token = decodeURIComponent(param);
  });

  async function handleSubmit() {
    error = '';
    if (!token.trim()) {
      error = 'Reset token is missing';
      return;
    }
    if (newPassword !== confirmPassword) {
      error = 'Passwords do not match';
      return;
    }
    if (newPassword.length < 8) {
      error = 'Password must be at least 8 characters';
      return;
    }
    loading = true;
    try {
      await resetPassword(token.trim(), newPassword);
      success = true;
      setTimeout(() => goto('/login'), 2500);
    } catch (e: any) {
      error = e.message || 'Something went wrong';
    } finally {
      loading = false;
    }
  }
</script>

<svelte:head>
  <title>Reset Password – Rforum</title>
</svelte:head>

<div class="min-h-screen flex items-center justify-center px-6">
  <div class="w-full max-w-sm animate-fade-in">
    <a href="/" class="flex items-center gap-2 justify-center mb-10">
      <Orbit class="w-8 h-8 text-brand-500" />
      <span class="text-2xl font-heading font-bold tracking-wide">Rforum</span>
    </a>

    <div class="card p-6">
      {#if success}
        <div class="flex flex-col items-center gap-3 py-4">
          <CheckCircle class="w-10 h-10 text-green-500" />
          <h1 class="text-xl font-heading font-bold">Password updated</h1>
          <p class="text-sm text-surface-500 text-center">Your password has been reset. Redirecting you to login…</p>
        </div>
      {:else}
        <h1 class="text-xl font-heading font-bold mb-1">Set new password</h1>
        <p class="text-xs text-surface-500 mb-6">Choose a strong password for your account.</p>

        <form onsubmit={(e) => { e.preventDefault(); handleSubmit(); }} class="space-y-4">
          {#if !$page.url.searchParams.get('token')}
            <!-- Token wasn't in URL — let user paste it manually -->
            <div class="relative">
              <input
                type="text"
                bind:value={token}
                placeholder="Reset token"
                class="input-field font-mono text-sm"
                autocomplete="off"
              />
            </div>
          {/if}

          <div class="relative">
            <Lock class="absolute left-3.5 top-3.5 w-4 h-4 text-surface-400" />
            <input
              type={showPassword ? 'text' : 'password'}
              bind:value={newPassword}
              placeholder="New password (min. 8 characters)"
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

          <div class="relative">
            <Lock class="absolute left-3.5 top-3.5 w-4 h-4 text-surface-400" />
            <input
              type={showPassword ? 'text' : 'password'}
              bind:value={confirmPassword}
              placeholder="Confirm new password"
              class="input-field pl-10"
              required
            />
          </div>

          {#if error}
            <p class="text-danger text-sm">{error}</p>
          {/if}

          <button type="submit" class="btn-primary w-full" disabled={loading}>
            {loading ? 'Updating password…' : 'Reset password'}
          </button>
        </form>

        <div class="mt-6 text-center text-sm text-surface-500">
          <a href="/login" class="text-brand-500 hover:underline font-medium">Back to login</a>
        </div>
      {/if}
    </div>
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
