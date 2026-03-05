<script lang="ts">
  import { goto } from '$app/navigation';
  import { listPublicEvents } from '$lib/api';
  import { theme, toggleTheme } from '$lib/theme';
  import { RadioTower, Moon, Sun, Zap, Users, BarChart3, MessageSquare, Calendar } from 'lucide-svelte';
  import { onMount } from 'svelte';
  import FeatureCard from '$lib/components/FeatureCard.svelte';
  import Nav from '$lib/components/Nav.svelte';

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

<div class="min-h-screen flex flex-col bg-slate-50 dark:bg-slate-950">

  <!-- Nav -->
  <Nav />

  <!-- Main -->
  <main class="flex-1 flex flex-col px-8 py-16">
    <div class="mx-auto w-full max-w-4xl space-y-12">
      <!-- Hero Section -->
      <div class="text-center space-y-3">
        <h1 class="text-5xl font-bold text-slate-900 dark:text-white">Rforum</h1>
        <p class="text-xl text-slate-500 dark:text-slate-400">Real-time engagement for live events and presentations</p>
      </div>

      <!-- Features Grid -->
      <div class="grid md:grid-cols-2 gap-4">
        <FeatureCard icon={Zap} title="Live Interaction" description="Engage your audience in real-time with instant polls, Q&A sessions, and feedback collection." color="amber" />
        <FeatureCard icon={Users} title="Audience Participation" description="Simple join codes make it easy for participants to join sessions from any device." color="cyan" />
        <FeatureCard icon={BarChart3} title="Real-time Analytics" description="View live poll results, word clouds, and feedback insights as they happen." color="emerald" />
        <FeatureCard icon={MessageSquare} title="Multiple Formats" description="Polls, Q&A, feedback forms, word clouds, and content slides all in one platform." color="rose" />
      </div>

      <!-- Today's Events Section -->
      {#if loadingEvent}
        <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm p-6">
          <p class="text-slate-400">Loading events...</p>
        </div>
      {:else if eventError && todayEvents.length === 0}
        <div class="space-y-4">
          <h2 class="text-3xl font-bold text-slate-900 dark:text-white">Today's Events</h2>
          <div class="flex flex-col items-center justify-center text-center gap-4 py-16">
            <div class="w-14 h-14 flex items-center justify-center rounded-2xl bg-purple-500/10">
              <Calendar class="w-7 h-7 text-purple-500" />
            </div>
            <div>
              <h3 class="text-lg font-semibold text-slate-900 dark:text-white">No events scheduled today</h3>
              <p class="text-sm text-slate-400 mt-1">Create an event to start engaging your audience</p>
            </div>
          </div>
        </div>
      {:else}
        <div>
          <h2 class="text-3xl font-bold text-slate-900 dark:text-white mb-1">Today's Events</h2>
          <p class="text-slate-500 dark:text-slate-400 mb-4">Join a live session or explore what's happening</p>
        </div>
        <div class="space-y-4">
          {#each todayEvents as event (event.id)}
            <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm hover:shadow-md transition-all duration-200 hover:scale-[1.01] p-6">
              <div class="flex items-start justify-between gap-4">
                <div>
                  <h3 class="text-2xl font-bold text-slate-900 dark:text-white mb-1">{event.title}</h3>
                  <p class="text-xs text-slate-500">
                    {event.event_date ? new Date(event.event_date).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' }) : ''}
                  </p>
                  {#if event.description}
                    <p class="text-sm text-slate-400 mt-2">{event.description}</p>
                  {/if}
                </div>
              </div>

              <div class="mt-6 space-y-3">
                <h4 class="text-base font-semibold text-slate-700 dark:text-slate-300">Available Sessions</h4>
                {#if !event.sessions?.length}
                  <p class="text-sm text-slate-400">No sessions scheduled yet.</p>
                {:else}
                  <div class="grid gap-3 md:grid-cols-2">
                    {#each event.sessions as session (session.id)}
                      <div class="flex items-center justify-between gap-4 p-3 rounded-lg bg-slate-100 dark:bg-slate-800/40 hover:bg-slate-200 dark:hover:bg-slate-700/40 transition">
                        <div class="flex-1">
                          <div class="text-sm font-medium text-slate-900 dark:text-white">{session.title}</div>
                          <div class="text-xs text-slate-400 font-mono mt-1">
                            {session.unique_code || 'Not live yet'}
                          </div>
                        </div>
                        {#if session.is_live}
                          <a href={`/session/${session.unique_code}`} class="bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-medium px-3 py-1.5 rounded-lg shadow-lg shadow-purple-500/20 transition active:scale-95 text-sm whitespace-nowrap">Join</a>
                        {:else}
                          <div class="text-xs text-slate-500 whitespace-nowrap">Coming soon</div>
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
  <footer class="flex items-center justify-between px-8 py-8 border-t border-slate-200 dark:border-slate-800 text-slate-500 text-sm mt-auto">
    <p class="text-xs">Rforum &copy; {new Date().getFullYear()}</p>
    <p>Made with <span class="text-red-500">❤</span> by Ajith</p>
  </footer>

</div>