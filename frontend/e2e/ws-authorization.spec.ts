import { test, expect } from '@playwright/test';
import { registerAndLogin, createEvent, createSession, createSlide, setLive, loginViaToken } from './fixtures';

const API_BASE = process.env.E2E_API_BASE || 'http://localhost:8000';
const WS_BASE = API_BASE.replace(/^http/, 'ws');

test.describe('WebSocket moderator/guest/screen authorization', () => {
  test('an authorized moderator action (activating a slide) propagates live to guests', async ({ page, context, request }) => {
    const user = await registerAndLogin(request);
    const event = await createEvent(request, user.token, `E2E WS Event ${Date.now()}`);
    const session = await createSession(request, user.token, event.id, `E2E WS Session ${Date.now()}`);
    await createSlide(request, user.token, session.id, {
      type: 'POLL', order: 0, content_json: { question: 'First Poll Question', options: ['A', 'B'] },
    });
    await createSlide(request, user.token, session.id, {
      type: 'POLL', order: 1, content_json: { question: 'Second Poll Question', options: ['C', 'D'] },
    });
    await setLive(request, user.token, session.id, true);

    const guestPage = await context.newPage();
    await guestPage.goto(`/session/${session.unique_code}`);

    await loginViaToken(page, user.token);
    await page.goto(`/dashboard/${session.id}`);
    // This click fires the moderator dashboard's real ws.send('slide_change', ...) —
    // the same client-originated control event MODERATOR_ONLY_EVENTS now gates server-side.
    await page.getByRole('button', { name: 'Second Poll Question' }).click();

    await expect(guestPage.getByText('Second Poll Question')).toBeVisible({ timeout: 15000 });
  });

  test('an unauthenticated raw WebSocket cannot forge a slide_change for guests', async ({ page, context, request }) => {
    const user = await registerAndLogin(request);
    const event = await createEvent(request, user.token, `E2E WS Forge Event ${Date.now()}`);
    const session = await createSession(request, user.token, event.id, `E2E WS Forge Session ${Date.now()}`);
    const first = await createSlide(request, user.token, session.id, {
      type: 'POLL', order: 0, content_json: { question: 'Legit Poll Question', options: ['A', 'B'] },
    });
    await request.patch(`${API_BASE}/api/sessions/${session.id}/slides/${first.id}`, {
      headers: { Authorization: `Bearer ${user.token}` },
      data: { is_active: true },
    });
    await setLive(request, user.token, session.id, true);

    await page.goto(`/session/${session.unique_code}`);
    await expect(page.getByText('Legit Poll Question')).toBeVisible({ timeout: 15000 });

    // A second, fully unauthenticated tab opens a raw WebSocket to the session's join
    // code (no token, no role param -> plain guest) and tries to forge a control event.
    const attackerPage = await context.newPage();
    await attackerPage.goto('about:blank');
    const reply: any = await attackerPage.evaluate(async (wsUrl) => {
      return await new Promise((resolve) => {
        const ws = new WebSocket(wsUrl);
        ws.onopen = () => ws.send(JSON.stringify({
          event: 'slide_change',
          data: { slide_id: 'forged', slide: { content_json: { question: 'FORGED QUESTION' } }, activation: true },
        }));
        ws.onmessage = (e) => resolve(JSON.parse(e.data));
        setTimeout(() => resolve(null), 4000);
      });
    }, `${WS_BASE}/ws/${session.unique_code}`);

    expect(reply).toBeTruthy();
    expect(reply.event).toBe('error');

    // The real guest page never received the forged update.
    await page.waitForTimeout(1000);
    await expect(page.getByText('Legit Poll Question')).toBeVisible();
    await expect(page.getByText('FORGED QUESTION')).toHaveCount(0);
  });

  test('a screen (read-only) connection cannot send a session_update either', async ({ context, request }) => {
    const user = await registerAndLogin(request);
    const event = await createEvent(request, user.token, `E2E WS Screen Event ${Date.now()}`);
    const session = await createSession(request, user.token, event.id, `E2E WS Screen Session ${Date.now()}`);
    await setLive(request, user.token, session.id, true);

    const page = await context.newPage();
    await page.goto('about:blank');
    const reply: any = await page.evaluate(async (wsUrl) => {
      return await new Promise((resolve) => {
        const ws = new WebSocket(wsUrl);
        ws.onopen = () => ws.send(JSON.stringify({ event: 'session_update', data: { is_live: false } }));
        ws.onmessage = (e) => resolve(JSON.parse(e.data));
        setTimeout(() => resolve(null), 4000);
      });
    }, `${WS_BASE}/ws/${session.unique_code}?role=screen`);

    expect(reply).toBeTruthy();
    expect(reply.event).toBe('error');
  });
});
