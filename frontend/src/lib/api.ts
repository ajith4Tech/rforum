import { token as tokenStore } from './stores';

const API_PREFIX = '/api';
const DEFAULT_API_PORT = '8000';

export interface PaginatedResult<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface ListParams {
  limit?: number;
  offset?: number;
  search?: string;
}

function buildListQuery(params: ListParams = {}): string {
  const q = new URLSearchParams();
  if (params.limit !== undefined) q.set('limit', String(params.limit));
  if (params.offset !== undefined) q.set('offset', String(params.offset));
  if (params.search) q.set('search', params.search);
  const s = q.toString();
  return s ? `?${s}` : '';
}

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
  tokenStore.set(null);
};

export async function changePassword(currentPassword: string, newPassword: string) {
  return fetchJson('/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword })
  }, true);
}

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
  if (data?.access_token) {
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem('rforum_token', data.access_token);
    }
    tokenStore.set(data.access_token);
  }
  return data;
}

export async function register(email: string, password: string, inviteCode: string) {
  return fetchJson('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password, invite_code: inviteCode })
  });
}

// ── Sessions ─────────────────────────────────────────
export async function listSessions(params: ListParams = {}): Promise<PaginatedResult<any>> {
  return fetchJson(`/sessions${buildListQuery(params)}`, { method: 'GET' }, true);
}

