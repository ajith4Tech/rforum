<script lang="ts">
  import { goto } from '$app/navigation';
  import { getAnalytics, isAuthenticated } from '$lib/api';
  import { CalendarDays, Users, Radio, BarChart3, Star, TrendingUp, TrendingDown, ThumbsUp, ThumbsDown, Minus } from 'lucide-svelte';
  import { onMount } from 'svelte';

  let loading = $state(true);
  let error = $state('');
  let totalEvents = $state(0);
  let totalParticipants = $state(0);
  let activeSessions = $state(0);
  let slideTypeDistribution: Record<string, number> = $state({});
  let engagementOverTime: { date: string; responses: number }[] = $state([]);
  let avgRating: number | null = $state(null);
  let ratingDistribution: Record<string, number> = $state({});
  let feedbackSentiment: { positive: number; neutral: number; negative: number; total: number } = $state({ positive: 0, neutral: 0, negative: 0, total: 0 });
  let sessionEngagement: { session_id: string; title: string; total_responses: number; unique_participants: number; avg_rating: number | null }[] = $state([]);

  onMount(async () => {
    if (!isAuthenticated()) {
      goto('/login');
      return;
    }
    try {
      const data: any = await getAnalytics();
      totalEvents = data.total_events ?? 0;
      totalParticipants = data.total_participants ?? 0;
      activeSessions = data.active_sessions ?? 0;
      slideTypeDistribution = data.slide_type_distribution ?? {};
      engagementOverTime = data.engagement_over_time ?? [];
      avgRating = data.avg_rating ?? null;
      ratingDistribution = data.rating_distribution ?? {};
      feedbackSentiment = data.feedback_sentiment ?? { positive: 0, neutral: 0, negative: 0, total: 0 };
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

  // Donut chart helpers
  const donutColors: Record<string, string> = {
    POLL: '#7C3AED',
    QNA: '#06B6D4',
    FEEDBACK: '#F59E0B',
    CONTENT: '#10B981',
    WORD_CLOUD: '#EC4899'
  };

  const donutLabels: Record<string, string> = {
    POLL: 'Polls',
    QNA: 'Q&A',
    FEEDBACK: 'Feedback',
    CONTENT: 'Content',
    WORD_CLOUD: 'Word Cloud'
  };

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
      return {
        key,
        label: donutLabels[key] || key,
        color: donutColors[key] || '#94A3B8',
        value,
        pct: Math.round(pct * 100),
        startAngle,
        endAngle
      };
    });
  }

  function polarToCartesian(cx: number, cy: number, r: number, angleDeg: number) {
    const rad = ((angleDeg - 90) * Math.PI) / 180;
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
  }

  function describeArc(cx: number, cy: number, r: number, startAngle: number, endAngle: number) {
    const sweep = endAngle - startAngle;
    if (sweep >= 359.99) {
      // Full circle — draw two half-arcs
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
    if (engagementOverTime.length === 0) return { points: '', fillPath: '', labels: [], maxY: 0 };

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

    // Fill area path
    const firstX = coords[0]?.x ?? padding;
    const lastX = coords[coords.length - 1]?.x ?? padding;
    const bottom = padding + chartH;
    const fillPath = `M ${firstX},${bottom} L ${coords.map((c) => `${c.x},${c.y}`).join(' L ')} L ${lastX},${bottom} Z`;

    return { points, fillPath, coords, maxY, padding, width, height, chartH };
  }

  const statCards = $derived([
    { label: 'Total Events', value: totalEvents, icon: CalendarDays, color: 'purple' },
    { label: 'Total Participants', value: totalParticipants, icon: Users, color: 'cyan' },
    { label: 'Active Sessions', value: activeSessions, icon: Radio, color: 'emerald' },
    { label: 'Avg Rating', value: avgRating !== null ? avgRating.toFixed(1) : '—', icon: Star, color: 'amber' }
  ]);

  const maxRatingCount = $derived(Math.max(...Object.values(ratingDistribution), 1));

  const sentimentPct = $derived({
    positive: feedbackSentiment.total > 0 ? Math.round((feedbackSentiment.positive / feedbackSentiment.total) * 100) : 0,
    neutral: feedbackSentiment.total > 0 ? Math.round((feedbackSentiment.neutral / feedbackSentiment.total) * 100) : 0,
    negative: feedbackSentiment.total > 0 ? Math.round((feedbackSentiment.negative / feedbackSentiment.total) * 100) : 0,
  });

  const topSession = $derived(sessionEngagement.length > 0 ? sessionEngagement[0] : null);
  const bottomSession = $derived(
    sessionEngagement.length > 1
      ? sessionEngagement.filter((s) => s.total_responses > 0).at(-1) ??
        sessionEngagement[sessionEngagement.length - 1]
      : sessionEngagement.length === 1 ? sessionEngagement[0] : null
  );

  function ratingStars(rating: number | null): string {
    if (rating === null) return '—';
    return '★'.repeat(Math.round(rating)) + '☆'.repeat(5 - Math.round(rating));
  }
</script>

<svelte:head>
  <title>Analytics – Rforum</title>
</svelte:head>

<main class="flex-1 max-w-5xl mx-auto w-full px-8 py-8">
  <div class="mb-8">
    <h1 class="text-2xl font-bold text-slate-900 dark:text-white">Analytics</h1>
    <p class="text-sm text-slate-500 dark:text-slate-400 mt-1">Overview of your platform engagement</p>
  </div>

  {#if loading}
    <div class="text-center text-slate-400 py-20">Loading analytics...</div>
  {:else if error}
    <div class="text-center py-20">
      <p class="text-red-500 mb-2">{error}</p>
      <button onclick={() => window.location.reload()} class="text-sm text-purple-500 hover:underline">Retry</button>
    </div>
  {:else}
    <!-- Stat Cards -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-10">
      {#each statCards as card}
        {@const Icon = card.icon}
        <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm p-6">
          <div class="flex items-center justify-between mb-4">
            <div class="w-10 h-10 flex items-center justify-center rounded-xl bg-{card.color}-500/10">
              <Icon class="w-5 h-5 text-{card.color}-500" />
            </div>
          </div>
          <div class="text-3xl font-bold text-slate-900 dark:text-white">{card.value}</div>
          <div class="text-sm text-slate-500 dark:text-slate-400 mt-1">{card.label}</div>
        </div>
      {/each}
    </div>

    <!-- Charts Grid -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-10">
      <!-- Donut Chart: Slide Type Distribution -->
      <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm p-6">
        <h2 class="text-lg font-semibold text-slate-900 dark:text-white mb-6">Slide Type Distribution</h2>
        {#if Object.keys(slideTypeDistribution).length === 0}
          <div class="flex flex-col items-center justify-center py-12 text-slate-400">
            <BarChart3 class="w-10 h-10 mb-3 text-slate-300 dark:text-slate-700" />
            <p class="text-sm">No slides created yet</p>
          </div>
        {:else}
          <div class="flex items-center gap-8">
            <!-- SVG Donut -->
            <svg viewBox="0 0 200 200" class="w-44 h-44 flex-shrink-0">
              {#each getDonutSegments() as seg}
                <path
                  d={describeArc(100, 100, 70, seg.startAngle, seg.endAngle)}
                  fill="none"
                  stroke={seg.color}
                  stroke-width="28"
                  stroke-linecap="round"
                />
              {/each}
              <text x="100" y="95" text-anchor="middle" class="fill-slate-900 dark:fill-white text-2xl font-bold" style="font-size:24px; font-weight:700;">
                {Object.values(slideTypeDistribution).reduce((a, b) => a + b, 0)}
              </text>
              <text x="100" y="115" text-anchor="middle" class="fill-slate-400" style="font-size:11px;">
                total slides
              </text>
            </svg>

            <!-- Legend -->
            <div class="space-y-3 flex-1">
              {#each getDonutSegments() as seg}
                <div class="flex items-center justify-between">
                  <div class="flex items-center gap-2">
                    <span class="w-3 h-3 rounded-full flex-shrink-0" style="background: {seg.color}"></span>
                    <span class="text-sm text-slate-700 dark:text-slate-300">{seg.label}</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-sm font-semibold text-slate-900 dark:text-white">{seg.value}</span>
                    <span class="text-xs text-slate-400">({seg.pct}%)</span>
                  </div>
                </div>
              {/each}
            </div>
          </div>
        {/if}
      </div>

      <!-- Line Chart: Engagement Over Time -->
      <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm p-6">
        <h2 class="text-lg font-semibold text-slate-900 dark:text-white mb-6">Participant Engagement</h2>
        {#if engagementOverTime.length === 0}
          <div class="flex flex-col items-center justify-center py-12 text-slate-400">
            <BarChart3 class="w-10 h-10 mb-3 text-slate-300 dark:text-slate-700" />
            <p class="text-sm">No engagement data yet</p>
          </div>
        {:else}
          {@const chart = getLineChartPoints()}
          <svg viewBox="0 0 {chart.width} {chart.height}" class="w-full" preserveAspectRatio="xMidYMid meet">
            <!-- Grid lines -->
            {#each [0, 0.25, 0.5, 0.75, 1] as tick}
              {@const y = chart.padding + chart.chartH - tick * chart.chartH}
              <line x1={chart.padding} y1={y} x2={chart.width - chart.padding} y2={y} stroke="currentColor" class="text-slate-200 dark:text-slate-800" stroke-width="0.5" />
              <text x={chart.padding - 8} y={y + 4} text-anchor="end" class="fill-slate-400" style="font-size:9px;">
                {Math.round(tick * chart.maxY)}
              </text>
            {/each}

            <!-- Fill area -->
            <path d={chart.fillPath} fill="url(#engagementGradient)" opacity="0.3" />

            <!-- Line -->
            <polyline
              points={chart.points}
              fill="none"
              stroke="#7C3AED"
              stroke-width="2.5"
              stroke-linecap="round"
              stroke-linejoin="round"
            />

            <!-- Data points -->
            {#each chart.coords as pt}
              <circle cx={pt.x} cy={pt.y} r="4" fill="#7C3AED" stroke="white" stroke-width="2" class="dark:stroke-slate-900" />
            {/each}

            <!-- X-axis labels (show max 7) -->
            {#each chart.coords as pt, i}
              {#if chart.coords.length <= 7 || i % Math.ceil(chart.coords.length / 7) === 0}
                <text x={pt.x} y={chart.height - 8} text-anchor="middle" class="fill-slate-400" style="font-size:8px;">
                  {pt.label.slice(5)}
                </text>
              {/if}
            {/each}

            <defs>
              <linearGradient id="engagementGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#7C3AED" stop-opacity="0.4" />
                <stop offset="100%" stop-color="#7C3AED" stop-opacity="0" />
              </linearGradient>
            </defs>
          </svg>
          <p class="text-xs text-slate-400 mt-3 text-center">Responses per day (last 30 days)</p>
        {/if}
      </div>
    </div>

    <!-- Rating & Sentiment Row -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-10">
      <!-- Rating Distribution (horizontal bar chart) -->
      <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm p-6">
        <h2 class="text-lg font-semibold text-slate-900 dark:text-white mb-6">Rating Distribution</h2>
        {#if Object.values(ratingDistribution).every((v) => v === 0)}
          <div class="flex flex-col items-center justify-center py-12 text-slate-400">
            <Star class="w-10 h-10 mb-3 text-slate-300 dark:text-slate-700" />
            <p class="text-sm">No ratings yet</p>
          </div>
        {:else}
          <div class="space-y-3">
            {#each [5, 4, 3, 2, 1] as star}
              {@const count = ratingDistribution[String(star)] ?? 0}
              {@const pct = maxRatingCount > 0 ? (count / maxRatingCount) * 100 : 0}
              <div class="flex items-center gap-3">
                <span class="text-sm font-medium text-slate-600 dark:text-slate-300 w-6 text-right">{star}</span>
                <Star class="w-4 h-4 text-amber-400 flex-shrink-0" />
                <div class="flex-1 h-5 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                  <div
                    class="h-full rounded-full transition-all {star >= 4 ? 'bg-emerald-500' : star === 3 ? 'bg-amber-400' : 'bg-red-400'}"
                    style="width: {pct}%"
                  ></div>
                </div>
                <span class="text-sm text-slate-500 w-8 text-right">{count}</span>
              </div>
            {/each}
          </div>
          {#if avgRating !== null}
            <div class="mt-6 pt-4 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
              <span class="text-sm text-slate-500">Average</span>
              <div class="flex items-center gap-2">
                <span class="text-amber-400 text-sm tracking-wider">{ratingStars(avgRating)}</span>
                <span class="text-lg font-bold text-slate-900 dark:text-white">{avgRating.toFixed(1)}</span>
              </div>
            </div>
          {/if}
        {/if}
      </div>

      <!-- Feedback Sentiment -->
      <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm p-6">
        <h2 class="text-lg font-semibold text-slate-900 dark:text-white mb-6">Feedback Sentiment</h2>
        {#if feedbackSentiment.total === 0}
          <div class="flex flex-col items-center justify-center py-12 text-slate-400">
            <ThumbsUp class="w-10 h-10 mb-3 text-slate-300 dark:text-slate-700" />
            <p class="text-sm">No feedback responses yet</p>
          </div>
        {:else}
          <!-- Stacked bar -->
          <div class="h-6 rounded-full overflow-hidden flex mb-6">
            {#if sentimentPct.positive > 0}
              <div class="bg-emerald-500 h-full transition-all" style="width: {sentimentPct.positive}%"></div>
            {/if}
            {#if sentimentPct.neutral > 0}
              <div class="bg-amber-400 h-full transition-all" style="width: {sentimentPct.neutral}%"></div>
            {/if}
            {#if sentimentPct.negative > 0}
              <div class="bg-red-400 h-full transition-all" style="width: {sentimentPct.negative}%"></div>
            {/if}
          </div>

          <div class="grid grid-cols-3 gap-4">
            <div class="text-center">
              <div class="w-10 h-10 mx-auto flex items-center justify-center rounded-xl bg-emerald-500/10 mb-2">
                <ThumbsUp class="w-5 h-5 text-emerald-500" />
              </div>
              <div class="text-2xl font-bold text-slate-900 dark:text-white">{feedbackSentiment.positive}</div>
              <div class="text-xs text-slate-500 mt-0.5">Positive ({sentimentPct.positive}%)</div>
              <div class="text-[10px] text-slate-400">Rating 4-5</div>
            </div>
            <div class="text-center">
              <div class="w-10 h-10 mx-auto flex items-center justify-center rounded-xl bg-amber-400/10 mb-2">
                <Minus class="w-5 h-5 text-amber-400" />
              </div>
              <div class="text-2xl font-bold text-slate-900 dark:text-white">{feedbackSentiment.neutral}</div>
              <div class="text-xs text-slate-500 mt-0.5">Neutral ({sentimentPct.neutral}%)</div>
              <div class="text-[10px] text-slate-400">Rating 3</div>
            </div>
            <div class="text-center">
              <div class="w-10 h-10 mx-auto flex items-center justify-center rounded-xl bg-red-400/10 mb-2">
                <ThumbsDown class="w-5 h-5 text-red-400" />
              </div>
              <div class="text-2xl font-bold text-slate-900 dark:text-white">{feedbackSentiment.negative}</div>
              <div class="text-xs text-slate-500 mt-0.5">Negative ({sentimentPct.negative}%)</div>
              <div class="text-[10px] text-slate-400">Rating 1-2</div>
            </div>
          </div>

          <div class="mt-6 pt-4 border-t border-slate-100 dark:border-slate-800 text-center">
            <span class="text-xs text-slate-400">{feedbackSentiment.total} total rated feedback response{feedbackSentiment.total === 1 ? '' : 's'}</span>
          </div>
        {/if}
      </div>
    </div>

    <!-- Engagement Highlights + Session Table -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-10">
      <!-- Highest / Lowest Cards -->
      <div class="space-y-4 lg:col-span-1">
        <!-- Highest Engagement -->
        <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm p-6">
          <div class="flex items-center gap-2 mb-4">
            <div class="w-8 h-8 flex items-center justify-center rounded-lg bg-emerald-500/10">
              <TrendingUp class="w-4 h-4 text-emerald-500" />
            </div>
            <h3 class="text-sm font-semibold text-slate-900 dark:text-white">Highest Engagement</h3>
          </div>
          {#if topSession && topSession.total_responses > 0}
            <div class="text-lg font-bold text-slate-900 dark:text-white truncate" title={topSession.title}>{topSession.title}</div>
            <div class="mt-2 flex items-center gap-4 text-sm text-slate-500">
              <span>{topSession.total_responses} response{topSession.total_responses === 1 ? '' : 's'}</span>
              <span>{topSession.unique_participants} participant{topSession.unique_participants === 1 ? '' : 's'}</span>
            </div>
            {#if topSession.avg_rating !== null}
              <div class="mt-1 text-sm">
                <span class="text-amber-400 tracking-wider">{ratingStars(topSession.avg_rating)}</span>
                <span class="text-slate-500 ml-1">{topSession.avg_rating.toFixed(1)}</span>
              </div>
            {/if}
          {:else}
            <p class="text-sm text-slate-400">No engagement data yet</p>
          {/if}
        </div>

        <!-- Lowest Engagement -->
        <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm p-6">
          <div class="flex items-center gap-2 mb-4">
            <div class="w-8 h-8 flex items-center justify-center rounded-lg bg-red-400/10">
              <TrendingDown class="w-4 h-4 text-red-400" />
            </div>
            <h3 class="text-sm font-semibold text-slate-900 dark:text-white">Lowest Engagement</h3>
          </div>
          {#if bottomSession}
            <div class="text-lg font-bold text-slate-900 dark:text-white truncate" title={bottomSession.title}>{bottomSession.title}</div>
            <div class="mt-2 flex items-center gap-4 text-sm text-slate-500">
              <span>{bottomSession.total_responses} response{bottomSession.total_responses === 1 ? '' : 's'}</span>
              <span>{bottomSession.unique_participants} participant{bottomSession.unique_participants === 1 ? '' : 's'}</span>
            </div>
            {#if bottomSession.avg_rating !== null}
              <div class="mt-1 text-sm">
                <span class="text-amber-400 tracking-wider">{ratingStars(bottomSession.avg_rating)}</span>
                <span class="text-slate-500 ml-1">{bottomSession.avg_rating.toFixed(1)}</span>
              </div>
            {/if}
          {:else}
            <p class="text-sm text-slate-400">No engagement data yet</p>
          {/if}
        </div>
      </div>

      <!-- Session Engagement Table -->
      <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm p-6 lg:col-span-2">
        <h2 class="text-lg font-semibold text-slate-900 dark:text-white mb-4">Session Engagement</h2>
        {#if sessionEngagement.length === 0}
          <div class="flex flex-col items-center justify-center py-12 text-slate-400">
            <BarChart3 class="w-10 h-10 mb-3 text-slate-300 dark:text-slate-700" />
            <p class="text-sm">No sessions yet</p>
          </div>
        {:else}
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b border-slate-100 dark:border-slate-800 text-left">
                  <th class="pb-3 font-medium text-slate-500">#</th>
                  <th class="pb-3 font-medium text-slate-500">Session</th>
                  <th class="pb-3 font-medium text-slate-500 text-right">Responses</th>
                  <th class="pb-3 font-medium text-slate-500 text-right">Participants</th>
                  <th class="pb-3 font-medium text-slate-500 text-right">Avg Rating</th>
                </tr>
              </thead>
              <tbody>
                {#each sessionEngagement as session, i}
                  <tr class="border-b border-slate-50 dark:border-slate-800/50 last:border-0">
                    <td class="py-3 text-slate-400">{i + 1}</td>
                    <td class="py-3 font-medium text-slate-900 dark:text-white max-w-[200px] truncate" title={session.title}>{session.title}</td>
                    <td class="py-3 text-right">
                      <span class="inline-flex items-center gap-1">
                        {session.total_responses}
                        {#if i === 0 && session.total_responses > 0}
                          <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
                        {/if}
                      </span>
                    </td>
                    <td class="py-3 text-right text-slate-600 dark:text-slate-400">{session.unique_participants}</td>
                    <td class="py-3 text-right">
                      {#if session.avg_rating !== null}
                        <span class="text-amber-400">{ratingStars(session.avg_rating)}</span>
                        <span class="text-slate-500 ml-1">{session.avg_rating.toFixed(1)}</span>
                      {:else}
                        <span class="text-slate-400">—</span>
                      {/if}
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
