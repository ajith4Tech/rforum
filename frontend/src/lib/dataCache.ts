import { listEvents, listSessions, type ListParams, type PaginatedResult } from './api';

/**
 * Thin in-memory cache in front of listEvents()/listSessions(). Keyed by the
 * exact (limit, offset, search) combination a caller asks for, so Nav's
 * global search, and the Events/Sessions dashboard pages each get their own
 * cached page without colliding — a page-1-no-search request and a
 * search="foo" request are different cache entries. Concurrent callers for
 * the same key share one in-flight request; callers that mutate data call
 * invalidateEvents()/invalidateSessions()/invalidateAll() so the next read
 * of ANY key refetches.
 */

function keyFor(params: ListParams): string {
  return JSON.stringify({
    limit: params.limit ?? null,
    offset: params.offset ?? 0,
    search: params.search ?? '',
  });
}

const eventsCache = new Map<string, PaginatedResult<any>>();
const eventsInFlight = new Map<string, Promise<PaginatedResult<any>>>();

const sessionsCache = new Map<string, PaginatedResult<any>>();
const sessionsInFlight = new Map<string, Promise<PaginatedResult<any>>>();

export async function getEvents(params: ListParams = {}): Promise<PaginatedResult<any>> {
  const key = keyFor(params);
  const cached = eventsCache.get(key);
  if (cached) return cached;
  let inFlight = eventsInFlight.get(key);
  if (!inFlight) {
    inFlight = listEvents(params)
      .then((result) => {
        eventsCache.set(key, result);
        return result;
      })
      .finally(() => {
        eventsInFlight.delete(key);
      });
    eventsInFlight.set(key, inFlight);
  }
  return inFlight;
}

export async function getSessions(params: ListParams = {}): Promise<PaginatedResult<any>> {
  const key = keyFor(params);
  const cached = sessionsCache.get(key);
  if (cached) return cached;
  let inFlight = sessionsInFlight.get(key);
  if (!inFlight) {
    inFlight = listSessions(params)
      .then((result) => {
        sessionsCache.set(key, result);
        return result;
      })
      .finally(() => {
        sessionsInFlight.delete(key);
      });
    sessionsInFlight.set(key, inFlight);
  }
  return inFlight;
}

export function invalidateEvents(): void {
  eventsCache.clear();
  eventsInFlight.clear();
}

export function invalidateSessions(): void {
  sessionsCache.clear();
  sessionsInFlight.clear();
}

export function invalidateAll(): void {
  invalidateEvents();
  invalidateSessions();
}
