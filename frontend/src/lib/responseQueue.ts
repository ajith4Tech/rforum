/**
 * Durable, per-session queue for guest response submissions.
 *
 * Every submission gets a stable idempotency key and is written to IndexedDB
 * BEFORE the network attempt, then removed only once the server acknowledges
 * it (201 created, or 200 replay of an earlier delivery — the server derives
 * the response id from the key, see app/routers/responses.py). So:
 *   - connectivity failure  → stays queued, retried automatically later;
 *   - tab closed mid-request → retried on next visit, never stored twice;
 *   - server rejection (slide closed, session ended, invalid) → dropped and
 *     reported, never retried forever.
 *
 * Entries are scoped to a session code and only ever flushed by a page for
 * that same session; anything older than MAX_AGE_MS is discarded.
 * When IndexedDB is unavailable (some private modes), submissions are sent
 * directly with no queue — and a connectivity failure is reported as such
 * instead of being presented as saved.
 */
import { writable } from 'svelte/store';
import { submitResponse, isConnectivityError, ApiError } from './api';

export interface QueuedResponse {
  /** Idempotency key — also the IndexedDB primary key. */
  id: string;
  sessionCode: string;
  slideId: string;
  guestId: string;
  value: string;
  name?: string;
  rating?: number;
  createdAt: number;
  attempts: number;
  lastError?: string;
}

export interface RejectedSubmission {
  id: string;
  slideId: string;
  reason: string;
}

export type SubmitOutcome = { state: 'confirmed'; response: any } | { state: 'queued'; id: string };

const DB_NAME = 'rforum-offline';
const DB_VERSION = 1;
const STORE = 'pending_responses';
const MAX_AGE_MS = 24 * 60 * 60 * 1000;
const RETRY_INTERVAL_MS = 20000;

/** Pending (not yet server-confirmed) submissions for the session being flushed. */
export const pendingSubmissions = writable<QueuedResponse[]>([]);
/** Queued submissions the server refused on retry — shown to the guest, then dismissed. */
export const rejectedSubmissions = writable<RejectedSubmission[]>([]);
/** Bumped whenever a previously queued submission is confirmed by the server. */
export const lastConfirmed = writable<{ slideId: string; at: number } | null>(null);

let dbPromise: Promise<IDBDatabase | null> | null = null;

function openDb(): Promise<IDBDatabase | null> {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve) => {
    if (typeof indexedDB === 'undefined') return resolve(null);
    let request: IDBOpenDBRequest;
    try {
      request = indexedDB.open(DB_NAME, DB_VERSION);
    } catch {
      return resolve(null);
    }
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE)) {
        const store = db.createObjectStore(STORE, { keyPath: 'id' });
        store.createIndex('sessionCode', 'sessionCode', { unique: false });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => resolve(null);
    request.onblocked = () => resolve(null);
  });
  return dbPromise;
}

function txDone(tx: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  });
}

async function putEntry(entry: QueuedResponse): Promise<boolean> {
  const db = await openDb();
  if (!db) return false;
  try {
    const tx = db.transaction(STORE, 'readwrite');
    tx.objectStore(STORE).put(entry);
    await txDone(tx);
    return true;
  } catch {
    return false;
  }
}

async function deleteEntry(id: string): Promise<void> {
  const db = await openDb();
  if (!db) return;
  try {
    const tx = db.transaction(STORE, 'readwrite');
    tx.objectStore(STORE).delete(id);
    await txDone(tx);
  } catch {
    // Left in place; an acknowledged retry is a harmless server-side replay.
  }
}

async function entriesForSession(sessionCode: string): Promise<QueuedResponse[]> {
  const db = await openDb();
  if (!db) return [];
  try {
    const tx = db.transaction(STORE, 'readonly');
    const request = tx.objectStore(STORE).index('sessionCode').getAll(sessionCode);
    const entries = await new Promise<QueuedResponse[]>((resolve, reject) => {
      request.onsuccess = () => resolve(request.result as QueuedResponse[]);
      request.onerror = () => reject(request.error);
    });
    return entries.sort((a, b) => a.createdAt - b.createdAt);
  } catch {
    return [];
  }
}

function newKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  const bytes = new Uint8Array(16);
  if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
    crypto.getRandomValues(bytes);
  } else {
    for (let i = 0; i < bytes.length; i++) bytes[i] = Math.floor(Math.random() * 256);
  }
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

