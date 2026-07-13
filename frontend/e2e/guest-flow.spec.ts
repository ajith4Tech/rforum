import { test, expect } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
import {
  registerAndLogin, createEvent, createSession, setLive,
  uploadPresentation, insertTimelineItem, activateTimelineItem, getSessionPresentation,
} from './fixtures';

const SAMPLE_PDF = path.join(__dirname, 'fixtures', 'sample.pdf');

test.describe('Guest experience (presentation session)', () => {
  test('guest sees the active page, then votes on a poll and the vote survives a refresh', async ({ page, request }) => {
    const user = await registerAndLogin(request);
    const event = await createEvent(request, user.token, 'E2E Guest Event');
    const session = await createSession(request, user.token, event.id, 'E2E Guest Session');
    await uploadPresentation(request, user.token, session.id, SAMPLE_PDF);

    const withTimeline = await getSessionPresentation(request, user.token, session.id);
    const firstPageItem = withTimeline.timeline.items.find((i: any) => i.item_type === 'PAGE');
    await activateTimelineItem(request, user.token, session.id, firstPageItem.id);
    await setLive(request, user.token, session.id, true);

    await page.goto(`/session/${session.unique_code}`);
    await expect(page.getByText(/Page 1/)).toBeVisible({ timeout: 15000 });

    // Insert and activate a poll, then have the guest vote
    const poll = await insertTimelineItem(request, user.token, session.id, 'POLL', 1, {
      question: 'Pick one', options: ['Alpha', 'Beta'],
    });
    await activateTimelineItem(request, user.token, session.id, poll.id);

    await expect(page.getByText('Pick one')).toBeVisible({ timeout: 15000 });
    await page.getByRole('button', { name: 'Alpha' }).click();
    await expect(page.getByText('Vote submitted!')).toBeVisible();
    await expect(page.getByText('You chose: Alpha')).toBeVisible();

    // Refresh — the previously-submitted vote must not resurface a fresh voting form
    await page.reload();
    await expect(page.getByText('Vote submitted!')).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('You chose: Alpha')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Beta' })).toHaveCount(0);
  });
});
