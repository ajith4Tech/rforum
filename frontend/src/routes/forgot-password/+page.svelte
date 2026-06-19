<script lang="ts">
  import { goto } from '$app/navigation';
  import { forgotPassword } from '$lib/api';
  import { Orbit, Mail } from 'lucide-svelte';

  let email = $state('');
  let error = $state('');
  let loading = $state(false);
  let submitted = $state(false);
  let resetToken = $state<string | null>(null);

  async function handleSubmit() {
    error = '';
    loading = true;
    try {
      const res = await forgotPassword(email);
      resetToken = res.reset_token ?? null;
      submitted = true;
    } catch (e: any) {
      error = e.message || 'Something went wrong';
    } finally {
      loading = false;
    }
  }
</script>

<svelte:head>
  <title>Forgot Password – Rforum</title>
</svelte:head>

<div class="min-h-screen flex items-center justify-center px-6">
  <div class="w-full max-w-sm animate-fade-in">
    <a href="/" class="flex items-center gap-2 justify-center mb-10">
      <Orbit class="w-8 h-8 text-brand-500" />
      <span class="text-2xl font-heading font-bold tracking-wide">Rforum</span>
    </a>

    <div class="card p-6">
      {#if submitted}
        <h1 class="text-xl font-heading font-bold mb-1">Check your inbox</h1>
        <p class="text-sm text-surface-500 mb-6">
          If an account exists for <span class="font-medium text-surface-300">{email}</span>, a reset link has been generated.
        </p>

        {#if resetToken}
          <div class="bg-surface-800 rounded-lg p-4 mb-4 space-y-3">
            <p class="text-xs text-surface-400">Your reset link is ready. Click below to set a new password.</p>
            <a
              href="/reset-password?token={encodeURIComponent(resetToken)}"
              class="btn-primary w-full text-center block"
            >
              Reset my password
            </a>
          </div>
        {/if}

        <a href="/login" class="text-sm text-brand-500 hover:underline">Back to login</a>
      {:else}
        <h1 class="text-xl font-heading font-bold mb-1">Forgot your password?</h1>
        <p class="text-xs text-surface-500 mb-6">Enter your email and we'll generate a reset link.</p>

        <form onsubmit={(e) => { e.preventDefault(); handleSubmit(); }} class="space-y-4">
          <div class="relative">
            <Mail class="absolute left-3.5 top-3.5 w-4 h-4 text-surface-400" />
            <input
              type="email"
              bind:value={email}
              placeholder="Your email address"
              class="input-field pl-10"
              required
            />
          </div>

          {#if error}
            <p class="text-danger text-sm">{error}</p>
          {/if}

          <button type="submit" class="btn-primary w-full" disabled={loading}>
            {loading ? 'Please wait…' : 'Send reset link'}
          </button>
        </form>

        <div class="mt-6 text-center text-sm text-surface-500">
          Remembered it?
          <a href="/login" class="text-brand-500 hover:underline font-medium">Log in</a>
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
