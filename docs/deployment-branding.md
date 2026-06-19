# Rforum — Deployment & Branding Guide

## NO DATABASE MIGRATION REQUIRED

Track A configuration is entirely environment-variable driven.
No schema changes are made to the database.

---

## Deployment example

```env
# .env (production)

DATABASE_URL=postgresql+asyncpg://rforum:rforum@db:5432/rforum
REDIS_URL=redis://redis:6379/0

SECRET_KEY=<output of: python -c "import secrets; print(secrets.token_hex(32))">

INVITE_CODE=MYORG2025

CORS_ORIGINS=["https://rforum.myorg.com"]

ORG_NAME=My Organization
ORG_LOGO_URL=/logo-mascot.webp

BOOTSTRAP_SUPER_ADMIN_EMAIL=admin@myorg.com
BOOTSTRAP_SUPER_ADMIN_PASSWORD=<strong password>
```

---

## Branding fields

| Variable       | Where it appears                                                    | Required |
|----------------|---------------------------------------------------------------------|----------|
| `ORG_NAME`     | Footer on every page, logo alt text, session/screen/login pages     | yes      |
| `ORG_LOGO_URL` | Logo image on landing, session, screen, and waiting-room pages      | yes      |

`ORG_LOGO_URL` accepts:
- A path relative to the frontend static root: `/logo-mascot.webp`
- A full URL: `https://cdn.example.com/logo.png`

The frontend fetches branding from `GET /api/public/branding` on page load.
If the request fails, defaults are used and the page renders normally.

**Not configurable at runtime (rebuild required):**
- App name — always `Rforum`
- Footer attribution — always `Built with ❤ by Ajith` / `Rforum@2026`
- Theme colors
- PDF branding (inside analytics reports)

---

## Super admin bootstrap

Set both variables together to ensure the super admin exists on every startup:

```env
BOOTSTRAP_SUPER_ADMIN_EMAIL=admin@myorg.com
BOOTSTRAP_SUPER_ADMIN_PASSWORD=strongpassword
```

**Behavior on each startup:**

| State of DB                         | Action                          |
|-------------------------------------|---------------------------------|
| No user with that email             | Creates user as `SUPER_ADMIN`   |
| User exists as `USER`               | Promotes to `SUPER_ADMIN`       |
| User is already `SUPER_ADMIN`       | No change (idempotent)          |

It is safe to leave these set permanently. The check is read-only after first setup.

Leave both fields empty to skip bootstrap (requires a super admin to already exist in the DB).

---

## Startup failures

The application refuses to start if:

| Condition                                                        | Error                                          |
|------------------------------------------------------------------|------------------------------------------------|
| `SECRET_KEY` equals the default placeholder                      | `SECRET_KEY is the insecure placeholder`       |
| `INVITE_CODE` equals `RFORUM01`                                  | `INVITE_CODE is the default 'RFORUM01'`        |
| `BOOTSTRAP_SUPER_ADMIN_EMAIL` set but password empty             | `BOOTSTRAP_SUPER_ADMIN_PASSWORD is empty`      |
| `ORG_NAME` is empty                                              | `ORG_NAME must not be empty`                   |
| `ORG_LOGO_URL` is empty                                          | `ORG_LOGO_URL must not be empty`               |

All errors are printed to the log with actionable messages before the process exits.

---

## Rollback instructions

If you need to revert to pre-Track-A behavior:

1. **Remove from .env:** `ORG_NAME`, `ORG_LOGO_URL`, `BOOTSTRAP_SUPER_ADMIN_EMAIL`, `BOOTSTRAP_SUPER_ADMIN_PASSWORD`
2. **Restore git files:**
   ```
   git checkout HEAD -- app/config.py app/main.py app/routers/auth.py
   git checkout HEAD -- frontend/src/routes/+layout.svelte
   git checkout HEAD -- frontend/src/routes/+page.svelte
   git checkout HEAD -- frontend/src/routes/dashboard/+layout.svelte
   git checkout HEAD -- frontend/src/routes/login/+page.svelte
   git checkout HEAD -- frontend/src/routes/session/\[code\]/+page.svelte
   git checkout HEAD -- frontend/src/routes/screen/\[code\]/+page.svelte
   git checkout HEAD -- frontend/src/lib/components/JoinScreen.svelte
   ```
3. No database changes to undo — no migration was applied.

---

## Manual verification checklist

After deploying with new env vars:

- [ ] App starts without errors in log
- [ ] `GET /api/public/branding` returns correct `org_name` and `logo_url`
- [ ] Login page footer shows configured `ORG_NAME`
- [ ] Landing page logo image changes when `ORG_LOGO_URL` changes
- [ ] Session page footer and logo reflect `ORG_NAME` / `ORG_LOGO_URL`
- [ ] Screen (presenter) page footer and logo reflect config
- [ ] Super admin can log in
- [ ] Registering with the bootstrap email does NOT auto-promote (role = USER)
- [ ] `SECRET_KEY=change-me-in-production-use-a-real-secret` causes startup failure
- [ ] `INVITE_CODE=RFORUM01` causes startup failure
- [ ] Restart with same env → super admin unchanged (idempotent)
- [ ] Existing user sessions unaffected after restart