export async function createSession(
  title: string,
  eventId: string,
  moderatorName?: string | null,
  speakerNames: string[] = []
) {
  return fetchJson('/sessions', {
    method: 'POST',
    body: JSON.stringify({
      title,
      event_id: eventId,
      moderator_name: moderatorName ?? null,
      speaker_names: speakerNames
    })
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

export async function startSession(sessionId: string) {
  return updateSession(sessionId, { is_live: true });
}

// ── Events ───────────────────────────────────────────
export async function listEvents(params: ListParams = {}): Promise<PaginatedResult<any>> {
  return fetchJson(`/events${buildListQuery(params)}`, { method: 'GET' }, true);
}

export async function listPublicEvents(date?: string) {
  const query = date ? `?event_date=${encodeURIComponent(date)}` : '';
  return fetchJson(`/events/public${query}`, { method: 'GET' });
}

export async function listUpcomingPublicEvents() {
  return fetchJson('/events/public?upcoming=true', { method: 'GET' });
}

export async function createEvent(payload: Record<string, unknown>) {
  return fetchJson('/events', {
    method: 'POST',
    body: JSON.stringify(payload)
  }, true);
}

export async function updateEvent(eventId: string, payload: Record<string, unknown>) {
  return fetchJson(`/events/${eventId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  }, true);
}

export async function deleteEvent(eventId: string) {
  await fetchJson(`/events/${eventId}`, { method: 'DELETE' }, true);
}

export async function setEventSessions(eventId: string, session_ids: string[]) {
  return fetchJson(`/events/${eventId}/sessions`, {
    method: 'PUT',
    body: JSON.stringify({ session_ids })
  }, true);
}

// ── Public Events ───────────────────────────────────
export async function getTodayEvent() {
  return fetchJson('/events/public/today', { method: 'GET' });
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

export async function listSlides(sessionId: string): Promise<any[]> {
  return fetchJson(`/sessions/${sessionId}/slides`, { method: 'GET' }, true);
}

export async function uploadSlideFile(sessionId: string, slideId: string, file: File): Promise<any> {
  const form = new FormData();
  form.append('file', file);
  const token = getToken();
  const res = await withTimeout(fetch(buildUrl(`/sessions/${sessionId}/slides/${slideId}/upload`), {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  }));
  if (!res.ok) throw new Error(await extractError(res));
  return res.json();
}

// ── Guest / Responses ────────────────────────────────
export async function joinSession(code: string) {
  const normalized = code?.toUpperCase();
  return fetchJson(`/sessions/join/${normalized}`, { method: 'GET' });
}

export async function getSessionByCode(code: string) {
  const normalized = code?.toUpperCase();
  return fetchJson(`/sessions/code/${normalized}`, { method: 'GET' }, true);
}

export async function listResponses(slideId: string) {
  // auth=true attaches our JWT when we have one (moderator dashboard, needs
  // responses regardless of live status) but is a no-op for guests/screens.
  return fetchJson(`/slides/${slideId}/responses/`, { method: 'GET' }, true);
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

export async function clearResponses(slideId: string) {
  return fetchJson(`/slides/${slideId}/responses/`, {
    method: 'DELETE'
  }, true);
}

// ── Analytics ─────────────────────────────────────────
export async function getAnalytics() {
  return fetchJson('/analytics', { method: 'GET' }, true);
}

export async function exportEventAnalytics(eventId: string, format = 'csv') {
  const token = getToken();
  const url = buildUrl(`/analytics/event/${eventId}/download?format=${encodeURIComponent(format)}`);
  const res = await withTimeout(fetch(url, { method: 'GET', headers: token ? { Authorization: `Bearer ${token}` } : {} }));
  if (!res.ok) throw new Error(await extractError(res));
  return res;
}

export async function exportSessionAnalytics(sessionId: string, format = 'csv') {
  const token = getToken();
  const url = buildUrl(`/analytics/session/${sessionId}/download?format=${encodeURIComponent(format)}`);
  const res = await withTimeout(fetch(url, { method: 'GET', headers: token ? { Authorization: `Bearer ${token}` } : {} }));
  if (!res.ok) throw new Error(await extractError(res));
  return res;
}

// ── Current user ───────────────────────────────────────
export async function getMe() {
  return fetchJson('/auth/me', { method: 'GET' }, true);
}

// ── Admin – User Management ────────────────────────────
export async function adminListUsers() {
  return fetchJson('/admin/users', { method: 'GET' }, true);
}

export async function adminDeleteUser(userId: string) {
  await fetchJson(`/admin/users/${userId}`, { method: 'DELETE' }, true);
}

export async function adminUpdateUserRole(userId: string, role: string) {
  return fetchJson(`/admin/users/${userId}/role`, {
    method: 'PATCH',
    body: JSON.stringify({ role })
  }, true);
}

export async function adminToggleUserActive(userId: string, is_active: boolean) {
  return fetchJson(`/admin/users/${userId}/active`, {
    method: 'PATCH',
    body: JSON.stringify({ is_active })
  }, true);
}

// ── Admin – Session / Event Moderation ─────────────────
export async function adminListSessions() {
  return fetchJson('/admin/sessions', { method: 'GET' }, true);
}

export async function adminDeleteSession(sessionId: string) {
  await fetchJson(`/admin/sessions/${sessionId}`, { method: 'DELETE' }, true);
}

export async function adminListEvents() {
  return fetchJson('/admin/events', { method: 'GET' }, true);
}

export async function adminDeleteEvent(eventId: string) {
  await fetchJson(`/admin/events/${eventId}`, { method: 'DELETE' }, true);
}

// ── Session Assets ─────────────────────────────────────
export async function listAssets(): Promise<any[]> {
  return fetchJson('/assets', { method: 'GET' }, true) as Promise<any[]>;
}

export async function getStorageUsage(): Promise<{ user_id: string; total_bytes: number; asset_count: number }> {
  return fetchJson('/assets/storage', { method: 'GET' }, true) as any;
}

export async function replaceAssetFile(assetId: string, file: File): Promise<any> {
  const form = new FormData();
  form.append('file', file);
  const token = getToken();
  const res = await withTimeout(fetch(buildUrl(`/assets/${assetId}/file`), {
    method: 'PUT',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  }));
  if (!res.ok) throw new Error(await extractError(res));
  return res.json();
}

export async function deleteAsset(assetId: string): Promise<void> {
  await fetchJson(`/assets/${assetId}`, { method: 'DELETE' }, true);
}

export async function adminGetStorage(): Promise<{
  total_bytes: number;
  asset_count: number;
  top_users: { user_id: string; email: string; total_bytes: number; asset_count: number }[];
}> {
  return fetchJson('/admin/storage', { method: 'GET' }, true) as any;
}

// ── Organization Settings / Branding ───────────────────
export interface OrgSettingsAdmin {
  display_name: string;
  logo_url: string;
  favicon_url: string;
  updated_at: string;
  has_custom_logo: boolean;
  has_custom_favicon: boolean;
}

// logo_url/favicon_url come back as backend-relative paths (e.g.
// "/api/branding/logo") — resolveFileUrl (defined below) makes them
// absolute against API_ORIGIN, same as every other asset URL in this file,
// so they resolve correctly even when the frontend dev server runs on a
// different port than the backend.
function withAbsoluteBrandingUrls<T extends { logo_url: string; favicon_url: string }>(data: T): T {
  return { ...data, logo_url: resolveFileUrl(data.logo_url), favicon_url: resolveFileUrl(data.favicon_url) };
}

export async function getOrgSettings(): Promise<import('./stores').OrgSettingsPublic> {
  const data = await fetchJson<import('./stores').OrgSettingsPublic>('/settings/org', { method: 'GET' });
  return withAbsoluteBrandingUrls(data);
}

export async function adminGetOrgSettings(): Promise<OrgSettingsAdmin> {
  const data = await fetchJson<OrgSettingsAdmin>('/admin/settings/org', { method: 'GET' }, true);
  return withAbsoluteBrandingUrls(data);
}

export async function adminUpdateOrgDisplayName(displayName: string): Promise<OrgSettingsAdmin> {
  const data = await fetchJson<OrgSettingsAdmin>('/admin/settings/org', {
    method: 'PATCH',
    body: JSON.stringify({ display_name: displayName })
  }, true);
  return withAbsoluteBrandingUrls(data);
}

async function uploadOrgBrandingFile(path: string, file: File): Promise<OrgSettingsAdmin> {
  const form = new FormData();
  form.append('file', file);
  const token = getToken();
  const res = await withTimeout(fetch(buildUrl(path), {
    method: 'PUT',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  }));
  if (!res.ok) throw new Error(await extractError(res));
  return withAbsoluteBrandingUrls(await res.json());
}

export async function adminUploadOrgLogo(file: File): Promise<OrgSettingsAdmin> {
  return uploadOrgBrandingFile('/admin/settings/org/logo', file);
}

export async function adminDeleteOrgLogo(): Promise<OrgSettingsAdmin> {
  const data = await fetchJson<OrgSettingsAdmin>('/admin/settings/org/logo', { method: 'DELETE' }, true);
  return withAbsoluteBrandingUrls(data);
}

export async function adminUploadOrgFavicon(file: File): Promise<OrgSettingsAdmin> {
  return uploadOrgBrandingFile('/admin/settings/org/favicon', file);
}

export async function adminDeleteOrgFavicon(): Promise<OrgSettingsAdmin> {
  const data = await fetchJson<OrgSettingsAdmin>('/admin/settings/org/favicon', { method: 'DELETE' }, true);
  return withAbsoluteBrandingUrls(data);
}

// ── Utilities ─────────────────────────────────────────
export function formatBytes(bytes: number): string {
  if (bytes <= 0) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}
export function resolveFileUrl(fileUrl?: string | null) {
  if (!fileUrl) return '';
  if (/^https?:\/\//i.test(fileUrl)) return fileUrl;
  const origin = API_ORIGIN || (typeof window !== 'undefined' ? window.location.origin : '');
  const trimmed = fileUrl.startsWith('/') ? fileUrl : `/${fileUrl}`;
  return `${origin}${trimmed}`;
}

/** Build the URL for a single rendered page image from the backend */
export function getPageImageUrl(sessionId: string, slideId: string, page: number, sessionCode?: string) {
  return withAssetAuth(buildUrl(`/sessions/${sessionId}/slides/${slideId}/page/${page}`), sessionCode);
}

// ── Presentations / Timeline ──────────────────────────
// Presentation-first sessions (session.presentation_id set) are managed through
// these endpoints instead of the legacy Slide CRUD above.

async function uploadPresentationFile(path: string, file: File): Promise<any> {
  const form = new FormData();
  form.append('file', file);
  const token = getToken();
  const res = await withTimeout(fetch(buildUrl(path), {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  }), 60000);
  if (!res.ok) throw new Error(await extractError(res));
  return res.json();
}

export async function getSessionPresentation(sessionId: string): Promise<any> {
  return fetchJson(`/sessions/${sessionId}/presentation`, { method: 'GET' }, true);
}

export async function uploadPresentation(sessionId: string, file: File): Promise<any> {
  return uploadPresentationFile(`/sessions/${sessionId}/presentation/upload`, file);
}

export async function replacePresentation(sessionId: string, file: File): Promise<any> {
  return uploadPresentationFile(`/sessions/${sessionId}/presentation/replace`, file);
}

export async function regeneratePresentation(sessionId: string): Promise<any> {
  return fetchJson(`/sessions/${sessionId}/presentation/regenerate`, { method: 'POST' }, true);
}

export async function insertTimelineItem(
  sessionId: string,
  itemType: 'POLL' | 'QNA' | 'WORD_CLOUD' | 'FEEDBACK' | 'RATING',
  position: number,
  contentJson: Record<string, unknown> = {}
): Promise<any> {
  return fetchJson(`/sessions/${sessionId}/presentation/timeline/items`, {
    method: 'POST',
    body: JSON.stringify({ item_type: itemType, position, content_json: contentJson })
  }, true);
}

export async function updateTimelineItem(
  sessionId: string,
  itemId: string,
  contentJson: Record<string, unknown>
): Promise<any> {
  return fetchJson(`/sessions/${sessionId}/presentation/timeline/items/${itemId}`, {
    method: 'PATCH',
    body: JSON.stringify({ content_json: contentJson })
  }, true);
}

export async function deleteTimelineItem(sessionId: string, itemId: string): Promise<void> {
  await fetchJson(`/sessions/${sessionId}/presentation/timeline/items/${itemId}`, { method: 'DELETE' }, true);
}

export async function reorderTimelineItems(sessionId: string, itemIds: string[]): Promise<any> {
  return fetchJson(`/sessions/${sessionId}/presentation/timeline/items/reorder`, {
    method: 'POST',
    body: JSON.stringify({ item_ids: itemIds })
  }, true);
}

export async function activateTimelineItem(sessionId: string, itemId: string): Promise<any> {
  return fetchJson(`/sessions/${sessionId}/presentation/timeline/activate/${itemId}`, { method: 'POST' }, true);
}

/**
 * Appends whatever access proof is available for an otherwise-unauthenticated
 * asset URL: our own JWT if we're logged in (moderator previewing their own
 * library), otherwise the session's join code if the caller has one (guest/
 * screen viewing a live session's attached presentation).
 */
const withAssetAuth = (url: string, sessionCode?: string) => {
  const params = new URLSearchParams();
  const token = getToken();
  if (token) params.set('token', token);
  else if (sessionCode) params.set('code', sessionCode);
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
};

/** Build the URL for a full-resolution rendered presentation page. */
export function getPresentationPageImageUrl(presentationId: string, pageNumber: number, sessionCode?: string) {
  return withAssetAuth(buildUrl(`/presentations/${presentationId}/pages/${pageNumber}/image`), sessionCode);
}

/** Build the URL for a small pre-rendered presentation page thumbnail. */
export function getPresentationPageThumbnailUrl(presentationId: string, pageNumber: number, sessionCode?: string) {
  return withAssetAuth(buildUrl(`/presentations/${presentationId}/pages/${pageNumber}/thumbnail`), sessionCode);
}

// ── Reusable-presentation lifecycle: details, picker, attach/detach, delete ──

export async function getPresentationDetails(presentationId: string): Promise<any> {
  return fetchJson(`/presentations/${presentationId}/details`, { method: 'GET' }, true);
}

export async function listPresentations(
  opts: { eventId?: string; search?: string; sort?: 'recent' | 'last_used' | 'name' } = {}
): Promise<any[]> {
  const params = new URLSearchParams();
  if (opts.eventId) params.set('event_id', opts.eventId);
  if (opts.search) params.set('search', opts.search);
  if (opts.sort) params.set('sort', opts.sort);
  const qs = params.toString();
  return fetchJson(`/presentations${qs ? `?${qs}` : ''}`, { method: 'GET' }, true);
}

export async function attachPresentation(sessionId: string, presentationId: string): Promise<any> {
  return fetchJson(`/sessions/${sessionId}/presentation/attach/${presentationId}`, { method: 'POST' }, true);
}

export async function detachPresentation(sessionId: string): Promise<void> {
  await fetchJson(`/sessions/${sessionId}/presentation/detach`, { method: 'POST' }, true);
}

export async function deletePresentation(presentationId: string): Promise<void> {
  await fetchJson(`/presentations/${presentationId}`, { method: 'DELETE' }, true);
}

export async function downloadPresentationOriginal(presentationId: string, fileName: string): Promise<void> {
  const token = getToken();
  const res = await withTimeout(fetch(buildUrl(`/presentations/${presentationId}/download`), {
    method: 'GET',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  }));
  if (!res.ok) throw new Error(await extractError(res));
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
