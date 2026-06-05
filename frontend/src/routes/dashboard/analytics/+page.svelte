<script lang="ts">
  import { goto } from '$app/navigation';
  import { getAnalytics, listEvents, isAuthenticated, formatBytes } from '$lib/api';
  import {
    CalendarDays, ChevronRight, ArrowRight, Users, MessageSquare,
    Layers, BarChart2, HardDrive, Radio, TrendingUp, AlertCircle,
    Activity, Zap, Star
  } from 'lucide-svelte';
  import { onMount } from 'svelte';

  // ── Types ─────────────────────────────────────────────
  interface EventItem {
    id: string;
    title: string;
    event_date: string;
    description?: string | null;
    is_published: boolean;
    sessions: { id: string; title: string; is_live: boolean }[];
  }

  // ── State ─────────────────────────────────────────────
  let loading       = $state(true);
  let error         = $state('');
  let events: EventItem[] = $state([]);

  // Overview stats
  let totalEvents       = $state(0);
  let totalSessions     = $state(0);
  let totalSlides       = $state(0);
  let totalParticipants = $state(0);
  let totalResponses    = $state(0);
  let activeSessions    = $state(0);
  let storageUsedBytes  = $state(0);
  let avgRating: number | null = $state(null);
  let slideTypeDistribution: Record<string, number> = $state({});
  let responseCountsByType: Record<string, number> = $state({});
  let sessionEngagement: { session_id: string; title: string; total_responses: number; unique_participants: number; avg_rating: number | null }[] = $state([]);

  // ── Load ──────────────────────────────────────────────
  onMount(async () => {
    if (!isAuthenticated()) { goto('/login'); return; }
    try {
      const [analyticsData, eventsData]: [any, any] = await Promise.all([
        getAnalytics(),
        listEvents(),
      ]);
      totalEvents            = analyticsData.total_events            ?? 0;
      totalSessions          = analyticsData.total_sessions          ?? 0;
      totalSlides            = analyticsData.total_slides            ?? 0;
      totalParticipants      = analyticsData.total_participants      ?? 0;
      totalResponses         = analyticsData.total_responses         ?? 0;
      activeSessions         = analyticsData.active_sessions         ?? 0;
      storageUsedBytes       = analyticsData.storage_used_bytes      ?? 0;
      avgRating              = analyticsData.avg_rating              ?? null;
      slideTypeDistribution  = analyticsData.slide_type_distribution ?? {};
      responseCountsByType   = analyticsData.response_counts_by_type ?? {};
      sessionEngagement      = analyticsData.session_engagement      ?? [];
      events = eventsData as EventItem[];
    } catch (e: any) {
      const msg = e?.message || '';
      if (msg.includes('Unauthorized') || msg.includes('Not authenticated')) {
        goto('/login'); return;
      }
      error = msg || 'Failed to load analytics';
    } finally {
      loading = false;
    }
  });

  // ── Helpers ───────────────────────────────────────────
  function formatDate(dateStr: string) {
    if (!dateStr) return '—';
    try {
      return new Date(dateStr + 'T00:00:00').toLocaleDateString(undefined, {
        year: 'numeric', month: 'short', day: 'numeric'
      });
    } catch { return dateStr; }
  }

  function isToday(dateStr: string) {
    return dateStr === new Date().toISOString().slice(0, 10);
  }

  const sortedEvents = $derived(
    [...events].sort((a, b) => b.event_date.localeCompare(a.event_date))
  );

  const overallEngagement = $derived(
    totalSessions > 0
      ? Math.round((totalParticipants / totalSessions) * 10) / 10
      : 0
  );

  const avgResponsesPerParticipant = $derived(
    totalParticipants > 0 ? (totalResponses / totalParticipants).toFixed(1) : '0'
  );

  // Most active session
  const topSession = $derived(
    sessionEngagement.length > 0
      ? sessionEngagement.reduce((max, s) => s.total_responses > max.total_responses ? s : max, sessionEngagement[0])
      : null
  );

  // Type labels and colours
  const typeLabels: Record<string, string> = { POLL: 'Polls', QNA: 'Q&A', FEEDBACK: 'Feedback', CONTENT: 'Content', WORD_CLOUD: 'Word Cloud' };
  const typeColors: Record<string, string> = { POLL: '#7C3AED', QNA: '#06B6D4', FEEDBACK: '#F59E0B', CONTENT: '#10B981', WORD_CLOUD: '#EC4899' };


  // Donut helpers
  function getDonutSegments(dist: Record<string, number>) {
    const entries = Object.entries(dist);
    const total = entries.reduce((sum, [, v]) => sum + v, 0);
    if (total === 0) return [];
    let cumulative = 0;
    return entries.map(([key, value]) => {
      const pct = value / total;
      const start = cumulative;
      cumulative += pct;
      return { key, label: typeLabels[key] || key, color: typeColors[key] || '#94A3B8', value, pct: Math.round(pct * 100), startPct: start, endPct: cumulative };
    });
  }

  function describeArc(cx: number, cy: number, r: number, startPct: number, endPct: number) {
    const startAngle = startPct * 360 - 90;
    const endAngle = endPct * 360 - 90;
    const sweep = endAngle - startAngle;
    const toRad = (deg: number) => (deg * Math.PI) / 180;
    if (sweep >= 359.99) {
      const s = { x: cx + r * Math.cos(toRad(startAngle)), y: cy + r * Math.sin(toRad(startAngle)) };
      const m = { x: cx + r * Math.cos(toRad(startAngle + 180)), y: cy + r * Math.sin(toRad(startAngle + 180)) };
      return `M ${s.x} ${s.y} A ${r} ${r} 0 1 1 ${m.x} ${m.y} A ${r} ${r} 0 1 1 ${s.x} ${s.y}`;
    }
    const s = { x: cx + r * Math.cos(toRad(startAngle)), y: cy + r * Math.sin(toRad(startAngle)) };
    const e = { x: cx + r * Math.cos(toRad(endAngle)), y: cy + r * Math.sin(toRad(endAngle)) };
    const largeArc = sweep > 180 ? 1 : 0;
    return `M ${s.x} ${s.y} A ${r} ${r} 0 ${largeArc} 1 ${e.x} ${e.y}`;
  }
