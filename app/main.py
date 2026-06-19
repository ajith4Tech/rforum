from contextlib import asynccontextmanager
import logging
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from redis.asyncio import Redis
from sqlalchemy import select

from app.config import get_settings
from app.database import engine, async_session
from app.middleware import RequestTracingMiddleware, configure_json_logging
from app.routers import auth, responses, sessions, slides, ws, events, analytics
from app.routers import admin, session_assets, settings
from app.tasks import task_queue

sys.path.append(str(Path(__file__).resolve().parent.parent))

configure_json_logging()
logger = logging.getLogger("rforum.main")
_settings = get_settings()


# ── Startup validation ────────────────────────────────────────────────────────

def _validate_settings(s) -> None:
    if s.SECRET_KEY == "change-me-in-production-use-a-real-secret":
        raise SystemExit(
            "\n\nRforum startup aborted.\n"
            "  • SECRET_KEY is the insecure placeholder.\n"
            "  • Generate one: python -c \"import secrets; print(secrets.token_hex(32))\"\n"
            "  • Set it in your .env file and restart.\n"
        )


# ── System settings init ──────────────────────────────────────────────────────

async def _ensure_system_settings() -> None:
    from app.models import SystemSettings
    async with async_session() as db:
        result = await db.execute(select(SystemSettings).where(SystemSettings.id == 1))
        if result.scalar_one_or_none() is None:
            db.add(SystemSettings())
            await db.commit()
            logger.info("system_settings_initialized")


# ── Application lifespan ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_settings(_settings)
    app.state.redis = Redis.from_url(_settings.REDIS_URL, decode_responses=True)
    await _ensure_system_settings()
    task_queue.start()
    logger.info("startup_complete", extra={"service": "rforum"})
    yield
    await task_queue.stop()
    await app.state.redis.close()
    await engine.dispose()
    logger.info("shutdown_complete", extra={"service": "rforum"})


# ── Application ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Rforum",
    description="Real-time audience engagement platform",
    version="1.0.0",
    lifespan=lifespan,
    default_response_class=ORJSONResponse,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# Middleware — outermost first (last added = outermost wrapper).
# Order: RequestTracing (outer) → CORS → routes
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Trace-ID"],
    expose_headers=["X-Trace-ID"],
)
app.add_middleware(RequestTracingMiddleware)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(settings.router)
app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(slides.router)
app.include_router(responses.router)
app.include_router(events.router)
app.include_router(analytics.router)
app.include_router(ws.router)
app.include_router(admin.router)
app.include_router(session_assets.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "rforum"}
