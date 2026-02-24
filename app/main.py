from contextlib import asynccontextmanager
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.config import get_settings
from app.database import engine
from app.routers import auth, responses, sessions, slides, ws, polls, qna, feedback

# Ensure the 'rforum' directory is in PYTHONPATH
sys.path.append(str(Path(__file__).resolve().parent.parent))

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────
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
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Uploads are served through the /page/{page_num} endpoint — not as raw static files

# ── Register routers ─────────────────────────────────
app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(slides.router)
app.include_router(responses.router)
app.include_router(ws.router)
app.include_router(polls.router)
app.include_router(qna.router)
app.include_router(feedback.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "rforum"}
