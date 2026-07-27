# Rforum — Architecture Documentation

This document describes the system **as currently implemented**. It is not a design
proposal or roadmap — every section reflects code that exists in this repository today.

---

## 1. System Architecture

**Frontend** — SvelteKit 2 / Svelte 5 (runes mode), built with Vite 6, styled with
Tailwind CSS. Built as a static site via `@sveltejs/adapter-static` (`npm run build`
writes to `frontend/build`) and served entirely client-side (SPA fallback to
`index.html`). No SvelteKit SSR is used in production — the adapter produces static
HTML/JS/CSS only.

**Backend** — FastAPI (Python 3.12), fully async (`asyncpg` + SQLAlchemy 2.0 async
ORM). Runs as a single Uvicorn process (`uvicorn app.main:app`). Routers are grouped by
resource under `app/routers/` and registered in `app/main.py`. Auth is stateless JWT
(`app/auth.py`), no server-side session store.

**Database** — PostgreSQL 16, schema managed via Alembic migrations (`db/alembic/`).

**Redis** — single Redis instance used for two unrelated purposes: (1) the WebSocket
pub/sub fan-out that lets multiple app processes/sockets share live events
(`app/routers/ws.py`, `app/routers/*.py` via `request.app.state.redis.publish(...)`),
and (2) the rate-limiter's fixed-window counters (`app/rate_limit.py`). Not used as a
cache for HTTP responses.

**WebSocket flow** — a single endpoint, `/ws/{session_code}`. On connect: per-IP rate
limit check → session-existence check (query by `unique_code`) → role resolution
(`moderator` / `screen` / `guest`, via `app/routers/ws.py::resolve_ws_role`) → the
connection is registered in an in-process `ConnectionManager`, which opens exactly one
Redis pub/sub subscription per session code (not per socket) and fans incoming Redis
messages out to every locally-connected socket for that code. Clients relay a small
fixed set of event types (`ALLOWED_WS_EVENTS`); three of them
(`slide_change`, `page_change`, `session_update`) are rejected unless the sender
resolved as `moderator`. HTTP endpoints that mutate live state (e.g. slide activation,
new responses) also `redis.publish(...)` directly, so a change made over HTTP or over
the WebSocket both reach every connected client the same way.

