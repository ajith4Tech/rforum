from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=10,
    # Recycle pooled connections that have been open this long. Not a
    # capacity change (pool_size/max_overflow are already sized correctly for
    # 2 workers against Postgres's default max_connections=100 — see infra
    # audit) — this only guards against a connection going stale over a
    # multi-hour live workshop with uneven idle/burst traffic patterns.
    pool_recycle=1800,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session
