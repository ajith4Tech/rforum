<script lang="ts">
  import { goto } from '$app/navigation';
  import { joinSession, listPublicEvents } from '$lib/api';
  import { Radio } from 'lucide-svelte';
  import { onMount } from 'svelte';

  let joinCode = $state('');
  let joinError = $state('');
  let joining = $state(false);

  let todayEvent: any = $state(null);
  let eventError = $state('');
  let loadingEvent = $state(true);

  onMount(async () => {
    try {
      const today = new Date().toISOString().slice(0, 10);
      const events = await listPublicEvents(today);
      console.log('Public events response:', { today, events });
      todayEvent = events?.[0] || null;
      console.log('Today event:', todayEvent);
      if (!todayEvent) {
        eventError = 'No event scheduled for today';
      }
    } catch (e: any) {
      console.error('Error loading event:', e);
      eventError = e.message || 'No event scheduled for today';
    } finally {
      loadingEvent = false;
    }
  });

  async function handleJoin() {
    if (!joinCode.trim()) return;
    joining = true;
    joinError = '';

    try {
      const formatted = joinCode.toUpperCase().replace(/[^A-Z0-9]/g, '');
      const code =
        formatted.length > 4
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
  <title>Rforum</title>
</svelte:head>

<div class="min-h-screen flex flex-col">

  <!-- Nav -->
  <nav class="flex items-center justify-between px-6 py-4 border-b border-surface-800">
    <div class="flex items-center gap-2">
      <Radio class="w-7 h-7 text-brand-400" />
      <span class="text-xl font-bold tracking-tight">Rforum</span>
    </div>
    <div class="flex items-center gap-3">
      <a href="/login" class="btn-secondary text-sm">Log in</a>
      <a href="/login?mode=register" class="btn-primary text-sm">Sign up</a>
    </div>
  </nav>

  <!-- Main -->
  <main class="flex-1 flex flex-col items-center justify-center px-6 py-16 gap-10">

    <!-- Join Session Jumbotron -->
    <div class="card max-w-md w-full text-center">
      <h2 class="text-lg font-semibold mb-4">Join a Session</h2>

      <form on:submit|preventDefault={handleJoin} class="flex gap-3">
        <input
          type="text"
          bind:value={joinCode}
          placeholder="Enter code (e.g. ABCD-1234)"
          class="input-field flex-1 font-mono text-center text-lg tracking-widest uppercase"
          maxlength="9"
        />

        <button
          type="submit"
          class="btn-primary whitespace-nowrap"
          disabled={joining}
        >
          {joining ? 'Joining...' : 'Join'}
        </button>
      </form>

      {#if joinError}
        <p class="text-danger text-sm mt-3">{joinError}</p>
      {/if}
    </div>

    <!-- Today's Event -->
    <div class="card max-w-2xl w-full text-left">
      <div class="flex items-start justify-between gap-4">
        <div>
          <h2 class="text-xl font-semibold mb-1">{todayEvent?.title || "Today's Event"}</h2>
          <p class="text-sm text-surface-500">
            {todayEvent?.event_date ? new Date(todayEvent.event_date).toLocaleDateString() : ''}
          </p>
          {#if todayEvent?.description}
            <p class="text-surface-400 mt-2">{todayEvent.description}</p>
          {/if}
        </div>
      </div>

      <div class="mt-4">
        <h3 class="font-medium mb-2">Sessions</h3>
        {#if loadingEvent}
          <p class="text-surface-500">Loading event...</p>
        {:else if eventError && !todayEvent}
          <p class="text-surface-500">{eventError}</p>
        {:else if !todayEvent?.sessions?.length}
          <p class="text-surface-500">No sessions scheduled yet.</p>
        {:else}
          <div class="space-y-2">
            {#each todayEvent.sessions as session (session.id)}
              <div class="flex items-center justify-between gap-4 p-3 rounded-lg border border-surface-800">
                <div class="flex-1">
                  <div class="font-medium">{session.title}</div>
                  <div class="text-xs text-surface-500 font-mono">{session.unique_code || 'Not live yet'}</div>
                </div>
                {#if session.is_live}
                  <a href={`/session/${session.unique_code}`} class="btn-primary text-sm">Join</a>
                {:else}
                  <div class="text-xs text-surface-400">Coming soon</div>
                {/if}
              </div>
            {/each}
          </div>
        {/if}
      </div>
    </div>

  </main>

  <!-- Footer -->
  <footer class="text-center text-surface-600 text-sm py-6 border-t border-surface-800">
    Rforum &copy; {new Date().getFullYear()}
  </footer>

</div>