/** Server refusals that will never succeed on retry — everything but connectivity/back-pressure. */
function isPermanentRejection(err: unknown): boolean {
  if (isConnectivityError(err)) return false;
  if (err instanceof ApiError) return err.status !== 429 && err.status !== 409 && err.status < 500;
  return false;
}

async function send(entry: QueuedResponse) {
  return submitResponse(entry.slideId, entry.value, entry.guestId, entry.name, entry.rating, entry.id);
}

async function refreshPending(sessionCode: string) {
  pendingSubmissions.set(await entriesForSession(sessionCode));
}

/**
 * Submit a guest response. Resolves 'confirmed' when the server stored it,
 * 'queued' when it is saved on this device and will be retried. Throws when
 * the server rejected it, or when it could not be sent and could not be saved.
 */
export async function submitWithQueue(params: {
  sessionCode: string;
  slideId: string;
  guestId: string;
  value: string;
  name?: string;
  rating?: number;
}): Promise<SubmitOutcome> {
  const entry: QueuedResponse = { id: newKey(), ...params, createdAt: Date.now(), attempts: 0 };
  const saved = params.sessionCode ? await putEntry(entry) : false;
  try {
    const response = await send(entry);
    if (saved) await deleteEntry(entry.id);
    if (saved) await refreshPending(params.sessionCode);
    return { state: 'confirmed', response };
  } catch (err) {
    if (saved && !isPermanentRejection(err)) {
      await putEntry({ ...entry, attempts: 1, lastError: err instanceof Error ? err.message : String(err) });
      await refreshPending(params.sessionCode);
      return { state: 'queued', id: entry.id };
    }
    if (saved) {
      await deleteEntry(entry.id);
      await refreshPending(params.sessionCode);
    }
    if (isConnectivityError(err)) {
      throw new Error("You're offline and this device can't store responses — please try again when connected.");
    }
    throw err;
  }
}

const flushing = new Set<string>();

/**
 * Retry this session's queued submissions, oldest first. Stops at the first
 * connectivity failure (the rest would fail the same way). Safe to call
 * concurrently and from several tabs: the server deduplicates by key.
 */
export async function flushPending(sessionCode: string): Promise<void> {
  if (!sessionCode || flushing.has(sessionCode)) return;
  flushing.add(sessionCode);
  try {
    const entries = await entriesForSession(sessionCode);
    for (const entry of entries) {
      if (Date.now() - entry.createdAt > MAX_AGE_MS) {
        await deleteEntry(entry.id);
        rejectedSubmissions.update((list) => [...list, { id: entry.id, slideId: entry.slideId, reason: 'It was saved too long ago to send.' }]);
        continue;
      }
      try {
        await send(entry);
        await deleteEntry(entry.id);
        lastConfirmed.set({ slideId: entry.slideId, at: Date.now() });
      } catch (err) {
        if (isPermanentRejection(err)) {
          await deleteEntry(entry.id);
          rejectedSubmissions.update((list) => [
            ...list,
            { id: entry.id, slideId: entry.slideId, reason: err instanceof Error ? err.message : 'It was not accepted.' },
          ]);
          continue;
        }
        await putEntry({ ...entry, attempts: entry.attempts + 1, lastError: err instanceof Error ? err.message : String(err) });
        break;
      }
    }
  } finally {
    flushing.delete(sessionCode);
    await refreshPending(sessionCode);
  }
}

/**
 * Keep retrying this session's queue: now, whenever the browser comes back
 * online, and on a timer while anything is pending. Returns a stop function.
 */
export function startAutoFlush(sessionCode: string): () => void {
  if (typeof window === 'undefined' || !sessionCode) return () => {};
  let stopped = false;
  const flush = () => { if (!stopped) void flushPending(sessionCode); };
  const onOnline = () => flush();
  window.addEventListener('online', onOnline);
  const timer = setInterval(() => {
    let hasPending = false;
    const unsubscribe = pendingSubmissions.subscribe((list) => { hasPending = list.length > 0; });
    unsubscribe();
    if (hasPending && navigator.onLine !== false) flush();
  }, RETRY_INTERVAL_MS);
  flush();
  return () => {
    stopped = true;
    window.removeEventListener('online', onOnline);
    clearInterval(timer);
  };
}

export function dismissRejected(id: string) {
  rejectedSubmissions.update((list) => list.filter((r) => r.id !== id));
}
