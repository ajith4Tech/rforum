import type { APIRequestContext, Page } from '@playwright/test';
import { readFileSync } from 'fs';

const API_BASE = process.env.E2E_API_BASE || 'http://localhost:8000';
const INVITE_CODE = process.env.E2E_INVITE_CODE || 'BUILT201';

export interface TestUser {
  email: string;
  password: string;
  token: string;
}

/** Registers a fresh user (unique per test run) and returns a real JWT via /api/auth/login — no mocking. */
export async function registerAndLogin(request: APIRequestContext): Promise<TestUser> {
  const email = `e2e_${Date.now()}_${Math.floor(Math.random() * 1e6)}@example.com`;
  const password = 'E2ETestPass123';

  const reg = await request.post(`${API_BASE}/api/auth/register`, {
    data: { email, password, invite_code: INVITE_CODE },
  });
  if (!reg.ok()) throw new Error(`Register failed: ${reg.status()} ${await reg.text()}`);

  const login = await request.post(`${API_BASE}/api/auth/login`, {
    form: { username: email, password },
  });
  if (!login.ok()) throw new Error(`Login failed: ${login.status()} ${await login.text()}`);
  const { access_token } = await login.json();

  return { email, password, token: access_token };
}

export async function createEvent(request: APIRequestContext, token: string, title: string) {
  const res = await request.post(`${API_BASE}/api/events/`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { title, event_date: new Date().toISOString().slice(0, 10) },
  });
  if (!res.ok()) throw new Error(`Create event failed: ${res.status()} ${await res.text()}`);
  return res.json();
}

export async function createSession(
  request: APIRequestContext, token: string, eventId: string, title: string,
  extra: Record<string, unknown> = {}
) {
  const res = await request.post(`${API_BASE}/api/sessions/`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { title, event_id: eventId, ...extra },
  });
  if (!res.ok()) throw new Error(`Create session failed: ${res.status()} ${await res.text()}`);
  return res.json();
}

export async function setLive(request: APIRequestContext, token: string, sessionId: string, isLive: boolean) {
  const res = await request.patch(`${API_BASE}/api/sessions/${sessionId}`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { is_live: isLive },
  });
  if (!res.ok()) throw new Error(`Set live failed: ${res.status()} ${await res.text()}`);
  return res.json();
}

export async function createSlide(request: APIRequestContext, token: string, sessionId: string, payload: Record<string, unknown>) {
  const res = await request.post(`${API_BASE}/api/sessions/${sessionId}/slides/`, {
    headers: { Authorization: `Bearer ${token}` },
    data: payload,
  });
  if (!res.ok()) throw new Error(`Create slide failed: ${res.status()} ${await res.text()}`);
  return res.json();
}

export async function uploadPresentation(request: APIRequestContext, token: string, sessionId: string, filePath: string) {
  const res = await request.post(`${API_BASE}/api/sessions/${sessionId}/presentation/upload`, {
    headers: { Authorization: `Bearer ${token}` },
    multipart: { file: { name: filePath.split('/').pop()!, mimeType: 'application/pdf', buffer: readFileSync(filePath) } },
  });
  if (!res.ok()) throw new Error(`Upload presentation failed: ${res.status()} ${await res.text()}`);
  return res.json();
}

export async function insertTimelineItem(
  request: APIRequestContext,
  token: string,
  sessionId: string,
  itemType: string,
  position: number,
  contentJson: Record<string, unknown> = {}
) {
  const res = await request.post(`${API_BASE}/api/sessions/${sessionId}/presentation/timeline/items`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { item_type: itemType, position, content_json: contentJson },
  });
  if (!res.ok()) throw new Error(`Insert timeline item failed: ${res.status()} ${await res.text()}`);
  return res.json();
}

export async function activateTimelineItem(request: APIRequestContext, token: string, sessionId: string, itemId: string) {
  const res = await request.post(`${API_BASE}/api/sessions/${sessionId}/presentation/timeline/activate/${itemId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok()) throw new Error(`Activate timeline item failed: ${res.status()} ${await res.text()}`);
  return res.json();
}

export async function getSessionPresentation(request: APIRequestContext, token: string, sessionId: string) {
  const res = await request.get(`${API_BASE}/api/sessions/${sessionId}/presentation`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok()) throw new Error(`Get session presentation failed: ${res.status()} ${await res.text()}`);
  return res.json();
}

export async function attachPresentationApi(
  request: APIRequestContext, token: string, sessionId: string, presentationId: string
) {
  const res = await request.post(`${API_BASE}/api/sessions/${sessionId}/presentation/attach/${presentationId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok()) throw new Error(`Attach presentation failed: ${res.status()} ${await res.text()}`);
  return res.json();
}

export async function detachPresentationApi(request: APIRequestContext, token: string, sessionId: string) {
  const res = await request.post(`${API_BASE}/api/sessions/${sessionId}/presentation/detach`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok()) throw new Error(`Detach presentation failed: ${res.status()} ${await res.text()}`);
}

export async function deletePresentationApi(request: APIRequestContext, token: string, presentationId: string) {
  const res = await request.delete(`${API_BASE}/api/presentations/${presentationId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok()) throw new Error(`Delete presentation failed: ${res.status()} ${await res.text()}`);
}

export async function listPresentationsApi(
  request: APIRequestContext, token: string, opts: { eventId?: string; search?: string; sort?: string } = {}
) {
  const params = new URLSearchParams();
  if (opts.eventId) params.set('event_id', opts.eventId);
  if (opts.search) params.set('search', opts.search);
  if (opts.sort) params.set('sort', opts.sort);
  const qs = params.toString();
  const res = await request.get(`${API_BASE}/api/presentations${qs ? `?${qs}` : ''}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok()) throw new Error(`List presentations failed: ${res.status()} ${await res.text()}`);
  return res.json();
}

/** Logs a browser context in the way a real user would (fills the login form), rather than injecting a token — used by tests that need a fully realistic session. */
export async function loginViaUI(page: Page, email: string, password: string) {
  await page.goto('/login');
  await page.getByPlaceholder('Email').fill(email);
  await page.getByPlaceholder('Password').fill(password);
  await page.getByRole('button', { name: 'Log in' }).click();
  await page.waitForURL(/\/dashboard/);
}

/** Injects a token directly into localStorage — faster than the UI form for tests that aren't specifically testing login itself. */
export async function loginViaToken(page: Page, token: string) {
  await page.goto('/login');
  await page.evaluate((t) => localStorage.setItem('rforum_token', t), token);
}
