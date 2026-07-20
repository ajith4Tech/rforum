from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://rforum:rforum@db:5433/rforum"
    REDIS_URL: str = "redis://redis:6379/0"
    SECRET_KEY: str = "change-me-in-production-use-a-real-secret"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    INVITE_CODE: str = "RFORUM01"  # Override via INVITE_CODE env var
    CORS_ORIGINS: list[str] = [
    "https://rforum.t4gc.in",
    ]
    # Super admin: set this env var to auto-promote a user on registration
    SUPER_ADMIN_EMAIL: str = ""
    # Upload settings
    UPLOAD_MAX_MB: int = 20  # Maximum upload file size in MB
    UPLOAD_ALLOWED_EXTENSIONS: list[str] = [
        ".pdf", ".ppt", ".pptx", ".doc", ".docx", ".txt", ".odp", ".odt"
    ]
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
    # every key the app builds already starts with "presentations/" (see
    # app/storage/keys.py), so a non-empty default here would double it up
    # into s3://bucket/presentations/presentations/... Only set this to add an
    # *additional* segment above that (e.g. a per-environment namespace).
    S3_PREFIX: str = ""
    AWS_ACCESS_KEY_ID: str = ""  # empty = fall back to boto3's default credential chain
    AWS_SECRET_ACCESS_KEY: str = ""
    S3_MAX_RETRIES: int = 3
    USE_PRESIGNED_URLS: bool = False  # reserved — not yet implemented, backend still proxies bytes
    PRESENTATION_ORPHAN_RETENTION_DAYS: int = 7
    # Pagination defaults for list endpoints (Events, Sessions)
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
