import json
from functools import lru_cache
from typing import Annotated

from pydantic import AliasChoices, Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, NoDecode


class Settings(BaseSettings):
    # Security/environment-sensitive settings have no insecure fallback —
    # a missing value must fail startup loudly (see get_settings() below)
    # rather than silently run with a well-known default that's public in
    # this repo's history.
    DATABASE_URL: str
    REDIS_URL: str = "redis://redis:6379/0"
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    INVITE_CODE: str
    CORS_ORIGINS: list[str]
    # Super admin: set this env var to auto-promote a user on registration.
    # Auto-promotion also requires SUPER_ADMIN_BOOTSTRAP_TOKEN below to be
    # set and supplied by the registering client — see app/routers/auth.py.
    SUPER_ADMIN_EMAIL: str = ""
    # One-time bootstrap secret gating SUPER_ADMIN_EMAIL auto-promotion.
    # Without this, whoever registers first with SUPER_ADMIN_EMAIL's exact
    # address wins the role — a race anyone holding the (often widely-shared)
    # INVITE_CODE could win by beating the real admin to it. Requiring a
    # second, separately-distributed secret (never shared with the invite
    # code) closes that race. Leave empty to disable auto-promotion entirely.
    SUPER_ADMIN_BOOTSTRAP_TOKEN: str = ""
    # Optional one-time bootstrap value for the org_settings singleton's
    # display_name (app/models.py::OrgSettings, app/routers/org_settings.py).
    # Applied only while the DB row still holds the seeded default — once an
    # admin edits it from the Admin page, this env var is never consulted
    # again, so a later restart/redeploy never overwrites their change.
    ORG_DISPLAY_NAME: str = ""
    # Upload settings
    UPLOAD_MAX_MB: int = 20  # Maximum upload file size in MB
    # Accepts either a JSON array (`[".pdf", ".doc"]`) or a comma-separated
    # string (`.pdf,.doc`) via UPLOAD_ALLOWED_EXTENSIONS — see the validator
    # below. NoDecode opts this field out of pydantic-settings' default
    # JSON-only env parsing for list fields, which otherwise raises
    # SettingsError on a plain comma-separated value.
    UPLOAD_ALLOWED_EXTENSIONS: Annotated[list[str], NoDecode] = [
        ".pdf", ".ppt", ".pptx", ".doc", ".docx", ".txt", ".odp", ".odt",
        ".png", ".jpg", ".jpeg", ".webp",
    ]

    @field_validator("UPLOAD_ALLOWED_EXTENSIONS", mode="before")
    @classmethod
    def _parse_upload_allowed_extensions(cls, value):
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                return json.loads(stripped)
            return [ext.strip() for ext in stripped.split(",") if ext.strip()]
        return value

    # Presentation storage
    # "local" or "s3"; also settable via STORAGE_PROVIDER (S3 rollout convention) —
    # both env var names bind to this one field, STORAGE_PROVIDER takes priority
    # if both are set. See app/storage/.
    STORAGE_BACKEND: str = Field(
        default="local",
        validation_alias=AliasChoices("STORAGE_PROVIDER", "STORAGE_BACKEND"),
    )
    STORAGE_ROOT: str = "uploads"
    # S3 backend config (used only when STORAGE_BACKEND/STORAGE_PROVIDER == "s3").
    # When STORAGE_BACKEND=="s3", reads/existence checks fall back to the local
    # filesystem (STORAGE_ROOT) for presentations uploaded before the S3
    # switchover — see app/storage/fallback.py. New writes always go to S3.
    S3_BUCKET: str = ""
    S3_REGION: str = "eu-north-1"
    S3_ENDPOINT: str = ""  # optional override, e.g. for MinIO/R2; empty = AWS default
    # Bucket-level namespace root, analogous to STORAGE_ROOT. Defaults empty —
    # every key the app builds already starts with "presentations/" or
    # "branding/" (see app/storage/keys.py), so a non-empty default here
    # would double it up into s3://bucket/presentations/presentations/...
    # In the one-instance-per-organization deployment model, this is also
    # the per-organization namespace segment for the shared S3 bucket — set
    # it to e.g. "rforum/{org_slug}" per Helm release so every key (including
    # the org's own logo/favicon under "branding/") lands under
    # s3://bucket/rforum/{org_slug}/... with no separate ORG_PREFIX needed.
    S3_PREFIX: str = ""
    AWS_ACCESS_KEY_ID: str = ""  # empty = fall back to boto3's default credential chain
    AWS_SECRET_ACCESS_KEY: str = ""
    S3_MAX_RETRIES: int = 3
    USE_PRESIGNED_URLS: bool = False  # reserved — not yet implemented, backend still proxies bytes
    PRESENTATION_ORPHAN_RETENTION_DAYS: int = 7
    # Resource limits enforced before rendering an uploaded deck (see
    # app/services/file_processing.py::check_render_limits) — reject
    # oversized/oddly-dimensioned decks up front rather than spending
    # LibreOffice/PyMuPDF CPU and memory rendering every page of them.
    PRESENTATION_MAX_PAGES: int = 300
    # Page dimensions in PDF points (1/72 inch). 20000pt ≈ 278in per side —
    # generous enough for any real-world slide deck or poster, but bounds a
    # pathological/malicious PDF's MediaBox from blowing up render memory.
    PRESENTATION_MAX_PAGE_DIMENSION_PT: float = 20000.0
    # Pagination defaults for list endpoints (Events, Sessions)
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # ── Rate limiting ─────────────────────────────────────────────────
    # All limits below are fixed-window (app/rate_limit.py), keyed by
    # (client IP, session code) for join/WS-connect and by (client IP,
    # slide ID) for responses — see app/routers/sessions.py::join_session
    # and app/routers/ws.py::websocket_endpoint. That per-session/per-slide
    # scoping (added alongside this round of limit increases) is what makes
    # a generous budget safe: it bounds abuse against ONE target session/
    # slide, rather than one shared blanket bucket for every session a given
    # IP happens to touch.
    #
    # Sized for one live workshop of ~500 guests behind a single venue/NAT
    # IP joining/connecting within roughly the same 30-60s window: 600 per
    # 60s covers the full 500-guest burst with ~20% headroom in a single
    # window, while still bounding a script hammering one specific session.
    # Raise further via env for a single-IP audience larger than ~500-600.
    JOIN_RATE_LIMIT: int = 600
    JOIN_RATE_LIMIT_WINDOW_SECONDS: int = 60
    WS_CONNECT_RATE_LIMIT: int = 600
    WS_CONNECT_RATE_WINDOW_SECONDS: int = 60
    # Per-guest-identifier and per-IP caps on response submissions (guest
    # identifier is client-supplied, so the per-IP cap exists to stop
    # identifier-rotation abuse — see app/routers/responses.py). The per-IP
    # key is already scoped per slide_id (finer-grained than per-session),
    # so this cap only needs headroom for one slide's worth of a single
    # workshop's burst, not the whole app: ~500 responses over ~30s, same
    # 20%-headroom sizing as above.
    RESPONSE_RATE_LIMIT_PER_GUEST: int = 10
    RESPONSE_RATE_LIMIT_PER_GUEST_WINDOW_SECONDS: int = 60
    RESPONSE_RATE_LIMIT_PER_IP: int = 600
    RESPONSE_RATE_LIMIT_PER_IP_WINDOW_SECONDS: int = 60

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        missing = [str(err["loc"][0]) for err in exc.errors() if err["type"] == "missing"]
        if missing:
            raise RuntimeError(
                "Missing required environment variable(s): " + ", ".join(missing) + ". "
                "Copy .env.example to .env and set them (see README's "
                "'Environment Configuration for Production' section) before starting the app."
            ) from exc
        raise
