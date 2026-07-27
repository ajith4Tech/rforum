import { test, expect } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
import {
  registerAndLogin, createEvent, createSession, loginViaToken,
  uploadPresentation, detachPresentationApi
} from './fixtures';

const SAMPLE_PDF = path.join(__dirname, 'fixtures', 'sample.pdf');
const SAMPLE_PPTX = path.join(__dirname, 'fixtures', 'sample.pptx');
const CORRUPTED_PDF = path.join(__dirname, 'fixtures', 'corrupted.pdf');

test.describe('Presentation reuse & lifecycle', () => {
  test('uploading the same file twice reuses the existing presentation instead of reconverting', async ({ page, request }) => {
    const user = await registerAndLogin(request);
    const event = await createEvent(request, user.token, 'E2E Reuse Event');
    const sessionA = await createSession(request, user.token, event.id, 'E2E Reuse Session A');
    const sessionB = await createSession(request, user.token, event.id, 'E2E Reuse Session B');

    // Seed session A via the API — the interesting behavior under test is B's upload.
    await uploadPresentation(request, user.token, sessionA.id, SAMPLE_PDF);

    await loginViaToken(page, user.token);
    await page.goto(`/dashboard/${sessionB.id}`);

    await page.locator('input[type="file"]').setInputFiles(SAMPLE_PDF);
    await expect(page.getByText('This presentation already exists. Reusing existing assets.')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText(/Ready — 3 slides?/)).toBeVisible();

    // After the brief "Ready" beat, the full workspace takes over.
    await expect(page.getByText('Timeline')).toBeVisible({ timeout: 5000 });
  });

  test('replace requires confirmation and swaps the deck', async ({ page, request }) => {
    const user = await registerAndLogin(request);
    const event = await createEvent(request, user.token, 'E2E Replace Event');
    const session = await createSession(request, user.token, event.id, 'E2E Replace Session');
    await uploadPresentation(request, user.token, session.id, SAMPLE_PDF);

    await loginViaToken(page, user.token);
    await page.goto(`/dashboard/${session.id}`);
    await expect(page.getByText('Timeline')).toBeVisible({ timeout: 15000 });

    await page.getByRole('button', { name: 'Replace' }).click();
    await page.locator('input[accept=".pdf,.ppt,.pptx"]').setInputFiles(SAMPLE_PPTX);

    const replaceDialog = page.getByLabel('Replace this presentation?');
    await expect(replaceDialog).toBeVisible();
    await replaceDialog.getByRole('button', { name: 'Replace', exact: true }).click();

    await expect(page.getByText('Replace this presentation?')).toHaveCount(0);
    await expect(page.getByText('Timeline')).toBeVisible({ timeout: 20000 });
  });

  test('detach removes the deck from the session without deleting it, and it stays reusable via the picker', async ({ page, request }) => {
    const user = await registerAndLogin(request);
    const event = await createEvent(request, user.token, 'E2E Detach Event');
    const session = await createSession(request, user.token, event.id, 'E2E Detach Session');
    await uploadPresentation(request, user.token, session.id, SAMPLE_PDF);

    await loginViaToken(page, user.token);
    await page.goto(`/dashboard/${session.id}`);
    await expect(page.getByText('Timeline')).toBeVisible({ timeout: 15000 });

    await page.getByRole('button', { name: 'Details' }).click();
    await expect(page.getByText('Presentation Details')).toBeVisible();
    await page.getByRole('button', { name: 'Detach' }).click();
    const detachDialog = page.getByLabel('Detach this presentation?');
    await expect(detachDialog).toBeVisible();
    await detachDialog.getByRole('button', { name: 'Detach', exact: true }).click();

    // Re-fetches in place rather than closing — storage status flips and Delete
    // becomes actionable without leaving the panel.
    await expect(page.getByText('Detached')).toBeVisible({ timeout: 10000 });

    await page.getByRole('button', { name: 'Close' }).click();
    await expect(page.getByText('Drag & drop a file here, or click to browse')).toBeVisible();

    // The deck itself must not have been deleted — it should still show up
    // when choosing an existing presentation for this same (now empty) session.
    await page.getByRole('button', { name: 'Choose Existing Presentation' }).click();
    await expect(page.getByText('sample.pdf')).toBeVisible({ timeout: 10000 });
  });

  test('attach an existing presentation from the same event via the picker; cross-user isolation holds', async ({ page, request }) => {
    const owner = await registerAndLogin(request);
    const event = await createEvent(request, owner.token, 'E2E Attach Event');
    const sessionA = await createSession(request, owner.token, event.id, 'E2E Attach Session A');
    const sessionB = await createSession(request, owner.token, event.id, 'E2E Attach Session B');
    await uploadPresentation(request, owner.token, sessionA.id, SAMPLE_PDF);

    const stranger = await registerAndLogin(request);
    const strangerEvent = await createEvent(request, stranger.token, 'E2E Stranger Event');
    const strangerSession = await createSession(request, stranger.token, strangerEvent.id, 'E2E Stranger Session');

    // Cross-user isolation: an unrelated user's picker (different owner, different
    // event) must never surface someone else's presentation.
    await loginViaToken(page, stranger.token);
    await page.goto(`/dashboard/${strangerSession.id}`);
    await page.getByRole('button', { name: 'Choose Existing Presentation' }).click();
    await expect(page.getByText('No existing presentations yet.')).toBeVisible({ timeout: 10000 });
    await page.getByRole('button', { name: 'Close' }).click();

    // The actual owner attaching a same-event deck to a second, empty session.
    await loginViaToken(page, owner.token);
    await page.goto(`/dashboard/${sessionB.id}`);
    await page.getByRole('button', { name: 'Choose Existing Presentation' }).click();
    await expect(page.getByText('sample.pdf')).toBeVisible({ timeout: 10000 });

    await page.getByText('sample.pdf').click();
    const attachPreviewDialog = page.getByLabel('Preview presentation');
    await expect(attachPreviewDialog.getByText('3 slides')).toBeVisible();
    await attachPreviewDialog.getByRole('button', { name: 'Use this presentation' }).click();

    await expect(page.getByText('Timeline')).toBeVisible({ timeout: 15000 });
  });

  test('preview an existing presentation before attaching — read-only, cancel does not attach', async ({ page, request }) => {
    const user = await registerAndLogin(request);
    const event = await createEvent(request, user.token, 'E2E Preview Event');
    const sessionA = await createSession(request, user.token, event.id, 'E2E Preview Session A');
    const sessionB = await createSession(request, user.token, event.id, 'E2E Preview Session B');
    await uploadPresentation(request, user.token, sessionA.id, SAMPLE_PDF);

    await loginViaToken(page, user.token);
    await page.goto(`/dashboard/${sessionB.id}`);
    await page.getByRole('button', { name: 'Choose Existing Presentation' }).click();
    await page.getByText('sample.pdf').click();

    const previewDialog = page.getByLabel('Preview presentation');
    await expect(previewDialog.getByText('3 slides')).toBeVisible();
    await expect(previewDialog.getByAltText('Slide 1')).toBeVisible();
    await expect(previewDialog.getByRole('button', { name: 'Use this presentation' })).toBeVisible();

    await previewDialog.getByRole('button', { name: 'Cancel' }).click();
    await expect(page.getByText('Drag & drop a file here, or click to browse')).toBeVisible();
  });

  test('delete an orphaned presentation from the picker', async ({ page, request }) => {
    const user = await registerAndLogin(request);
    const event = await createEvent(request, user.token, 'E2E Delete Event');
    const session = await createSession(request, user.token, event.id, 'E2E Delete Session');
    await uploadPresentation(request, user.token, session.id, SAMPLE_PDF);
    await detachPresentationApi(request, user.token, session.id);

    await loginViaToken(page, user.token);
    await page.goto(`/dashboard/${session.id}`);
    await page.getByRole('button', { name: 'Choose Existing Presentation' }).click();
    await expect(page.getByText('sample.pdf')).toBeVisible({ timeout: 10000 });

    await page.getByLabel('Delete presentation').click();
    await expect(page.getByText('Delete this presentation?')).toBeVisible();
    await page.getByRole('button', { name: 'Delete', exact: true }).click();

    await expect(page.getByText('sample.pdf')).toHaveCount(0);
  });

  test('failed conversion shows the exact reason and allows retrying with a different file', async ({ page, request }) => {
    const user = await registerAndLogin(request);
    const event = await createEvent(request, user.token, 'E2E Failed Conversion Event');
    const session = await createSession(request, user.token, event.id, 'E2E Corrupted Deck Session');

    await loginViaToken(page, user.token);
    await page.goto(`/dashboard/${session.id}`);

    await page.locator('input[type="file"]').setInputFiles(CORRUPTED_PDF);
    await expect(page.getByText('Upload failed')).toBeVisible({ timeout: 20000 });
    await expect(page.getByText(/could not render any pages/i)).toBeVisible();

    await page.getByRole('button', { name: 'Choose a different file' }).click();
    await page.locator('input[type="file"]').setInputFiles(SAMPLE_PDF);
    await expect(page.getByText('Timeline')).toBeVisible({ timeout: 20000 });
  });
});
