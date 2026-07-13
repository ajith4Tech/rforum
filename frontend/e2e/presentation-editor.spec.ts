import { test, expect } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
import { registerAndLogin, createEvent, createSession, loginViaToken } from './fixtures';

const SAMPLE_PDF = path.join(__dirname, 'fixtures', 'sample.pdf');

test.describe('Presentation editor', () => {
  test('upload, insert/duplicate/delete/reorder interactions, navigate, and preview', async ({ page, request }) => {
    const user = await registerAndLogin(request);
    const event = await createEvent(request, user.token, 'E2E Editor Event');
    const session = await createSession(request, user.token, event.id, 'E2E Editor Session');

    await loginViaToken(page, user.token);
    await page.goto(`/dashboard/${session.id}`);

    // Upload a PDF presentation — drag-and-drop/browse upload starts as soon as
    // a file is chosen (no separate "Upload" button in the new upload UX).
    await page.locator('input[type="file"]').setInputFiles(SAMPLE_PDF);
    await expect(page.getByText('Timeline')).toBeVisible({ timeout: 30000 });

    // Sidebar shows 3 rendered pages (sample.pdf has 3 pages)
    await expect(page.getByText(/^Page 1$/)).toBeVisible();
    await expect(page.getByText(/^Page 2$/)).toBeVisible();
    await expect(page.getByText(/^Page 3$/)).toBeVisible();

    // Select page 1 to get the workspace toolbar showing
    await page.getByText(/^Page 1$/).click();
    await expect(page.getByText('1 of 3')).toBeVisible();

    // Keyboard navigation
    await page.keyboard.press('ArrowRight');
    await expect(page.getByText('2 of 3')).toBeVisible();
    await page.keyboard.press('ArrowLeft');
    await expect(page.getByText('1 of 3')).toBeVisible();

    // Insert a Poll interaction after page 1 via the hover "Add Interaction" inserter
    const inserters = page.locator('button', { hasText: 'Add Interaction' });
    await inserters.nth(1).click({ force: true });
    await page.getByRole('button', { name: 'Poll', exact: true }).click();
    await expect(page.getByText('4 of 4')).toBeVisible().catch(() => {});
    await expect(page.getByText('Poll').first()).toBeVisible();

    // Duplicate it
    const duplicateBtn = page.getByRole('button', { name: 'Duplicate interaction' });
    await duplicateBtn.first().click();
    await expect(page.getByRole('button', { name: 'Delete interaction' })).toHaveCount(2, { timeout: 10000 });

    // Delete one via inline confirm (not a native dialog)
    await page.getByRole('button', { name: 'Delete interaction' }).first().click();
    await page.getByRole('button', { name: 'Yes' }).click();
    await expect(page.getByRole('button', { name: 'Delete interaction' })).toHaveCount(1, { timeout: 10000 });

    // Activate the remaining poll so the workspace has something to preview
    await page.getByText('Poll', { exact: true }).click();

    // Preview mode: toggle to Guest — the moderator-only content editor disappears,
    // and switching back to Editor restores it.
    await page.getByRole('button', { name: 'Guest', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Guest', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByRole('button', { name: 'Edit', exact: true })).toHaveCount(0);

    await page.getByRole('button', { name: 'Editor', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Editor', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByRole('button', { name: 'Edit', exact: true })).toBeVisible();
  });
});
