import { test, expect } from '@playwright/test';
import { registerAndLogin, createEvent, createSession, loginViaToken } from './fixtures';

test.describe('Sessions page search', () => {
  test('filters by title, moderator, and session code; supports clear and empty state', async ({ page, request }) => {
    const user = await registerAndLogin(request);
    const event = await createEvent(request, user.token, `E2E Search Event ${Date.now()}`);
    const one = await createSession(request, user.token, event.id, `E2E Keynote ${Date.now()}`, { moderator_name: 'Jordan Rivera' });
    const two = await createSession(request, user.token, event.id, `E2E Workshop ${Date.now()}`, { moderator_name: 'Casey Wong' });

    await loginViaToken(page, user.token);
    await page.goto('/dashboard/sessions');

    await expect(page.getByText(one.title)).toBeVisible();
    await expect(page.getByText(two.title)).toBeVisible();

    const search = page.getByLabel('Search sessions');
    await search.fill('Jordan');
    await page.waitForTimeout(400);

    await expect(page.getByText(one.title)).toBeVisible();
    await expect(page.getByText(two.title)).toHaveCount(0);

    await page.getByLabel('Clear search').click();
    await expect(search).toHaveValue('');

    // Search by session code (case-insensitive, partial match)
    await search.fill(two.unique_code.slice(0, 4).toLowerCase());
    await page.waitForTimeout(400);
    await expect(page.getByText(two.title)).toBeVisible();
    await expect(page.getByText(one.title)).toHaveCount(0);

    await search.fill('no-such-session-xyz');
    await page.waitForTimeout(400);
    await expect(page.getByText(/No sessions match/i)).toBeVisible();
  });
});
