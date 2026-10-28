/// <reference types="@sveltejs/kit" />
/// <reference no-default-lib="true"/>
/// <reference lib="esnext" />
/// <reference lib="webworker" />

/**
 * Offline resilience for live events (registered automatically by SvelteKit).
 *
 * 1. App shell: the SPA fallback page plus this build's hashed assets and
 *    static files are precached per build `version`, so guest / projector /
 *    dashboard pages can start even when the network is down or very slow.
 *    A new version waits until every tab of the old one is closed (no
 *    skipWaiting): a projector left open mid-event never mixes old and new code.
 *
 * 2. Live-session data, network-first with an offline fallback — only the
 *    guest-facing, code-authorized requests a projector/guest needs to keep
 *    showing the current slide through an outage:
 *      GET /api/sessions/join/{CODE}                       (sanitized session state)
 *      GET /api/presentations/{id}/pages/{n}/image|thumbnail?code=CODE
 *      GET /api/sessions/{id}/slides/{slide}/page/{n}?code=CODE
 *    Stored per session code in its own cache ("rforum-live-{CODE}"), keyed
 *    WITHOUT any `token` query parameter (a moderator's JWT never becomes part
 *    of a cache key), only ever served when the network fails (or, for an
 *    image already cached, takes too long). A 401/403/404/410 from the server
 *    evicts the entry, so revoked access is honoured whenever the server is
 *    reachable. Caches expire after LIVE_MAX_AGE_MS, are size-capped, and are
 *    cleared on logout ($lib/api.ts).
 *
 * Everything else — authenticated API calls, POSTs, responses lists, WebSockets
 * — is not intercepted and behaves exactly as without a service worker.
 */
import { build, files, version } from '$service-worker';

const sw = self as unknown as ServiceWorkerGlobalScope;

const SHELL_CACHE = `rforum-shell-${version}`;
const SHELL_URL = '/index.html';
// @fontsource emits every unicode-range subset of every weight in woff2 and
// woff (~1.5 MB). Pages only ever fetch the subsets they render, so precache
// just the Latin woff2 files and the heading font; the rest still load on
// demand (1-year immutable HTTP cache) and fall back to system fonts offline.
const isFont = (path: string) => /\.(woff2?|ttf|otf)$/.test(path);
const isPrecachedFont = (path: string) =>
  /-latin-\d+-normal\.[\w-]+\.woff2$/.test(path) || path.includes('/GlacialIndifference-');
const PRECACHE = [...build.filter((path) => !isFont(path) || isPrecachedFont(path)), ...files];
const PRECACHE_PATHS = new Set(PRECACHE);

const LIVE_PREFIX = 'rforum-live-';
const LIVE_META_KEY = '/__rforum_live_meta';
const LIVE_MAX_ENTRIES = 300;
const LIVE_MAX_AGE_MS = 24 * 60 * 60 * 1000;

// On a weak network, stop waiting for the app shell / an already-cached image
// after this long and use the local copy (the request keeps going).
const NAVIGATION_TIMEOUT_MS = 4000;
const IMAGE_TIMEOUT_MS = 5000;

const CODE_RE = /^[A-Z0-9-]{4,32}$/;

sw.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(SHELL_CACHE);
      await cache.addAll(PRECACHE);
      // The SPA fallback (adapter-static `fallback: 'index.html'`). Not part of
      // `build`/`files`; a failure here (e.g. dev server) must not block install.
      await cache.add(SHELL_URL).catch(() => {});
    })()
  );
});

sw.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      for (const key of await caches.keys()) {
        if (key.startsWith('rforum-shell-') && key !== SHELL_CACHE) await caches.delete(key);
      }
      await pruneExpiredLiveCaches();
      // First install only takes effect without a reload when we claim open pages.
      await sw.clients.claim();
    })()
  );
});

type LiveTarget = { code: string; key: string; kind: 'session' | 'image' };

