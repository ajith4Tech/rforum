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

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
