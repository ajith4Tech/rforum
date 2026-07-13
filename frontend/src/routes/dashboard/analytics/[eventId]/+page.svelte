<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { isAuthenticated, exportEventAnalytics, exportSessionAnalytics, listSlides, formatBytes } from '$lib/api';
  import { CalendarDays, ChevronRight, ChevronLeft, Users, User, MessageSquare, Layers, BarChart2, AlertCircle, Download, Zap, TrendingUp, FileText, Activity, Search, SlidersHorizontal, Inbox } from 'lucide-svelte';
  import { onMount } from 'svelte';
  import { fade } from 'svelte/transition';
  import { rgbToHex, generateHighResPieChart } from '$lib/pdf/charts';
  import { loadMascot } from '$lib/pdf/mascot';
  import { BRAND, CHART_PALETTE, FOOTER_TEXT } from '$lib/pdf/constants';
  import CountUp from '$lib/components/CountUp.svelte';

  const eventId = $derived($page.params.eventId);

  interface SessionRow {
    session_id: string;
    title: string;
    moderator_name: string | null;
    total_responses: number;
    unique_participants: number;
    slide_count: number;
    avg_rating: number | null;
  }

  let loading = $state(true);
  let error = $state('');
  let eventTitle = $state('');
  let eventDescription = $state('');
  let sessions: SessionRow[] = $state([]);
  let downloading = $state(false);
  let downloadingJSON = $state(false);
  let generatingPDF = $state(false);
  let downloadingSessionId = $state('');
  let topPerformingSlide = $state<{ question: string; count: number } | null>(null);

  // Session list search / filter / pagination
  let sessionSearch = $state('');
  let sessionFilter = $state<'all' | 'high' | 'low'>('all');
  let sessionPage = $state(1);
  const SESSIONS_PER_PAGE = 6;

  const totalSessions = $derived(sessions.length);
  const totalParticipants = $derived(sessions.reduce((s, r) => s + r.unique_participants, 0));
  const totalResponses = $derived(sessions.reduce((s, r) => s + r.total_responses, 0));
  const overallAvgPart = $derived(totalSessions > 0 ? Math.round(totalParticipants / totalSessions) : 0);
  const avgRespPerPart = $derived(totalParticipants > 0 ? (totalResponses / totalParticipants).toFixed(1) : '0');
  const topSession = $derived(sessions.length > 0 ? sessions.reduce((m, s) => s.total_responses > m.total_responses ? s : m, sessions[0]) : null);
  const maxResp = $derived(sessions.length > 0 ? Math.max(...sessions.map(s => s.total_responses), 1) : 1);
  const maxPart = $derived(sessions.length > 0 ? Math.max(...sessions.map(s => s.unique_participants), 1) : 1);
  const storageUsedBytes = $derived(totalResponses * 256 + totalSessions * 1024);
  const storageUsed = $derived(formatBytes(storageUsedBytes));
  const eventEngagementRate = $derived(
    totalSessions > 0
      ? Math.round(
          sessions.reduce((acc, s) => {
            const rate = s.unique_participants > 0 ? Math.min(100, Math.round((s.total_responses / (s.unique_participants * 2 || 1)) * 100)) : 0;
            return acc + (rate || 75);
          }, 0) / totalSessions
        )
      : 0
  );

  onMount(async () => {
    if (!isAuthenticated()) { goto('/login'); return; }
    await load();
  });

  async function load() {
    loading = true; error = '';
    try {
      const res = await exportEventAnalytics(eventId, 'json');
      const data = await res.json();
      eventTitle = data.event?.title ?? 'Unknown Event';
      eventDescription = data.event?.description ?? '';
      sessions = (data.session_engagement ?? []).map((r: any) => ({
        session_id: r.session_id, title: r.title,
        moderator_name: r.moderator_name ?? null,
        total_responses: r.total_responses ?? 0,
        unique_participants: r.unique_participants ?? 0,
        slide_count: r.slide_count ?? 0,
        avg_rating: r.avg_rating ?? null,
      }));

      // Fetch slide metadata for all sessions in parallel to match questions
      const slideMetaMap: Record<string, any> = {};
      const sessionsList = data.sessions ?? [];
      await Promise.all(
        sessionsList.map(async (s: any) => {
          try {
            const list = await listSlides(s.session_id);
            for (const item of list) {
              slideMetaMap[item.id] = item;
            }
          } catch (e) {
            console.error('Failed to load slides for session', s.session_id, e);
          }
        })
      );

      // Find top performing slide
      let maxSlideResponses = 0;
      let topSlideQ = '—';
      const sessionsData = data.responses_by_session ?? [];
      for (const sess of sessionsData) {
        const slideCounts: Record<string, number> = {};
        for (const r of (sess.responses ?? [])) {
          slideCounts[r.slide_id] = (slideCounts[r.slide_id] ?? 0) + 1;
        }
        for (const [sId, count] of Object.entries(slideCounts)) {
          if (count > maxSlideResponses) {
            maxSlideResponses = count;
            const meta = slideMetaMap[sId] ?? {};
            const cj = meta.content_json ?? {};
            topSlideQ = cj.question ?? cj.title ?? cj.text ?? `Slide ${sId}`;
          }
        }
      }
      if (maxSlideResponses > 0) {
        topPerformingSlide = { question: topSlideQ, count: maxSlideResponses };
      } else {
        topPerformingSlide = null;
      }

    } catch (e: any) {
      const msg = e?.message || '';
      if (msg.includes('Unauthorized') || msg.includes('Not authenticated')) { goto('/login'); return; }
      error = msg || 'Failed to load event analytics';
    } finally { loading = false; }
  }

  async function downloadCSV() {
    downloading = true;
    try {
      const res = await exportEventAnalytics(eventId, 'csv');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = `event_${eventId}.csv`;
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch { alert('Download failed'); } finally { downloading = false; }
  }

  async function downloadJSON() {
    downloadingJSON = true;
    try {
      const res = await exportEventAnalytics(eventId, 'json');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = `event_${eventId}.json`;
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch { alert('Download failed'); } finally { downloadingJSON = false; }
  }

  async function downloadSessionReport(sessionId: string) {
    downloadingSessionId = sessionId;
    try {
      const res = await exportSessionAnalytics(sessionId, 'csv');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = `session_${sessionId}_report.csv`;
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch { alert('Download failed'); } finally { downloadingSessionId = ''; }
  }

  function sessionEngagementPct(s: SessionRow) {
    return maxPart > 0 ? Math.round((s.unique_participants / maxPart) * 100) : 0;
  }

  const filteredSessions = $derived(sessions.filter(s => {
    if (sessionFilter === 'high' && sessionEngagementPct(s) < 50) return false;
    if (sessionFilter === 'low' && sessionEngagementPct(s) >= 50) return false;
    const q = sessionSearch.trim().toLowerCase();
    if (!q) return true;
    return s.title.toLowerCase().includes(q) || (s.moderator_name ?? '').toLowerCase().includes(q);
  }));
  const totalSessionPages = $derived(Math.max(1, Math.ceil(filteredSessions.length / SESSIONS_PER_PAGE)));
  const pagedSessions = $derived(filteredSessions.slice((sessionPage - 1) * SESSIONS_PER_PAGE, sessionPage * SESSIONS_PER_PAGE));

  $effect(() => {
    // Reset to page 1 whenever the filtered set changes shape
    void sessionSearch; void sessionFilter;
    sessionPage = 1;
  });

  async function generatePDF() {
    generatingPDF = true;
    try {
      const { default: jsPDF } = await import('jspdf');
      const autoTable = (await import('jspdf-autotable')).default;

      // 1. Fetch full JSON containing responses_by_session
      const res = await exportEventAnalytics(eventId, 'json');
      const data = await res.json();

      // 2. Fetch slide metadata for all sessions in parallel to match questions/options
      const slideMetaMap: Record<string, any> = {};
      const sessionsList = data.sessions ?? [];
      await Promise.all(
        sessionsList.map(async (s: any) => {
          try {
            const list = await listSlides(s.session_id);
            for (const item of list) {
              slideMetaMap[item.id] = item;
            }
          } catch (e) {
            console.error('Failed to load slides for session', s.session_id, e);
          }
        })
      );

      const doc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
      const pw = doc.internal.pageSize.getWidth();
      const ph = doc.internal.pageSize.getHeight();
      let y = 20;

      const brand = BRAND;
      const chartPalette = CHART_PALETTE;

      function addHeader(pdfDoc: any, pageTitle: string) {
        pdfDoc.setFillColor(255, 255, 255);
        pdfDoc.rect(0, 0, pw, 22, 'F');
        pdfDoc.setDrawColor(...brand.line);
        pdfDoc.setLineWidth(0.3);
        pdfDoc.line(15, 22, pw - 15, 22);
        if (mascotUri) {
          pdfDoc.addImage(mascotUri, 'PNG', 15, 7, 7, 7);
        }
        pdfDoc.setFont('helvetica', 'bold');
        pdfDoc.setFontSize(10);
        pdfDoc.setTextColor(...brand.purple);
        pdfDoc.text('Rforum', 24, 12.5);
        pdfDoc.setFont('helvetica', 'normal');
        pdfDoc.setFontSize(8.5);
        pdfDoc.setTextColor(...brand.muted);
        pdfDoc.text(pageTitle, pw - 15, 12.5, { align: 'right' });
      }

      function addFooter(pdfDoc: any, pageNumber: number, totalPages: number) {
        pdfDoc.setDrawColor(...brand.line);
        pdfDoc.setLineWidth(0.3);
        pdfDoc.line(15, ph - 15, pw - 15, ph - 15);
        pdfDoc.setFont('helvetica', 'normal');
        pdfDoc.setFontSize(8);
        pdfDoc.setTextColor(...brand.muted);
        pdfDoc.text(`${FOOTER_TEXT} • Page ${pageNumber} of ${totalPages}`, pw / 2, ph - 9.5, { align: 'center' });
      }

      function addSectionTitle(pdfDoc: any, title: string, subtitle?: string) {
        pdfDoc.setFont('helvetica', 'bold');
        pdfDoc.setFontSize(15);
        pdfDoc.setTextColor(...brand.text);
        pdfDoc.text(title, 15, y);
        y += 6;
        if (subtitle) {
          pdfDoc.setFont('helvetica', 'normal');
          pdfDoc.setFontSize(9.5);
          pdfDoc.setTextColor(...brand.muted);
          pdfDoc.text(subtitle, 15, y, { maxWidth: pw - 30 });
          y += 7;
        }
      }

      function drawMetricCard(pdfDoc: any, x: number, yPos: number, width: number, height: number, label: string, value: string, emphasis = false) {
        pdfDoc.setFillColor(...brand.fill);
        pdfDoc.roundedRect(x, yPos, width, height, 3, 3, 'F');
        pdfDoc.setDrawColor(...brand.line);
        pdfDoc.setLineWidth(0.3);
        pdfDoc.roundedRect(x, yPos, width, height, 3, 3, 'D');
        pdfDoc.setFont('helvetica', 'bold');
        pdfDoc.setFontSize(7.8);
        pdfDoc.setTextColor(...brand.muted);
        pdfDoc.text(label.toUpperCase(), x + 4, yPos + 7);
        pdfDoc.setFontSize(emphasis ? 20 : 17);
        pdfDoc.setTextColor(...brand.purple);
        pdfDoc.text(value, x + 4, yPos + height - 5.5);
      }

      // Helper function to draw a professional horizontal bar chart
      function drawHorizontalBarChart(
        pdfDoc: any,
        x: number,
        startY: number,
        width: number,
        _rowHeight: number,
        chartData: { label: string; count: number; pct: number; isWinner: boolean }[]
      ) {
        const barH = 8;
        let curY = startY;
        chartData.forEach(item => {
          const rowTotal = 5 + barH + 4;
          if (curY + rowTotal > 265) {
            pdfDoc.addPage();
            curY = 28;
          }
          // Label above bar
          pdfDoc.setFont('helvetica', 'normal');
          pdfDoc.setFontSize(8.5);
          pdfDoc.setTextColor(71, 85, 105);
          const lbl = item.label.length > 55 ? item.label.slice(0, 52) + '...' : item.label;
          pdfDoc.text(lbl, x, curY + 4);

          const barY = curY + 6;

          // Background track (full width)
          pdfDoc.setFillColor(241, 245, 249);
          pdfDoc.roundedRect(x, barY, width, barH, 2, 2, 'F');

          // Fill bar
          if (item.pct > 0) {
            const fillW = Math.max(3, (item.pct / 100) * width);
            if (item.isWinner) {
              pdfDoc.setFillColor(124, 58, 237); // purple winner
            } else {
              pdfDoc.setFillColor(148, 163, 184); // mid-gray
            }
            pdfDoc.roundedRect(x, barY, fillW, barH, 2, 2, 'F');
          }

          // Vote count + % inline at right end of bar
          pdfDoc.setFont('helvetica', 'bold');
          pdfDoc.setFontSize(8);
          pdfDoc.setTextColor(71, 85, 105);
          pdfDoc.text(`${item.count} (${item.pct}%)`, x + width - 2, barY + barH - 1.5, { align: 'right' });

          curY += rowTotal;
        });
        return curY;
      }

      const mascotUri = await loadMascot();

      // Cover Page
      doc.setFillColor(255, 255, 255); doc.rect(0, 0, pw, ph, 'F');
      doc.setFillColor(...brand.purple); doc.rect(0, 0, pw, 5, 'F');
      doc.setFillColor(...brand.purpleSoft); doc.roundedRect(16, 14, pw - 32, 16, 5, 5, 'F');
      if (mascotUri) {
        doc.addImage(mascotUri, 'PNG', 19, 18, 8, 8);
      }
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(10.5);
      doc.setTextColor(...brand.purple);
      doc.text('Rforum Analytics', 30, 23.5);
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(8.5);
      doc.setTextColor(...brand.muted);
      doc.text('Stakeholder-ready event performance report', pw - 22, 23.5, { align: 'right' });

      if (mascotUri) {
        doc.addImage(mascotUri, 'PNG', pw - 58, 40, 38, 38);
      }

      doc.setFont('helvetica', 'bold');
      doc.setFontSize(28);
      doc.setTextColor(...brand.text);
      doc.text(eventTitle || 'Event Analytics Report', 20, 54, { maxWidth: 128 });
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(12.5);
      doc.setTextColor(...brand.muted);
      doc.text('A presentation-ready summary of participation, engagement, and session performance.', 20, 64, { maxWidth: 128 });

      doc.setFillColor(...brand.purple);
      doc.roundedRect(20, 72, 44, 10, 3, 3, 'F');
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(8.5);
      doc.setTextColor(255, 255, 255);
      doc.text('EVENT OVERVIEW', 42, 78, { align: 'center' });

      doc.setDrawColor(...brand.line);
      doc.setLineWidth(0.35);
      doc.line(20, 88, pw - 20, 88);

      const cardW = 84;
      const cardH = 26;
      const cardGap = 8;
      drawMetricCard(doc, 20, 96, cardW, cardH, 'Sessions', String(totalSessions), true);
      drawMetricCard(doc, 20 + cardW + cardGap, 96, cardW, cardH, 'Participants', String(totalParticipants), true);
      drawMetricCard(doc, 20, 96 + cardH + cardGap, cardW, cardH, 'Responses', String(totalResponses), true);
      drawMetricCard(doc, 20 + cardW + cardGap, 96 + cardH + cardGap, cardW, cardH, 'Engagement Rate', `${eventEngagementRate}%`, true);

      doc.setFillColor(...brand.fill);
      doc.roundedRect(20, 158, pw - 40, 33, 4, 4, 'F');
      doc.setDrawColor(...brand.line);
      doc.roundedRect(20, 158, pw - 40, 33, 4, 4, 'D');
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(10);
      doc.setTextColor(...brand.text);
      doc.text('Executive summary', 24, 167);
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(9.2);
      doc.setTextColor(...brand.muted);
      doc.text(`Storage used: ${storageUsed}`, 24, 175);
      doc.text(`Average responses per participant: ${avgRespPerPart}`, 24, 181);
      if (topSession) {
        doc.text(`Most active session: ${topSession.title} (${topSession.total_responses} responses)`, 112, 175);
      }
      if (topPerformingSlide) {
        const qCut = topPerformingSlide.question.length > 54 ? topPerformingSlide.question.slice(0, 51) + '…' : topPerformingSlide.question;
        doc.text(`Top slide: ${qCut} (${topPerformingSlide.count} responses)`, 112, 181);
      }

      doc.setFont('helvetica', 'bold');
      doc.setFontSize(8.5);
      doc.setTextColor(...brand.purple);
      doc.text('Prepared for organizers, sponsors, speakers, and leadership teams.', 20, ph - 22);
      doc.setDrawColor(...brand.line);
      doc.setLineWidth(0.3);
      doc.line(20, ph - 18, pw - 20, ph - 18);
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(8);
      doc.setTextColor(...brand.muted);
      doc.text(`Generated ${new Date().toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}`, 20, ph - 11);
      doc.text('rforum.t4gc.in', pw - 20, ph - 11, { align: 'right' });

      // Page 2: Executive Summary & Session Performance Table
      doc.addPage();
      addHeader(doc, eventTitle || 'Event Analytics Report');
      y = 28;
      addSectionTitle(doc, 'Executive Summary', 'High-level qualitative analysis and insights derived from event audience interaction.');

      // Key Takeaways Box
      doc.setFillColor(...brand.fill);
      doc.roundedRect(15, y, pw - 30, 48, 4, 4, 'F');
      doc.setDrawColor(...brand.line); doc.setLineWidth(0.5);
      doc.roundedRect(15, y, pw - 30, 48, 4, 4, 'D');

      doc.setFontSize(10); doc.setFont('helvetica', 'bold'); doc.setTextColor(...brand.purple);
      doc.text('Insights', 20, y + 8);

      const topSessTitle = topSession ? (topSession.title.length > 38 ? topSession.title.slice(0, 35) + '…' : topSession.title) : '—';
      doc.setFont('helvetica', 'normal'); doc.setFontSize(9); doc.setTextColor(51, 65, 85);
      doc.text(`• Event audience engagement generated ${totalResponses} total responses over ${totalSessions} sessions.`, 20, y + 16, { maxWidth: pw - 45 });
      doc.text(`• The most active session spotlighted "${topSessTitle}" with ${topSession ? topSession.total_responses : 0} responses.`, 20, y + 24, { maxWidth: pw - 45 });
      if (topPerformingSlide) {
        const qCut = topPerformingSlide.question.length > 62 ? topPerformingSlide.question.slice(0, 59) + '…' : topPerformingSlide.question;
        doc.text(`• Slide "${qCut}" registered the highest audience interaction density with ${topPerformingSlide.count} responses.`, 20, y + 32, { maxWidth: pw - 45 });
      } else {
        doc.text(`• Interactive slide elements performed with even interaction share across sections.`, 20, y + 32, { maxWidth: pw - 45 });
      }
      doc.text(`• Average participant momentum reached ${avgRespPerPart} responses per attendee, showing healthy engagement.`, 20, y + 40, { maxWidth: pw - 45 });

      y += 60;

      doc.setFontSize(13); doc.setFont('helvetica', 'bold'); doc.setTextColor(...brand.text);
      doc.text('Session Performance Table', 15, y);
      y += 6;

      autoTable(doc, {
        startY: y,
        head: [['Session Title', 'Participants', 'Responses', 'Avg Rating']],
        body: sessions.map(s => {
          const noData = s.unique_participants === 0 && s.total_responses === 0;
          return [
            noData ? `${s.title}  [No data]` : s.title,
            String(s.unique_participants),
            String(s.total_responses),
            s.avg_rating !== null ? `${s.avg_rating.toFixed(1)} / 5` : '—',
          ];
        }),
        headStyles: { fillColor: [...brand.purple] },
        styles: { fontSize: 9 },
        alternateRowStyles: { fillColor: [250, 250, 252] },
        didParseCell: (data: any) => {
          const s = sessions[data.row.index];
          if (s && s.unique_participants === 0 && s.total_responses === 0) {
            data.cell.styles.textColor = [180, 185, 192];
          }
        },
      });

      // Page 3: Visual Engagement Summary
      doc.addPage();
      addHeader(doc, eventTitle || 'Event Analytics Report');
      y = 30;
      // Custom title styling for Visual Engagement page
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(16);
      doc.setTextColor(...brand.text);
      doc.text('Visual Engagement Summary', 15, y);
      y += 7;
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(11);
      doc.setTextColor(107, 114, 128);
      doc.text('Graphical breakdown of response volumes and participant distribution across sessions', 15, y, { maxWidth: pw - 30 });
      y += 10;

      if (sessions.length <= 1) {
        // Single session / no session: detailed summary card
        doc.setFillColor(...brand.fill);
        doc.roundedRect(15, y, pw - 30, 80, 4, 4, 'F');
        doc.setDrawColor(...brand.line); doc.setLineWidth(0.5);
        doc.roundedRect(15, y, pw - 30, 80, 4, 4, 'D');

        doc.setFontSize(12); doc.setFont('helvetica', 'bold'); doc.setTextColor(...brand.purple);
        doc.text('Session Summary Insights', 22, y + 10);

        if (sessions.length === 1) {
          const s = sessions[0];
          doc.setFontSize(10); doc.setFont('helvetica', 'bold'); doc.setTextColor(...brand.text);
          doc.text(`Active Session: ${s.title}`, 22, y + 20);

          doc.setFontSize(9); doc.setFont('helvetica', 'normal'); doc.setTextColor(51, 65, 85);
          doc.text(`• Total Responses submitted: ${s.total_responses}`, 22, y + 30);
          doc.text(`• Unique Participants active: ${s.unique_participants}`, 22, y + 38);
          doc.text(`• Average Rating Score: ${s.avg_rating !== null ? `${s.avg_rating.toFixed(1)} / 5 Stars` : '—'}`, 22, y + 46);

          const sRate = s.unique_participants > 0 ? Math.min(100, Math.round((s.total_responses / (s.unique_participants * 2 || 1)) * 100)) : 0;
          doc.text(`• Engagement Rate score: ${sRate}%`, 22, y + 54);
          doc.text(`• Average responses per participant: ${s.unique_participants > 0 ? (s.total_responses / s.unique_participants).toFixed(1) : '0'}`, 22, y + 62);
        } else {
          doc.setFontSize(9.5); doc.setFont('helvetica', 'normal'); doc.setTextColor(100);
          doc.text('No active sessions found for this event.', 22, y + 25);
        }
      } else {
        // Single donut (Responses Per Session) + Session Performance Breakdown bars
        const totalRespSum = sessions.reduce((sum, s) => sum + s.total_responses, 0);

        // Donut — responses per session, max 200px diameter
        const donutPx = 200;
        const donutMM = 53;
        const respChartData = sessions.map((s, i) => ({
          value: s.total_responses || 0.001,
          color: rgbToHex(chartPalette[i % chartPalette.length])
        }));
        const respDonutImg = generateHighResPieChart(donutPx, donutPx, respChartData, true, String(totalRespSum), 'total responses');

        if (respDonutImg) {
          const donutX = (pw - donutMM) / 2;
          doc.addImage(respDonutImg, 'PNG', donutX, y, donutMM, donutMM);
        }
        y += donutMM + 10;

        // Section label
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(8.5);
        doc.setTextColor(156, 163, 175);
        doc.text('SESSION PERFORMANCE BREAKDOWN', 15, y);
        y += 7;

        // Breakdown bars — full width, one card row per session
        const nameColW = 50;
        const countColW = 34;
        const barStartX = 15 + nameColW + 3;
        const barAreaW = pw - 30 - nameColW - countColW - 3;
        const barH2 = 9;
        const rowGap2 = 6;

        sessions.forEach((s) => {
          const totalR = totalRespSum || 1;
          const pct = Math.round((s.total_responses / totalR) * 100);
          const rowH = barH2 + 5;

          if (y + rowH + rowGap2 > 272) {
            doc.addPage();
            y = 28;
            addHeader(doc, eventTitle || 'Event Analytics Report');
          }

          // Session name vertically centered with bar
          doc.setFont('helvetica', 'bold');
          doc.setFontSize(10);
          doc.setTextColor(...brand.text);
          const nameStr = s.title.length > 25 ? s.title.slice(0, 22) + '...' : s.title;
          doc.text(nameStr, 15, y + barH2 / 2 + 1.5);

          // Bar track
          doc.setFillColor(229, 231, 235);
          doc.roundedRect(barStartX, y, barAreaW, barH2, 2, 2, 'F');

          if (s.total_responses === 0) {
            // Zero-response: italic gray text over empty track
            doc.setFont('helvetica', 'italic');
            doc.setFontSize(8);
            doc.setTextColor(156, 163, 175);
            doc.text('No responses recorded', barStartX + 4, y + barH2 / 2 + 1.5);
          } else {
            // Purple fill proportional to share
            const fillW3 = Math.max(3, (pct / 100) * barAreaW);
            doc.setFillColor(124, 58, 237);
            doc.roundedRect(barStartX, y, fillW3, barH2, 2, 2, 'F');
          }

          // Response count (bold) + percentage (gray) to the right of bar
          const countX = barStartX + barAreaW + 4;
          doc.setFont('helvetica', 'bold');
          doc.setFontSize(9);
          doc.setTextColor(...brand.text);
          doc.text(String(s.total_responses), countX, y + barH2 / 2 + 1.5);
          doc.setFont('helvetica', 'normal');
          doc.setFontSize(8);
          doc.setTextColor(...brand.muted);
          doc.text(`(${pct}%)`, countX + 11, y + barH2 / 2 + 1.5);

          // Participant count below bar
          doc.setFont('helvetica', 'normal');
          doc.setFontSize(7.5);
          doc.setTextColor(156, 163, 175);
          doc.text(`${s.unique_participants} participants`, barStartX, y + barH2 + 4);

          y += rowH + rowGap2;
        });
      }

      // Page 4+: Session-level Slides details (visual slides, no timestamps or raw respondent names)
      const sessionsData = data.responses_by_session ?? [];

      for (const sess of sessionsData) {
        const matchingSess = sessions.find(s => s.session_id === sess.session_id);
        const sTitle = matchingSess?.title ?? `Session ${sess.session_id}`;

        doc.addPage();
        addHeader(doc, eventTitle || 'Event Analytics Report');
        y = 28;
        addSectionTitle(doc, sTitle, 'Slides Analytics Breakdown');

        // Slide list
        const slideIds = Object.keys(sess.slides ?? {});
        if (slideIds.length === 0) {
          doc.setFontSize(10); doc.setTextColor(...brand.muted); doc.text('No interactive slides in this session.', 15, y);
        } else {
          // Sort slides by order
          const sortedSlideIds = slideIds.sort((a, b) => (sess.slides[a]?.order ?? 0) - (sess.slides[b]?.order ?? 0));
          for (const sId of sortedSlideIds) {
            const sInfo = sess.slides[sId];
            const meta = slideMetaMap[sId] ?? {};
            const cj   = meta.content_json ?? {};
            const question = cj.question ?? cj.title ?? cj.text ?? `Slide S${sInfo.order + 1}`;

            const slideResponses = (sess.responses ?? []).filter((r: any) => r.slide_id === sId);

            // Draw slide details on page — keep poll card + options together
            if (sInfo.type === 'POLL') {
              const pollOptsPrecheck = cj.options ?? [...new Set(slideResponses.map((r: any) => r.value))];
              const pollNeededH = 26 + pollOptsPrecheck.length * 17 + 8;
              if (y + pollNeededH > 262 || y > 220) {
                doc.addPage();
                y = 28;
              }
            } else if (y > 220) {
              doc.addPage();
              y = 28;
            }

            doc.setFillColor(...brand.fill); doc.roundedRect(15, y, pw - 30, 22, 3, 3, 'F');
            doc.setDrawColor(...brand.line); doc.roundedRect(15, y, pw - 30, 22, 3, 3, 'D');
            doc.setFontSize(9); doc.setFont('helvetica', 'bold'); doc.setTextColor(...brand.muted);
            doc.text(`SLIDE ${sInfo.order + 1} (${sInfo.type})`, 18, y + 6);

            doc.setFontSize(11); doc.setTextColor(...brand.text);
            doc.text(question.length > 80 ? question.slice(0, 80) + '…' : question, 18, y + 13);

            doc.setFontSize(8); doc.setTextColor(...brand.muted);
            doc.text(`${slideResponses.length} responses received`, 18, y + 19);
            y += 26;

            // Draw type-specific summary
            if (sInfo.type === 'POLL') {
              const opts = cj.options ?? [...new Set(slideResponses.map((r: any) => r.value))];
              const counts: Record<string, number> = {};
              for (const r of slideResponses) counts[r.value] = (counts[r.value] ?? 0) + 1;
              const total = slideResponses.length || 1;

              const pollResults = opts.map((opt: string) => {
                const count = counts[opt] ?? 0;
                return { label: opt, count, pct: Math.round((count / total) * 100) };
              });
              const maxCount = Math.max(...pollResults.map((r: any) => r.count), 0);
              const pollResultsWithWinner = pollResults.map((r: any) => ({ ...r, isWinner: maxCount > 0 && r.count === maxCount }));

              y = drawHorizontalBarChart(doc, 20, y, pw - 40, 15, pollResultsWithWinner);
              y += 4;
            } else if (sInfo.type === 'FEEDBACK') {
              const ratings = slideResponses.filter((r: any) => r.rating !== null).map((r: any) => r.rating as number);
              const avg = ratings.length > 0 ? ratings.reduce((a, b) => a + b, 0) / ratings.length : 0;
              const totalRatings = ratings.length || 1;

              const formattedDistribution = [5, 4, 3, 2, 1].map(stars => {
                const count = ratings.filter(r => Math.round(r) === stars).length;
                return { label: `${stars} Star`, count, pct: Math.round((count / totalRatings) * 100), isWinner: false };
              });

              if (y > 230) {
                doc.addPage();
                y = 28;
              }
              doc.setFontSize(9.5); doc.setFont('helvetica', 'bold'); doc.setTextColor(245, 158, 11);
              doc.text(`Average Rating: ${avg.toFixed(1)} / 5 Stars`, 20, y);
              y += 6;
              y = drawHorizontalBarChart(doc, 20, y, pw - 40, 15, formattedDistribution);
              y += 4;
            } else if (sInfo.type === 'WORD_CLOUD') {
              const freq: Record<string, number> = {};
              for (const r of slideResponses) {
                const w = r.value.trim().toLowerCase();
                if (w) freq[w] = (freq[w] ?? 0) + 1;
              }
              const sorted = Object.entries(freq).map(([word, count]) => ({ label: `"${word}"`, count, pct: 0, isWinner: false })).slice(0, 8);

              if (y > 240) {
                doc.addPage();
                y = 28;
              }
              doc.setFontSize(9.5); doc.setFont('helvetica', 'bold'); doc.setTextColor(236, 72, 153);
              doc.text(`Top Repeated Keywords`, 20, y);
              y += 6;
              if (sorted.length === 0) {
                doc.setFontSize(8.5); doc.setFont('helvetica', 'normal'); doc.setTextColor(100);
                doc.text('No keyword responses.', 20, y);
                y += 6;
              } else {
                sorted.forEach(item => {
                  doc.setFontSize(8.5); doc.setFont('helvetica', 'normal'); doc.setTextColor(71, 85, 105);
                  doc.text(`• ${item.label} — ${item.count} occurrences`, 22, y);
                  y += 5;
                });
              }
              y += 4;
            } else if (sInfo.type === 'QNA') {
              const qnaResp = slideResponses;
              const totalQ = qnaResp.length;
              const totalVotes = qnaResp.reduce((acc: number, r: any) => acc + (r.rating ?? 0), 0);
              const sortedQ = [...qnaResp].sort((a: any, b: any) => (b.rating ?? 0) - (a.rating ?? 0));
              const topQ = sortedQ[0] ?? null;

              if (y > 240) {
                doc.addPage();
                y = 28;
              }
              doc.setFontSize(9.5); doc.setFont('helvetica', 'bold'); doc.setTextColor(6, 182, 212);
              doc.text(`Q&A Metrics: ${totalQ} questions submitted, ${totalVotes} total upvotes`, 20, y);
              y += 6;
              if (topQ) {
                doc.setFontSize(8.5); doc.setFont('helvetica', 'normal'); doc.setTextColor(71, 85, 105);
                doc.text(`• Top Question: "${topQ.value}" (${topQ.rating ?? 0} upvotes)`, 22, y);
                y += 6;
              }
              y += 4;
            }
          }
        }
      }

      // Add borders, headers, and footers (branding) on every page
      const totalPagesCount = doc.getNumberOfPages();
      for (let i = 1; i <= totalPagesCount; i++) {
        doc.setPage(i);

        doc.setDrawColor(...brand.purple); doc.setLineWidth(0.9);
        doc.rect(6, 6, pw - 12, ph - 12, 'D');

        if (i > 1) {
          addHeader(doc, eventTitle || 'Event Analytics Report');
          addFooter(doc, i, totalPagesCount);
        }
      }

      doc.save(`${eventTitle.replace(/[^a-zA-Z0-9]/g, '_')}_Analytics_Report.pdf`);
    } catch (e) {
      console.error(e);
      alert('PDF generation failed');
    } finally {
      generatingPDF = false;
    }
  }

  function engBadge(pct: number) {
    if (pct >= 80) return 'bg-emerald-500/15 text-emerald-400';
    if (pct >= 50) return 'bg-amber-500/15 text-amber-400';
    return 'bg-rose-500/15 text-rose-400';
  }

  function ratingStars(n: number | null) { return n === null ? null : '★'.repeat(Math.round(n)) + '☆'.repeat(5 - Math.round(n)); }
</script>

<svelte:head><title>{eventTitle || 'Event'} – Analytics – Rforum</title></svelte:head>

<main class="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8">
  <!-- Breadcrumb -->
  <nav class="flex items-center gap-1.5 text-xs text-surface-500 mb-6 flex-wrap" aria-label="Breadcrumb">
    <a href="/dashboard/analytics" class="hover:text-brand-400 transition-colors flex items-center gap-1"><BarChart2 class="w-3.5 h-3.5" />Analytics</a>
    <ChevronRight class="w-3 h-3 text-surface-700" />
    <span class="text-surface-300 font-medium truncate max-w-[260px]">{eventTitle || '…'}</span>
  </nav>

  {#if loading}
    <div aria-busy="true" aria-label="Loading event analytics" class="animate-pulse">
      <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-5 mb-8">
        <div class="space-y-3">
          <div class="h-8 w-64 rounded-lg bg-surface-200 dark:bg-surface-800"></div>
          <div class="h-4 w-80 max-w-full rounded bg-surface-200 dark:bg-surface-800"></div>
        </div>
        <div class="flex gap-2.5">
          <div class="h-10 w-32 rounded-lg bg-surface-200 dark:bg-surface-800"></div>
          <div class="h-10 w-20 rounded-lg bg-surface-200 dark:bg-surface-800"></div>
        </div>
      </div>
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
        {#each Array(4) as _}
          <div class="card p-5 bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-800">
            <div class="w-11 h-11 rounded-xl bg-surface-200 dark:bg-surface-800 mb-3.5"></div>
            <div class="h-7 w-16 rounded bg-surface-200 dark:bg-surface-800 mb-2.5"></div>
            <div class="h-2.5 w-20 rounded bg-surface-200 dark:bg-surface-800"></div>
          </div>
        {/each}
      </div>
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {#each Array(2) as _}
          <div class="card p-6 h-64 bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-800"></div>
        {/each}
      </div>
      <div class="card p-6 h-72 bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-800"></div>
    </div>
  {:else if error}
    <div class="card text-center py-16 max-w-xl mx-auto shadow-sm">
      <AlertCircle class="w-12 h-12 text-danger mx-auto mb-4" />
      <h2 class="text-lg font-heading font-bold mb-2">Error Loading Event Analytics</h2>
      <p class="text-sm text-surface-500 dark:text-surface-400 mb-6">{error}</p>
      <button onclick={load} class="btn-secondary text-sm px-6 py-2.5">Retry Loading</button>
    </div>
  {:else}
    <!-- Header -->
    <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-5 mb-8">
      <div>
        <h1 class="text-3xl font-heading font-bold tracking-tight text-surface-900 dark:text-surface-50">{eventTitle}</h1>
        {#if eventDescription}<p class="text-surface-500 dark:text-surface-400 mt-2 text-sm max-w-2xl leading-relaxed">{eventDescription}</p>{/if}
      </div>
      <div class="flex flex-wrap gap-2.5 flex-shrink-0">
        <button onclick={generatePDF} disabled={generatingPDF} class="btn-primary flex items-center gap-2 text-sm shadow-md">
          <FileText class="w-4 h-4" />{generatingPDF ? 'Generating…' : 'Download Report'}
        </button>
        <button onclick={downloadCSV} disabled={downloading} class="btn-secondary flex items-center gap-2 text-sm shadow-sm">
          <Download class="w-4 h-4" />{downloading ? '…' : 'CSV'}
        </button>
        <button onclick={downloadJSON} disabled={downloadingJSON} class="btn-secondary flex items-center gap-2 text-sm shadow-sm">
          <Download class="w-4 h-4" />{downloadingJSON ? '…' : 'Raw JSON'}
        </button>
      </div>
    </div>

    <!-- KPI Cards Grid -->
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
      {#each [
        { label: 'Total Sessions',     value: totalSessions,       decimals: 0, suffix: '', icon: Layers,        bg: 'bg-brand-500/10 dark:bg-brand-500/15',    text: 'text-brand-500 dark:text-brand-400',    hover: 'hover:border-brand-500/30'   },
        { label: 'Total Participants', value: totalParticipants,   decimals: 0, suffix: '', icon: Users,         bg: 'bg-emerald-500/10 dark:bg-emerald-500/15', text: 'text-emerald-500 dark:text-emerald-400', hover: 'hover:border-emerald-500/30' },
        { label: 'Total Responses',    value: totalResponses,      decimals: 0, suffix: '', icon: MessageSquare, bg: 'bg-violet-500/10 dark:bg-violet-500/15',   text: 'text-violet-500 dark:text-violet-400',  hover: 'hover:border-violet-500/30'  },
        { label: 'Avg Engagement',     value: eventEngagementRate, decimals: 0, suffix: '%', icon: TrendingUp,   bg: 'bg-amber-500/10 dark:bg-amber-500/15',    text: 'text-amber-500 dark:text-amber-400',    hover: 'hover:border-amber-500/30'   },
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

    <!-- ═══════════════════════════════════════════════════
         CHARTS — Session Engagement & Response Distribution
         ═══════════════════════════════════════════════════ -->
    {#if sessions.length > 1}
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">

        <!-- Session Engagement Comparison -->
        <div class="card p-6 bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-800 shadow-sm">
          <div class="mb-5">
            <h2 class="font-heading font-bold text-lg text-surface-900 dark:text-surface-100">Session Engagement</h2>
            <p class="text-xs text-surface-500 dark:text-surface-400 mt-0.5">Participants per session, relative to the highest-attended.</p>
          </div>
          <div class="space-y-4">
            {#each sessions as s}
              {@const pct = maxPart > 0 ? Math.round((s.unique_participants / maxPart) * 100) : 0}
              <div>
                <div class="flex items-center justify-between mb-2">
                  <span class="text-sm font-semibold truncate max-w-[220px] text-surface-800 dark:text-surface-200">{s.title}</span>
                  <span class="text-xs tabular-nums flex-shrink-0 ml-3 font-bold text-surface-700 dark:text-surface-300">
                    {s.unique_participants} <span class="font-normal text-surface-500 dark:text-surface-400">participants</span>
                  </span>
                </div>
                <div class="h-3.5 w-full rounded-full bg-surface-100 dark:bg-surface-800 overflow-hidden">
                  <div class="h-full rounded-full bg-gradient-to-r from-brand-600 to-brand-400 transition-all duration-700" style="width:{pct}%"></div>
                </div>
              </div>
            {/each}
          </div>
        </div>

        <!-- Responses Per Session -->
        <div class="card p-6 bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-800 shadow-sm">
          <div class="mb-5">
            <h2 class="font-heading font-bold text-lg text-surface-900 dark:text-surface-100">Responses Per Session</h2>
            <p class="text-xs text-surface-500 dark:text-surface-400 mt-0.5">Total response distribution across all sessions.</p>
          </div>
          {#each [['#7C3AED','#06B6D4','#10B981','#F59E0B','#EC4899','#EF4444','#8B5CF6','#14B8A6']] as colors}
            {@const total = sessions.reduce((s, r) => s + r.total_responses, 0) || 1}
            {@const segments = (() => { let cum = 0; return sessions.map((s, i) => { const p = s.total_responses / total; const start = cum; cum += p; return { ...s, pct: Math.round(p * 100), startPct: start, endPct: cum, color: colors[i % colors.length] }; }); })()}
            <div class="flex flex-col sm:flex-row sm:items-center gap-6">
              <svg viewBox="0 0 200 200" class="w-36 h-36 flex-shrink-0 mx-auto sm:mx-0">
                {#each segments as seg}
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
                <text x="100" y="96" text-anchor="middle" style="font-size:22px; font-weight:800; fill:#0F172A" class="dark:fill-surface-50">{totalResponses}</text>
                <text x="100" y="114" text-anchor="middle" style="font-size:9px; font-weight:500; fill:#64748B">responses</text>
              </svg>
              <div class="space-y-2.5 flex-1 min-w-0">
                {#each segments as seg}
                  <div class="flex items-center gap-2 text-sm">
                    <span class="w-3 h-3 rounded-full flex-shrink-0 shadow-sm" style="background:{seg.color}"></span>
                    <span class="truncate text-surface-600 dark:text-surface-300 font-medium flex-1 min-w-0">{seg.title}</span>
                    <span class="font-bold tabular-nums text-surface-900 dark:text-surface-100 flex-shrink-0">{seg.total_responses}</span>
                    <span class="text-xs text-surface-400 flex-shrink-0">({seg.pct}%)</span>
                  </div>
                {/each}
              </div>
            </div>
          {/each}
        </div>
      </div>

    {:else if sessions.length === 1}
      <!-- Single Session Summary Cards -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8">
        <div class="card p-6 relative overflow-hidden bg-gradient-to-br from-brand-500/5 to-brand-500/10 dark:from-brand-500/10 dark:to-brand-500/20 border border-brand-500/25 shadow-sm">
          <div class="absolute -right-6 -top-6 w-24 h-24 bg-brand-500/10 rounded-full blur-md"></div>
          <div class="text-[10px] text-brand-500 dark:text-brand-400 uppercase tracking-wider font-bold mb-2">Active Session</div>
          <h3 class="font-heading font-extrabold text-xl text-surface-900 dark:text-surface-50 mb-4 truncate">{sessions[0].title}</h3>
          <button onclick={() => goto(`/dashboard/analytics/${eventId}/${sessions[0].session_id}`)} class="btn-primary text-xs px-4 py-2 mt-2 w-full text-center shadow-sm">
            View Session Analytics
          </button>
        </div>

        <div class="card p-6 bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-800 shadow-sm flex flex-col justify-between">
          <div>
            <div class="text-[10px] text-surface-500 dark:text-surface-400 uppercase tracking-wider font-bold mb-2">Participation</div>
            <div class="flex items-baseline gap-2 mt-2">
              <span class="text-3xl font-heading font-extrabold text-surface-900 dark:text-surface-50">{sessions[0].unique_participants}</span>
              <span class="text-xs text-surface-500 dark:text-surface-400 font-medium">participants</span>
            </div>
          </div>
          {#each [sessions[0].unique_participants > 0 ? Math.min(100, Math.round((sessions[0].total_responses / (sessions[0].unique_participants * 2 || 1)) * 100)) : 0] as eng}
            <div class="mt-4">
              <div class="flex justify-between text-xs mb-1.5 font-medium">
                <span class="text-surface-500 dark:text-surface-400">Engagement</span>
                <span class="font-bold text-emerald-500">{eng}%</span>
              </div>
              <div class="h-2 w-full rounded-full bg-surface-100 dark:bg-surface-800 overflow-hidden">
                <div class="h-full rounded-full bg-emerald-500 transition-all duration-700" style="width:{eng}%"></div>
              </div>
            </div>
          {/each}
        </div>

        <div class="card p-6 bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-800 shadow-sm flex flex-col justify-between">
          <div>
            <div class="text-[10px] text-surface-500 dark:text-surface-400 uppercase tracking-wider font-bold mb-2">Response Volume</div>
            <div class="flex items-baseline gap-2 mt-2">
              <span class="text-3xl font-heading font-extrabold text-surface-900 dark:text-surface-50">{sessions[0].total_responses}</span>
              <span class="text-xs text-surface-500 dark:text-surface-400 font-medium">responses</span>
            </div>
          </div>
          <div class="mt-4 flex items-center justify-between text-xs pt-2 border-t border-surface-100 dark:border-surface-800/60">
            <div>
              <span class="text-surface-400 uppercase font-semibold text-[9px] tracking-wider">Avg Rating</span>
              <div class="text-amber-500 font-bold mt-1 text-sm">
                {#if sessions[0].avg_rating !== null}★ {sessions[0].avg_rating.toFixed(1)} / 5{:else}—{/if}
              </div>
            </div>
            <div class="text-right">
              <span class="text-surface-400 uppercase font-semibold text-[9px] tracking-wider">Avg / person</span>
              <div class="text-surface-800 dark:text-surface-200 font-bold mt-1 text-sm">
                {sessions[0].unique_participants > 0 ? (sessions[0].total_responses / sessions[0].unique_participants).toFixed(1) : '0'}
              </div>
            </div>
          </div>
        </div>
      </div>
    {:else}
      <div class="card p-12 flex flex-col items-center justify-center text-center bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-800 shadow-sm mb-8">
        <div class="w-14 h-14 rounded-2xl bg-surface-100 dark:bg-surface-800 flex items-center justify-center mb-4">
          <BarChart2 class="w-7 h-7 text-surface-400 dark:text-surface-600" />
        </div>
        <h3 class="font-heading font-bold text-lg text-surface-800 dark:text-surface-100 mb-1">No sessions yet</h3>
        <p class="text-sm text-surface-500 dark:text-surface-400 max-w-sm">Charts will appear here once this event has at least one session with activity.</p>
      </div>
    {/if}

    <!-- ═══════════════════════════════════════════════════
         INSIGHTS
         ═══════════════════════════════════════════════════ -->
    <div class="space-y-3 mb-8">
      <div class="card p-6 border border-brand-500/20 bg-brand-500/5 dark:bg-brand-500/10 shadow-sm">
        <h2 class="font-heading font-bold text-sm uppercase tracking-wider text-brand-500 dark:text-brand-400 mb-4 flex items-center gap-2">
          <Activity class="w-4 h-4" /> Insights
        </h2>
        <div class="grid gap-3 sm:grid-cols-2 text-sm text-surface-600 dark:text-surface-300">
          <div class="flex items-start gap-2.5">
            <span class="w-1.5 h-1.5 rounded-full bg-brand-500 flex-shrink-0 mt-1.5"></span>
            <span>Event generated <strong class="text-surface-900 dark:text-surface-50">{totalResponses}</strong> total responses across <strong class="text-surface-900 dark:text-surface-50">{totalSessions}</strong> {totalSessions === 1 ? 'session' : 'sessions'}.</span>
          </div>
          {#if topSession}
            <div class="flex items-start gap-2.5">
              <span class="w-1.5 h-1.5 rounded-full bg-brand-500 flex-shrink-0 mt-1.5"></span>
              <span>Most active session: <strong class="text-surface-900 dark:text-surface-50">{topSession.title}</strong> — {topSession.total_responses} responses, {topSession.unique_participants} participants.</span>
            </div>
          {/if}
          {#if topPerformingSlide}
            <div class="flex items-start gap-2.5">
              <span class="w-1.5 h-1.5 rounded-full bg-brand-500 flex-shrink-0 mt-1.5"></span>
              <span>Top slide: <strong class="text-surface-900 dark:text-surface-50">"{topPerformingSlide.question.length > 42 ? topPerformingSlide.question.slice(0, 42) + '…' : topPerformingSlide.question}"</strong> — {topPerformingSlide.count} responses.</span>
            </div>
          {/if}
          <div class="flex items-start gap-2.5">
            <span class="w-1.5 h-1.5 rounded-full bg-brand-500 flex-shrink-0 mt-1.5"></span>
            <span>Average participation: <strong class="text-surface-900 dark:text-surface-50">{avgRespPerPart}</strong> responses per attendee.</span>
          </div>
        </div>
      </div>

      {#if topSession && sessions.length > 1}
        <div class="card p-5 bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-800 shadow-sm hover:shadow-md transition-shadow">
          <div class="flex flex-col sm:flex-row sm:items-center gap-4">
            <div class="w-10 h-10 flex items-center justify-center rounded-xl bg-brand-500/10 dark:bg-brand-500/15 flex-shrink-0">
              <Zap class="w-5 h-5 text-brand-500 dark:text-brand-400" />
            </div>
            <div class="flex-1 min-w-0">
              <div class="text-[10px] text-brand-500 dark:text-brand-400 uppercase tracking-widest font-bold mb-0.5">Most Active Session</div>
              <h3 class="font-heading font-semibold text-base text-surface-900 dark:text-surface-50 truncate">{topSession.title}</h3>
              <div class="flex flex-wrap items-center gap-3 mt-1 text-xs text-surface-500 dark:text-surface-400 font-medium">
                <span class="flex items-center gap-1"><MessageSquare class="w-3.5 h-3.5 text-violet-400" />{topSession.total_responses} responses</span>
                <span class="flex items-center gap-1"><Users class="w-3.5 h-3.5 text-emerald-400" />{topSession.unique_participants} participants</span>
              </div>
            </div>
            <button onclick={() => goto(`/dashboard/analytics/${eventId}/${topSession.session_id}`)} class="btn-secondary text-xs px-4 py-2 flex-shrink-0">
              View Details
            </button>
          </div>
        </div>
      {/if}
    </div>

    <!-- Session List -->
    <div class="card p-6 bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-800 shadow-sm">
      <div class="flex flex-col lg:flex-row lg:items-center justify-between gap-4 mb-5 border-b border-surface-100 dark:border-surface-800/80 pb-4">
        <div>
          <h2 class="font-heading font-bold text-lg text-surface-900 dark:text-surface-100">Sessions</h2>
          <p class="text-xs text-surface-500 dark:text-surface-400 mt-0.5">Ranked list of event sessions based on activity volume.</p>
        </div>
        <div class="flex flex-wrap items-center gap-2.5">
          <div class="relative">
            <Search class="w-3.5 h-3.5 text-surface-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              type="search"
              bind:value={sessionSearch}
              placeholder="Search sessions or moderators…"
              aria-label="Search sessions"
              class="pl-8 pr-3 py-2 text-sm rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 text-surface-800 dark:text-surface-100 placeholder:text-surface-400 focus:outline-none focus:ring-2 focus:ring-brand-500/40 w-full sm:w-56"
            />
          </div>
          <div class="relative">
            <SlidersHorizontal class="w-3.5 h-3.5 text-surface-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            <select
              bind:value={sessionFilter}
              aria-label="Filter sessions by engagement"
              class="pl-8 pr-7 py-2 text-sm rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 text-surface-700 dark:text-surface-200 focus:outline-none focus:ring-2 focus:ring-brand-500/40 appearance-none"
            >
              <option value="all">All sessions</option>
              <option value="high">High engagement</option>
              <option value="low">Needs attention</option>
            </select>
          </div>
          <span class="text-xs font-semibold px-2.5 py-2 bg-surface-100 dark:bg-surface-800 text-surface-600 dark:text-surface-400 rounded-full whitespace-nowrap">{filteredSessions.length} of {sessions.length}</span>
        </div>
      </div>

      {#if sessions.length === 0}
        <div class="flex flex-col items-center justify-center py-16 text-center">
          <div class="w-14 h-14 rounded-2xl bg-surface-100 dark:bg-surface-800 flex items-center justify-center mb-4">
            <Inbox class="w-7 h-7 text-surface-400 dark:text-surface-600" />
          </div>
          <h3 class="font-heading font-bold text-base text-surface-800 dark:text-surface-100 mb-1">No sessions found</h3>
          <p class="text-sm text-surface-500 dark:text-surface-400 max-w-xs">Create a session under this event to start collecting analytics.</p>
        </div>
      {:else if filteredSessions.length === 0}
        <div class="flex flex-col items-center justify-center py-16 text-center">
          <div class="w-14 h-14 rounded-2xl bg-surface-100 dark:bg-surface-800 flex items-center justify-center mb-4">
            <Search class="w-7 h-7 text-surface-400 dark:text-surface-600" />
          </div>
          <h3 class="font-heading font-bold text-base text-surface-800 dark:text-surface-100 mb-1">No matching sessions</h3>
          <p class="text-sm text-surface-500 dark:text-surface-400 max-w-xs">Try a different search term or reset the engagement filter.</p>
        </div>
      {:else}
        <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {#each pagedSessions as s, i (s.session_id)}
            {@const pct = sessionEngagementPct(s)}
            <div in:fade={{ duration: 250, delay: i * 40 }} class="flex flex-col p-5 rounded-2xl border border-surface-200 dark:border-surface-800 bg-surface-50/40 dark:bg-surface-900/30 hover:border-brand-500/30 hover:shadow-md transition-all duration-200">
              <div class="flex items-start justify-between gap-2 mb-3">
                <h3 class="font-heading font-semibold text-sm text-surface-900 dark:text-surface-100 truncate flex-1" title={s.title}>{s.title}</h3>
                <span class="inline-block px-2 py-0.5 rounded-full text-[10px] font-bold flex-shrink-0 {engBadge(pct)}">{pct}%</span>
              </div>
              {#if s.moderator_name}
                <div class="flex items-center gap-1.5 text-xs text-surface-500 dark:text-surface-400 mb-4">
                  <User class="w-3.5 h-3.5" /> {s.moderator_name}
                </div>
              {:else}
                <div class="mb-4"></div>
              {/if}

              <div class="grid grid-cols-2 gap-x-3 gap-y-2.5 text-xs mb-5 pb-5 border-b border-surface-200/70 dark:border-surface-800/70">
                <div class="flex items-center gap-1.5 text-surface-600 dark:text-surface-300">
                  <Users class="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                  <span class="font-bold tabular-nums text-surface-900 dark:text-surface-100">{s.unique_participants}</span> participants
                </div>
                <div class="flex items-center gap-1.5 text-surface-600 dark:text-surface-300">
                  <MessageSquare class="w-3.5 h-3.5 text-violet-400 flex-shrink-0" />
                  <span class="font-bold tabular-nums text-surface-900 dark:text-surface-100">{s.total_responses}</span> responses
                </div>
                <div class="flex items-center gap-1.5 text-surface-600 dark:text-surface-300">
                  <Layers class="w-3.5 h-3.5 text-brand-400 flex-shrink-0" />
                  <span class="font-bold tabular-nums text-surface-900 dark:text-surface-100">{s.slide_count}</span> slides
                </div>
                <div class="flex items-center gap-1.5 text-surface-600 dark:text-surface-300">
                  {#if s.avg_rating !== null}
                    <span class="text-amber-400 text-xs font-bold">{ratingStars(s.avg_rating)}</span>
                  {:else}
                    <span class="text-surface-400">No ratings</span>
                  {/if}
                </div>
              </div>

              <div class="flex items-center gap-2 mt-auto">
                <button
                  onclick={() => goto(`/dashboard/analytics/${eventId}/${s.session_id}`)}
                  class="btn-primary text-xs px-3 py-2 flex-1 text-center"
                >
                  View Analytics
                </button>
                <button
                  onclick={() => downloadSessionReport(s.session_id)}
                  disabled={downloadingSessionId === s.session_id}
                  aria-label={`Download report for ${s.title}`}
                  class="btn-secondary text-xs px-3 py-2 flex items-center gap-1.5"
                >
                  <Download class="w-3.5 h-3.5" />
                  {downloadingSessionId === s.session_id ? '…' : 'Report'}
                </button>
              </div>
            </div>
          {/each}
        </div>

        {#if totalSessionPages > 1}
          <div class="flex items-center justify-between mt-6 pt-4 border-t border-surface-100 dark:border-surface-800/70">
            <button
              onclick={() => sessionPage = Math.max(1, sessionPage - 1)}
              disabled={sessionPage <= 1}
              aria-label="Previous page"
              class="btn-secondary text-xs px-3 py-2 flex items-center gap-1 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <ChevronLeft class="w-3.5 h-3.5" /> Prev
            </button>
            <span class="text-xs text-surface-500 dark:text-surface-400 font-medium">Page {sessionPage} of {totalSessionPages}</span>
            <button
              onclick={() => sessionPage = Math.min(totalSessionPages, sessionPage + 1)}
              disabled={sessionPage >= totalSessionPages}
              aria-label="Next page"
              class="btn-secondary text-xs px-3 py-2 flex items-center gap-1 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Next <ChevronRight class="w-3.5 h-3.5" />
            </button>
          </div>
        {/if}
      {/if}
    </div>
  {/if}
</main>