/** Which live-session request (if any) this is, and its token-free cache key. */
function liveTarget(url: URL): LiveTarget | null {
  const path = url.pathname;
  const join = path.match(/^\/api\/sessions\/join\/([^/]+)$/);
  if (join) {
    const code = decodeURIComponent(join[1]).toUpperCase();
    return CODE_RE.test(code) ? { code, key: `/api/sessions/join/${code}`, kind: 'session' } : null;
  }
  const isPresentationImage = /^\/api\/presentations\/[^/]+\/pages\/\d+\/(image|thumbnail)$/.test(path);
  const isSlideImage = /^\/api\/sessions\/[^/]+\/slides\/[^/]+\/page\/\d+$/.test(path);
  if (!isPresentationImage && !isSlideImage) return null;
  // Only cache what a guest with the session code may see. Token-only requests
  // (the moderator dashboard) are left alone.
  const code = (url.searchParams.get('code') || '').toUpperCase();
  if (!CODE_RE.test(code)) return null;
  return { code, key: `${path}?code=${encodeURIComponent(code)}`, kind: 'image' };
}

function delay(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms));
}

async function touchLiveCache(cache: Cache) {
  await cache.put(LIVE_META_KEY, new Response(JSON.stringify({ at: Date.now() }), {
    headers: { 'Content-Type': 'application/json' },
  }));
}

async function trimLiveCache(cache: Cache) {
  const keys = (await cache.keys()).filter((req) => new URL(req.url).pathname !== LIVE_META_KEY);
  // Oldest first (insertion order).
  for (const req of keys.slice(0, Math.max(0, keys.length - LIVE_MAX_ENTRIES))) {
    await cache.delete(req);
  }
}

async function pruneExpiredLiveCaches() {
  for (const name of await caches.keys()) {
    if (!name.startsWith(LIVE_PREFIX)) continue;
    const cache = await caches.open(name);
    let at = 0;
    try {
      const meta = await cache.match(LIVE_META_KEY);
      at = meta ? (await meta.json()).at || 0 : 0;
    } catch {
      at = 0;
    }
    if (Date.now() - at > LIVE_MAX_AGE_MS) await caches.delete(name);
  }
}

async function handleLive(request: Request, target: LiveTarget): Promise<Response> {
  const cache = await caches.open(LIVE_PREFIX + target.code);
  const cacheKey = new URL(target.key, sw.location.origin).href;

  const network = fetch(request).then(async (response) => {
    if (response.ok) {
      await cache.put(cacheKey, response.clone());
      await touchLiveCache(cache);
      await trimLiveCache(cache);
    } else if ([401, 403, 404, 410].includes(response.status)) {
      // The server said no: never serve this from cache again.
      await cache.delete(cacheKey);
    }
    return response;
  });

  if (target.kind === 'image') {
    const cached = await cache.match(cacheKey);
    if (cached) {
      // Images are immutable per URL for presentations; on a stalled network,
      // show what we have rather than a blank slide.
      return Promise.race([
        network.catch(() => cached),
        delay(IMAGE_TIMEOUT_MS).then(() => cached),
      ]);
    }
  }

  try {
    return await network;
  } catch (err) {
    const cached = await cache.match(cacheKey);
    if (cached) return cached;
    throw err;
  }
}

async function handleNavigation(request: Request): Promise<Response> {
  const network = fetch(request);
  const cachedShell = await caches.match(SHELL_URL, { cacheName: SHELL_CACHE });
  if (!cachedShell) return network;
  try {
    return await Promise.race([
      network,
      delay(NAVIGATION_TIMEOUT_MS).then(() => cachedShell),
    ]);
  } catch {
    return cachedShell;
  }
}

sw.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  // Same-origin only: a deployment with a separate API origin (VITE_API_ORIGIN)
  // keeps today's network-only behaviour for API data.
  if (url.origin !== sw.location.origin) return;

  if (request.mode === 'navigate') {
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/ws/') || url.pathname === '/healthz') return;
    event.respondWith(handleNavigation(request));
    return;
  }

  if (PRECACHE_PATHS.has(url.pathname)) {
    event.respondWith(
      caches.match(url.pathname, { cacheName: SHELL_CACHE }).then((cached) => cached || fetch(request))
    );
    return;
  }

  const target = liveTarget(url);
  if (target) event.respondWith(handleLive(request, target));
});
