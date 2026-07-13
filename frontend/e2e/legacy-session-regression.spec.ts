import { test, expect } from '@playwright/test';
import { registerAndLogin, createEvent, createSession, createSlide, setLive, loginViaToken } from './fixtures';

const API_BASE = process.env.E2E_API_BASE || 'http://localhost:8000';

/**
 * Guards the legacy (non-presentation) slide-list flow — every route/component this
 * exercises (Sidebar.svelte, SlideCard.svelte, the {:else} branch in session/[code] and
 * screen/[code]) is untouched by the Presentation-first hardening work. If this ever
 * fails, something intended to be additive-only has regressed a pre-existing flow.
 */
test.describe('Legacy slide-only session (regression)', () => {
  test('a session with no presentation still serves the classic poll flow to guests', async ({ page, request }) => {
    const user = await registerAndLogin(request);
    const event = await createEvent(request, user.token, 'E2E Legacy Event');
    const session = await createSession(request, user.token, event.id, 'E2E Legacy Session');
    expect(session.presentation_id).toBeNull();

    const slide = await createSlide(request, user.token, session.id, {
      type: 'POLL', order: 0, content_json: { question: 'Legacy poll question', options: ['Red', 'Blue'] },
    });
    await request.patch(`${API_BASE}/api/sessions/${session.id}/slides/${slide.id}`, {
      headers: { Authorization: `Bearer ${user.token}` },
      data: { is_active: true },
    });
    await setLive(request, user.token, session.id, true);

    await page.goto(`/session/${session.unique_code}`);
    await expect(page.getByText('Legacy poll question')).toBeVisible({ timeout: 15000 });
    await page.getByRole('button', { name: 'Red' }).click();
    await expect(page.getByText('Vote submitted!')).toBeVisible();
    await expect(page.getByText('You chose: Red')).toBeVisible();
  });

  test('the moderator dashboard for a legacy session still shows the classic slide editor, unaffected by the new Presentation upload card', async ({ page, request }) => {
    const user = await registerAndLogin(request);
    const event = await createEvent(request, user.token, 'E2E Legacy Dashboard Event');
    const session = await createSession(request, user.token, event.id, 'E2E Legacy Dashboard Session');
    await createSlide(request, user.token, session.id, {
      type: 'POLL', order: 0, content_json: { question: 'Legacy dashboard question', options: ['Yes', 'No'] },
    });

    await loginViaToken(page, user.token);
    await page.goto(`/dashboard/${session.id}`);

    // The new Presentation upload card stacks above the legacy slide editor —
    // both must render; the legacy "Add slide" grid must be untouched by it.
    await expect(page.getByText('Drag & drop a file here, or click to browse')).toBeVisible();
    await expect(page.getByText('Add slide')).toBeVisible();
    await expect(page.getByText('Legacy dashboard question')).toBeVisible();
  });
});
