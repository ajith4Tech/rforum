import { CHART_FONT_FAMILY } from './constants';

/** Converts an RGB tuple (as used by jsPDF's setFillColor et al.) to a CSS hex string for canvas fillStyle. */
export function rgbToHex(rgb: readonly number[]): string {
  return '#' + rgb.map((x) => {
    const hex = x.toString(16);
    return hex.length === 1 ? '0' + hex : hex;
  }).join('');
}

export interface PieSlice {
  value: number;
  color: string;
}

/**
 * High-resolution canvas-based donut/pie chart, returned as a PNG data URI for jsPDF's addImage.
 * Draws a percentage label on each slice large enough to fit one (>= 6%) so readers don't have to
 * cross-reference a separate legend for the dominant segments.
 */
export function generateHighResPieChart(
  width: number,
  height: number,
  chartData: PieSlice[],
  isDonut = false,
  centerText = '',
  centerSubtext = ''
): string {
  const canvas = document.createElement('canvas');
  const scale = 3;
  canvas.width = width * scale;
  canvas.height = height * scale;
  const ctx = canvas.getContext('2d');
  if (!ctx) return '';
  ctx.scale(scale, scale);

  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(width, height) / 2 - 10;
  const total = chartData.reduce((sum, d) => sum + d.value, 0) || 1;

  let cumulativeAngle = -Math.PI / 2; // Start from top
  const labelRadius = isDonut ? radius * 0.82 : radius * 0.62;

  chartData.forEach((d) => {
    const pct = d.value / total;
    const sweep = pct * Math.PI * 2;
    if (sweep <= 0.001) return;

    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, radius, cumulativeAngle, cumulativeAngle + sweep);
    ctx.closePath();
    ctx.fillStyle = d.color;
    ctx.fill();

    // Percentage label at the slice's midpoint angle — only when the slice is
    // wide enough (>= ~6%) for a two-digit "NN%" label to fit legibly.
    if (pct >= 0.06) {
      const midAngle = cumulativeAngle + sweep / 2;
      const lx = cx + labelRadius * Math.cos(midAngle);
      const ly = cy + labelRadius * Math.sin(midAngle);
      ctx.fillStyle = '#FFFFFF';
      ctx.font = `bold 9px ${CHART_FONT_FAMILY}`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(`${Math.round(pct * 100)}%`, lx, ly);
    }

    cumulativeAngle += sweep;
  });

  if (isDonut) {
    ctx.beginPath();
    ctx.arc(cx, cy, radius * 0.65, 0, Math.PI * 2);
    ctx.fillStyle = '#FFFFFF';
    ctx.fill();

    if (centerText) {
      ctx.fillStyle = '#0F172A';
      ctx.font = `bold 15px ${CHART_FONT_FAMILY}`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(centerText, cx, cy - (centerSubtext ? 4 : 0));
    }
    if (centerSubtext) {
      ctx.fillStyle = '#64748B';
      ctx.font = `normal 8px ${CHART_FONT_FAMILY}`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(centerSubtext, cx, cy + 9);
    }
  }

  return canvas.toDataURL('image/png');
}

/**
 * High-resolution canvas-based word-cloud image, returned as a PNG data URI for jsPDF's addImage.
 * Word placement uses a fixed set of hand-tuned offsets around the center so the layout is stable
 * across renders (no overlap heuristics needed at this scale).
 */
export function generateHighResWordCloud(
  width: number,
  height: number,
  keywords: { word: string; count: number }[],
  colorHex: string
): string {
  const canvas = document.createElement('canvas');
  const scale = 3;
  canvas.width = width * scale;
  canvas.height = height * scale;
  const ctx = canvas.getContext('2d');
  if (!ctx) return '';
  ctx.scale(scale, scale);

  ctx.fillStyle = '#F8FAFC';
  ctx.fillRect(0, 0, width, height);

  if (keywords.length === 0) {
    ctx.fillStyle = '#94A3B8';
    ctx.font = `normal 12px ${CHART_FONT_FAMILY}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('No responses recorded', width / 2, height / 2);
    return canvas.toDataURL('image/png');
  }

  const maxCount = Math.max(...keywords.map((k) => k.count), 1);
  const centerX = width / 2;
  const centerY = height / 2;

  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';

  const offsets = [
    { dx: 0, dy: 0 },
    { dx: -55, dy: -25 },
    { dx: 60, dy: 25 },
    { dx: -60, dy: 25 },
    { dx: 55, dy: -25 },
    { dx: 0, dy: 35 },
    { dx: 0, dy: -35 },
    { dx: -90, dy: 0 },
    { dx: 90, dy: 0 },
    { dx: -40, dy: -45 },
    { dx: 40, dy: 45 },
    { dx: -45, dy: 45 },
    { dx: 45, dy: -45 },
    { dx: -100, dy: -30 },
    { dx: 100, dy: 30 },
    { dx: -100, dy: 30 },
    { dx: 100, dy: -30 },
  ];

  keywords.slice(0, offsets.length).forEach((kw, i) => {
    const ratio = kw.count / maxCount;
    const fontSize = Math.max(9, Math.min(24, 9 + ratio * 15));
    ctx.font = `bold ${fontSize}px ${CHART_FONT_FAMILY}`;
    ctx.fillStyle = colorHex;

    const offset = offsets[i] ?? { dx: (Math.random() - 0.5) * 120, dy: (Math.random() - 0.5) * 80 };
    ctx.fillText(kw.word, centerX + offset.dx, centerY + offset.dy);
  });

  return canvas.toDataURL('image/png');
}
