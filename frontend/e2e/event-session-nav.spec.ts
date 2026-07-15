import { test, expect } from '@playwright/test';
import { registerAndLogin, createEvent, createSession, loginViaToken } from './fixtures';

test.describe('Event -> Session navigation', () => {
  test('Events page shows session count and lets you open a session or its analytics directly', async ({ page, request }) => {
    const user = await registerAndLogin(request);
    const event = await createEvent(request, user.token, `E2E Nav Event ${Date.now()}`);
    const session = await createSession(request, user.token, event.id, `E2E Nav Session ${Date.now()}`);
    // setEventSessions links happen automatically on createSession via event_id, but the
    // Events page reads the link from GET /events' nested `sessions`, so no extra call needed.

    await loginViaToken(page, user.token);
    await page.goto('/dashboard/events');

    const card = page.locator(`#event-${event.id}`);
    await expect(card).toBeVisible();
    await expect(card.getByText(`Sessions (1)`)).toBeVisible();
    await expect(card.getByText(session.title)).toBeVisible();

    // "Open Session" -> the session's moderator dashboard, without visiting the Sessions page.
    const [openPage] = await Promise.all([
      page.waitForEvent('popup').catch(() => null),
      card.getByRole('link', { name: 'Open Session' }).click(),
    ]);
    const target = openPage ?? page;
    await target.waitForURL(new RegExp(`/dashboard/${session.id}$`));
  });

  test('"Edit Session" deep-links to the Sessions page with that session\'s inline editor open', async ({ page, request }) => {
    const user = await registerAndLogin(request);
    const event = await createEvent(request, user.token, `E2E Nav Edit Event ${Date.now()}`);
    const session = await createSession(request, user.token, event.id, `E2E Nav Edit Session ${Date.now()}`);

    await loginViaToken(page, user.token);
    await page.goto('/dashboard/events');

    const card = page.locator(`#event-${event.id}`);
    await card.getByRole('link', { name: 'Edit Session' }).click();

    await page.waitForURL(new RegExp(`/dashboard/sessions\\?edit=${session.id}`));
    await expect(page.getByLabel('Title').or(page.locator(`#session-${session.id}`))).toBeVisible();
    // Inline edit form is open: a Save button is visible for this session's card.
    await expect(page.locator(`#session-${session.id}`).getByRole('button', { name: /Save/i })).toBeVisible();
  });

  test('"Analytics" from an Event card links to the nested per-session analytics route', async ({ page, request }) => {
    const user = await registerAndLogin(request);
    const event = await createEvent(request, user.token, `E2E Nav Analytics Event ${Date.now()}`);
    const session = await createSession(request, user.token, event.id, `E2E Nav Analytics Session ${Date.now()}`);

    await loginViaToken(page, user.token);
    await page.goto('/dashboard/events');

    const card = page.locator(`#event-${event.id}`);
    await card.getByRole('link', { name: 'Analytics' }).click();
    await page.waitForURL(new RegExp(`/dashboard/analytics/${event.id}/${session.id}`));
  });
});
