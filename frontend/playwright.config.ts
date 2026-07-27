import { defineConfig, devices } from '@playwright/test';

/**
 * Runs against the real dev stack — Vite dev server (proxies /api and /ws to
 * the FastAPI backend on :8000, see vite.config.ts) plus a real Postgres and
 * Redis. No mocking: auth is a real POST /api/auth/login, presentation
 * uploads go through the real conversion/render pipeline. Requires the
 * backend, Postgres (:5433), and Redis (:6379) already running — see
 * e2e/README.md.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: process.env.E2E_SKIP_WEBSERVER
    ? undefined
    : {
        command: 'npm run dev',
        url: 'http://localhost:5173',
        reuseExistingServer: true,
        timeout: 30_000,
      },
});
