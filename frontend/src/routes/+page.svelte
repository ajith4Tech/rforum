<script lang="ts">
  import { listUpcomingPublicEvents } from '$lib/api';
  import { Orbit, Zap, Users, BarChart3, MessageSquare, Calendar, ExternalLink } from 'lucide-svelte';
  import { onMount, onDestroy } from 'svelte';
  import FeatureCard from '$lib/components/FeatureCard.svelte';
  import Nav from '$lib/components/Nav.svelte';

  let upcomingEvents: any[] = $state([]);
  let loadingEvents = $state(true);
  let eventsError = $state('');

  // Per-event countdowns: { [id]: { days, hours, minutes, seconds } }
  let countdowns: Record<string, { days: number; hours: number; minutes: number; seconds: number }> = $state({});
  let countdownInterval: ReturnType<typeof setInterval> | null = null;

  function computeCountdowns() {
    const now = new Date();
    const updated: typeof countdowns = {};
    for (const event of upcomingEvents) {
      const target = new Date(event.event_date + 'T00:00:00');
      const diff = target.getTime() - now.getTime();
      if (diff <= 0) {
        updated[event.id] = { days: 0, hours: 0, minutes: 0, seconds: 0 };
      } else {
        updated[event.id] = {
          days: Math.floor(diff / (1000 * 60 * 60 * 24)),
          hours: Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60)),
          minutes: Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60)),
          seconds: Math.floor((diff % (1000 * 60)) / 1000)
        };
      }
    }
    countdowns = updated;
  }

  function isToday(dateStr: string) {
    return dateStr === new Date().toISOString().slice(0, 10);
  }

  onMount(async () => {
    try {
      const data = await listUpcomingPublicEvents();
      upcomingEvents = Array.isArray(data) ? data : [];
    } catch (e: any) {
      eventsError = e.message || 'Could not load events';
    } finally {
      loadingEvents = false;
      computeCountdowns();
      countdownInterval = setInterval(computeCountdowns, 1000);
    }
  });

  onDestroy(() => {
    if (countdownInterval) clearInterval(countdownInterval);
  });
</script>

<svelte:head>
  <title>Rforum</title>
</svelte:head>