**Deployment topology** — see [§9 Deployment](#9-deployment).

---

## 2. Database

Managed by SQLAlchemy models in `app/models.py`; migrations in `db/alembic/versions/`.

**Major tables**

| Table | Purpose |
|---|---|
| `users` | Accounts. `role` is `USER` or `SUPER_ADMIN`; `is_active` can disable login. |
| `events` | Top-level container a user creates; has zero or more sessions. |
| `sessions` | A single audience-engagement session. Holds `unique_code` (join code), `is_live`, `moderator_name`, `speaker_names`, and `presentation_id` (nullable — see below). |
| `slides` | Legacy per-session content items (POLL/QNA/FEEDBACK/CONTENT/WORD_CLOUD), each with a `content_json` blob and an `is_active` flag. Also reused by the presentation-first model (see §4). |
| `responses` | Guest-submitted answers to a `slide`, with `guest_identifier`, optional `rating`, and `upvotes`. |
| `presentations` | An uploaded deck (PDF/PPT/PPTX), immutable once processed. Tracks `checksum` (dedup), `orphaned_since` (soft-delete grace period), `last_used_at`, `replaces_presentation_id`. |
| `presentation_pages` | One row per rendered page of a `presentation` (image + thumbnail storage keys). |
| `presentation_timelines` | One per session; orders a session's presentation flow and tracks `active_timeline_item_id`. |
| `presentation_timeline_items` | One ordered slot in a timeline — either a `PAGE` (points at a `presentation_pages` row) or an interaction (points at a `slides` row). |
| `session_assets` | Upload audit trail — every file a user has uploaded, linked to whichever of slide/session/event/presentation it belongs to. |
| `polls`, `poll_options`, `questions`, `feedbacks` | Present in the schema but **not referenced by any current router** — dead tables superseded by the `slides` + `content_json` approach. |

**Key relationships** — `users` 1:N `events` and `sessions`; `events` 1:N `sessions`
(optional — `session.event_id` is nullable); `sessions` 1:N `slides` (legacy path) and
0:1 `presentation_timelines`; `presentations` 1:N `presentation_pages`;
`presentation_timelines` 1:N `presentation_timeline_items`, each item pointing at
*either* a `presentation_pages` row *or* a `slides` row.

**Presentation-first model** — a session is "legacy" or "presentation-first" purely
based on whether `session.presentation_id` is `NULL`. There is no separate mode flag.
Legacy sessions manage content directly through the `slides` CRUD router
(`app/routers/slides.py`); presentation-first sessions manage content through
`app/routers/presentations.py`'s timeline endpoints, which use `slides` rows internally
for every *interactive* item (POLL/QNA/WORD_CLOUD/FEEDBACK/RATING) — only page-turn
items are backed by `presentation_pages` instead. Because interactions are still plain
`slides` rows, `responses`, analytics, and the PDF export path require no branching
between the two architectures — both are queried through `slides`/`responses`
identically.

---

## 3. API

All routers are mounted under `/api` (see `app/main.py`). No API versioning exists —
there is a single, unversioned surface.

- **Auth** (`app/routers/auth.py`, prefix `/api/auth`) — `POST /register` (invite-code
  gated), `POST /login` (OAuth2 password form → JWT), `GET /me`,
  `POST /change-password`. Login and register are rate-limited per-IP
  (`app/rate_limit.py`).
- **Events** (`app/routers/events.py`, prefix `/api/events`) — `POST /`, paginated
  `GET /` (see §Pagination below), `GET /{id}`, `PATCH /{id}`, `DELETE /{id}`,
  `PUT /{id}/sessions` (bulk attach/detach sessions), plus unauthenticated
  `GET /public`, `GET /public/today` for guest event listings.
- **Sessions** (`app/routers/sessions.py`, prefix `/api/sessions`) — `POST /`,
  paginated `GET /`, `GET /{id}`, `GET /code/{code}`, `PATCH /{id}`, `DELETE /{id}`,
  and the unauthenticated, rate-limited `GET /join/{code}` guests use to load a live
  session.
- **Slides** (`app/routers/slides.py`, prefix `/api/sessions/{session_id}/slides`) —
  legacy-only CRUD (`POST/GET/PATCH/DELETE`), file upload, and page-image rendering.
  Every mutation 409s if the session is presentation-first
  (`_ensure_not_presentation_session`).
- **Presentations** (`app/routers/presentations.py`, prefix `/api`) — upload/replace/
  regenerate a deck, get/attach/detach it from a session, a per-user presentation
  library (`GET /api/presentations`, filterable by `event_id`/`search`), timeline item
  CRUD + reorder + activate, and unauthenticated page-image/thumbnail serving (gated by
  token-or-code proof, see §6).
- **Analytics** (`app/routers/analytics.py`, prefix `/api/analytics`) — aggregate stats
  (`GET /`), and CSV/JSON export per event or per session
  (`GET /event/{id}/download`, `GET /session/{id}/download`).
- **Responses** (`app/routers/responses.py`, prefix `/api/slides/{slide_id}/responses`)
  — guest submission (rate-limited, only accepted while the slide `is_active`), listing
  (live-session-gated for non-owners), upvoting, and owner-only clearing.
- **Admin** (`app/routers/admin.py`, prefix `/api/admin`) — super-admin-only user
  management, and platform-wide session/event/storage listings.
- **Session assets** (`app/routers/session_assets.py`) — per-user uploaded-file
  listing, storage usage, replace, delete.
- **WebSocket** — `GET /ws/{session_code}` (see §1).

**Pagination** — `GET /api/events` and `GET /api/sessions` accept `limit`, `offset`,
and `search` query params and return
`{items, total, limit, offset, has_more}` instead of a bare array. `limit` defaults to
`Settings.DEFAULT_PAGE_SIZE` (20) and is clamped to `Settings.MAX_PAGE_SIZE` (100).
Ordering is newest-first (`event_date` then `created_at` for events; `created_at` for
sessions) and permission scoping (owner-only unless `SUPER_ADMIN`) is applied before
the count and page queries. `search` matches title/description/attached-session-
moderator for events, and title/moderator/code/attached-presentation-filename for
sessions. No other list endpoint in the API is paginated (event-nested sessions,
slide lists, response lists, and the presentation library are all returned in full).

---

## 4. Presentation Architecture

Implemented in `app/routers/presentations.py`, `app/services/file_processing.py`, and
`app/storage/`.

- **Upload flow** — a PDF/PPT/PPTX is validated (extension, size, magic-byte MIME
  sniffing), PPT/PPTX is converted to PDF via LibreOffice if available (falls back to a
  PyMuPDF-based renderer otherwise), and thumbnails for every page are rendered
  immediately. A SHA-256 checksum of the raw upload is computed; if a `READY`
  presentation with the same owner + checksum already exists, that existing
  `Presentation` is reused instead of creating a duplicate (no re-render, no re-store).
- **Storage** — every asset (original file, thumbnails, full-resolution pages) is
  addressed by a string key, never a raw filesystem path, through the
  `StorageBackend` interface (see §7).
- **Lazy rendering** — only thumbnails are rendered at upload time. A page's
  full-resolution image is rendered on first request
  (`presentations.py::_serve_page_file`) and then cached to storage permanently with a
  long `Cache-Control: immutable` header; every subsequent request for that page is a
  storage read, not a re-render. `regenerate` invalidates cached full-res pages
  (deletes them) without re-rendering them, so they lazily re-render next view.
- **Timeline** — a `PresentationTimeline` is one ordered sequence of items per session.
  Uploading a deck creates one `PAGE` item per rendered page. Replacing a deck
  re-interleaves existing interaction items evenly among the new pages
  (`_distribute_interactions_among_pages`), preserving their relative order. Pages are
  read-only in the timeline (cannot be deleted/reordered independently of the deck);
  only interaction items can be inserted, edited, deleted, or reordered.
- **Interactive elements** — POLL, QNA, WORD_CLOUD, FEEDBACK, and RATING timeline items
  are each backed by an ordinary `slides` row (RATING is stored as a FEEDBACK slide
  with `content_json.mode = "rating_only"`). Activating a timeline item
  (`POST .../timeline/activate/{item_id}`) flips exactly one `slides.is_active` flag
  session-wide and publishes a `slide_change` event over Redis/WebSocket — the same
  mechanism the legacy slide flow uses, so `responses.py::submit_response`'s
  single "is this slide active" gate needs no presentation-specific branch.
- **Reusable presentations** — a `Presentation` is not owned exclusively by one
  session; it can be detached (pointer cleared, row kept), reattached to a different
  session, or deleted once nothing references it. Detached/replaced presentations are
  marked `orphaned_since` and swept after `PRESENTATION_ORPHAN_RETENTION_DAYS` (7 days
  by default) rather than deleted immediately.

---

## 5. Analytics

Implemented in `app/routers/analytics.py`; the PDF report is generated entirely
client-side.

- **Event analytics** (`GET /api/analytics/event/{id}/download`) — per-event session
  engagement (response counts, unique participants, average rating), plus every
  response grouped by session → slide. Returns CSV or JSON (`?format=`).
- **Session analytics** (`GET /api/analytics/session/{id}/download`) — the session's
  slides (id, type, order, **and `content_json`**, so callers don't need the separate
  legacy `/slides` endpoint) and all of its responses. Also CSV or JSON.
- Both endpoints query `Slide`/`Response` directly by `session_id` — since
  presentation-first interaction items are ordinary `slides` rows (§4), no branching
  between legacy and presentation-first sessions is needed anywhere in analytics.
- **PDF generation** is entirely client-side
  (`frontend/src/routes/dashboard/analytics/[eventId]/[sessionId]/+page.svelte`, using
  `jspdf`/`jspdf-autotable`): it fetches the session/event analytics JSON, builds
  charts (poll bars, word clouds, rating distributions) and tables from that data, and
  renders a multi-page branded PDF entirely in the browser. There is no server-side PDF
  renderer.

---

## 6. Security

- **Authentication** — JWT bearer tokens (`app/auth.py`), `HS256`, signed with
  `Settings.SECRET_KEY`, expiring after `ACCESS_TOKEN_EXPIRE_MINUTES` (24h default).
  Passwords are hashed with bcrypt (`passlib`, with a direct-`bcrypt` fallback for the
  72-byte input limit). Registration requires a shared `INVITE_CODE`; the account whose
  email matches `SUPER_ADMIN_EMAIL` is auto-promoted to `SUPER_ADMIN` on registration.
- **Authorization** — two roles (`USER`, `SUPER_ADMIN`). Almost every owner-scoped
  query follows the same pattern: filter by `owner_id == current_user.id` unless the
  caller is `SUPER_ADMIN`. Guest-facing endpoints (join, submit response, view a page
  image) have no user account at all and are instead gated on session liveness
  (`is_live`) and/or a matching `unique_code`.
- **Rate limiting** — a single shared fixed-window Redis counter
  (`app/rate_limit.py::check_rate_limit`), applied to: WS connect (60/min/IP), session
  join-by-code (60/min/IP), login (30/min/IP), register (30/min/IP), guest response
  submission (10/min per guest identifier *and* 20/min per IP, per slide), and response
  upvoting (1 per response per IP per 24h). Thresholds are intentionally generous
  because many legitimate users can share one IP (conference Wi-Fi/NAT) — the limiter
  bounds scripted abuse, not organic bursts.
- **Asset protection** — presentation/legacy-slide page images and thumbnails have no
  `Depends(get_current_user)` (guests must be able to view them without an account),
  so each image-serving endpoint instead requires proof via either a valid owner/admin
  JWT (`?token=`) or a `?code=` matching a currently-*live* session that has that exact
  presentation/slide attached (`_authorize_presentation_asset` /
  `_authorize_slide_asset`). Local file paths are confined to the storage root via
  path-resolution checks (`os.path.realpath` containment).
- **WebSocket validation** — before a connection is accepted (before
  `websocket.accept()` and before the shared Redis pub/sub subscription for that
  session code is opened), the server rate-limits the connecting IP and verifies the
  session code exists. Role (`moderator`/`screen`/`guest`) is then resolved from an
  optional JWT plus the session's `owner_id`; a token valid for one session degrades to
  `guest` on any other session code. Only `moderator` may relay the three
  state-mutating event types; unknown event types are silently dropped.

---

## 7. Storage

- **Current local storage** — `app/storage/local.py::LocalFilesystemBackend` writes
  under `Settings.STORAGE_ROOT` (default `uploads/`), on the same disk as the
  application process. Writes are atomic (write to a `.tmp` file, then `os.replace`).
  Key resolution is backward-compatible with the pre-storage-abstraction convention of
  storing a literal `/uploads/...` path, so old and new rows resolve through the same
  code path with no data migration.
- **Storage abstraction** — `app/storage/base.py::StorageBackend` is an ABC
  (`save`/`read`/`exists`/`delete`/`delete_prefix`/`size`) that all business logic
  (`app/routers/presentations.py`, `app/services/file_processing.py`) calls through —
  never the filesystem directly. `app/storage/__init__.py::get_storage_backend()`
  selects an implementation from `Settings.STORAGE_BACKEND` (currently only
  `"local"` is implemented).
- **Future S3 compatibility** — the interface is designed so an S3-compatible backend
  could be added as a second `StorageBackend` subclass without touching any call site.
  **No such backend exists yet** — selecting any `STORAGE_BACKEND` value other than
  `"local"` raises `NotImplementedError` at startup.

---

## 8. Testing

- **Pytest** (`tests/`, run with a real Postgres on `:5433` and Redis on `:6379` —
  no ORM/DB mocking): `test_endpoint_hardening.py`, `test_legacy_compatibility.py`,
  `test_pagination.py`, `test_presentations.py`, `test_rate_limit.py`,
  `test_upload_reliability.py`, `test_file_processing_bytes.py`,
  `test_storage_backend.py`, `test_ws_auth.py` — roughly 190 tests in total. Each file
  that needs Postgres creates/truncates its own tables against a dedicated
  `rforum_test` database (never the `rforum` dev/prod database) and skips itself if
  that Postgres isn't reachable.
- **Playwright** (`frontend/e2e/`) — runs against the real dev stack (real Postgres,
  real Redis, the actual FastAPI backend on `:8000`, no mocking); each spec registers
  its own fresh throwaway user via the real register/login endpoints. Covers auth,
  analytics, guest flow, screen mode, presentation editing/lifecycle,
  WS authorization, search (events/sessions/global), event↔session navigation, error
  recovery, and a dedicated legacy-session regression spec.
- **Legacy compatibility** — `tests/test_legacy_compatibility.py` specifically
  exercises sessions with `presentation_id IS NULL` (as opposed to every other test
  fixture in the suite, which happens to use presentation-attached sessions) against
  asset auth, the response-listing live-gate, and the analytics/PDF data endpoint, plus
  the presentation-first counterpart of each, side by side.
  `frontend/e2e/legacy-session-regression.spec.ts` covers the same distinction from the
  browser side.
- **No CI pipeline exists** — there is no `.github/workflows` or other CI
  configuration in this repository; both suites are run manually.

---

## 9. Deployment

- **Docker** — `docker-compose.yml` runs Postgres 16 and Redis 7 as containers
  (`db`, `redis`, both with healthchecks). An `api` service definition exists in the
  compose file but is **commented out** — in the current deployment the FastAPI
  backend runs directly on the host via Uvicorn, not inside a container, despite
  `app/Dockerfile` existing (Python 3.12-slim + LibreOffice + libmagic, `CMD uvicorn
  app.main:app --host 0.0.0.0 --port 8000`).
- **Nginx** — terminates TLS for `rforum.t4gc.in` (Let's Encrypt certs), and:
  - proxies `location /api/` and `location /ws/` to `127.0.0.1:8000` (the Uvicorn
    process), with WebSocket upgrade headers and an 86400s read timeout for `/ws/`;
  - serves everything else as static files with `root frontend/build; try_files $uri
    $uri/ /index.html`, a 1-hour cache for normal assets, and a 1-year immutable cache
    specifically for `_app/immutable/`;
  - a catch-all default server returns HTTP 444 for any request that doesn't match
    `rforum.t4gc.in` (direct-IP probing, etc.).
- **PostgreSQL** — schema changes are applied via Alembic (`db/alembic/`,
  `alembic upgrade head`); not automated as part of any deploy step in this repo.
- **Redis** — a single instance, no persistence/replication configuration beyond the
  Docker image defaults.
- **Static assets** — the SvelteKit build output (`frontend/build`) *is* Nginx's
  document root — there is no separate CDN or object-storage step for the frontend
  bundle. Uploaded presentation/slide assets are served through backend endpoints
  (§6), not directly by Nginx.

---

## 10. Current Known Limitations

- **Non-paginated views are capped at 100 items.** The Events page's "attach session"
  picker, the Sessions page's "select event" dropdown, the dashboard overview
  (`/dashboard`), and the Analytics landing page's event browser all request
  `limit=100` (the backend's `MAX_PAGE_SIZE`) rather than truly "every" event/session —
  an account with more than 100 of either will not see the rest in those views.
- **Nested/nested-adjacent lists are unpaginated.** An event's attached `sessions`
  array, a session's `slides` list, a slide's `responses` list, and the presentation
  library (`GET /api/presentations`) are all still returned in full on every request.
- **Four DB tables are dead.** `polls`, `poll_options`, `questions`, and `feedbacks`
  exist in the schema (and in every migration history) but are not read or written by
  any current router — POLL/QNA/FEEDBACK are implemented entirely through
  `slides.content_json` instead.
- **Rate limits are per-IP, not per-account.** Users behind the same NAT/shared Wi-Fi
  (a realistic scenario at a live event) share one rate-limit bucket for login,
  register, join, and WS connect.
- **Single-instance WebSocket state.** `ConnectionManager` (`app/routers/ws.py`) keeps
  connected sockets in an in-process dict. Redis pub/sub fans a published event out to
  every *subscribed process*, but if more than one backend process/instance were ever
  run concurrently, there is no shared registry of which sockets are connected where —
  the current deployment (§9) runs exactly one Uvicorn process, so this isn't
  triggered today, but the code has no multi-instance WS story.
- **No production storage redundancy.** The only implemented `StorageBackend` writes
  to local disk with no replication or backup step in this repo.
- **No automated test/deploy pipeline.** No CI configuration exists; both the pytest
  and Playwright suites, and any deployment step, are run manually.
- **Migrations are not applied automatically.** `alembic upgrade head` is a manual
  step, not wired into any startup or deploy script.
