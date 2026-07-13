import logging
from contextlib import asynccontextmanager
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from redis.asyncio import Redis

from app.config import get_settings
from app.database import engine
from app.routers import auth, responses, sessions, slides, ws, events, analytics
from app.routers import admin, session_assets, presentations

# Ensure the 'rforum' directory is in PYTHONPATH
sys.path.append(str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()


def _log_startup_capabilities() -> None:
    """Log conversion and rendering capability at startup."""
    from app.services.file_processing import libreoffice_status
    import fitz

    lo = libreoffice_status()
    if lo["available"]:
        logger.info("[startup] LibreOffice: AVAILABLE at '%s'. PPT/PPTX→PDF conversion enabled.", lo["path"])
    else:
        logger.warning(
            "[startup] LibreOffice: NOT FOUND. "
            "PPT/PPTX files will render via PyMuPDF fallback (page counts may vary). "
            "To enable full conversion: apt-get install -y libreoffice-headless"
        )

    logger.info("[startup] PyMuPDF (fitz) version: %s — PDF/PPTX/DOCX rendering available.", fitz.version[0])


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────
    _log_startup_capabilities()
    app.state.redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    yield
    # ── Shutdown ──────────────────────────────────────
    await app.state.redis.close()
    await engine.dispose()


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Uploads are served through the /page/{page_num} endpoint — not as raw static files

# ── Register routers ─────────────────────────────────
app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(slides.router)
app.include_router(responses.router)
app.include_router(events.router)
app.include_router(analytics.router)
app.include_router(ws.router)
app.include_router(admin.router)
app.include_router(session_assets.router)
app.include_router(presentations.router)


@app.get("/api/health")
async def health():
    from app.services.file_processing import libreoffice_status
    lo = libreoffice_status()
    return {
        "status": "ok",
        "service": "rforum",
        "capabilities": {
            "pdf_rendering": True,
            "pptx_conversion": lo["available"],
            "conversion_note": lo["message"],
        },
    }
