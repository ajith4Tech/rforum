/**
 * Event dates are calendar dates (`YYYY-MM-DD`, no time or zone) meant in the
 * viewer's local timezone. Comparing them against
 * `new Date().toISOString().slice(0, 10)` uses the *UTC* date instead, which in
 * IST (UTC+5:30) still says "yesterday" until 05:30 — so today's events showed
 * as past and today's badges were missing in the early morning.
 */

/** Today's date in the local timezone as `YYYY-MM-DD`. */
export function todayKey(now: Date = new Date()): string {
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

/** Whether a `YYYY-MM-DD` event date is today in the local timezone. */
export function isToday(dateStr: string | null | undefined): boolean {
  return !!dateStr && dateStr.slice(0, 10) === todayKey();
}

/** Local midnight of a `YYYY-MM-DD` event date (never parsed as UTC). */
export function parseEventDate(dateStr: string): Date {
  return new Date(dateStr.slice(0, 10) + 'T00:00:00');
}
