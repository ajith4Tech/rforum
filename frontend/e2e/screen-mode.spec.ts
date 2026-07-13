import { test, expect } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
import {
  registerAndLogin, createEvent, createSession, setLive,
  uploadPresentation, getSessionPresentation, activateTimelineItem,
} from './fixtures';

const SAMPLE_PDF = path.join(__dirname, 'fixtures', 'sample.pdf');

test.describe('Screen (projector) view', () => {
  test('shows a waiting state before activation, then the active page', async ({ page, request }) => {
    const user = await registerAndLogin(request);
    const event = await createEvent(request, user.token, 'E2E Screen Event');
    const session = await createSession(request, user.token, event.id, 'E2E Screen Session');
    await uploadPresentation(request, user.token, session.id, SAMPLE_PDF);
    await setLive(request, user.token, session.id, true);

    await page.goto(`/screen/${session.unique_code}`);
    await expect(page.getByText(/Waiting for presenter/i)).toBeVisible({ timeout: 15000 });

    const withTimeline = await getSessionPresentation(request, user.token, session.id);
    const firstPageItem = withTimeline.timeline.items.find((i: any) => i.item_type === 'PAGE');
    await activateTimelineItem(request, user.token, session.id, firstPageItem.id);

    await expect(page.getByText(/Waiting for presenter/i)).toHaveCount(0, { timeout: 15000 });
    await expect(page.locator('img[alt="Page 1"]')).toBeVisible();
  });
});