<div class="min-h-screen flex flex-col">
  <Nav />

  <main class="flex-1 flex flex-col px-8 pt-32 pb-16">
    <div class="mx-auto w-full max-w-4xl space-y-16">

      <!-- Hero -->
      <div class="text-center space-y-4">
        <h1 class="text-6xl font-heading font-bold tracking-wider">Rforum</h1>
        <p class="text-xl text-surface-500">Real-time engagement for live events and presentations</p>
      </div>

      <!-- Features Grid -->
      <div class="grid md:grid-cols-2 gap-5">
        <FeatureCard icon={Zap} title="Live Interaction" description="Engage your audience in real-time with instant polls, Q&A sessions, and feedback collection." color="amber" />
        <FeatureCard icon={Users} title="Audience Participation" description="Simple join codes make it easy for participants to join sessions from any device." color="cyan" />
        <FeatureCard icon={BarChart3} title="Real-time Analytics" description="View live poll results, word clouds, and feedback insights as they happen." color="emerald" />
        <FeatureCard icon={MessageSquare} title="Multiple Formats" description="Polls, Q&A, feedback forms, word clouds, and content slides all in one platform." color="rose" />
      </div>

      <!-- Upcoming Events -->
      <div>
        <div class="flex items-end justify-between mb-6">
          <div>
            <h2 class="text-3xl font-heading font-bold tracking-wide">Upcoming Events</h2>
            <p class="text-surface-500 mt-1">Join a live session or see what's coming up</p>
          </div>
        </div>

        {#if loadingEvents}
          <div class="card p-8 text-center text-surface-400">Loading events…</div>
        {:else if upcomingEvents.length === 0}
          <div class="card py-16 flex flex-col items-center gap-4 text-center">
            <div class="w-14 h-14 flex items-center justify-center rounded-2xl bg-brand-500/10">
              <Calendar class="w-7 h-7 text-brand-500" />
            </div>
            <div>
              <h3 class="text-lg font-heading font-semibold">No upcoming events</h3>
              <p class="text-sm text-surface-400 mt-1">Check back soon or sign in to create events</p>
            </div>
          </div>
        {:else}
          <div class="space-y-5">
            {#each upcomingEvents as event (event.id)}
              {@const cd = countdowns[event.id]}
              {@const today = isToday(event.event_date)}
              <div class="card card-interactive">
                <!-- Event header -->
                <div class="flex flex-col sm:flex-row sm:items-start justify-between gap-6">
                  <div class="flex-1">
                    <div class="flex items-center gap-3 mb-2 flex-wrap">
                      {#if today}
                        <span class="inline-flex items-center gap-1.5 text-live text-xs font-bold px-3 py-1 rounded-full bg-live/10 uppercase tracking-wider">
                          <span class="w-1.5 h-1.5 bg-live rounded-full animate-pulse-live"></span>
                          Today
                        </span>
                      {:else}
                        <span class="inline-flex items-center gap-1.5 text-brand-400 text-xs font-semibold px-3 py-1 rounded-full bg-brand-500/10 uppercase tracking-wider">
                          <Calendar class="w-3 h-3" />
                          Upcoming
                        </span>
                      {/if}
                    </div>
                    <h3 class="text-2xl font-heading font-bold tracking-wide">{event.title}</h3>
                    <p class="text-sm text-surface-500 mt-1">
                      {new Date(event.event_date + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
                    </p>
                    {#if event.description}
                      <p class="text-sm text-surface-400 mt-2">{event.description}</p>
                    {/if}
                  </div>

                  <!-- Countdown -->
                  {#if cd && !today}
                    <div class="flex-shrink-0">
                      <p class="text-xs uppercase tracking-widest text-surface-500 mb-2 text-center">Starts in</p>
                      <div class="grid grid-cols-4 gap-2">
                        {#each [{ label: 'D', value: cd.days }, { label: 'H', value: cd.hours }, { label: 'M', value: cd.minutes }, { label: 'S', value: cd.seconds }] as unit}
                          <div class="rounded-xl border border-surface-200 dark:border-surface-800 bg-surface-100 dark:bg-surface-900 px-3 py-3 flex flex-col items-center gap-0.5 min-w-[52px]">
                            <span class="text-xl font-heading font-bold tabular-nums leading-none">{String(unit.value).padStart(2, '0')}</span>
                            <span class="text-[10px] text-surface-500 uppercase tracking-widest">{unit.label}</span>
                          </div>
                        {/each}
                      </div>
                    </div>
                  {:else if today}
                    <div class="flex-shrink-0 flex items-center">
                      <div class="rounded-2xl border border-live/30 bg-live/5 px-6 py-4 text-center">
                        <span class="text-live text-2xl font-heading font-bold">LIVE</span>
                        <p class="text-live/70 text-xs mt-1 uppercase tracking-wider">Today</p>
                      </div>
                    </div>
                  {/if}
                </div>

                <!-- Sessions -->
                {#if event.sessions?.length}
                  <div class="mt-5 pt-5 border-t border-surface-200 dark:border-surface-800">
                    <h4 class="text-xs font-semibold uppercase tracking-widest text-surface-500 mb-3">Sessions</h4>
                    <div class="grid gap-2 sm:grid-cols-2">
                      {#each event.sessions as session (session.id)}
                        <div class="flex items-center justify-between gap-3 px-4 py-3 rounded-xl border border-surface-200 dark:border-surface-800 hover:border-surface-300 dark:hover:border-surface-700 transition">
                          <div class="flex-1 min-w-0">
                            <div class="font-medium text-sm truncate">{session.title}</div>
                            <div class="font-mono text-xs text-surface-500 mt-0.5">{session.unique_code}</div>
                          </div>
                          {#if session.is_live}
                            <a href="/session/{session.unique_code}" class="btn-primary text-xs px-4 py-2 flex items-center gap-1.5 flex-shrink-0">
                              <ExternalLink class="w-3.5 h-3.5" />
                              Join
                            </a>
                          {:else}
                            <span class="text-xs text-surface-500 flex-shrink-0">Coming soon</span>
                          {/if}
                        </div>
                      {/each}
                    </div>
                  </div>
                {/if}
              </div>
            {/each}
          </div>
        {/if}
      </div>

    </div>
  </main>

  <footer class="flex items-center justify-between px-8 py-8 border-t text-surface-500 text-sm mt-auto">
    <p class="text-xs">Rforum &copy; {new Date().getFullYear()}</p>
    <p>Made with <span class="text-red-500">❤</span> by Ajith</p>
  </footer>
</div>
