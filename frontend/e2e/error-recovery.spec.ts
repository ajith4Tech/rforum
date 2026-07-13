import { test, expect } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
import { registerAndLogin, createEvent, createSession, loginViaToken } from './fixtures';

const CORRUPTED_PDF = path.join(__dirname, 'fixtures', 'corrupted.pdf');
const SAMPLE_PDF = path.join(__dirname, 'fixtures', 'sample.pdf');

test.describe('Error recovery', () => {
  test('uploading an unrenderable file surfaces an error instead of a blank/broken editor', async ({ page, request }) => {
    const user = await registerAndLogin(request);
    const event = await createEvent(request, user.token, 'E2E Error Event');
    const session = await createSession(request, user.token, event.id, 'E2E Error Session');

    await loginViaToken(page, user.token);
    await page.goto(`/dashboard/${session.id}`);

    await page.locator('input[type="file"]').setInputFiles(CORRUPTED_PDF);

    await expect(page.getByText('Upload failed')).toBeVisible({ timeout: 20000 });
    await expect(page.getByText(/could not render any pages/i)).toBeVisible();

    // The page must still be usable afterwards — not stuck behind a dead-end,
    // page-level error card. Choosing a different, good file and retrying must work.
    await expect(page.getByRole('heading', { name: /error loading|failed to load/i })).toHaveCount(0);
    await page.getByRole('button', { name: 'Choose a different file' }).click();
    await page.locator('input[type="file"]').setInputFiles(SAMPLE_PDF);
    await expect(page.getByText('Timeline')).toBeVisible({ timeout: 20000 });
  });

  test('joining a code that does not exist shows a clear message, not a blank page', async ({ page }) => {
    await page.goto('/session/ZZZZ-0000');
    await expect(page.getByText(/not found|not live/i)).toBeVisible({ timeout: 15000 });
  });
});
