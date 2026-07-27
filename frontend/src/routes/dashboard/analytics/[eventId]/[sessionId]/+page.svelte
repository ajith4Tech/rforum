<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { isAuthenticated, exportEventAnalytics, exportSessionAnalytics } from '$lib/api';
  import {
    ChevronRight, Users, MessageSquare,
    Download, BarChart2, AlertCircle, FileText,
    BarChart3, Cloud, HelpCircle, AlignLeft, Star, ThumbsUp, Activity, Layers
  } from 'lucide-svelte';
  import { onMount } from 'svelte';
  import { fade } from 'svelte/transition';
  import { rgbToHex, generateHighResPieChart, generateHighResWordCloud } from '$lib/pdf/charts';
  import { loadMascot } from '$lib/pdf/mascot';
  import { BRAND, CHART_PALETTE, FOOTER_TEXT } from '$lib/pdf/constants';
  import CountUp from '$lib/components/CountUp.svelte';

  const eventId   = $derived($page.params.eventId);
  const sessionId = $derived($page.params.sessionId);

  // ── Types ─────────────────────────────────────────────
  interface RawResponse {
    response_id: string;
    slide_id: string;
    value: string;
    guest_identifier: string;
    name: string | null;
    rating: number | null;
    created_at: string;
  }

  interface SlideDetail {
    slide_id: string;
    type: string;
    order: number;
    question: string;
    options: string[];
    responses: RawResponse[];
  }

  // ── State ─────────────────────────────────────────────
  let loading           = $state(true);
  let error             = $state('');
  let sessionTitle      = $state('');
  let eventTitle        = $state('');
  let moderatorName     = $state('');
  let totalResponses    = $state(0);
  let totalParticipants = $state(0);
  let slides: SlideDetail[] = $state([]);
  let downloading       = $state(false);
  let downloadingJSON   = $state(false);
  let generatingPDF     = $state(false);

  // ── Load ──────────────────────────────────────────────
  onMount(async () => {
    if (!isAuthenticated()) { goto('/login'); return; }
    await load();
  });

  async function load() {
    loading = true; error = '';
    try {
      const [sessData, evData] = await Promise.all([
        exportSessionAnalytics(sessionId, 'json').then((r: Response) => r.json()),
        exportEventAnalytics(eventId,   'json').then((r: Response) => r.json()).catch(() => null),
      ]);

      sessionTitle  = sessData.session?.title ?? 'Session';
      eventTitle    = evData?.event?.title    ?? '';

      const rawResponses: RawResponse[] = sessData.responses ?? [];
      totalResponses    = rawResponses.length;
      totalParticipants = new Set(rawResponses.map((r: RawResponse) => r.guest_identifier)).size;

      const bySlide: Record<string, RawResponse[]> = {};
      for (const r of rawResponses) {
        if (!bySlide[r.slide_id]) bySlide[r.slide_id] = [];
        bySlide[r.slide_id].push(r);
      }

      slides = (sessData.slides ?? [])
        .map((sl: any) => {
          const cj = sl.content_json ?? {};
          const question = cj.question ?? cj.title ?? cj.text ?? '';
          const options: string[] = Array.isArray(cj.options) ? cj.options : [];
          return {
            slide_id:    sl.slide_id,
            type:        sl.type,
            order:       sl.order,
            question,
            options,
            responses:   bySlide[sl.slide_id] ?? [],
          } satisfies SlideDetail;
        })
        .sort((a: SlideDetail, b: SlideDetail) => a.order - b.order);

    } catch (e: any) {
      const msg = e?.message || '';
      if (msg.includes('Unauthorized') || msg.includes('Not authenticated')) { goto('/login'); return; }
      error = msg || 'Failed to load session analytics';
    } finally {
      loading = false;
    }
  }

  // ── CSV & JSON Exports ───────────────────────────────
  async function downloadCSV() {
    downloading = true;
    try {
      const res  = await exportSessionAnalytics(sessionId, 'csv');
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href = url; a.download = `session_responses_${sessionId}.csv`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch { alert('Download failed'); }
    finally { downloading = false; }
  }

  async function downloadJSON() {
    downloadingJSON = true;
    try {
      const res  = await exportSessionAnalytics(sessionId, 'json');
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href = url; a.download = `session_responses_${sessionId}.json`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch { alert('Download failed'); }
    finally { downloadingJSON = false; }
  }

  // ── Derived Statistics ──────────────────────────────
  const averageResponsesPerParticipant = $derived(
    totalParticipants > 0 ? (totalResponses / totalParticipants).toFixed(1) : '0'
  );
  const averageResponsesPerParticipantNum = $derived(
    totalParticipants > 0 ? totalResponses / totalParticipants : 0
  );

  const mostActiveSlide = $derived(
    slides.length > 0
      ? [...slides].sort((a, b) => b.responses.length - a.responses.length)[0]
      : null
  );

  const sessionEngagementRate = $derived(
    slides.length > 0 && totalParticipants > 0
      ? Math.round(
          (slides.reduce((acc, slide) => acc + new Set(slide.responses.map(r => r.guest_identifier)).size, 0) /
            (slides.length * totalParticipants)) *
            100
        )
      : 0
  );

  // ── Slide type config ─────────────────────────────────
  const typeConfig: Record<string, { label: string; color: string; bg: string; icon: any }> = {
    POLL:       { label: 'Poll',       color: 'text-brand-500 dark:text-brand-400', bg: 'bg-brand-500/10 dark:bg-brand-500/15', icon: BarChart3  },
    WORD_CLOUD: { label: 'Word Cloud', color: 'text-pink-500 dark:text-pink-400',   bg: 'bg-pink-500/10 dark:bg-pink-500/15',   icon: Cloud      },
    QNA:        { label: 'Q&A',        color: 'text-cyan-500 dark:text-cyan-400',   bg: 'bg-cyan-500/10 dark:bg-cyan-500/15',   icon: HelpCircle },
    FEEDBACK:   { label: 'Feedback',   color: 'text-amber-500 dark:text-amber-400',  bg: 'bg-amber-500/10 dark:bg-amber-500/15',  icon: Star       },
    CONTENT:    { label: 'Open Text',  color: 'text-emerald-500 dark:text-emerald-400',bg: 'bg-emerald-500/10 dark:bg-emerald-500/15',icon: AlignLeft  },
  };

  function tc(type: string) {
    return typeConfig[type] ?? { label: type, color: 'text-surface-500', bg: 'bg-surface-100', icon: BarChart2 };
  }

  function getSlideParticipationRate(slide: SlideDetail): number {
    if (totalParticipants === 0) return 0;
    const unique = new Set(slide.responses.map(r => r.guest_identifier)).size;
    return Math.round((unique / totalParticipants) * 100);
  }

  function getStatusBadgeClass(rate: number): string {
    if (rate >= 80) return 'bg-emerald-500/15 text-emerald-500 dark:text-emerald-400';
    if (rate >= 50) return 'bg-amber-500/15 text-amber-500 dark:text-amber-400';
    return 'bg-rose-500/15 text-rose-500 dark:text-rose-400';
  }

  // Poll aggregated votes
  function getPollResults(slide: SlideDetail) {
    const opts = slide.options.length > 0
      ? slide.options
      : [...new Set(slide.responses.map(r => r.value))];
    const counts: Record<string, number> = {};
    for (const r of slide.responses) counts[r.value] = (counts[r.value] ?? 0) + 1;
    const total = slide.responses.length || 1;

    const results = opts.map(opt => ({
      option: opt,
      count: counts[opt] ?? 0,
      pct: Math.round(((counts[opt] ?? 0) / total) * 100),
    }));

    const maxCount = Math.max(...results.map(r => r.count), 0);
    return results.map(r => ({ ...r, isWinner: maxCount > 0 && r.count === maxCount }));
  }

  // Word Cloud calculations
  function getWordCloudData(slide: SlideDetail) {
    const freq: Record<string, number> = {};
    for (const r of slide.responses) {
      const w = r.value.trim().toLowerCase();
      if (w) freq[w] = (freq[w] ?? 0) + 1;
    }
    const sorted = Object.entries(freq).map(([word, count]) => ({ word, count }))
      .sort((a, b) => b.count - a.count);
    return {
      topKeywords: sorted.slice(0, 5),
      cloud: sorted,
    };
  }

  // Q&A Calculations
  function getQnaData(slide: SlideDetail) {
    const qResponses = slide.responses;
    const totalQuestions = qResponses.length;
    const totalUpvotes = qResponses.reduce((acc, r) => acc + (r.rating ?? 0), 0);
    const sorted = [...qResponses].sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0));
    const mostUpvoted = sorted[0] ?? null;

    const contributorFreq: Record<string, number> = {};
    for (const r of qResponses) {
      if (r.name) {
        contributorFreq[r.name] = (contributorFreq[r.name] ?? 0) + 1;
      }
    }
    const activeContributors = Object.entries(contributorFreq)
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 3);

    return { totalQuestions, totalUpvotes, mostUpvoted, activeContributors, sorted };
  }

  // Feedback/Ratings calculation
  function getFeedbackData(slide: SlideDetail) {
    const ratings = slide.responses.filter(r => r.rating !== null).map(r => r.rating as number);
    const totalRatings = ratings.length;
    const avg = totalRatings > 0 ? ratings.reduce((a, b) => a + b, 0) / totalRatings : 0;

    const distribution = [5, 4, 3, 2, 1].map(stars => {
      const count = ratings.filter(r => Math.round(r) === stars).length;
      return {
        stars,
        pct: totalRatings > 0 ? Math.round((count / totalRatings) * 100) : 0,
        count
      };
    });

    return { avg, distribution, totalRatings };
  }

  // Slide-type distribution for the on-screen charts row
  const slideTypeBreakdown = $derived.by(() => {
    const counts: Record<string, number> = {};
    const responses: Record<string, number> = {};
    for (const s of slides) {
      counts[s.type] = (counts[s.type] ?? 0) + 1;
      responses[s.type] = (responses[s.type] ?? 0) + s.responses.length;
    }
    const palette = ['#7C3AED', '#06B6D4', '#10B981', '#F59E0B', '#EC4899', '#6366F1', '#14B8A6', '#EF4444'];
    const total = slides.length || 1;
    let cum = 0;
    return Object.keys(counts).map((type, i) => {
      const p = counts[type] / total;
      const start = cum; cum += p;
      return {
        type,
        count: counts[type],
        responses: responses[type] ?? 0,
        pct: Math.round(p * 100),
        startPct: start,
        endPct: cum,
        color: palette[i % palette.length],
      };
    });
  });
  const maxTypeResponses = $derived(Math.max(1, ...slideTypeBreakdown.map(s => s.responses)));

  function ratingStars(n: number | null) {
    if (n === null) return '—';
    return '★'.repeat(Math.round(n)) + '☆'.repeat(5 - Math.round(n));
  }

  // ── PDF Analytics Report Generator ──────────────────
  async function generatePDFReport() {
    generatingPDF = true;
    try {
      const { default: jsPDF } = await import('jspdf');
      const autoTable = (await import('jspdf-autotable')).default;
      const doc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
      const pw = doc.internal.pageSize.getWidth();
      const ph = doc.internal.pageSize.getHeight();
      let y = 20;

      // Helper function to draw a professional horizontal bar chart
      function drawHorizontalBarChart(
        pdfDoc: any,
        x: number,
        startY: number,
        width: number,
        rowHeight: number,
        chartData: { label: string; count: number; pct: number; isWinner: boolean }[]
      ) {
        let curY = startY;
        chartData.forEach(item => {
          if (curY > 265) {
            pdfDoc.addPage();
            curY = 25;
          }
          // Label
          pdfDoc.setFont('helvetica', 'normal');
          pdfDoc.setFontSize(8.5);
          pdfDoc.setTextColor(...BRAND.muted);
          const lbl = item.label.length > 50 ? item.label.slice(0, 48) + '...' : item.label;
          pdfDoc.text(`${lbl} (${item.count} votes, ${item.pct}%)`, x, curY + 4);
          
          // Outer bar (background)
          pdfDoc.setFillColor(241, 245, 249);
          pdfDoc.roundedRect(x, curY + 6, width, 4, 1, 1, 'F');
          
          // Inner bar (fill)
          if (item.pct > 0) {
            const fillWidth = (item.pct / 100) * width;
            if (item.isWinner) {
              pdfDoc.setFillColor(...BRAND.purple); // Violet
            } else {
              pdfDoc.setFillColor(148, 163, 184); // Slate grey
            }
            pdfDoc.roundedRect(x, curY + 6, fillWidth, 4, 1, 1, 'F');
          }
          curY += rowHeight;
        });
        return curY;
      }

      const mascotUri = await loadMascot();

      // Cover Page (White Theme)
      doc.setFillColor(255, 255, 255); doc.rect(0, 0, pw, ph, 'F');

      // Top violet banner
      doc.setFillColor(...BRAND.purple); doc.rect(0, 0, pw, 6, 'F');

      // Top Header Logo
      const logoX = 20;
      const logoY = 22;
      if (mascotUri) {
        doc.addImage(mascotUri, 'PNG', logoX, logoY, 15, 15);
      } else {
        doc.setFillColor(...BRAND.purple); doc.ellipse(logoX + 7.5, logoY + 7.5, 4, 4, 'F');
        doc.setDrawColor(...BRAND.purple); doc.setLineWidth(0.3);
        doc.ellipse(logoX + 7.5, logoY + 7.5, 7, 3, 'D'); doc.ellipse(logoX + 7.5, logoY + 7.5, 3, 7, 'D');
      }
      
      doc.setTextColor(...BRAND.text);
      doc.setFontSize(24); doc.setFont('helvetica', 'bold');
      doc.text('Rforum', logoX + 18, logoY + 11);

      doc.setFontSize(28); doc.setTextColor(...BRAND.purple);
      doc.text(sessionTitle, 20, 75);

      doc.setFontSize(14); doc.setFont('helvetica', 'normal');
      doc.setTextColor(...BRAND.muted);
      doc.text(`Event: ${eventTitle || 'Event Analytics'}`, 20, 85);

      doc.setFillColor(...BRAND.line); doc.rect(20, 93, pw - 40, 0.5, 'F');

      // Cover page KPI cards in a 2x2 grid
      const cardW = 80;
      const cardH = 22;
      const cardGap = 10;
      
      // Card 1: Slides
      doc.setFillColor(...BRAND.fill); doc.roundedRect(20, 105, cardW, cardH, 2, 2, 'F');
      doc.setDrawColor(...BRAND.line); doc.setLineWidth(0.3); doc.roundedRect(20, 105, cardW, cardH, 2, 2, 'D');
      doc.setFontSize(8); doc.setFont('helvetica', 'bold'); doc.setTextColor(100);
      doc.text('TOTAL SLIDES', 25, 112);
      doc.setFontSize(18); doc.setFont('helvetica', 'bold'); doc.setTextColor(...BRAND.purple);
      doc.text(`${slides.length}`, 25, 122);

      // Card 2: Engagement Rate
      doc.setFillColor(...BRAND.fill); doc.roundedRect(20 + cardW + cardGap, 105, cardW, cardH, 2, 2, 'F');
      doc.roundedRect(20 + cardW + cardGap, 105, cardW, cardH, 2, 2, 'D');
      doc.setFontSize(8); doc.setFont('helvetica', 'bold'); doc.setTextColor(100);
      doc.text('ENGAGEMENT RATE', 25 + cardW + cardGap, 112);
      doc.setFontSize(18); doc.setFont('helvetica', 'bold'); doc.setTextColor(...BRAND.purple);
      doc.text(`${sessionEngagementRate}%`, 25 + cardW + cardGap, 122);

      // Card 3: Participants
      doc.setFillColor(...BRAND.fill); doc.roundedRect(20, 105 + cardH + cardGap, cardW, cardH, 2, 2, 'F');
      doc.roundedRect(20, 105 + cardH + cardGap, cardW, cardH, 2, 2, 'D');
      doc.setFontSize(8); doc.setFont('helvetica', 'bold'); doc.setTextColor(100);
      doc.text('TOTAL PARTICIPANTS', 25, 112 + cardH + cardGap);
      doc.setFontSize(18); doc.setFont('helvetica', 'bold'); doc.setTextColor(...BRAND.purple);
      doc.text(`${totalParticipants}`, 25, 122 + cardH + cardGap);

      // Card 4: Responses
      doc.setFillColor(...BRAND.fill); doc.roundedRect(20 + cardW + cardGap, 105 + cardH + cardGap, cardW, cardH, 2, 2, 'F');
      doc.roundedRect(20 + cardW + cardGap, 105 + cardH + cardGap, cardW, cardH, 2, 2, 'D');
      doc.setFontSize(8); doc.setFont('helvetica', 'bold'); doc.setTextColor(100);
      doc.text('TOTAL RESPONSES', 25 + cardW + cardGap, 112 + cardH + cardGap);
      doc.setFontSize(18); doc.setFont('helvetica', 'bold'); doc.setTextColor(...BRAND.purple);
      doc.text(`${totalResponses}`, 25 + cardW + cardGap, 122 + cardH + cardGap);

      // Other highlights
      doc.setFontSize(9.5); doc.setFont('helvetica', 'bold'); doc.setTextColor(...BRAND.text);
      doc.text('ADDITIONAL HIGHLIGHTS', 20, 165);
      
      doc.setFontSize(8.5); doc.setFont('helvetica', 'normal'); doc.setTextColor(100);
      let highlightsY = 173;
      if (moderatorName) {
        doc.text(`Moderated by: ${moderatorName}`, 20, highlightsY);
        highlightsY += 6;
      }
      doc.text(`Average Responses per Participant: ${averageResponsesPerParticipant}`, 20, highlightsY);
      highlightsY += 6;
      if (mostActiveSlide) {
        const qCut = mostActiveSlide.question.length > 50 ? mostActiveSlide.question.slice(0, 48) + '…' : mostActiveSlide.question;
        doc.text(`Most Active Slide: "${qCut}" (${mostActiveSlide.responses.length} responses)`, 20, highlightsY);
      }

      doc.setFontSize(8); doc.setTextColor(148, 163, 184);
      doc.text('Rforum Platform • Stakeholder Insight Document', 20, ph - 15);

      // Page 2: Executive Summary & Slide Performance Table
      doc.addPage();
      y = 25;
      doc.setTextColor(...BRAND.text); doc.setFontSize(16); doc.setFont('helvetica', 'bold');
      doc.text('Executive Summary', 15, y);
      y += 8;
      doc.setFontSize(9.5); doc.setFont('helvetica', 'normal'); doc.setTextColor(100);
      doc.text('High-level qualitative analysis and insights derived from this interaction session.', 15, y);
      y += 12;

      // Key Takeaways Box
      doc.setFillColor(...BRAND.fill);
      doc.rect(15, y, pw - 30, 48, 'F');
      doc.setDrawColor(...BRAND.line); doc.setLineWidth(0.5);
      doc.rect(15, y, pw - 30, 48, 'D');
      
      doc.setFontSize(10); doc.setFont('helvetica', 'bold'); doc.setTextColor(...BRAND.purple);
      doc.text('Insights', 20, y + 8);
      
      doc.setFont('helvetica', 'normal'); doc.setFontSize(9); doc.setTextColor(51, 65, 85);
      doc.text(`• Audience interaction in this session yielded ${totalResponses} total responses across ${slides.length} slides.`, 20, y + 16);
      doc.text(`• The session achieved an average engagement rate of ${sessionEngagementRate}% among active participants.`, 20, y + 24);
      if (mostActiveSlide) {
        const qCut = mostActiveSlide.question.length > 65 ? mostActiveSlide.question.slice(0, 62) + '…' : mostActiveSlide.question;
        doc.text(`• Slide "S${mostActiveSlide.order + 1}: ${qCut}" was the most active, receiving ${mostActiveSlide.responses.length} responses.`, 20, y + 32);
      } else {
        doc.text(`• Slide interaction density was evenly distributed across the session slides.`, 20, y + 32);
      }
      doc.text(`• An average of ${averageResponsesPerParticipant} responses were submitted per participant.`, 20, y + 40);

      y += 60;

      doc.setFontSize(13); doc.setFont('helvetica', 'bold'); doc.setTextColor(...BRAND.text);
      doc.text('Slide Performance Breakdown', 15, y);
      y += 6;

      autoTable(doc, {
        startY: y,
        head: [['#', 'Slide Question / Title', 'Type', 'Responses', 'Participation %']],
        body: slides.map((s, i) => [
          String(i + 1),
          s.question || `Slide ${s.order + 1}`,
          s.type,
          String(s.responses.length),
          `${getSlideParticipationRate(s)}%`
        ]),
        headStyles: { fillColor: [...BRAND.purple] },
        styles: { fontSize: 9 },
      });

      // Page 3: Session Format & Engagement Breakdown
      doc.addPage();
      y = 25;
      doc.setTextColor(...BRAND.text); doc.setFontSize(16); doc.setFont('helvetica', 'bold');
      doc.text('Session Format & Engagement Breakdown', 15, y);
      y += 8;

      doc.setFontSize(10); doc.setFont('helvetica', 'normal'); doc.setTextColor(100);
      doc.text('Analysis of configured slide interactive formats and responses received', 15, y);
      y += 15;

      const colorsList = CHART_PALETTE;

      // Calculate slide counts by type for charts
      const slideTypeCounts: Record<string, number> = {};
      const slideTypeResponses: Record<string, number> = {};
      slides.forEach(s => {
        slideTypeCounts[s.type] = (slideTypeCounts[s.type] ?? 0) + 1;
        slideTypeResponses[s.type] = (slideTypeResponses[s.type] ?? 0) + s.responses.length;
      });

      const uniqueTypes = Object.keys(slideTypeCounts);
      const chartY = y + 20;

      // Chart 1: Slide types donut
      const slideChartData = uniqueTypes.map((type, i) => ({
        value: slideTypeCounts[type],
        color: rgbToHex(colorsList[i % colorsList.length])
      }));
      const totalSlidesSum = slides.length || 1;
      const slideDonutImg = generateHighResPieChart(150, 150, slideChartData, true, String(totalSlidesSum), 'slides');
      if (slideDonutImg) {
        doc.addImage(slideDonutImg, 'PNG', 20, chartY, 70, 70);
      }

      // Chart 2: Responses pie
      const respChartData = uniqueTypes.map((type, i) => ({
        value: slideTypeResponses[type] || 0,
        color: rgbToHex(colorsList[i % colorsList.length])
      }));
      const totalRespSum = slides.reduce((sum, s) => sum + s.responses.length, 0) || 1;
      const respPieImg = generateHighResPieChart(150, 150, respChartData, false, String(totalRespSum), 'responses');
      if (respPieImg) {
        doc.addImage(respPieImg, 'PNG', 110, chartY, 70, 70);
      }

      doc.setTextColor(...BRAND.text); doc.setFontSize(10); doc.setFont('helvetica', 'bold');
      doc.text('Slide Type Distribution', 55, chartY + 76, { align: 'center' });
      doc.text('Engagement Share by Type', 145, chartY + 76, { align: 'center' });

      // Draw Legend below the charts
      y = chartY + 88;
      doc.setFontSize(9); doc.setFont('helvetica', 'normal');

      uniqueTypes.forEach((type, i) => {
        const color = colorsList[i % colorsList.length];
        if (y > 260) {
          doc.addPage();
          y = 25;
        }
        doc.setFillColor(color[0], color[1], color[2]);
        doc.rect(20, y, 4, 4, 'F');
        doc.setTextColor(...BRAND.muted);

        const totalSlidesVal = slides.length || 1;
        const totalRespVal = slides.reduce((sum, s) => sum + s.responses.length, 0) || 1;

        const slidePct = Math.round((slideTypeCounts[type] / totalSlidesVal) * 100);
        const respPct = Math.round(((slideTypeResponses[type] || 0) / totalRespVal) * 100);

        doc.text(`${type}: ${slideTypeCounts[type]} slides (${slidePct}%) · ${slideTypeResponses[type] || 0} responses (${respPct}%)`, 28, y + 3.5);
        y += 7;
      });

      // Individual slide insights page loop (clean, visual, no timestamps/usernames/raw respondent names)
      slides.forEach((slide, idx) => {
        doc.addPage();
        y = 25;
        doc.setFontSize(14); doc.setFont('helvetica', 'bold');
        doc.setTextColor(...BRAND.purple);
        doc.text(`Slide ${idx + 1}: ${slide.type}`, 15, y);
        y += 8;

        doc.setFontSize(12); doc.setTextColor(...BRAND.text);
        doc.text(slide.question || `Slide Title Not Specified`, 15, y);
        y += 10;

        doc.setFontSize(9); doc.setTextColor(100);
        doc.text(`Total Responses: ${slide.responses.length}   |   Participation Rate: ${getSlideParticipationRate(slide)}%`, 15, y);
        y += 12;

        if (slide.type === 'POLL') {
          const pollData = getPollResults(slide);
          const formattedPollData = pollData.map(row => ({
            label: row.option,
            count: row.count,
            pct: row.pct,
            isWinner: row.isWinner
          }));
          y = drawHorizontalBarChart(doc, 20, y, pw - 40, 14, formattedPollData);
        } else if (slide.type === 'WORD_CLOUD') {
          const cloudData = getWordCloudData(slide);
          doc.setFontSize(10); doc.setFont('helvetica', 'bold'); doc.setTextColor(236, 72, 153);
          doc.text('Top Keywords Cloud:', 15, y);
          y += 6;

          // Generate high-resolution canvas word cloud and embed it!
          const wcPngImg = generateHighResWordCloud(160, 80, cloudData.cloud, '#EC4899');
          if (wcPngImg) {
            doc.addImage(wcPngImg, 'PNG', 25, y, 150, 75);
            y += 82;
          }

          if (y > 240) {
            doc.addPage();
            y = 25;
          }

          doc.setFontSize(9.5); doc.setFont('helvetica', 'bold'); doc.setTextColor(...BRAND.muted);
          doc.text('Frequency Table:', 15, y);
          y += 6;
          doc.setFont('helvetica', 'normal'); doc.setFontSize(9); doc.setTextColor(100);
          if (cloudData.topKeywords.length === 0) {
            doc.text('No keyword responses.', 20, y);
            y += 6;
          } else {
            cloudData.topKeywords.forEach(kw => {
              doc.text(`• "${kw.word}" — ${kw.count} occurrences`, 20, y);
              y += 6;
            });
          }
        } else if (slide.type === 'QNA') {
          const qna = getQnaData(slide);
          doc.setFontSize(10); doc.setFont('helvetica', 'bold'); doc.setTextColor(6, 182, 212);
          doc.text(`Q&A Metrics: ${qna.totalQuestions} questions submitted, ${qna.totalUpvotes} total upvotes`, 15, y);
          y += 8;
          doc.setFont('helvetica', 'normal'); doc.setFontSize(9); doc.setTextColor(...BRAND.muted);
          if (qna.sorted.length > 0) {
            // Print top 5 Q&A questions (aggregate, no timestamps or names)
            doc.setFont('helvetica', 'bold');
            doc.text('Top Submitted Questions:', 15, y);
            y += 6;
            doc.setFont('helvetica', 'normal');
            qna.sorted.slice(0, 5).forEach((qItem, qIdx) => {
              if (y > 260) {
                doc.addPage();
                y = 25;
              }
              doc.text(`${qIdx + 1}. "${qItem.value}" — ${qItem.rating ?? 0} upvotes`, 18, y);
              y += 7;
            });
          } else {
            doc.text('No questions submitted.', 20, y);
            y += 8;
          }
        } else if (slide.type === 'FEEDBACK') {
          const fb = getFeedbackData(slide);
          const formattedFbData = fb.distribution.map(dist => ({
            label: `${dist.stars} Star`,
            count: dist.count,
            pct: dist.pct,
            isWinner: false
          }));
          doc.setFontSize(10); doc.setFont('helvetica', 'bold'); doc.setTextColor(245, 158, 11);
          doc.text(`Average Rating: ${fb.avg.toFixed(1)} / 5 Stars`, 15, y);
          y += 6;
          y = drawHorizontalBarChart(doc, 20, y, pw - 40, 14, formattedFbData);
        } else if (slide.type === 'CONTENT') {
          const cloudData = getWordCloudData(slide);
          doc.setFontSize(10); doc.setFont('helvetica', 'bold'); doc.setTextColor(16, 185, 129);
          doc.text('Open Text Keywords Cloud:', 15, y);
          y += 6;

          // Generate high-resolution canvas word cloud and embed it!
          const wcPngImg = generateHighResWordCloud(160, 80, cloudData.cloud, '#10B981');
          if (wcPngImg) {
            doc.addImage(wcPngImg, 'PNG', 25, y, 150, 75);
            y += 82;
          }

          if (y > 240) {
            doc.addPage();
            y = 25;
          }

          doc.setFontSize(9.5); doc.setFont('helvetica', 'bold'); doc.setTextColor(...BRAND.muted);
          doc.text('Frequency Table:', 15, y);
          y += 6;
          doc.setFont('helvetica', 'normal'); doc.setFontSize(9); doc.setTextColor(100);
          if (cloudData.topKeywords.length === 0) {
            doc.text('No responses.', 20, y);
            y += 6;
          } else {
            cloudData.topKeywords.forEach(kw => {
              doc.text(`• "${kw.word}" — ${kw.count} occurrences`, 20, y);
              y += 6;
            });
          }
        }
      });

      // Add borders, headers, and footers (branding) on every page
      const totalPagesCount = doc.getNumberOfPages();
      for (let i = 1; i <= totalPagesCount; i++) {
        doc.setPage(i);
        
        // Page Accent border
        doc.setDrawColor(...BRAND.purple); doc.setLineWidth(1.5);
        doc.rect(5, 5, pw - 10, ph - 10, 'D');

        if (i > 1) {
          // Header
          if (mascotUri) {
            doc.addImage(mascotUri, 'PNG', 15, 12, 6, 6);
          }
          doc.setFont('helvetica', 'bold');
          doc.setFontSize(10);
          doc.setTextColor(...BRAND.purple);
          doc.text('Rforum', 23, 16.5);
          
          doc.setFont('helvetica', 'normal');
          doc.setFontSize(8.5);
          doc.setTextColor(100);
          const topTitle = sessionTitle.length > 50 ? sessionTitle.slice(0, 48) + '...' : sessionTitle;
          doc.text(topTitle, pw - 15, 16.5, { align: 'right' });

          doc.setDrawColor(...BRAND.line); doc.setLineWidth(0.3);
          doc.line(15, 20, pw - 15, 20);

          // Footer
          doc.setDrawColor(...BRAND.line); doc.setLineWidth(0.3);
          doc.line(15, ph - 15, pw - 15, ph - 15);

          doc.setFont('helvetica', 'normal');
          doc.setFontSize(8);
          doc.setTextColor(148, 163, 184);
          doc.text(FOOTER_TEXT, 15, ph - 10);
          doc.text(`Page ${i} of ${totalPagesCount}`, pw - 15, ph - 10, { align: 'right' });
        }
      }

      doc.save(`${sessionTitle.replace(/[^a-zA-Z0-9]/g, '_')}_Analytics_Report.pdf`);
    } catch (e) {
      console.error(e);
      alert('PDF generation failed');
    } finally {
      generatingPDF = false;
    }
  }
