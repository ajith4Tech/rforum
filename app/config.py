from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://rforum:rforum@db:5432/rforum"
    REDIS_URL: str = "redis://redis:6379/0"
    SECRET_KEY: str = "change-me-in-production-use-a-real-secret"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",  # SvelteKit dev server
        "http://localhost:3000",  # React dev server
        "http://localhost:4173",  # SvelteKit preview
        "http://localhost:8080",
        "http://localhost:8000",  # Vite preview
        "http://127.0.0.1:5173",
        "http://127.0.0.1:4173",
        "http://127.0.0.1:8080",
        "http://13.50.245.253:5173",  # deployed frontend
        "http://13.50.245.253",
        "https://13.50.245.253",
    ]

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
