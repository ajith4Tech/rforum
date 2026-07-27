import { test, expect } from '@playwright/test';
import { registerAndLogin, createEvent, createSession, createSlide, setLive, loginViaToken } from './fixtures';

const API_BASE = process.env.E2E_API_BASE || 'http://localhost:8000';

test.describe('Analytics', () => {
  test('event analytics KPIs render and the PDF report downloads without error', async ({ page, request }) => {
    const user = await registerAndLogin(request);
    const event = await createEvent(request, user.token, 'E2E Analytics Event');
    const session = await createSession(request, user.token, event.id, 'E2E Analytics Session');

    const slide = await createSlide(request, user.token, session.id, {
      type: 'POLL', order: 0, content_json: { question: 'Analytics Q', options: ['A', 'B'] },
    });
    await setLive(request, user.token, session.id, true);
    await request.patch(`${API_BASE}/api/sessions/${session.id}/slides/${slide.id}`, {
      headers: { Authorization: `Bearer ${user.token}` },
      data: { is_active: true },
    });
    await request.post(`${API_BASE}/api/slides/${slide.id}/responses/`, {
      data: { value: 'A', guest_identifier: 'e2e-guest-1' },
    });

    await loginViaToken(page, user.token);
    await page.goto(`/dashboard/analytics/${event.id}`);

    await expect(page.getByText('Sessions').first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('Responses').first()).toBeVisible();

    const downloadPromise = page.waitForEvent('download', { timeout: 30000 });
    // Exact match: the per-session row also has a "Download report for {title}"
    // button whose accessible name contains this substring, so a loose regex
    // here is ambiguous (strict-mode violation) even though both labels are
    // legitimately distinct for assistive tech.
    await page.getByRole('button', { name: 'Download Report', exact: true }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/\.pdf$/i);
  });
});