</script>

<svelte:head>
  <title>Analytics – Rforum</title>
</svelte:head>

<main class="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8">

  <!-- Page Header -->
  <div class="mb-8 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
    <div>
      <h1 class="text-3xl font-heading font-bold tracking-tight text-surface-900 dark:text-surface-50">Analytics</h1>
      <p class="text-surface-500 dark:text-surface-400 mt-1">Platform-wide engagement insights and event performance metrics.</p>
    </div>
  </div>

  {#if loading}
    <div class="flex flex-col items-center justify-center py-24 gap-3">
      <div class="w-10 h-10 border-3 border-brand-500 border-t-transparent rounded-full animate-spin"></div>
      <span class="text-sm text-surface-500 dark:text-surface-400 font-medium">Loading analytics…</span>
    </div>

  {:else if error}
    <div class="card text-center py-16 max-w-xl mx-auto shadow-sm">
      <AlertCircle class="w-12 h-12 text-danger mx-auto mb-4" />
      <h2 class="text-lg font-heading font-bold mb-2">Error Loading Analytics</h2>
      <p class="text-sm text-surface-500 dark:text-surface-400 mb-6">{error}</p>
      <button onclick={() => window.location.reload()} class="btn-secondary text-sm px-6 py-2.5">Retry Loading</button>
    </div>

  {:else}

    <!-- ═══════════════════════════════════════════════════
         OVERVIEW KPI CARDS
         ═══════════════════════════════════════════════════ -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-5 mb-8">
      {#each [
        { label: 'Events',       value: totalEvents,       icon: CalendarDays,  bg: 'bg-brand-500/10 dark:bg-brand-500/15',   text: 'text-brand-500 dark:text-brand-400',   hover: 'hover:border-brand-500/30'   },
        { label: 'Sessions',     value: totalSessions,     icon: Layers,         bg: 'bg-accent-500/10 dark:bg-accent-500/15',  text: 'text-accent-500 dark:text-accent-400',  hover: 'hover:border-accent-500/30'  },
        { label: 'Participants', value: totalParticipants, icon: Users,          bg: 'bg-emerald-500/10 dark:bg-emerald-500/15', text: 'text-emerald-500 dark:text-emerald-400', hover: 'hover:border-emerald-500/30' },
        { label: 'Responses',    value: totalResponses,    icon: MessageSquare,  bg: 'bg-violet-500/10 dark:bg-violet-500/15',  text: 'text-violet-500 dark:text-violet-400',  hover: 'hover:border-violet-500/30'  },
        { label: 'Live Now',     value: activeSessions,    icon: Radio,          bg: 'bg-live/10 dark:bg-live/15',        text: 'text-live',        hover: 'hover:border-live/30'        },
        { label: 'Avg Rating',   value: avgRating !== null ? avgRating.toFixed(1) : '—', icon: Star, bg: 'bg-amber-500/10 dark:bg-amber-500/15', text: 'text-amber-500 dark:text-amber-400', hover: 'hover:border-amber-500/30' },
      ] as card}
        {@const Icon = card.icon}
        <div class="card p-6 bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-800 shadow-sm hover:shadow-md transition-all duration-300 relative overflow-hidden group {card.hover}">
          <div class="flex items-center justify-between mb-4">
            <div class="w-12 h-12 flex items-center justify-center rounded-2xl {card.bg} transition-transform duration-300 group-hover:scale-110 shadow-sm">
              <Icon class="w-6 h-6 {card.text}" />
            </div>
            {#if card.label === 'Live Now' && activeSessions > 0}
              <span class="flex h-2 w-2 relative">
                <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-live opacity-75"></span>
                <span class="relative inline-flex rounded-full h-2 w-2 bg-live"></span>
              </span>
            {/if}
          </div>
          <div class="text-3xl font-heading font-extrabold tabular-nums tracking-tight leading-none text-surface-900 dark:text-surface-50">{card.value}</div>
          <div class="text-xs text-surface-500 dark:text-surface-400 mt-2.5 uppercase tracking-wider font-semibold">{card.label}</div>
        </div>
      {/each}
    </div>

    <!-- ═══════════════════════════════════════════════════
         SECONDARY INSIGHTS ROW
         ═══════════════════════════════════════════════════ -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8">
      <!-- Avg participants / session -->
      <div class="card p-6 bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-800 shadow-sm flex items-center gap-5">
        <div class="w-14 h-14 flex items-center justify-center rounded-2xl bg-amber-500/10 dark:bg-amber-500/15 flex-shrink-0">
          <TrendingUp class="w-6 h-6 text-amber-500 dark:text-amber-400" />
        </div>
        <div>
          <div class="text-3xl font-heading font-extrabold tabular-nums text-surface-900 dark:text-surface-50">{overallEngagement}</div>
          <div class="text-xs text-surface-500 dark:text-surface-400 mt-1 uppercase tracking-wider font-semibold">Avg participants / session</div>
        </div>
      </div>

      <!-- Avg responses / participant -->
      <div class="card p-6 bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-800 shadow-sm flex items-center gap-5">
        <div class="w-14 h-14 flex items-center justify-center rounded-2xl bg-violet-500/10 dark:bg-violet-500/15 flex-shrink-0">
          <Activity class="w-6 h-6 text-violet-500 dark:text-violet-400" />
        </div>
        <div>
          <div class="text-3xl font-heading font-extrabold tabular-nums text-surface-900 dark:text-surface-50">{avgResponsesPerParticipant}</div>
          <div class="text-xs text-surface-500 dark:text-surface-400 mt-1 uppercase tracking-wider font-semibold">Avg responses / participant</div>
        </div>
      </div>

      <!-- Storage -->
      <div class="card p-6 bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-800 shadow-sm flex items-center gap-5">
        <div class="w-14 h-14 flex items-center justify-center rounded-2xl bg-brand-500/10 dark:bg-brand-500/15 flex-shrink-0">
          <HardDrive class="w-6 h-6 text-brand-500 dark:text-brand-400" />
        </div>
        <div class="flex-1 min-w-0">
          <div class="text-3xl font-heading font-extrabold text-surface-900 dark:text-surface-50">{formatBytes(storageUsedBytes)}</div>
          <div class="text-xs text-surface-500 dark:text-surface-400 mt-1 uppercase tracking-wider font-semibold">Storage used</div>
        </div>
        <a href="/dashboard/assets" class="btn-secondary text-xs px-3.5 py-2 flex-shrink-0 flex items-center gap-1.5 shadow-sm">
          Manage <ArrowRight class="w-3.5 h-3.5" />
        </a>
      </div>
    </div>

    <!-- ═══════════════════════════════════════════════════
         VISUALISATIONS ROW
         ═══════════════════════════════════════════════════ -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">

      <!-- Interactive Slide Types Donut -->
      <div class="card p-6 bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-800 shadow-sm">
        <div class="mb-6">
          <h2 class="font-heading font-bold text-lg text-surface-900 dark:text-surface-100">Interactive Slide Types</h2>
          <p class="text-xs text-surface-500 dark:text-surface-400 mt-0.5">Distribution of slide formats configured in active sessions.</p>
        </div>
        {#if Object.keys(slideTypeDistribution).length === 0}
          <div class="flex flex-col items-center justify-center py-12 text-surface-400">
            <Layers class="w-10 h-10 mb-3 opacity-30 text-surface-500" />
            <p class="text-sm font-medium">No slide configurations found</p>
          </div>
        {:else}
          {@const segments = getDonutSegments(slideTypeDistribution)}
          {@const total = Object.values(slideTypeDistribution).reduce((a, b) => a + b, 0)}
          <div class="flex flex-col sm:flex-row sm:items-center gap-8 min-h-[200px]">
            <svg viewBox="0 0 200 200" class="w-40 h-40 flex-shrink-0 mx-auto sm:mx-0">
              {#each segments as seg}
                <path d={describeArc(100, 100, 70, seg.startPct, seg.endPct)} fill="none" stroke={seg.color} stroke-width="20" stroke-linecap="round" />
              {/each}
              <text x="100" y="96" text-anchor="middle" class="fill-surface-900 dark:fill-surface-50" style="font-size:24px; font-weight:800; font-family:var(--font-heading);">{total}</text>
              <text x="100" y="116" text-anchor="middle" class="fill-surface-500 dark:fill-surface-400" style="font-size:10px; font-weight:500; uppercase tracking-widest">slides</text>
            </svg>
            <div class="space-y-3 flex-1 max-h-48 overflow-y-auto pr-1">
              {#each segments as seg}
                <div class="flex items-center justify-between text-sm py-0.5 border-b border-surface-100 dark:border-surface-800/40 last:border-0">
                  <div class="flex items-center gap-2.5">
                    <span class="w-3 h-3 rounded-full flex-shrink-0 shadow-sm" style="background:{seg.color}"></span>
                    <span class="text-surface-600 dark:text-surface-300 font-medium">{seg.label}</span>
                  </div>
                  <div class="flex items-center gap-2 font-mono">
                    <span class="font-bold text-surface-900 dark:text-surface-100">{seg.value}</span>
                    <span class="text-xs text-surface-400">({seg.pct}%)</span>
                  </div>
                </div>
              {/each}
            </div>
          </div>
        {/if}
      </div>

      <!-- Content Distribution Donut -->
      <div class="card p-6 bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-800 shadow-sm">
        <div class="mb-6">
          <h2 class="font-heading font-bold text-lg text-surface-900 dark:text-surface-100">Content Distribution</h2>
          <p class="text-xs text-surface-500 dark:text-surface-400 mt-0.5">Response engagement volumes categorized by slide type.</p>
        </div>
        {#if Object.keys(responseCountsByType).length === 0}
          <div class="flex flex-col items-center justify-center py-12 text-surface-400">
            <Layers class="w-10 h-10 mb-3 opacity-30 text-surface-500" />
            <p class="text-sm font-medium">No responses recorded yet</p>
          </div>
        {:else}
          {@const segments = getDonutSegments(responseCountsByType)}
          {@const totalResp = Object.values(responseCountsByType).reduce((a, b) => a + b, 0)}
          <div class="flex flex-col sm:flex-row sm:items-center gap-8 min-h-[200px]">
            <svg viewBox="0 0 200 200" class="w-40 h-40 flex-shrink-0 mx-auto sm:mx-0">
              {#each segments as seg}
                <path d={describeArc(100, 100, 70, seg.startPct, seg.endPct)} fill="none" stroke={seg.color} stroke-width="20" stroke-linecap="round" />
              {/each}
              <text x="100" y="96" text-anchor="middle" class="fill-surface-900 dark:fill-surface-50" style="font-size:24px; font-weight:800; font-family:var(--font-heading);">{totalResp}</text>
              <text x="100" y="116" text-anchor="middle" class="fill-surface-500 dark:fill-surface-400" style="font-size:10px; font-weight:500; uppercase tracking-widest">responses</text>
            </svg>
            <div class="space-y-3 flex-1 max-h-48 overflow-y-auto pr-1">
              {#each segments as seg}
                <div class="flex items-center justify-between text-sm py-0.5 border-b border-surface-100 dark:border-surface-800/40 last:border-0">
                  <div class="flex items-center gap-2.5">
                    <span class="w-3 h-3 rounded-full flex-shrink-0 shadow-sm" style="background:{seg.color}"></span>
                    <span class="text-surface-600 dark:text-surface-300 font-medium">{seg.label}</span>
                  </div>
                  <div class="flex items-center gap-2 font-mono">
                    <span class="font-bold text-surface-900 dark:text-surface-100">{seg.value}</span>
                    <span class="text-xs text-surface-400">({seg.pct}%)</span>
                  </div>
                </div>
              {/each}
            </div>
          </div>
        {/if}
      </div>
    </div>

    <!-- ═══════════════════════════════════════════════════
         MOST ACTIVE SESSION HIGHLIGHT
         ═══════════════════════════════════════════════════ -->
    {#if topSession}
      <div class="card p-6 mb-8 bg-gradient-to-r from-brand-500/5 to-accent-500/5 dark:from-brand-500/10 dark:to-accent-500/10 border border-brand-500/20 dark:border-brand-500/30 relative overflow-hidden shadow-sm hover:shadow-md transition-all duration-300">
        <div class="absolute -right-10 -top-10 w-44 h-44 bg-gradient-to-br from-brand-500/10 to-accent-500/10 rounded-full blur-xl pointer-events-none"></div>
        <div class="flex flex-col sm:flex-row sm:items-center gap-5 relative z-10">
          <div class="w-14 h-14 flex items-center justify-center rounded-2xl bg-brand-500/10 dark:bg-brand-500/15 flex-shrink-0 shadow-sm">
            <Zap class="w-7 h-7 text-brand-500 dark:text-brand-400" />
          </div>
          <div class="flex-1 min-w-0">
            <div class="text-[10px] text-brand-500 dark:text-brand-400 uppercase tracking-widest font-bold mb-1">Featured Active Session</div>
            <h3 class="font-heading font-extrabold text-xl text-surface-900 dark:text-surface-50 truncate">{topSession.title}</h3>
            <div class="flex flex-wrap items-center gap-4 mt-2 text-sm text-surface-500 dark:text-surface-400">
              <span class="flex items-center gap-1.5"><MessageSquare class="w-4 h-4 text-violet-400" />{topSession.total_responses} responses</span>
              <span class="flex items-center gap-1.5"><Users class="w-4 h-4 text-emerald-400" />{topSession.unique_participants} participants</span>
              {#if topSession.avg_rating !== null}
                <span class="flex items-center gap-1.5 text-amber-400 font-semibold">
                  <Star class="w-4 h-4 fill-current" /> {topSession.avg_rating.toFixed(1)} / 5.0
                </span>
              {/if}
            </div>
          </div>
          <button onclick={() => {
            const ev = events.find(e => e.sessions?.some(s => s.id === topSession.session_id));
            if (ev) goto(`/dashboard/analytics/${ev.id}/${topSession.session_id}`);
          }} class="btn-primary text-sm px-6 py-2.5 flex-shrink-0 shadow-md">
            View Details
          </button>
        </div>
      </div>
    {/if}

    <!-- ═══════════════════════════════════════════════════
         EVENTS LIST — ANALYTICS SUMMARY CARDS
         ═══════════════════════════════════════════════════ -->
    <div class="mb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-surface-200 dark:border-surface-800/80 pb-4">
      <div>
        <h2 class="font-heading font-bold text-xl text-surface-900 dark:text-surface-100">Events Analytics</h2>
        <p class="text-xs text-surface-500 dark:text-surface-400 mt-0.5">Select an event below to inspect deeper session summaries.</p>
      </div>
      <span class="text-xs font-semibold px-3 py-1 bg-surface-100 dark:bg-surface-800 text-surface-600 dark:text-surface-400 rounded-full">{events.length} total events</span>
    </div>

    {#if events.length === 0}
      <div class="card text-center py-16 bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-800 max-w-xl mx-auto shadow-sm">
        <CalendarDays class="w-12 h-12 text-surface-400 dark:text-surface-600 mx-auto mb-4 opacity-40" />
        <h3 class="font-heading font-bold text-xl mb-1">No Events Found</h3>
        <p class="text-surface-500 dark:text-surface-400 text-sm mb-6 max-w-md mx-auto">Create and publish interactive events in the dashboard to start collecting responses.</p>
        <a href="/dashboard/events" class="btn-primary text-sm px-6 py-2.5 shadow-md">Go to Events</a>
      </div>
    {:else}
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        {#each sortedEvents as ev (ev.id)}
          {@const today = isToday(ev.event_date)}
          {@const sessionCount = ev.sessions?.length ?? 0}
          {@const liveSess = ev.sessions?.filter(s => s.is_live).length ?? 0}
          <button
            onclick={() => goto(`/dashboard/analytics/${ev.id}`)}
            class="card text-left bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-800 hover:border-brand-500/40 dark:hover:border-brand-500/40 shadow-sm hover:shadow-md transition-all duration-300 group w-full flex flex-col justify-between"
          >
            <div>
              <!-- Top Header: Date/Status -->
              <div class="flex items-start justify-between gap-3 mb-4">
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2 flex-wrap mb-2">
                    {#if today}
                      <span class="text-live text-[10px] font-bold uppercase tracking-widest bg-live/10 px-2 py-0.5 rounded-md">Today</span>
                    {/if}
                    {#if ev.is_published}
                      <span class="text-[10px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-500 dark:text-emerald-400">Published</span>
                    {:else}
                      <span class="text-[10px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-surface-100 dark:bg-surface-800 text-surface-500 dark:text-surface-400">Draft</span>
                    {/if}
                    {#if liveSess > 0}
                      <span class="text-[10px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-rose-500/15 text-live flex items-center gap-1.5 border border-live/10">
                        <span class="w-1.5 h-1.5 rounded-full bg-live animate-pulse"></span>{liveSess} Live
                      </span>
                    {/if}
                  </div>
                  <h3 class="font-heading font-extrabold text-lg leading-snug text-surface-900 dark:text-surface-100 group-hover:text-brand-500 dark:group-hover:text-brand-400 transition-colors truncate">{ev.title}</h3>
                  <p class="text-xs text-surface-500 dark:text-surface-400 mt-1 font-medium">{formatDate(ev.event_date)}</p>
                </div>
                <div class="w-9 h-9 flex items-center justify-center rounded-xl bg-surface-50 dark:bg-surface-800 group-hover:bg-brand-500/10 group-hover:text-brand-500 transition-all duration-300">
                  <ChevronRight class="w-5 h-5 text-surface-400 dark:text-surface-500 group-hover:text-brand-500 dark:group-hover:text-brand-400" />
                </div>
              </div>

              {#if ev.description}
                <p class="text-xs text-surface-500 dark:text-surface-400 mb-5 line-clamp-2 leading-relaxed">{ev.description}</p>
              {/if}
            </div>

            <!-- Stats grid -->
            <div class="grid grid-cols-3 gap-4 pt-4 border-t border-surface-100 dark:border-surface-800/80 mt-auto">
              <div>
                <div class="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-surface-400 dark:text-surface-500 mb-1">
                  <Layers class="w-3.5 h-3.5" />Sessions
                </div>
                <div class="text-lg font-heading font-bold text-surface-900 dark:text-surface-50 tabular-nums">{sessionCount}</div>
              </div>
              <div>
                <div class="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-surface-400 dark:text-surface-500 mb-1">
                  <Users class="w-3.5 h-3.5" />Participants
                </div>
                <div class="text-lg font-heading font-bold text-surface-900 dark:text-surface-50 tabular-nums">
                  {sessionEngagement.filter(s => ev.sessions?.some(es => es.id === s.session_id)).reduce((sum, s) => sum + s.unique_participants, 0)}
                </div>
              </div>
              <div>
                <div class="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-surface-400 dark:text-surface-500 mb-1">
                  <MessageSquare class="w-3.5 h-3.5" />Responses
                </div>
                <div class="text-lg font-heading font-bold text-surface-900 dark:text-surface-50 tabular-nums">
                  {sessionEngagement.filter(s => ev.sessions?.some(es => es.id === s.session_id)).reduce((sum, s) => sum + s.total_responses, 0)}
                </div>
              </div>
            </div>
          </button>
        {/each}
      </div>
    {/if}

  {/if}
</main>
