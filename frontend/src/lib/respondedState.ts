/**
 * Clear-awareness for a guest's "already answered" state.
 *
 * Which slides a guest has answered is kept in localStorage
 * (`rforum_responded_{guestId}`, written by InteractionView), so a reload
 * doesn't offer a fresh vote. When the moderator clears a slide's responses
 * the server bumps `content_json.responses_cleared` (part of every join /
 * resync payload). Each stored answer is recorded with the count the server
 * returned for it (app/routers/responses.py — authoritative even when a clear
 * races the submission), so a guest who missed the live clear event — e.g.
 * while disconnected — notices the clear later and can answer again.
 *
 * An answer only queued on this device records `null` ("pending"): it isn't
 * on the server yet, so no clear can have removed it. The count is filled in
 * when the queue delivers it (see $lib/responseQueue).
 */

const respondedKey = (guestId: string) => `rforum_responded_${guestId}`;
const clearCountKey = (guestId: string) => `rforum_responded_clears_${guestId}`;

function readMap(key: string): Record<string, any> {
  if (typeof localStorage === 'undefined') return {};
  try {
    const parsed = JSON.parse(localStorage.getItem(key) || '{}');
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function writeMap(key: string, map: Record<string, any>) {
  try {
    localStorage.setItem(key, JSON.stringify(map));
  } catch {
    // Storage unavailable — non-fatal, the state just won't persist.
  }
}

/** How many times the moderator has cleared this slide's responses. */
export function responsesClearedCount(slide: any): number {
  const n = Number(slide?.content_json?.responses_cleared);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

/** Call whenever a response is recorded as answered: `count` is the server's
 * responses_cleared for that stored response, or null while it is only queued. */
export function recordAnsweredClearCount(guestId: string, slideId: string, count: number | null) {
  if (!guestId || !slideId || typeof localStorage === 'undefined') return;
  const map = readMap(clearCountKey(guestId));
  map[slideId] = count;
  writeMap(clearCountKey(guestId), map);
}

/** A queued answer was delivered: fill in its pending (null) count with the
 * server's. No-op for slides not marked answered or already counted. */
export function confirmQueuedAnswerClearCount(guestId: string, slideId: string, count: unknown) {
  if (!guestId || !slideId || typeof count !== 'number' || typeof localStorage === 'undefined') return;
  if (!(slideId in readMap(respondedKey(guestId)))) return;
  const map = readMap(clearCountKey(guestId));
  if (map[slideId] !== null) return;
  map[slideId] = count;
  writeMap(clearCountKey(guestId), map);
}

/** Drop the "already answered" state for a slide. */
export function forgetAnswered(guestId: string, slideId: string) {
  if (!guestId || !slideId || typeof localStorage === 'undefined') return;
  for (const key of [respondedKey(guestId), clearCountKey(guestId)]) {
    const map = readMap(key);
    if (slideId in map) {
      delete map[slideId];
      writeMap(key, map);
    }
  }
}

/** If this guest's saved answer predates a clear of `slide`, forget it.
 * Returns true when state was dropped (the form should be reset). */
export function reconcileAnsweredWithClears(guestId: string, slide: any): boolean {
  if (!guestId || !slide?.id || typeof localStorage === 'undefined') return false;
  if (!(slide.id in readMap(respondedKey(guestId)))) return false;
  const counts = readMap(clearCountKey(guestId));
  // Still queued on this device: no clear can have removed it.
  if (counts[slide.id] === null) return false;
  // Answers saved before this existed carry no count: treat as 0, i.e.
  // "answered before any clear" — correct, since earlier clears never bumped it.
  const recorded = Number(counts[slide.id] ?? 0);
  if (recorded === responsesClearedCount(slide)) return false;
  forgetAnswered(guestId, slide.id);
  return true;
}
