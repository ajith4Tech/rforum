<script lang="ts">
  import { goto } from '$app/navigation';
  import { isAuthenticated, joinSession } from '$lib/api';
  import { Radio, Users, BarChart3, MessageSquare, Zap } from 'lucide-svelte';

  let joinCode = $state('');
  let joinError = $state('');
  let joining = $state(false);

  async function handleJoin() {
    if (!joinCode.trim()) return;
    joining = true;
    joinError = '';
    try {
      const formatted = joinCode.toUpperCase().replace(/[^A-Z0-9]/g, '');
      const code = formatted.length > 4
        ? `${formatted.slice(0, 4)}-${formatted.slice(4, 8)}`
        : formatted;
      await joinSession(code);
      goto(`/session/${code}`);
    } catch (e: any) {
      joinError = e.message || 'Session not found';
    } finally {
      joining = false;
    }
  }
</script>

<svelte:head>
  <title>Rforum – Real-time Audience Engagement</title>
  <meta name="description" content="Engage your audience in real-time with polls, Q&A, and feedback. No app download required." />
</svelte:head>

<div class="min-h-screen flex flex-col">
  <!-- Nav -->
  <nav class="flex items-center justify-between px-6 py-4 border-b border-surface-800">
    <div class="flex items-center gap-2">
      <Radio class="w-7 h-7 text-brand-400" />
      <span class="text-xl font-bold tracking-tight">Rforum</span>
    </div>
    <div class="flex items-center gap-3">
      {#if isAuthenticated()}
        <a href="/dashboard" class="btn-primary text-sm">Dashboard</a>
      {:else}
        <a href="/login" class="btn-secondary text-sm">Log in</a>
        <a href="/login?mode=register" class="btn-primary text-sm">Sign up</a>
      {/if}
    </div>
  </nav>

  <!-- Hero -->
  <main class="flex-1 flex flex-col items-center justify-center px-6 py-20">
    <div class="max-w-2xl text-center animate-fade-in">
      <div class="inline-flex items-center gap-2 bg-brand-500/10 border border-brand-500/20 text-brand-400 text-sm font-medium px-4 py-1.5 rounded-full mb-8">
        <Zap class="w-4 h-4" />
        Real-time audience engagement
      </div>

      <h1 class="text-5xl md:text-6xl font-extrabold tracking-tight mb-6 leading-tight">
        Make every
        <span class="text-transparent bg-clip-text bg-gradient-to-r from-brand-400 to-brand-600">
          presentation
        </span>
        interactive
      </h1>

      <p class="text-lg text-surface-400 mb-12 max-w-lg mx-auto">
        Create polls, Q&A sessions, and collect feedback from your audience in real-time.
        No downloads, no sign-ups for participants.
      </p>

      <!-- Join Box -->
      <div class="card max-w-md mx-auto mb-16">
        <h2 class="text-sm font-semibold text-surface-400 uppercase tracking-wider mb-4">
          Join a session
        </h2>
        <form on:submit|preventDefault={handleJoin} class="flex gap-3">
          <input
            type="text"
            bind:value={joinCode}
            placeholder="Enter code (e.g. ABCD-1234)"
            class="input-field flex-1 font-mono text-center text-lg tracking-widest uppercase"
            maxlength="9"
          />
          <button type="submit" class="btn-primary whitespace-nowrap" disabled={joining}>
            {joining ? 'Joining...' : 'Join'}
          </button>
        </form>
        {#if joinError}
          <p class="text-danger text-sm mt-3">{joinError}</p>
        {/if}
      </div>

      <!-- Features -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-3xl mx-auto">
        <div class="card text-left animate-slide-up">
          <BarChart3 class="w-8 h-8 text-brand-400 mb-3" />
          <h3 class="font-semibold mb-1">Live Polls</h3>
          <p class="text-sm text-surface-400">Real-time bar charts that update as your audience votes.</p>
        </div>
        <div class="card text-left animate-slide-up" style="animation-delay: 0.1s">
          <MessageSquare class="w-8 h-8 text-brand-400 mb-3" />
          <h3 class="font-semibold mb-1">Q&A Board</h3>
          <p class="text-sm text-surface-400">Crowdsource questions with upvoting to surface what matters.</p>
        </div>
        <div class="card text-left animate-slide-up" style="animation-delay: 0.2s">
          <Users class="w-8 h-8 text-brand-400 mb-3" />
          <h3 class="font-semibold mb-1">Open Feedback</h3>
          <p class="text-sm text-surface-400">Collect thoughts and opinions from everyone in the room.</p>
        </div>
      </div>
    </div>
  </main>

  <!-- Footer -->
  <footer class="text-center text-surface-600 text-sm py-6 border-t border-surface-800">
    Rforum &copy; {new Date().getFullYear()}
  </footer>
</div>
