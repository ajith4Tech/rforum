<script lang="ts">
  import { goto } from '$app/navigation';
  import { listPublicEvents } from '$lib/api';
  import { theme, toggleTheme } from '$lib/theme';
  import { RadioTower, Moon, Sun, Zap, Users, BarChart3, MessageSquare } from 'lucide-svelte';
  import { onMount } from 'svelte';

  let todayEvents: any[] = $state([]);
  let eventError = $state('');
  let loadingEvent = $state(true);

  onMount(async () => {
    try {
      const today = new Date().toISOString().slice(0, 10);
      const events = await listPublicEvents(today);
      console.log('Public events response:', { today, events });
      todayEvents = Array.isArray(events) ? events : [];
      if (todayEvents.length === 0) {
        eventError = 'No event scheduled for today';
      }
    } catch (e: any) {
      console.error('Error loading event:', e);
      eventError = e.message || 'No event scheduled for today';
    } finally {
      loadingEvent = false;
    }
  });
</script>

<svelte:head>
  <title>Rforum</title>
</svelte:head>

<div class="min-h-screen flex flex-col">

  <!-- Nav -->
  <nav class="flex items-center justify-between px-6 py-4 border-b">
    <div class="flex items-center gap-2">
      <RadioTower class="w-7 h-7 text-brand-500" />
      <span class="text-xl font-bold tracking-tight">Rforum</span>
    </div>
    <div class="flex items-center gap-3">
      <button
        on:click={toggleTheme}
        class="btn-secondary p-2.5"
        title="Toggle theme"
      >
        {#if $theme === 'dark'}
          <Sun class="w-5 h-5" />
        {:else}
          <Moon class="w-5 h-5" />
        {/if}
      </button>
      <a href="/login" class="btn-secondary text-sm">Log in</a>
      <a href="/login?mode=register" class="btn-primary text-sm">Sign up</a>
    </div>
  </nav>

  <!-- Main -->
  <main class="flex-1 flex flex-col px-6 py-16">
    <div class="mx-auto w-full max-w-4xl space-y-12">
      <!-- Hero Section -->
      <div class="text-center space-y-2">
        <h1 class="text-5xl font-bold">Rforum</h1>
        <p class="text-xl text-surface-500">Real-time engagement for live events and presentations</p>
      </div>

      <!-- Features Grid -->
      <div class="grid md:grid-cols-2 gap-4">
        <div class="card">
          <div class="flex items-start gap-3">
            <Zap class="w-6 h-6 text-amber-400 flex-shrink-0 mt-1" />
            <div>
              <h3 class="font-semibold mb-1">Live Interaction</h3>
              <p class="text-sm text-surface-500">Engage your audience in real-time with instant polls, Q&A sessions, and feedback collection.</p>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="flex items-start gap-3">
            <Users class="w-6 h-6 text-cyan-400 flex-shrink-0 mt-1" />
            <div>
              <h3 class="font-semibold mb-1">Audience Participation</h3>
              <p class="text-sm text-surface-500">Simple join codes make it easy for participants to join sessions from any device.</p>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="flex items-start gap-3">
            <BarChart3 class="w-6 h-6 text-emerald-400 flex-shrink-0 mt-1" />
            <div>
              <h3 class="font-semibold mb-1">Real-time Analytics</h3>
              <p class="text-sm text-surface-500">View live poll results, word clouds, and feedback insights as they happen.</p>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="flex items-start gap-3">
            <MessageSquare class="w-6 h-6 text-rose-400 flex-shrink-0 mt-1" />
            <div>
              <h3 class="font-semibold mb-1">Multiple Formats</h3>
              <p class="text-sm text-surface-500">Polls, Q&A, feedback forms, word clouds, and content slides all in one platform.</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Today's Events Section -->
      {#if loadingEvent}
        <div class="card">
          <p class="text-surface-500">Loading events...</p>
        </div>
      {:else if eventError && todayEvents.length === 0}
        <div>
          <h2 class="text-3xl font-bold mb-2">Today's Events</h2>
          <p class="text-surface-500">{eventError}</p>
        </div>
      {:else}
        <div>
          <h2 class="text-3xl font-bold mb-1">Today's Events</h2>
          <p class="text-surface-500 mb-4">Join a live session or explore what's happening</p>
        </div>
        <div class="space-y-4">
          {#each todayEvents as event (event.id)}
            <div class="card">
              <div class="flex items-start justify-between gap-4">
                <div>
                  <h3 class="text-2xl font-bold mb-1">{event.title}</h3>
                  <p class="text-sm text-surface-500">
                    {event.event_date ? new Date(event.event_date).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' }) : ''}
                  </p>
                  {#if event.description}
                    <p class="text-surface-400 mt-2">{event.description}</p>
                  {/if}
                </div>
              </div>

              <div class="mt-6">
                <h4 class="font-semibold mb-3 text-lg">Available Sessions</h4>
                {#if !event.sessions?.length}
                  <p class="text-surface-500">No sessions scheduled yet.</p>
                {:else}
                  <div class="grid gap-3 md:grid-cols-2">
                    {#each event.sessions as session (session.id)}
                      <div class="flex items-center justify-between gap-4 p-4 rounded-lg border">
                        <div class="flex-1">
                          <div class="font-semibold">{session.title}</div>
                          <div class="text-xs text-surface-500 font-mono mt-1">
                            {session.unique_code || 'Not live yet'}
                          </div>
                        </div>
                        {#if session.is_live}
                          <a href={`/session/${session.unique_code}`} class="btn-primary text-sm whitespace-nowrap">Join</a>
                        {:else}
                          <div class="text-xs text-surface-400 whitespace-nowrap">Coming soon</div>
                        {/if}
                      </div>
                    {/each}
                  </div>
                {/if}
              </div>
            </div>
          {/each}
        </div>
      {/if}
    </div>
  </main>


  <!-- Footer -->
  <footer class="flex items-center justify-between px-6 py-8 border-t text-surface-500 text-sm mt-auto">
    <p class="text-xs">Rforum &copy; {new Date().getFullYear()}</p>
    <p>Made with <span class="text-danger">❤</span> by Ajith</p>
  </footer>

</div>