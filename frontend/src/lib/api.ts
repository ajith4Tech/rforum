const API_PREFIX = '/api';
const DEFAULT_API_PORT = '8000';

const guessApiOrigin = () => {
  if (typeof window === 'undefined') return '';
  if (import.meta.env?.VITE_API_ORIGIN) return import.meta.env.VITE_API_ORIGIN as string;
  // In dev/prod when frontend runs on a different port, assume backend is same host on 8000
  if (window.location.port && window.location.port !== DEFAULT_API_PORT) {
    return `${window.location.protocol}//${window.location.hostname}:${DEFAULT_API_PORT}`;
  }
  return window.location.origin;
};

export const API_ORIGIN = guessApiOrigin();
export const WS_ORIGIN = (import.meta.env?.VITE_WS_ORIGIN as string | undefined)
  || (API_ORIGIN ? API_ORIGIN.replace(/^http/, 'ws') : '');

const withPrefix = (path: string) => `${API_PREFIX}${path.startsWith('/') ? path : `/${path}`}`;
const buildUrl = (path: string) => {
  const prefix = API_ORIGIN || '';
  return `${prefix}${withPrefix(path)}`;
};

const withTimeout = async <T>(promise: Promise<T>, ms = 10000): Promise<T> => {
  if (ms <= 0) return promise;
  return Promise.race([
    promise,
    new Promise<T>((_, reject) => setTimeout(() => reject(new Error('Request timed out')), ms)),
  ]);
};

const getToken = () => (typeof localStorage !== 'undefined' ? localStorage.getItem('rforum_token') : null);

const buildHeaders = (opts: { auth?: boolean; json?: boolean } = {}) => {
  const headers: Record<string, string> = {};
  if (opts.json) headers['Content-Type'] = 'application/json';
  const token = getToken();
  if (opts.auth && token) headers.Authorization = `Bearer ${token}`;
  return headers;
};

const extractError = async (response: Response) => {
  try {
    const data = await response.json();
    return (data && (data.detail || data.message)) || response.statusText;
  } catch {
    return response.statusText;
  }
};

async function fetchJson<T>(path: string, options: RequestInit = {}, auth = false): Promise<T> {
  const res = await withTimeout(fetch(buildUrl(path), {
    ...options,
    headers: {
      ...buildHeaders({ auth, json: options.body instanceof FormData ? false : true }),
      ...(options.headers as Record<string, string> | undefined)
    }
  }));

  if (!res.ok) {
    throw new Error(await extractError(res));
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ── Auth ─────────────────────────────────────────────
export const isAuthenticated = () => Boolean(getToken());

export const logout = () => {
  if (typeof localStorage !== 'undefined') {
    localStorage.removeItem('rforum_token');
  }
};

export async function login(email: string, password: string) {
  const form = new FormData();
  form.append('username', email);
  form.append('password', password);

  const res = await fetch(buildUrl('/auth/login'), {
    method: 'POST',
    body: form
  });

  if (!res.ok) {
    throw new Error(await extractError(res));
  }

  const data = await res.json();
  if (data?.access_token && typeof localStorage !== 'undefined') {
    localStorage.setItem('rforum_token', data.access_token);
  }
  return data;
}

export async function register(email: string, password: string) {
  return fetchJson('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password })
  });
}

// ── Sessions ─────────────────────────────────────────
export async function listSessions() {
  return fetchJson('/sessions', { method: 'GET' }, true);
}

export async function createSession(title: string) {
  return fetchJson('/sessions', {
    method: 'POST',
    body: JSON.stringify({ title })
  }, true);
}

export async function deleteSession(sessionId: string) {
  await fetchJson(`/sessions/${sessionId}`, { method: 'DELETE' }, true);
}

export async function getSession(sessionId: string) {
  return fetchJson(`/sessions/${sessionId}`, { method: 'GET' }, true);
}

export async function updateSession(sessionId: string, payload: Record<string, unknown>) {
  return fetchJson(`/sessions/${sessionId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  }, true);
}

// ── Slides ───────────────────────────────────────────
export async function createSlide(sessionId: string, payload: Record<string, unknown>) {
  return fetchJson(`/sessions/${sessionId}/slides`, {
    method: 'POST',
    body: JSON.stringify(payload)
  }, true);
}

export async function updateSlide(sessionId: string, slideId: string, payload: Record<string, unknown>) {
  return fetchJson(`/sessions/${sessionId}/slides/${slideId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  }, true);
}

export async function deleteSlide(sessionId: string, slideId: string) {
  await fetchJson(`/sessions/${sessionId}/slides/${slideId}`, { method: 'DELETE' }, true);
}

// ── Guest / Responses ────────────────────────────────
export async function joinSession(code: string) {
  const normalized = code?.toUpperCase();
  return fetchJson(`/sessions/join/${normalized}`, { method: 'GET' });
}

export async function listResponses(slideId: string) {
  return fetchJson(`/slides/${slideId}/responses/`, { method: 'GET' });
}

export async function submitResponse(
  slideId: string,
  value: string,
  guest_identifier: string,
  name?: string,
  rating?: number
) {
  return fetchJson(`/slides/${slideId}/responses/`, {
    method: 'POST',
    body: JSON.stringify({ value, guest_identifier, name, rating })
  });
}

export async function upvoteResponse(slideId: string, responseId: string) {
  return fetchJson(`/slides/${slideId}/responses/${responseId}/upvote`, {
    method: 'POST'
  });
}

// ── Utilities ─────────────────────────────────────────
export function resolveFileUrl(fileUrl?: string | null) {
  if (!fileUrl) return '';
  if (/^https?:\/\//i.test(fileUrl)) return fileUrl;
  const origin = API_ORIGIN || (typeof window !== 'undefined' ? window.location.origin : '');
  const trimmed = fileUrl.startsWith('/') ? fileUrl : `/${fileUrl}`;
  return `${origin}${trimmed}`;
}

/** Wrap a file URL in Google Docs Viewer for cross-device (especially mobile) PDF/PPT display */
export function getDocViewerUrl(fileUrl?: string | null) {
  const resolved = resolveFileUrl(fileUrl);
  if (!resolved) return '';
  return `https://docs.google.com/gview?url=${encodeURIComponent(resolved)}&embedded=true`;
}