</script>

<svelte:head>
  <title>{sessionTitle || 'Session Analytics'} – Rforum</title>
</svelte:head>

<main class="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8">

  <!-- Breadcrumb -->
  <nav class="sticky top-16 z-30 -mx-4 sm:-mx-6 lg:-mx-8 px-4 sm:px-6 lg:px-8 py-3 mb-6 flex items-center gap-1.5 text-xs text-surface-500 flex-wrap bg-white/90 dark:bg-surface-950/90 backdrop-blur-md border-b border-surface-200 dark:border-surface-800/80" aria-label="Breadcrumb">
    <a href="/dashboard/analytics" class="hover:text-brand-400 transition-colors flex items-center gap-1">
      <BarChart2 class="w-3.5 h-3.5" />Analytics
    </a>
    <ChevronRight class="w-3 h-3 flex-shrink-0 text-surface-700" />
    {#if eventTitle}
      <a href="/dashboard/analytics/{eventId}" class="hover:text-brand-400 transition-colors truncate max-w-[150px]">
        {eventTitle}
      </a>
      <ChevronRight class="w-3 h-3 flex-shrink-0 text-surface-700" />
    {/if}
    <span class="text-surface-300 font-medium truncate max-w-[180px]">{sessionTitle || '…'}</span>
  </nav>

  {#if loading}
    <div aria-busy="true" aria-label="Loading session analytics" class="animate-pulse">
      <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-5 mb-8">
        <div class="space-y-3">
          <div class="h-8 w-64 rounded-lg bg-surface-200 dark:bg-surface-800"></div>
          <div class="h-4 w-48 rounded bg-surface-200 dark:bg-surface-800"></div>
        </div>
        <div class="flex gap-2.5">
          <div class="h-10 w-32 rounded-lg bg-surface-200 dark:bg-surface-800"></div>
          <div class="h-10 w-20 rounded-lg bg-surface-200 dark:bg-surface-800"></div>
        </div>
      </div>
      <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-4 mb-8">
        {#each Array(5) as _}
          <div class="card p-5 bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-800">
            <div class="w-11 h-11 rounded-xl bg-surface-200 dark:bg-surface-800 mb-3.5"></div>
            <div class="h-7 w-14 rounded bg-surface-200 dark:bg-surface-800 mb-2.5"></div>
            <div class="h-2.5 w-16 rounded bg-surface-200 dark:bg-surface-800"></div>
          </div>
        {/each}
      </div>
      <div class="card h-24 bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-800 mb-8"></div>
      <div class="space-y-4">
        {#each Array(3) as _}
          <div class="card h-40 bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-800"></div>
        {/each}
      </div>
    </div>

  {:else if error}
    <div class="card text-center py-16 max-w-xl mx-auto shadow-sm">
      <AlertCircle class="w-12 h-12 text-danger mx-auto mb-4" />
      <h2 class="text-lg font-heading font-bold mb-2">Error Loading Session Analytics</h2>
      <p class="text-sm text-surface-500 dark:text-surface-400 mb-6">{error}</p>
      <button onclick={load} class="btn-secondary text-sm px-6 py-2.5">Retry Loading</button>
    </div>

  {:else}

    <!-- Header -->
    <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-5 mb-8">
      <div>
        <h1 class="text-3xl font-heading font-bold tracking-tight text-surface-900 dark:text-surface-50">{sessionTitle}</h1>
        {#if eventTitle}
          <p class="text-surface-500 dark:text-surface-400 mt-2 text-sm font-medium">
            Part of <a href="/dashboard/analytics/{eventId}" class="text-brand-500 dark:text-brand-400 hover:underline font-bold">{eventTitle}</a>
          </p>
        {/if}
        {#if moderatorName}
          <p class="text-xs text-surface-500 dark:text-surface-400 mt-1 font-sans font-medium">Moderated by <span class="font-bold text-surface-700 dark:text-surface-300">{moderatorName}</span></p>
        {/if}
      </div>
      <div class="flex flex-wrap gap-2.5 flex-shrink-0">
        <button
          onclick={generatePDFReport}
          disabled={generatingPDF}
          class="btn-primary flex items-center gap-2 text-sm shadow-md"
        >
          <FileText class="w-4 h-4" />
          {generatingPDF ? 'Generating…' : 'Download Report'}
        </button>
        <button
          onclick={downloadCSV}
          disabled={downloading}
          class="btn-secondary flex items-center gap-2 text-sm shadow-sm"
        >
          <Download class="w-4 h-4" />
          {downloading ? '…' : 'CSV'}
        </button>
        <button
          onclick={downloadJSON}
          disabled={downloadingJSON}
          class="btn-secondary flex items-center gap-2 text-sm shadow-sm"
        >
          <Download class="w-4 h-4" />
          {downloadingJSON ? '…' : 'Raw JSON'}
        </button>
      </div>
    </div>

    <!-- ── Session Overview KPI Cards ────────────────────── -->
    <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-4 mb-8">
      {#each [
        { label: 'Participants',  value: totalParticipants,                 decimals: 0, suffix: '', icon: Users,        bg: 'bg-emerald-500/10 dark:bg-emerald-500/15', text: 'text-emerald-500 dark:text-emerald-400', hover: 'hover:border-emerald-500/30' },
        { label: 'Slides',        value: slides.length,                     decimals: 0, suffix: '', icon: Layers,       bg: 'bg-brand-500/10 dark:bg-brand-500/15',     text: 'text-brand-500 dark:text-brand-400',    hover: 'hover:border-brand-500/30'   },
        { label: 'Responses',     value: totalResponses,                    decimals: 0, suffix: '', icon: MessageSquare, bg: 'bg-violet-500/10 dark:bg-violet-500/15',  text: 'text-violet-500 dark:text-violet-400',  hover: 'hover:border-violet-500/30'  },
        { label: 'Engagement',    value: sessionEngagementRate,             decimals: 0, suffix: '%', icon: BarChart2,    bg: 'bg-accent-500/10 dark:bg-accent-500/15',   text: 'text-accent-500 dark:text-accent-400',  hover: 'hover:border-accent-500/30'  },
        { label: 'Avg / Person',  value: averageResponsesPerParticipantNum, decimals: 1, suffix: '', icon: Activity,     bg: 'bg-amber-500/10 dark:bg-amber-500/15',    text: 'text-amber-500 dark:text-amber-400',    hover: 'hover:border-amber-500/30'   },
      ] as card, i}
        {@const Icon = card.icon}
        <div in:fade={{ duration: 300, delay: i * 60 }} class="card p-5 bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-800 transition-all duration-300 {card.hover} hover:shadow-md cursor-default group overflow-hidden">
          <div class="w-11 h-11 flex items-center justify-center rounded-xl {card.bg} mb-3.5 transition-transform duration-300 group-hover:scale-110 shadow-sm">
            <Icon class="w-5 h-5 {card.text}" />
          </div>
          <div class="text-2xl sm:text-3xl font-heading font-extrabold tabular-nums tracking-tight leading-none text-surface-900 dark:text-surface-50">
            <CountUp value={card.value} decimals={card.decimals} suffix={card.suffix} />
          </div>
          <div class="text-[10px] text-surface-500 dark:text-surface-400 mt-2.5 uppercase tracking-wider font-bold">{card.label}</div>
        </div>
      {/each}
    </div>

    <!-- Insights -->
    <div class="card p-6 mb-8 border border-brand-500/20 bg-brand-500/5 dark:bg-brand-500/10 shadow-sm">
      <h2 class="font-heading font-bold text-sm uppercase tracking-wider text-brand-500 dark:text-brand-400 mb-4 flex items-center gap-2">
        <Activity class="w-4 h-4" /> Insights
      </h2>
      <div class="grid gap-3 sm:grid-cols-2 text-sm text-surface-600 dark:text-surface-300">
        <div class="flex items-start gap-2.5">
          <span class="w-1.5 h-1.5 rounded-full bg-brand-500 flex-shrink-0 mt-1.5"></span>
          <span>Session generated <strong class="text-surface-900 dark:text-surface-50">{totalResponses}</strong> responses across <strong class="text-surface-900 dark:text-surface-50">{slides.length}</strong> {slides.length === 1 ? 'slide' : 'slides'}.</span>
        </div>
        <div class="flex items-start gap-2.5">
          <span class="w-1.5 h-1.5 rounded-full bg-brand-500 flex-shrink-0 mt-1.5"></span>
          <span>Average engagement rate: <strong class="text-surface-900 dark:text-surface-50">{sessionEngagementRate}%</strong> across active participants.</span>
        </div>
        {#if mostActiveSlide}
          <div class="flex items-start gap-2.5">
            <span class="w-1.5 h-1.5 rounded-full bg-brand-500 flex-shrink-0 mt-1.5"></span>
            <span>Most active slide: <strong class="text-surface-900 dark:text-surface-50">"{mostActiveSlide.question.length > 38 ? mostActiveSlide.question.slice(0, 38) + '…' : mostActiveSlide.question}"</strong> — {mostActiveSlide.responses.length} responses.</span>
          </div>
        {/if}
        <div class="flex items-start gap-2.5">
          <span class="w-1.5 h-1.5 rounded-full bg-brand-500 flex-shrink-0 mt-1.5"></span>
          <span>Average: <strong class="text-surface-900 dark:text-surface-50">{averageResponsesPerParticipant}</strong> responses per participant.</span>
        </div>
      </div>
    </div>

    <!-- ── Charts ───────────────────────────────────────── -->
    {#if slides.length > 0}
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <div class="card p-6 bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-800 shadow-sm">
          <div class="mb-5">
            <h2 class="font-heading font-bold text-lg text-surface-900 dark:text-surface-100">Slide Type Distribution</h2>
            <p class="text-xs text-surface-500 dark:text-surface-400 mt-0.5">Share of configured slides by interaction format.</p>
          </div>
          <div class="flex flex-col sm:flex-row sm:items-center gap-6">
            <svg viewBox="0 0 200 200" class="w-36 h-36 flex-shrink-0 mx-auto sm:mx-0">
              {#each slideTypeBreakdown as seg}
                {@const sa = seg.startPct * 360 - 90}
                {@const ea = seg.endPct * 360 - 90}
                {@const sw = ea - sa}
                {@const toRad = (d: number) => d * Math.PI / 180}
                {@const sx = 100 + 70 * Math.cos(toRad(sa))}
                {@const sy = 100 + 70 * Math.sin(toRad(sa))}
                {@const ex = 100 + 70 * Math.cos(toRad(ea))}
                {@const ey = 100 + 70 * Math.sin(toRad(ea))}
                {@const large = sw > 180 ? 1 : 0}
                {#if sw >= 359.99}
                  <circle cx="100" cy="100" r="70" fill="none" stroke={seg.color} stroke-width="22" />
                {:else if sw > 0.5}
                  <path d="M {sx} {sy} A 70 70 0 {large} 1 {ex} {ey}" fill="none" stroke={seg.color} stroke-width="22" stroke-linecap="round" />
                {/if}
              {/each}
              <circle cx="100" cy="100" r="52" fill="white" class="dark:fill-surface-900" />
              <text x="100" y="96" text-anchor="middle" style="font-size:22px; font-weight:800; fill:#0F172A" class="dark:fill-surface-50">{slides.length}</text>
              <text x="100" y="114" text-anchor="middle" style="font-size:9px; font-weight:500; fill:#64748B">slides</text>
            </svg>
            <div class="space-y-2.5 flex-1 min-w-0">
              {#each slideTypeBreakdown as seg}
                <div class="flex items-center gap-2 text-sm">
                  <span class="w-3 h-3 rounded-full flex-shrink-0 shadow-sm" style="background:{seg.color}"></span>
                  <span class="truncate text-surface-600 dark:text-surface-300 font-medium flex-1 min-w-0">{tc(seg.type).label}</span>
                  <span class="font-bold tabular-nums text-surface-900 dark:text-surface-100 flex-shrink-0">{seg.count}</span>
                  <span class="text-xs text-surface-400 flex-shrink-0">({seg.pct}%)</span>
                </div>
              {/each}
            </div>
          </div>
        </div>

        <div class="card p-6 bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-800 shadow-sm">
          <div class="mb-5">
            <h2 class="font-heading font-bold text-lg text-surface-900 dark:text-surface-100">Engagement by Slide Type</h2>
            <p class="text-xs text-surface-500 dark:text-surface-400 mt-0.5">Response volume across each interactive format.</p>
          </div>
          <div class="space-y-4">
            {#each slideTypeBreakdown as seg}
              <div>
                <div class="flex items-center justify-between mb-2">
                  <span class="text-sm font-semibold truncate max-w-[220px] text-surface-800 dark:text-surface-200">{tc(seg.type).label}</span>
                  <span class="text-xs tabular-nums flex-shrink-0 ml-3 font-bold text-surface-700 dark:text-surface-300">
                    {seg.responses} <span class="font-normal text-surface-500 dark:text-surface-400">responses</span>
                  </span>
                </div>
                <div class="h-3.5 w-full rounded-full bg-surface-100 dark:bg-surface-800 overflow-hidden">
                  <div class="h-full rounded-full bg-gradient-to-r from-brand-600 to-brand-400 transition-all duration-700" style="width:{Math.round((seg.responses / maxTypeResponses) * 100)}%"></div>
                </div>
              </div>
            {/each}
          </div>
        </div>
      </div>
    {/if}

    <!-- ── Slides Section ──────────────────────────────── -->
    <div class="mb-6 flex items-center justify-between border-b border-surface-200 dark:border-surface-800/80 pb-4">
      <div>
        <h2 class="font-heading font-bold text-xl text-surface-900 dark:text-surface-100">Interactive Slide Analytics</h2>
        <p class="text-xs text-surface-500 dark:text-surface-400 mt-0.5">Aggregated visual summaries of participant answers for each configured slide.</p>
      </div>
      <span class="text-xs font-semibold px-3 py-1 bg-surface-100 dark:bg-surface-800 text-surface-600 dark:text-surface-400 rounded-full">{slides.length} total slides</span>
    </div>

    {#if slides.length === 0}
      <div class="card text-center py-16 bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-800 max-w-xl mx-auto shadow-sm">
        <BarChart2 class="w-12 h-12 text-surface-400 dark:text-surface-600 mx-auto mb-4 opacity-40" />
        <h3 class="font-heading font-bold text-xl mb-1">No Slides Found</h3>
        <p class="text-surface-500 dark:text-surface-400 text-sm mb-6 max-w-md mx-auto">No interactive slides were registered during this session.</p>
      </div>
    {:else}
      <div class="space-y-6 mb-8">
        {#each slides as slide, i (slide.slide_id)}
          {@const cfg  = tc(slide.type)}
          {@const Icon = cfg.icon}
          {@const rate = getSlideParticipationRate(slide)}

          <div class="card p-0 overflow-hidden bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-800 shadow-sm rounded-2xl">
            <!-- Slide Header Bar -->
            <div class="w-full flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-6 py-4 border-b border-surface-100 dark:border-surface-800/80 bg-surface-50/60 dark:bg-surface-800/20">
              <div class="flex items-center gap-3 min-w-0">
                <!-- Order badge -->
                <span class="w-7 h-7 rounded-lg bg-surface-200 dark:bg-surface-700 text-surface-600 dark:text-surface-300 text-xs font-mono font-bold flex items-center justify-center flex-shrink-0">
                  {slide.order + 1}
                </span>

                <!-- Type Badge -->
                <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold {cfg.bg} {cfg.color} flex-shrink-0 shadow-sm border border-current/10">
                  <Icon class="w-3.5 h-3.5" />{cfg.label}
                </span>

                <!-- Title / Question -->
                <span class="font-heading font-semibold text-sm sm:text-base text-surface-900 dark:text-surface-100 truncate">
                  {slide.question || 'Untitled Slide'}
                </span>
              </div>

              <!-- Stats Block -->
              <div class="flex items-center gap-3 self-end sm:self-auto flex-shrink-0">
                <span class="text-xs font-bold tabular-nums text-surface-700 dark:text-surface-300">
                  {slide.responses.length} <span class="font-medium text-surface-400">resp</span>
                </span>
                <span class="px-3 py-1 rounded-full text-xs font-bold {getStatusBadgeClass(rate)}">
                  {rate}% engaged
                </span>
              </div>
            </div>

            <!-- Expanded Analytics Area -->
            <div class="px-6 py-6 bg-white dark:bg-surface-900/10">

              <!-- ── TYPE-SPECIFIC VISUALISATIONS ──────── -->

              <!-- POLL ANALYTICS -->
              {#if slide.type === 'POLL'}
                {@const results = getPollResults(slide)}
                {#if slide.responses.length === 0}
                  <p class="text-sm text-surface-500 dark:text-surface-400 italic py-4 text-center">No responses recorded yet.</p>
                {:else}
                  {@const colors = ['#7C3AED', '#06B6D4', '#10B981', '#F59E0B', '#EC4899']}
                  {@const totalPoll = results.reduce((acc, r) => acc + r.count, 0) || 1}
                  {@const segs = (() => { let cum = 0; return results.map((r, i) => { const p = r.count / totalPoll; const s = cum; cum += p; return { ...r, start: s, end: cum, color: colors[i % colors.length] }; }); })()}
                  <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
                    <!-- Results Bars -->
                    <div class="space-y-2.5">
                      {#each results as row}
                        <div class="p-3.5 rounded-xl border transition-all duration-200
                                    {row.isWinner ? 'bg-brand-500/5 dark:bg-brand-500/10 border-brand-500/30' : 'bg-surface-50 dark:bg-surface-800/20 border-surface-200/70 dark:border-surface-800/60'}">
                          <div class="flex items-center justify-between mb-2 gap-3">
                            <span class="text-sm font-semibold text-surface-800 dark:text-surface-200 truncate flex-1 min-w-0">
                              {#if row.isWinner}<span class="text-brand-500 mr-1.5">▲</span>{/if}{row.option}
                            </span>
                            <span class="tabular-nums flex-shrink-0 text-xs font-bold text-surface-900 dark:text-surface-100">
                              {row.count} <span class="font-normal text-surface-500">votes</span>
                              <span class="text-brand-500 ml-1.5 font-extrabold">{row.pct}%</span>
                            </span>
                          </div>
                          <div class="h-3 w-full rounded-full bg-surface-200 dark:bg-surface-700/60 overflow-hidden">
                            <div class="h-full rounded-full transition-all duration-700
                                        {row.isWinner ? 'bg-gradient-to-r from-brand-600 to-brand-400' : 'bg-surface-400/60 dark:bg-surface-500/50'}"
                                 style="width:{row.pct}%"></div>
                          </div>
                        </div>
                      {/each}
                    </div>

                    <!-- Vote Distribution Donut -->
                    <div class="flex flex-col items-center justify-center p-5 border border-surface-200 dark:border-surface-800/60 rounded-2xl bg-surface-50/30 dark:bg-surface-900/30 max-w-xs mx-auto w-full">
                      <span class="text-[10px] uppercase tracking-widest text-surface-500 dark:text-surface-400 font-bold mb-4">Vote Distribution</span>
                      <svg viewBox="0 0 100 100" class="w-28 h-28">
                        {#each segs as seg}
                          {#if seg.pct > 0}
                            <circle cx="50" cy="50" r="35" fill="none" stroke={seg.color} stroke-width="13"
                                    stroke-dasharray="{seg.pct} 100" stroke-dashoffset="-{seg.start * 100}"
                                    transform="rotate(-90 50 50)" />
                          {/if}
                        {/each}
                        <text x="50" y="54" text-anchor="middle" style="font-size:9px; font-weight:700; fill:#64748B">POLL</text>
                      </svg>
                      <div class="flex flex-wrap justify-center gap-x-3 gap-y-2 mt-4 text-xs">
                        {#each results as row, idx}
                          <div class="flex items-center gap-1.5">
                            <span class="w-2.5 h-2.5 rounded-full flex-shrink-0" style="background:{colors[idx % colors.length]}"></span>
                            <span class="text-surface-500 dark:text-surface-400 font-medium">{row.option} <span class="font-bold text-surface-700 dark:text-surface-300">({row.pct}%)</span></span>
                          </div>
                        {/each}
                      </div>
                    </div>
                  </div>
                {/if}

              <!-- WORD CLOUD ANALYTICS -->
              {:else if slide.type === 'WORD_CLOUD'}
                {@const wcData = getWordCloudData(slide)}
                {#if slide.responses.length === 0}
                  <p class="text-sm text-surface-500 dark:text-surface-400 italic py-4 text-center">No responses recorded yet.</p>
                {:else}
                  <div class="mb-4 flex items-center gap-3">
                    <span class="text-xs font-semibold text-surface-500 dark:text-surface-400 uppercase tracking-wider">{slide.responses.length} responses</span>
                    <span class="text-surface-300 dark:text-surface-600">·</span>
                    <span class="text-xs font-semibold text-surface-500 dark:text-surface-400 uppercase tracking-wider">{wcData.cloud.length} unique terms</span>
                  </div>
                  <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <!-- Word Cloud Tags -->
                    <div class="p-5 rounded-2xl border border-surface-200 dark:border-surface-800 bg-surface-50/40 dark:bg-surface-900/20 flex flex-wrap gap-2 items-center justify-center min-h-[180px]">
                      {#each wcData.cloud.slice(0, 25) as wordObj}
                        <span class="inline-flex items-center gap-1 px-3 py-1.5 rounded-full font-bold transition-all duration-200 hover:scale-105 shadow-sm
                                     bg-pink-500/10 text-pink-600 dark:text-pink-300 border border-pink-500/20 hover:border-pink-500/35"
                              style="font-size: {Math.max(0.7, Math.min(1.35, 0.7 + wordObj.count * 0.1))}rem">
                          {wordObj.word}
                          <span class="text-[9px] text-pink-700 dark:text-pink-400 font-extrabold ml-1 opacity-80">{wordObj.count}</span>
                        </span>
                      {/each}
                    </div>

                    <!-- Top Keywords Table -->
                    <div class="space-y-3">
                      <span class="text-xs uppercase tracking-widest text-surface-500 dark:text-surface-400 font-bold block">Top keywords</span>
                      <div class="divide-y divide-surface-100 dark:divide-surface-800/80">
                        {#each wcData.topKeywords as kw, idx}
                          <div class="flex items-center justify-between py-2.5 text-sm">
                            <div class="flex items-center gap-3">
                              <span class="w-6 h-6 rounded-lg bg-pink-500/10 text-pink-500 text-[10px] font-extrabold flex items-center justify-center flex-shrink-0">{idx + 1}</span>
                              <span class="font-semibold text-surface-800 dark:text-surface-200">"{kw.word}"</span>
                            </div>
                            <span class="font-bold tabular-nums text-pink-500 dark:text-pink-400">{kw.count}×</span>
                          </div>
                        {/each}
                      </div>
                    </div>
                  </div>
                {/if}

              <!-- Q&A ANALYTICS -->
              {:else if slide.type === 'QNA'}
                {@const qna = getQnaData(slide)}
                {#if slide.responses.length === 0}
                  <p class="text-sm text-surface-500 dark:text-surface-400 italic py-4 text-center">No questions submitted yet.</p>
                {:else}
                  <div class="space-y-5">
                    <!-- KPI row -->
                    <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
                      <div class="p-4 rounded-xl bg-cyan-500/5 dark:bg-cyan-500/10 border border-cyan-500/20 dark:border-cyan-500/25">
                        <div class="text-[10px] uppercase tracking-widest text-surface-500 dark:text-surface-400 font-bold mb-1.5">Questions</div>
                        <div class="text-2xl font-heading font-extrabold text-cyan-600 dark:text-cyan-400">{qna.totalQuestions}</div>
                      </div>
                      <div class="p-4 rounded-xl bg-cyan-500/5 dark:bg-cyan-500/10 border border-cyan-500/20 dark:border-cyan-500/25">
                        <div class="text-[10px] uppercase tracking-widest text-surface-500 dark:text-surface-400 font-bold mb-1.5">Total Upvotes</div>
                        <div class="text-2xl font-heading font-extrabold text-cyan-600 dark:text-cyan-400">{qna.totalUpvotes}</div>
                      </div>
                      {#if qna.mostUpvoted}
                        <div class="p-4 rounded-xl bg-cyan-500/5 dark:bg-cyan-500/10 border border-cyan-500/20 dark:border-cyan-500/25 hidden sm:block">
                          <div class="text-[10px] uppercase tracking-widest text-surface-500 dark:text-surface-400 font-bold mb-1.5">Top Question</div>
                          <div class="text-sm font-semibold text-surface-800 dark:text-surface-200 line-clamp-2 leading-tight">{qna.mostUpvoted.value}</div>
                        </div>
                      {/if}
                    </div>

                    <!-- Questions list (sorted by upvotes) -->
                    <div>
                      <span class="text-xs uppercase tracking-widest text-surface-500 dark:text-surface-400 font-bold block mb-3">Most Upvoted Questions</span>
                      <div class="space-y-2">
                        {#each qna.sorted.slice(0, 8) as r, qi}
                          <div class="flex items-start gap-3 p-3.5 rounded-xl border border-surface-200 dark:border-surface-800/80 bg-surface-50/30 dark:bg-surface-900/20 hover:border-cyan-500/25 transition-colors">
                            <span class="w-6 h-6 rounded-lg bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 text-[10px] font-extrabold flex items-center justify-center flex-shrink-0 mt-0.5">{qi + 1}</span>
                            <p class="flex-1 text-sm text-surface-800 dark:text-surface-100 font-medium leading-relaxed min-w-0">{r.value}</p>
                            <div class="flex items-center gap-1 bg-cyan-500/10 dark:bg-cyan-500/15 text-cyan-600 dark:text-cyan-400 px-2.5 py-1 rounded-full text-xs font-bold flex-shrink-0">
                              <ThumbsUp class="w-3 h-3" />{r.rating ?? 0}
                            </div>
                          </div>
                        {/each}
                      </div>
                    </div>
                  </div>
                {/if}

              <!-- FEEDBACK / RATING ANALYTICS -->
              {:else if slide.type === 'FEEDBACK'}
                {@const fb = getFeedbackData(slide)}
                {#if slide.responses.length === 0}
                  <p class="text-sm text-surface-500 dark:text-surface-400 italic py-4 text-center">No ratings recorded yet.</p>
                {:else}
                  <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
                    <!-- Rating Distribution -->
                    <div class="space-y-2.5">
                      <span class="text-xs uppercase tracking-widest text-surface-500 dark:text-surface-400 font-bold block mb-3">Rating Distribution</span>
                      {#each fb.distribution as row}
                        <div class="flex items-center gap-3 text-sm">
                          <span class="w-9 text-right text-surface-600 dark:text-surface-400 font-bold text-xs tabular-nums flex-shrink-0">{row.stars}★</span>
                          <div class="h-3 flex-1 rounded-full bg-surface-100 dark:bg-surface-800 overflow-hidden">
                            <div class="h-full rounded-full bg-gradient-to-r from-amber-500 to-amber-400 transition-all duration-700" style="width:{row.pct}%"></div>
                          </div>
                          <span class="w-20 text-right text-xs text-surface-500 dark:text-surface-400 tabular-nums font-bold flex-shrink-0">
                            {row.count} <span class="font-normal opacity-70">({row.pct}%)</span>
                          </span>
                        </div>
                      {/each}
                    </div>

                    <!-- Average Score Card -->
                    <div class="flex flex-col items-center justify-center p-6 border border-surface-200 dark:border-surface-800 bg-amber-500/5 dark:bg-amber-500/10 rounded-2xl text-center max-w-xs mx-auto w-full">
                      <span class="text-[10px] uppercase tracking-widest text-surface-500 dark:text-surface-400 font-bold mb-3">Average Score</span>
                      <span class="text-5xl font-heading font-extrabold text-amber-500 tracking-tight leading-none">{fb.avg.toFixed(1)}</span>
                      <span class="text-xs text-surface-400 mt-1 font-medium">out of 5</span>
                      <div class="text-amber-400 text-2xl tracking-widest mt-3 select-none">{ratingStars(fb.avg)}</div>
                      <span class="text-xs text-surface-500 dark:text-surface-400 mt-3 font-medium">Based on {fb.totalRatings} {fb.totalRatings === 1 ? 'rating' : 'ratings'}</span>
                    </div>
                  </div>
                {/if}

              <!-- OPEN TEXT / CONTENT -->
              {:else}
                {@const wcData = getWordCloudData(slide)}
                {#if slide.responses.length === 0}
                  <p class="text-sm text-surface-500 dark:text-surface-400 italic py-4 text-center">No responses recorded yet.</p>
                {:else}
                  <div class="mb-4 flex items-center gap-3">
                    <span class="text-xs font-semibold text-surface-500 dark:text-surface-400 uppercase tracking-wider">{slide.responses.length} responses</span>
                    <span class="text-surface-300 dark:text-surface-600">·</span>
                    <span class="text-xs font-semibold text-surface-500 dark:text-surface-400 uppercase tracking-wider">{wcData.cloud.length} unique terms</span>
                  </div>
                  <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <!-- Tags -->
                    <div class="p-5 rounded-2xl border border-surface-200 dark:border-surface-800 bg-surface-50/40 dark:bg-surface-900/20 flex flex-wrap gap-2 items-center justify-center min-h-[180px]">
                      {#each wcData.cloud.slice(0, 25) as wordObj}
                        <span class="inline-flex items-center gap-1 px-3 py-1.5 rounded-full font-bold transition-all duration-200 hover:scale-105 shadow-sm
                                     bg-emerald-500/10 text-emerald-600 dark:text-emerald-300 border border-emerald-500/20 hover:border-emerald-500/35"
                              style="font-size: {Math.max(0.7, Math.min(1.35, 0.7 + wordObj.count * 0.1))}rem">
                          {wordObj.word}
                          <span class="text-[9px] text-emerald-700 dark:text-emerald-400 font-extrabold ml-1 opacity-80">{wordObj.count}</span>
                        </span>
                      {/each}
                    </div>

                    <!-- Top Keywords Table -->
                    <div class="space-y-3">
                      <span class="text-xs uppercase tracking-widest text-surface-500 dark:text-surface-400 font-bold block">Top keywords</span>
                      <div class="divide-y divide-surface-100 dark:divide-surface-800/80">
                        {#each wcData.topKeywords as kw, idx}
                          <div class="flex items-center justify-between py-2.5 text-sm">
                            <div class="flex items-center gap-3">
                              <span class="w-6 h-6 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-[10px] font-extrabold flex items-center justify-center flex-shrink-0">{idx + 1}</span>
                              <span class="font-semibold text-surface-800 dark:text-surface-200">"{kw.word}"</span>
                            </div>
                            <span class="font-bold tabular-nums text-emerald-500 dark:text-emerald-400">{kw.count}×</span>
                          </div>
                        {/each}
                      </div>
                    </div>
                  </div>
                {/if}
              {/if}

            </div>
          </div>
        {/each}
      </div>
    {/if}

  {/if}
</main>
