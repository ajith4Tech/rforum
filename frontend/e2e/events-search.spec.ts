import { test, expect } from '@playwright/test';
import { registerAndLogin, createEvent, createSession, loginViaToken } from './fixtures';

test.describe('Events page search', () => {
  test('filters by title, description, and moderator; supports clear and empty state', async ({ page, request }) => {
    const user = await registerAndLogin(request);
    const alpha = await createEvent(request, user.token, `E2E Alpha Conference ${Date.now()}`);
    const beta = await createEvent(request, user.token, `E2E Beta Summit ${Date.now()}`);
    await createSession(request, user.token, alpha.id, 'Alpha Kickoff', { moderator_name: 'Priya Shah' });
    await createSession(request, user.token, beta.id, 'Beta Kickoff', { moderator_name: 'Sam Lee' });

    await loginViaToken(page, user.token);
    await page.goto('/dashboard/events');

    await expect(page.getByText(alpha.title)).toBeVisible();
    await expect(page.getByText(beta.title)).toBeVisible();

    const search = page.getByLabel('Search events');
    await search.fill('Priya');
    await page.waitForTimeout(400); // 250ms debounce

    await expect(page.getByText(alpha.title)).toBeVisible();
    await expect(page.getByText(beta.title)).toHaveCount(0);

    // Clear button resets to the full list
    await page.getByLabel('Clear search').click();
    await expect(search).toHaveValue('');
    await expect(page.getByText(beta.title)).toBeVisible();

    // No matches -> empty state
    await search.fill('no-such-event-xyz');
    await page.waitForTimeout(400);
    await expect(page.getByText(/No events match/i)).toBeVisible();

    // Esc clears the query
    await search.press('Escape');
    await expect(search).toHaveValue('');
    await expect(page.getByText(alpha.title)).toBeVisible();
  });
});
