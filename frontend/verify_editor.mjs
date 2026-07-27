import { chromium } from 'playwright';
import { readFileSync } from 'fs';

const API_BASE = 'http://localhost:8000';
const FRONTEND_BASE = 'http://localhost:5173';

const email = `editorv2_${Date.now()}@example.com`;
const password = 'EditorV2TestPass123';

function log(label, ok, extra = '') {
  console.log(`${ok ? '✓' : '✗'} ${label}${extra ? ' — ' + extra : ''}`);
}

await fetch(`${API_BASE}/api/auth/register`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email, password, invite_code: 'BUILT201' }),
});
const loginForm = new URLSearchParams();
loginForm.set('username', email); loginForm.set('password', password);
const loginRes = await fetch(`${API_BASE}/api/auth/login`, { method: 'POST', body: loginForm });
const { access_token } = await loginRes.json();
const authHeaders = { 'Content-Type': 'application/json', Authorization: `Bearer ${access_token}` };

const evRes = await fetch(`${API_BASE}/api/events/`, {
  method: 'POST', headers: authHeaders,
  body: JSON.stringify({ title: 'Editor V2 Test Event', event_date: new Date().toISOString().slice(0, 10) }),
});
const event = await evRes.json();

// Two sessions: one stays legacy, one gets a presentation attached.
const legacySessRes = await fetch(`${API_BASE}/api/sessions/`, {
  method: 'POST', headers: authHeaders,
  body: JSON.stringify({ title: 'Legacy Session', event_id: event.id }),
});
const legacySession = await legacySessRes.json();

const tlSessRes = await fetch(`${API_BASE}/api/sessions/`, {
  method: 'POST', headers: authHeaders,
  body: JSON.stringify({ title: 'Timeline Session', event_id: event.id }),
});
const tlSession = await tlSessRes.json();

const browser = await chromium.launch();
const context = await browser.newContext();
const page = await context.newPage();
const pageErrors = [];
page.on('pageerror', (err) => pageErrors.push(err.message));
page.on('console', (msg) => { if (msg.type() === 'error') pageErrors.push(msg.text()); });

await page.goto(`${FRONTEND_BASE}/login`, { waitUntil: 'domcontentloaded' });
await page.evaluate((token) => localStorage.setItem('rforum_token', token), access_token);

console.log('\n=== LEGACY EDITOR ===');
await page.goto(`${FRONTEND_BASE}/dashboard/${legacySession.id}`, { waitUntil: 'networkidle' });

// Add a POLL slide
await page.getByRole('button', { name: 'Poll', exact: true }).first().click();
await page.waitForTimeout(600);
let slideCount = await page.locator('text=Slides').locator('..').locator('span.text-slate-400').first().textContent().catch(() => null);
log('Add slide (Poll) via sidebar button', (await page.locator('text=No slides yet').count()) === 0);

// Edit + Save the poll (buffered form, explicit Save)
await page.getByRole('button', { name: 'Edit' }).first().click();
const pollQInput = page.locator('input[placeholder="Poll question"]');
await pollQInput.fill('What is your favorite color?');
await page.waitForTimeout(200);
const dirtyBadgeVisible = await page.locator('text=Unsaved changes').count();
log('Unsaved-changes badge appears while editing', dirtyBadgeVisible > 0);

// beforeunload should warn now — verify via the browser's native handler registration
const hasBeforeUnloadHandler = await page.evaluate(() => {
  return new Promise((resolve) => {
    const ev = new Event('beforeunload', { cancelable: true });
    const result = window.dispatchEvent(ev);
    resolve(ev.defaultPrevented || result === false);
  });
});
log('beforeunload is intercepted while dirty', hasBeforeUnloadHandler);

await page.getByRole('button', { name: 'Save' }).first().click();
await page.waitForTimeout(400);
const dirtyBadgeAfterSave = await page.locator('text=Unsaved changes').count();
log('Unsaved-changes badge clears after Save', dirtyBadgeAfterSave === 0);

// Undo the content edit
await page.keyboard.press('Control+z');
await page.waitForTimeout(500);
const revertedQuestion = await page.locator('text=What is your favorite color?').count();
log('Ctrl+Z reverts the poll question edit', revertedQuestion === 0);

