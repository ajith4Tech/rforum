import { test, expect } from '@playwright/test';
import { registerAndLogin, createEvent, createSession, loginViaToken } from './fixtures';

test.describe('Global search (navbar)', () => {
  test('shows grouped Events/Sessions results and Enter navigates to the highlighted one', async ({ page, request }) => {
    const user = await registerAndLogin(request);
    const event = await createEvent(request, user.token, `E2E Global Search Event ${Date.now()}`);
    const session = await createSession(request, user.token, event.id, `E2E Global Search Session ${Date.now()}`);

    await loginViaToken(page, user.token);
    await page.goto('/dashboard');

    await page.getByLabel('Search events and sessions').click();
    const input = page.getByPlaceholder('Search events and sessions…');
    await expect(input).toBeFocused();

    await input.fill(session.title);
    await page.waitForTimeout(400);

    await expect(page.getByText('Sessions', { exact: false })).toBeVisible();
    await expect(page.getByRole('button', { name: new RegExp(session.title) })).toBeVisible();

    // Enter opens the (only, auto-highlighted) result and navigates to its dashboard.
    await input.press('Enter');
    await page.waitForURL(new RegExp(`/dashboard/${session.id}`));
  });

  test('Esc closes the search overlay', async ({ page, request }) => {
    const user = await registerAndLogin(request);
    await loginViaToken(page, user.token);
    await page.goto('/dashboard');

    await page.getByLabel('Search events and sessions').click();
    const input = page.getByPlaceholder('Search events and sessions…');
    await expect(input).toBeVisible();
    await input.press('Escape');
    await expect(input).toHaveCount(0);
  });

  test('selecting an Event result deep-links to the Events page and highlights it', async ({ page, request }) => {
    const user = await registerAndLogin(request);
    const event = await createEvent(request, user.token, `E2E Global Event Nav ${Date.now()}`);

    await loginViaToken(page, user.token);
    await page.goto('/dashboard');

    await page.getByLabel('Search events and sessions').click();
    const input = page.getByPlaceholder('Search events and sessions…');
    await input.fill(event.title);
    await page.waitForTimeout(400);
    await page.getByRole('button', { name: new RegExp(event.title) }).click();

    await page.waitForURL(new RegExp(`/dashboard/events\\?event=${event.id}`));
    await expect(page.getByText(event.title)).toBeVisible();
  });
});
