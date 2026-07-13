# E2E tests (Playwright)

These tests run against the real dev stack — no mocking. Before running them, have running:

- Postgres on `:5433` (migrations applied — `alembic upgrade head` from `db/`)
- Redis on `:6379`
- The FastAPI backend on `:8000` (`uvicorn app.main:app --port 8000`, invite code from `.env`'s `INVITE_CODE`)

The Vite dev server (`:5173`) is started automatically by `playwright.config.ts` if it
isn't already running (it proxies `/api` and `/ws` to `:8000`, see `vite.config.ts`).

```bash
npm run test:e2e            # headless, chromium
npm run test:e2e -- --ui    # interactive UI mode
```

Env overrides: `E2E_BASE_URL` (frontend origin), `E2E_API_BASE` (backend origin, for
direct API setup calls in `fixtures.ts`), `E2E_INVITE_CODE` (registration invite code).

Each spec registers its own fresh user via the real `/api/auth/register` + `/api/auth/login`
endpoints — no shared or seeded test accounts, no dependency-injection mocking. `fixtures.ts`
holds the API setup helpers (create event/session, upload a presentation, insert/activate
timeline items) so each spec's `test(...)` body stays focused on the UI flow it's actually
verifying.
