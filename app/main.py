import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
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


# asyncio's default executor caps at min(32, cpu_count + 4) threads — 6 on a
# 2-vCPU host. Every storage.read()/exists()/save() call (presentation page
# serving, uploads) runs on this executor via asyncio.to_thread, and those
# calls block on network I/O (S3) or disk, not CPU — a blocked thread costs
# negligible RSS beyond its stack, so raising the pool is safe on this host's
# memory budget. Sized for "hundreds of guests requesting the same page at
# once" without being a large/unbounded pool.
STORAGE_IO_EXECUTOR_WORKERS = 24


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────
    _log_startup_capabilities()
    storage_io_executor = ThreadPoolExecutor(
        max_workers=STORAGE_IO_EXECUTOR_WORKERS, thread_name_prefix="storage-io"
    )
    asyncio.get_running_loop().set_default_executor(storage_io_executor)
    app.state.redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    yield
    # ── Shutdown ──────────────────────────────────────
    await app.state.redis.close()
    await engine.dispose()
    # wait=False: don't block process shutdown on an in-flight blocking S3/disk
    # call — threads can't be forcibly interrupted, and systemd already expects
    # a fast stop (Restart=always). cancel_futures drops only queued-but-not-
    # yet-started work, not anything already running.
    storage_io_executor.shutdown(wait=False, cancel_futures=True)


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