// Redo
await page.keyboard.press('Control+Shift+z');
await page.waitForTimeout(500);
const redoneQuestion = await page.locator('text=What is your favorite color?').count();
log('Ctrl+Shift+Z re-applies the poll question edit', redoneQuestion > 0);

// Duplicate the slide
const beforeDupeCount = await page.locator('[title="Duplicate"]').count();
await page.locator('[title="Duplicate"]').first().click();
await page.waitForTimeout(600);
const afterDupeCount = await page.locator('[title="Delete"]').count();
log('Duplicate slide button adds a new slide', afterDupeCount >= 2);

// Move up/down buttons present (keyboard-operable reorder)
const moveButtons = await page.locator('[aria-label="Move up"], [aria-label="Move down"]').count();
log('Keyboard move up/down buttons present on slide cards', moveButtons > 0);

// Delete a slide, then undo
const deleteBtns = page.locator('[title="Delete"]');
const countBeforeDelete = await deleteBtns.count();
await deleteBtns.first().click();
await page.waitForTimeout(500);
const countAfterDelete = await page.locator('[title="Delete"]').count();
log('Delete slide removes it', countAfterDelete === countBeforeDelete - 1);
await page.keyboard.press('Control+z');
await page.waitForTimeout(600);
const countAfterUndoDelete = await page.locator('[title="Delete"]').count();
log('Ctrl+Z restores a deleted slide', countAfterUndoDelete === countBeforeDelete);

console.log('\n=== PRESENTATION-TIMELINE EDITOR ===');
const pdfBuffer = readFileSync('/home/ubuntu/rforum/frontend/e2e/fixtures/sample.pdf');
await page.goto(`${FRONTEND_BASE}/dashboard/${tlSession.id}`, { waitUntil: 'networkidle' });
const fileInput = page.locator('#presentation-file-input');
await fileInput.setInputFiles({ name: 'sample.pdf', mimeType: 'application/pdf', buffer: pdfBuffer });
await page.waitForTimeout(4000); // upload + fake stage progression + reveal workspace
const workspaceVisible = await page.locator('text=Select a page or interaction to get started').or(page.locator('text=Page 1')).count();
log('Presentation upload reveals the timeline workspace', workspaceVisible > 0 || (await page.locator('[aria-label="Zoom in"]').count()) > 0);

// Insert a Poll interaction
await page.locator('button:has-text("Add Interaction")').first().click();
await page.waitForTimeout(200);
await page.locator('button[title="Poll"]').click();
await page.waitForTimeout(800);
const interactionInserted = await page.locator('[aria-label="Duplicate interaction"]').count();
log('Insert interaction (Poll) adds a timeline row', interactionInserted > 0);

// Duplicate the interaction
await page.locator('[aria-label="Duplicate interaction"]').first().click();
await page.waitForTimeout(800);
const afterDupInteraction = await page.locator('[aria-label="Delete interaction"]').count();
log('Duplicate interaction adds another timeline row', afterDupInteraction >= 2);

// Zoom controls present on a PAGE item
await page.locator('text=Page 1').first().click().catch(() => {});
await page.waitForTimeout(500);
const zoomControlsPresent = await page.locator('[aria-label="Zoom in"]').count();
log('Zoom controls render for a page item', zoomControlsPresent > 0);
if (zoomControlsPresent > 0) {
  await page.locator('[aria-label="Zoom in"]').click();
  await page.waitForTimeout(150);
  const zoomPct = await page.locator('text=/\\d+%/').first().textContent().catch(() => '');
  log('Zoom in changes the displayed percentage', zoomPct !== '100%' && zoomPct !== '');
  await page.locator('[aria-label="Fit to screen"]').click();
}

// Fullscreen button present
const fullscreenBtn = await page.locator('[aria-label="Enter fullscreen"]').count();
log('Fullscreen toggle button present', fullscreenBtn > 0);

// Undo/Redo buttons present after mutations
const undoBtnPresent = await page.locator('[aria-label="Undo"]').count();
log('Undo button present in header after timeline mutations', undoBtnPresent > 0);

console.log('\n=== Console/page errors during the whole run ===');
if (pageErrors.length === 0) {
  console.log('✓ No console errors or uncaught exceptions');
} else {
  pageErrors.forEach((e) => console.log('✗', e));
}

await browser.close();
