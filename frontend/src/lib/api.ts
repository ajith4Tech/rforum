const API_BASE = (import.meta as any)?.env?.VITE_API_BASE || '/api';
const API_ORIGIN = (import.meta as any)?.env?.VITE_API_ORIGIN;
const DEFAULT_API_ORIGIN = typeof window !== 'undefined'
  ? `${window.location.protocol}//${window.location.hostname}:8001`
  : 'http://localhost:8001';

export function resolveFileUrl(path: string | undefined) {
  if (!path) return '';
  if (path.startsWith('http://') || path.startsWith('https://')) return path;
  const origin = API_ORIGIN || DEFAULT_API_ORIGIN;
  return `${origin}${path}`;
}

async function request(path: string, options: RequestInit = {}) {
  const token = typeof localStorage !== 'undefined' ? localStorage.getItem('rforum_token') : null;

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {})
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const origin = API_ORIGIN || '';
  const url = `${origin}${API_BASE}${path}`;
  const res = await fetch(url, { ...options, headers });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: 'Unknown error' }));
    console.error(`API Error: ${res.status} - ${body.detail || 'Unknown error'}`);
    throw new Error(body.detail || `HTTP ${res.status}`);
  }

  if (res.status === 204) return null;
  return res.json();
}

// ── Auth ──────────────────────────────────────────────
export async function register(email: string, password: string) {
  return request('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password })
  });
}

export async function login(email: string, password: string) {
  const formData = new URLSearchParams();
  formData.append('username', email);
  formData.append('password', password);

  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: formData
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: 'Login failed' }));
    throw new Error(body.detail);
  }

  const data = await res.json();
  localStorage.setItem('rforum_token', data.access_token);
  return data;
}

export function logout() {
  localStorage.removeItem('rforum_token');
}

export function isAuthenticated(): boolean {
  return typeof localStorage !== 'undefined' && !!localStorage.getItem('rforum_token');
}

// ── Sessions ──────────────────────────────────────────
export async function createSession(title: string) {
  return request('/sessions/', { method: 'POST', body: JSON.stringify({ title }) });
}

export async function listSessions() {
  return request('/sessions/');
}

export async function getSession(id: string) {
  return request(`/sessions/${id}`);
}

export async function updateSession(id: string, data: { title?: string; is_live?: boolean }) {
  return request(`/sessions/${id}`, { method: 'PATCH', body: JSON.stringify(data) });
}

export async function deleteSession(id: string) {
  return request(`/sessions/${id}`, { method: 'DELETE' });
}

export async function joinSession(code: string) {
  return request(`/sessions/join/${code}`);
}

// ── Slides ────────────────────────────────────────────
export async function createSlide(sessionId: string, data: { type: string; order?: number; content_json?: object }) {
  return request(`/sessions/${sessionId}/slides/`, { method: 'POST', body: JSON.stringify(data) });
}

export async function listSlides(sessionId: string) {
  return request(`/sessions/${sessionId}/slides/`);
}

export async function updateSlide(sessionId: string, slideId: string, data: object) {
  return request(`/sessions/${sessionId}/slides/${slideId}`, { method: 'PATCH', body: JSON.stringify(data) });
}

export async function deleteSlide(sessionId: string, slideId: string) {
  return request(`/sessions/${sessionId}/slides/${slideId}`, { method: 'DELETE' });
}

// ── Responses ─────────────────────────────────────────
export async function submitResponse(
  slideId: string,
  value: string,
  guestIdentifier: string,
  name?: string,
  rating?: number
) {
  return request(`/slides/${slideId}/responses/`, {
    method: 'POST',
    body: JSON.stringify({
      value,
      guest_identifier: guestIdentifier,
      name,
      rating
    })
  });
}

export async function listResponses(slideId: string) {
  return request(`/slides/${slideId}/responses/`);
}

export async function upvoteResponse(slideId: string, responseId: string) {
  return request(`/slides/${slideId}/responses/${responseId}/upvote`, { method: 'POST' });
}
