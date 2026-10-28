/**
 * Shared chart colours for the analytics pages (inline SVG) and the PDF
 * reports (canvas/jsPDF), so the same series or slide type gets the same
 * colour on screen and in the exported report.
 *
 * Series colours are Tailwind 500/600 steps: saturated enough to read as
 * strokes/fills on both a white card and a surface-900 card. Text inside
 * on-screen SVGs should NOT use these hex values — use theme classes
 * (`fill-surface-900 dark:fill-surface-50`) instead, since an inline
 * `style="fill:…"` always beats a `dark:` class.
 */

/** Categorical series palette (same order as CHART_PALETTE in $lib/pdf/constants). */
export const SERIES_COLORS = [
  '#7C3AED', // brand-600
  '#06B6D4', // accent / cyan-500
  '#10B981', // emerald-500
  '#F59E0B', // amber-500
  '#EC4899', // pink-500
  '#6366F1', // indigo-500
  '#14B8A6', // teal-500
  '#EF4444', // red-500
] as const;

/** Colour for the i-th series, cycling through the palette. */
export function seriesColor(i: number): string {
  return SERIES_COLORS[i % SERIES_COLORS.length];
}

/** Neutral used for unknown categories. */
export const FALLBACK_SERIES_COLOR = '#94A3B8';

/**
 * One fixed colour per slide type, matching the type badges used across the
 * dashboard (POLL = brand, QNA = cyan, FEEDBACK = amber, CONTENT = emerald,
 * WORD_CLOUD = pink).
 */
export const SLIDE_TYPE_COLORS: Record<string, string> = {
  POLL: '#7C3AED',
  QNA: '#06B6D4',
  FEEDBACK: '#F59E0B',
  CONTENT: '#10B981',
  WORD_CLOUD: '#EC4899',
};

/** Slide-type colour, falling back to the series palette for unknown types. */
export function slideTypeColor(type: string, fallbackIndex = 0): string {
  return SLIDE_TYPE_COLORS[type] ?? seriesColor(fallbackIndex);
}

/**
 * Neutrals for charts drawn onto the (always light) PDF page via canvas.
 * Not for on-screen use — the screen follows the app theme.
 */
export const PAPER = {
  background: '#FFFFFF',
  panel: '#F8FAFC',
  text: '#0F172A',
  muted: '#64748B',
  faint: '#94A3B8',
} as const;

/**
 * Badge classes for an engagement/participation percentage
 * (>= 80 good, >= 50 fair, else needs attention). 700/400 text steps keep
 * the label readable on the tinted background in both themes.
 */
export function engagementBadgeClass(pct: number): string {
  if (pct >= 80) return 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400';
  if (pct >= 50) return 'bg-amber-500/15 text-amber-700 dark:text-amber-400';
  return 'bg-rose-500/15 text-rose-700 dark:text-rose-400';
}
