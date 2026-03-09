<script lang="ts">
  import { goto } from '$app/navigation';
  import { getAnalytics, isAuthenticated } from '$lib/api';
  import { CalendarDays, Users, Radio, BarChart3, Star, TrendingUp, Layers, MessageSquare, Zap } from 'lucide-svelte';
  import { onMount } from 'svelte';

  let loading = $state(true);
  let error = $state('');
  let totalEvents = $state(0);
  let totalSessions = $state(0);
  let totalSlides = $state(0);
  let totalResponses = $state(0);
  let totalParticipants = $state(0);
  let activeSessions = $state(0);
  let slideTypeDistribution: Record<string, number> = $state({});
  let responseCountsByType: Record<string, number> = $state({});
  let engagementOverTime: { date: string; responses: number }[] = $state([]);
  let avgRating: number | null = $state(null);
  let ratingDistribution: Record<string, number> = $state({});
  let sessionEngagement: { session_id: string; title: string; total_responses: number; unique_participants: number; avg_rating: number | null }[] = $state([]);

  onMount(async () => {
    if (!isAuthenticated()) {
      goto('/login');
      return;
    }
    try {
      const data: any = await getAnalytics();
      totalEvents = data.total_events ?? 0;
      totalSessions = data.total_sessions ?? 0;
      totalSlides = data.total_slides ?? 0;
      totalResponses = data.total_responses ?? 0;
      totalParticipants = data.total_participants ?? 0;
      activeSessions = data.active_sessions ?? 0;
      slideTypeDistribution = data.slide_type_distribution ?? {};
      responseCountsByType = data.response_counts_by_type ?? {};
      engagementOverTime = data.engagement_over_time ?? [];
      avgRating = data.avg_rating ?? null;
      ratingDistribution = data.rating_distribution ?? {};
      sessionEngagement = data.session_engagement ?? [];
    } catch (e: any) {
      const msg = e?.message || '';
      if (msg.includes('Unauthorized') || msg.includes('Not authenticated')) {
        goto('/login');
        return;
      }
      error = msg || 'Failed to load analytics';
    } finally {
      loading = false;
    }
  });

  // Slide / response type colours and labels
  const typeColors: Record<string, string> = {
    POLL: '#7C3AED',
    QNA: '#06B6D4',
    FEEDBACK: '#F59E0B',
    CONTENT: '#10B981',
    WORD_CLOUD: '#EC4899'
  };
  const typeLabels: Record<string, string> = {
    POLL: 'Polls',
    QNA: 'Q&A',
    FEEDBACK: 'Feedback',
    CONTENT: 'Content',
    WORD_CLOUD: 'Word Cloud'
  };

  // Donut chart helpers (slide type distribution)
  function getDonutSegments() {
    const entries = Object.entries(slideTypeDistribution);
    const total = entries.reduce((sum, [, v]) => sum + v, 0);
    if (total === 0) return [];
    let cumulative = 0;
    return entries.map(([key, value]) => {
      const pct = value / total;
      const startAngle = cumulative * 360;
      cumulative += pct;
      const endAngle = cumulative * 360;
      return { key, label: typeLabels[key] || key, color: typeColors[key] || '#94A3B8', value, pct: Math.round(pct * 100), startAngle, endAngle };
    });
  }

  function polarToCartesian(cx: number, cy: number, r: number, angleDeg: number) {
    const rad = ((angleDeg - 90) * Math.PI) / 180;
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
  }

  function describeArc(cx: number, cy: number, r: number, startAngle: number, endAngle: number) {
    const sweep = endAngle - startAngle;
    if (sweep >= 359.99) {
      const mid = polarToCartesian(cx, cy, r, startAngle + 180);
      const end = polarToCartesian(cx, cy, r, startAngle + 359.99);
      const start = polarToCartesian(cx, cy, r, startAngle);
      return `M ${start.x} ${start.y} A ${r} ${r} 0 1 1 ${mid.x} ${mid.y} A ${r} ${r} 0 1 1 ${end.x} ${end.y}`;
    }
    const start = polarToCartesian(cx, cy, r, startAngle);
    const end = polarToCartesian(cx, cy, r, endAngle);
    const largeArc = sweep > 180 ? 1 : 0;
    return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 1 ${end.x} ${end.y}`;
  }

  // Line chart helpers
  function getLineChartPoints() {
    if (engagementOverTime.length === 0) return { points: '', fillPath: '', coords: [], maxY: 0, padding: 40, width: 600, height: 200, chartH: 120 };
    const padding = 40;
    const width = 600;
    const height = 200;
    const chartW = width - padding * 2;
    const chartH = height - padding * 2;
    const maxY = Math.max(...engagementOverTime.map((d) => d.responses), 1);
    const stepX = engagementOverTime.length > 1 ? chartW / (engagementOverTime.length - 1) : 0;
    const coords = engagementOverTime.map((d, i) => ({
      x: padding + i * stepX,
      y: padding + chartH - (d.responses / maxY) * chartH,
      label: d.date,
      value: d.responses
    }));
    const points = coords.map((c) => `${c.x},${c.y}`).join(' ');
    const firstX = coords[0]?.x ?? padding;
    const lastX = coords[coords.length - 1]?.x ?? padding;
    const bottom = padding + chartH;
    const fillPath = `M ${firstX},${bottom} L ${coords.map((c) => `${c.x},${c.y}`).join(' L ')} L ${lastX},${bottom} Z`;
    return { points, fillPath, coords, maxY, padding, width, height, chartH };
  }

  // Derived stat cards
  const statCards = $derived([
    { label: 'Total Events', value: totalEvents, icon: CalendarDays, bgClass: 'bg-brand-500/10', textClass: 'text-brand-500' },
    { label: 'Total Sessions', value: totalSessions, icon: Layers, bgClass: 'bg-accent-500/10', textClass: 'text-accent-500' },
    { label: 'Total Participants', value: totalParticipants, icon: Users, bgClass: 'bg-emerald-500/10', textClass: 'text-emerald-500' },
    { label: 'Avg Rating', value: avgRating !== null ? avgRating.toFixed(1) : '—', icon: Star, bgClass: 'bg-amber-500/10', textClass: 'text-amber-500' }
  ]);

  // Participation funnel
  const funnelSteps = $derived([
    { label: 'Events', value: totalEvents, color: '#7C3AED' },
    { label: 'Sessions', value: totalSessions, color: '#06B6D4' },
    { label: 'Slides', value: totalSlides, color: '#10B981' },
    { label: 'Responses', value: totalResponses, color: '#F59E0B' },
    { label: 'Participants', value: totalParticipants, color: '#EC4899' }
  ]);

  const funnelMax = $derived(Math.max(...funnelSteps.map((s) => s.value), 1));

  // Response distribution by type
  const responseTypeEntries = $derived(
    Object.entries(responseCountsByType).sort(([, a], [, b]) => b - a)
  );
  const maxResponseCount = $derived(Math.max(...responseTypeEntries.map(([, v]) => v), 1));

  // Rating helpers
  const maxRatingCount = $derived(Math.max(...Object.values(ratingDistribution), 1));

  function ratingStars(rating: number | null): string {
    if (rating === null) return '—';
    return '★'.repeat(Math.round(rating)) + '☆'.repeat(5 - Math.round(rating));
  }

  // Engagement score per session (composite: responses weighted + participants + rating)
  function engagementScore(s: { total_responses: number; unique_participants: number; avg_rating: number | null }): number {
    const ratingBonus = s.avg_rating ? s.avg_rating / 5 : 0.5;
    return Math.round((s.total_responses * 0.5 + s.unique_participants * 0.5) * (0.6 + ratingBonus * 0.4));
  }

  const topSession = $derived(sessionEngagement.length > 0 ? sessionEngagement[0] : null);
</script>

<svelte:head>
  <title>Analytics – Rforum</title>
</svelte:head>

<main class="flex-1 max-w-6xl mx-auto w-full px-8 py-10">
  <div class="mb-10">
    <h1 class="text-3xl font-heading font-bold tracking-wide">Analytics</h1>
    <p class="text-surface-500 mt-1.5">Platform engagement insights and audience data</p>
  </div>

  {#if loading}
    <div class="text-center text-surface-400 py-20">Loading analytics...</div>
  {:else if error}
    <div class="text-center py-20">
      <p class="text-danger mb-2">{error}</p>
      <button onclick={() => window.location.reload()} class="text-sm text-brand-500 hover:underline">Retry</button>
    </div>
  {:else}
    <!-- Stat Cards -->
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-10">
      {#each statCards as card}
        {@const Icon = card.icon}
        <div class="card">
          <div class="flex items-center justify-between mb-4">
            <div class="w-11 h-11 flex items-center justify-center rounded-xl {card.bgClass}">
              <Icon class="w-5 h-5 {card.textClass}" />
            </div>
          </div>
          <div class="text-3xl font-heading font-bold tracking-tight">{card.value}</div>
          <div class="text-xs text-surface-500 mt-1.5 uppercase tracking-widest">{card.label}</div>
        </div>
      {/each}
    </div>

    <!-- Row 2: Content Distribution + Response Activity by Type -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">

      <!-- Donut: Slide Type Distribution (what content you have) -->
      <div class="card">
        <h2 class="text-sm font-heading font-semibold uppercase tracking-widest text-surface-500 mb-1">Content Distribution</h2>
        <p class="text-xs text-surface-400 mb-5">How many slides of each type you've created</p>
        {#if Object.keys(slideTypeDistribution).length === 0}
          <div class="flex flex-col items-center justify-center py-12 text-surface-400">
            <Layers class="w-10 h-10 mb-3 text-surface-500" />
            <p class="text-sm">No slides created yet</p>
          </div>
        {:else}
          <div class="flex items-center gap-8">
            <svg viewBox="0 0 200 200" class="w-40 h-40 flex-shrink-0">
              {#each getDonutSegments() as seg}
                <path d={describeArc(100, 100, 70, seg.startAngle, seg.endAngle)} fill="none" stroke={seg.color} stroke-width="28" stroke-linecap="round" />
              {/each}
              <text x="100" y="95" text-anchor="middle" style="font-size:24px; font-weight:700; fill:currentColor;">{Object.values(slideTypeDistribution).reduce((a, b) => a + b, 0)}</text>
              <text x="100" y="115" text-anchor="middle" style="font-size:11px; fill:#667091;">slides</text>
            </svg>
            <div class="space-y-2.5 flex-1">
              {#each getDonutSegments() as seg}
                <div class="flex items-center justify-between">
                  <div class="flex items-center gap-2">
                    <span class="w-2.5 h-2.5 rounded-full flex-shrink-0" style="background:{seg.color}"></span>
                    <span class="text-sm text-surface-400">{seg.label}</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-sm font-semibold">{seg.value}</span>
                    <span class="text-xs text-surface-500">({seg.pct}%)</span>
                  </div>
                </div>
              {/each}
            </div>
          </div>
        {/if}
      </div>

      <!-- Bar: Response Activity by Slide Type (where engagement actually comes from) -->
      <div class="card">
        <h2 class="text-sm font-heading font-semibold uppercase tracking-widest text-surface-500 mb-1">Engagement by Format</h2>
        <p class="text-xs text-surface-400 mb-5">Total responses received per slide type</p>
        {#if responseTypeEntries.length === 0}
          <div class="flex flex-col items-center justify-center py-12 text-surface-400">
            <MessageSquare class="w-10 h-10 mb-3 text-surface-500" />
            <p class="text-sm">No responses recorded yet</p>
          </div>
        {:else}
          <div class="space-y-4">
            {#each responseTypeEntries as [type, count]}
              {@const pct = maxResponseCount > 0 ? (count / maxResponseCount) * 100 : 0}
              {@const color = typeColors[type] || '#94A3B8'}
              {@const label = typeLabels[type] || type}
              <div class="flex items-center gap-3">
                <span class="w-3 h-3 rounded-full flex-shrink-0" style="background:{color}"></span>
                <span class="text-sm text-surface-400 w-22 flex-shrink-0">{label}</span>
                <div class="flex-1 h-6 bg-surface-100 dark:bg-surface-800 rounded-full overflow-hidden">
                  <div class="h-full rounded-full transition-all duration-500" style="width:{pct}%; background:{color}"></div>
                </div>
                <span class="text-sm font-semibold w-10 text-right">{count}</span>
              </div>
            {/each}
            <p class="text-xs text-surface-500 pt-2">{totalResponses} total responses across all sessions</p>
          </div>
        {/if}
      </div>
    </div>

    <!-- Row 3: Engagement Timeline + Rating Distribution -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">

      <!-- Line Chart: Engagement over time -->
      <div class="card">
        <h2 class="text-sm font-heading font-semibold uppercase tracking-widest text-surface-500 mb-1">Response Trend</h2>
        <p class="text-xs text-surface-400 mb-5">Daily responses over the last 30 days</p>
        {#if engagementOverTime.length === 0}
          <div class="flex flex-col items-center justify-center py-12 text-surface-400">
            <TrendingUp class="w-10 h-10 mb-3 text-surface-500" />
            <p class="text-sm">No engagement data yet</p>
          </div>
        {:else}
          {@const chart = getLineChartPoints()}
          <svg viewBox="0 0 {chart.width} {chart.height}" class="w-full" preserveAspectRatio="xMidYMid meet">
            {#each [0, 0.25, 0.5, 0.75, 1] as tick}
              {@const y = chart.padding + chart.chartH - tick * chart.chartH}
              <line x1={chart.padding} y1={y} x2={chart.width - chart.padding} y2={y} stroke="currentColor" class="text-surface-800" stroke-width="0.5" />
              <text x={chart.padding - 8} y={y + 4} text-anchor="end" style="font-size:9px; fill:#667091;">{Math.round(tick * chart.maxY)}</text>
            {/each}
            <path d={chart.fillPath} fill="url(#engGradient)" opacity="0.3" />
            <polyline points={chart.points} fill="none" stroke="#7C3AED" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
            {#each chart.coords as pt}
              <circle cx={pt.x} cy={pt.y} r="4" fill="#7C3AED" stroke="currentColor" stroke-width="2" />
            {/each}
            {#each chart.coords as pt, i}
              {#if chart.coords.length <= 7 || i % Math.ceil(chart.coords.length / 7) === 0}
                <text x={pt.x} y={chart.height - 8} text-anchor="middle" style="font-size:8px; fill:#667091;">{pt.label.slice(5)}</text>
              {/if}
            {/each}
            <defs>
              <linearGradient id="engGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#7C3AED" stop-opacity="0.4" />
                <stop offset="100%" stop-color="#7C3AED" stop-opacity="0" />
              </linearGradient>
            </defs>
          </svg>
        {/if}
      </div>

      <!-- Rating Distribution -->
      <div class="card">
        <h2 class="text-sm font-heading font-semibold uppercase tracking-widest text-surface-500 mb-1">Feedback Ratings</h2>
        <p class="text-xs text-surface-400 mb-5">Distribution of star ratings from feedback slides</p>
        {#if Object.values(ratingDistribution).every((v) => v === 0)}
          <div class="flex flex-col items-center justify-center py-12 text-surface-400">
            <Star class="w-10 h-10 mb-3 text-surface-500" />
            <p class="text-sm">No ratings yet</p>
          </div>
        {:else}
          <div class="space-y-3">
            {#each [5, 4, 3, 2, 1] as star}
              {@const count = ratingDistribution[String(star)] ?? 0}
              {@const pct = maxRatingCount > 0 ? (count / maxRatingCount) * 100 : 0}
              <div class="flex items-center gap-3">
                <span class="text-sm font-medium text-surface-400 w-4 text-right">{star}</span>
                <Star class="w-4 h-4 text-amber-400 flex-shrink-0" />
                <div class="flex-1 h-5 bg-surface-100 dark:bg-surface-800 rounded-full overflow-hidden">
                  <div class="h-full rounded-full transition-all {star >= 4 ? 'bg-emerald-500' : star === 3 ? 'bg-amber-400' : 'bg-red-400'}" style="width:{pct}%"></div>
                </div>
                <span class="text-sm text-surface-500 w-8 text-right">{count}</span>
              </div>
            {/each}
          </div>
          {#if avgRating !== null}
            <div class="mt-5 pt-4 border-t border-surface-200 dark:border-surface-800 flex items-center justify-between">
              <span class="text-sm text-surface-500">Overall average</span>
              <div class="flex items-center gap-2">
                <span class="text-amber-400 text-sm tracking-wider">{ratingStars(avgRating)}</span>
                <span class="text-lg font-bold">{avgRating.toFixed(1)}</span>
              </div>
            </div>
          {/if}
        {/if}
      </div>
    </div>

    <!-- Row 4: Participation Funnel + Session Leaderboard -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-10">

      <!-- Participation Funnel -->
      <div class="card lg:col-span-1">
        <h2 class="text-sm font-heading font-semibold uppercase tracking-widest text-surface-500 mb-1">Participation Funnel</h2>
        <p class="text-xs text-surface-400 mb-6">How engagement flows through your platform</p>
        <div class="space-y-3">
          {#each funnelSteps as step, i}
            {@const widthPct = funnelMax > 0 ? Math.max((step.value / funnelMax) * 100, 8) : 8}
            <div class="flex items-center gap-3">
              <div class="flex-1 flex flex-col gap-1">
                <div class="h-9 rounded-lg flex items-center px-3 transition-all duration-500" style="width:{widthPct}%; background:{step.color}22; border: 1px solid {step.color}44;">
                  <span class="text-sm font-heading font-bold" style="color:{step.color}">{step.value}</span>
                </div>
              </div>
              <span class="text-xs text-surface-500 w-20 flex-shrink-0">{step.label}</span>
            </div>
            {#if i < funnelSteps.length - 1}
              <div class="flex items-center gap-3">
                <div class="flex-1 flex justify-start pl-4">
                  <div class="w-px h-3 bg-surface-700"></div>
                </div>
                <span class="w-20"></span>
              </div>
            {/if}
          {/each}
        </div>
      </div>

      <!-- Session Leaderboard -->
      <div class="card lg:col-span-2">
        <h2 class="text-sm font-heading font-semibold uppercase tracking-widest text-surface-500 mb-1">Session Leaderboard</h2>
        <p class="text-xs text-surface-400 mb-5">Ranked by combined responses and participation</p>
        {#if sessionEngagement.length === 0}
          <div class="flex flex-col items-center justify-center py-12 text-surface-400">
            <BarChart3 class="w-10 h-10 mb-3 text-surface-500" />
            <p class="text-sm">No sessions yet</p>
          </div>
        {:else}
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b border-surface-200 dark:border-surface-800 text-left">
                  <th class="pb-3 font-medium text-surface-500 text-xs uppercase tracking-widest w-8">#</th>
                  <th class="pb-3 font-medium text-surface-500 text-xs uppercase tracking-widest">Session</th>
                  <th class="pb-3 font-medium text-surface-500 text-xs uppercase tracking-widest text-right">Responses</th>
                  <th class="pb-3 font-medium text-surface-500 text-xs uppercase tracking-widest text-right">People</th>
                  <th class="pb-3 font-medium text-surface-500 text-xs uppercase tracking-widest text-right">Rating</th>
                  <th class="pb-3 font-medium text-surface-500 text-xs uppercase tracking-widest text-right">Score</th>
                </tr>
              </thead>
              <tbody>
                {#each sessionEngagement as session, i}
                  {@const score = engagementScore(session)}
                  <tr class="border-b border-surface-200/60 dark:border-surface-800/60 last:border-0">
                    <td class="py-3 text-surface-400 font-mono text-xs">{i + 1}</td>
                    <td class="py-3 font-medium max-w-[180px] truncate" title={session.title}>
                      <div class="flex items-center gap-2">
                        {#if i === 0}
                          <Zap class="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />
                        {/if}
                        {session.title}
                      </div>
                    </td>
                    <td class="py-3 text-right tabular-nums">{session.total_responses}</td>
                    <td class="py-3 text-right text-surface-400 tabular-nums">{session.unique_participants}</td>
                    <td class="py-3 text-right">
                      {#if session.avg_rating !== null}
                        <span class="text-amber-400 text-xs">{ratingStars(session.avg_rating)}</span>
                      {:else}
                        <span class="text-surface-500">—</span>
                      {/if}
                    </td>
                    <td class="py-3 text-right">
                      <span class="inline-block px-2 py-0.5 rounded-full text-xs font-semibold {i === 0 ? 'bg-brand-500/15 text-brand-400' : i === 1 ? 'bg-accent-500/15 text-accent-400' : 'bg-surface-100 dark:bg-surface-800 text-surface-500'}">{score}</span>
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
      </div>
    </div>
  {/if}
</main>
