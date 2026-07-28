"""
Presentation-first architecture: upload/replace/regenerate a Presentation,
manage its PresentationTimeline (interleaved pages + interactions), and serve
rendered page images/thumbnails.

Interaction timeline items are backed by ordinary `Slide` rows (same
session_id/type/content_json shape as the legacy slide list) so Response
storage, analytics, and PDF export need zero changes — see app/models.py for
the full rationale. `Slide.is_active` remains the single gate
`responses.py::submit_response` checks, so every mutation here that changes
`active_timeline_item_id` keeps it in sync.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import json

from app.auth import get_current_user
from app.config import get_settings
from app.database import get_db
from app.rate_limit import check_rate_limit
from app.models import (
    Event,
    Presentation,
    PresentationPage,
    PresentationSourceFormat,
    PresentationStatus,
    PresentationTimeline,
    PresentationTimelineItem,
    Session,
    SessionAsset,
    Slide,
    SlideType,
    TimelineItemType,
    User,
    UserRole,
)
from app.schemas import (
    PresentationAttachedSessionOut,
    PresentationDetailsOut,
    PresentationLibraryOut,
    PresentationOut,
    PresentationUploadOut,
    PresentationWithTimelineOut,
    TimelineItemCreate,
    TimelineItemOut,
    TimelineItemUpdate,
    TimelineOut,
    TimelineReorderPayload,
)
from app.services.file_processing import (
    check_content_length,
    check_render_limits,
    compute_checksum,
    convert_to_pdf_bytes,
    extract_page_count_and_size,
    render_all_thumbnails,
    render_page,
    validate_upload,
)
from app.storage import get_storage_backend, run_in_storage_executor
from app.storage.keys import (
    dir_prefix_from_known_key,
    original_key,
    page_key,
    pdf_key_for_dir,
    thumbnail_key,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["presentations"])

# Deck upload/replace/regenerate run LibreOffice + PyMuPDF and are the most
# expensive requests in the app — rate-limited per user like every other
# credential/resource-adjacent endpoint (login, register, join).
PRESENTATION_WRITE_RATE_LIMIT = 10
PRESENTATION_WRITE_RATE_WINDOW_SECONDS = 60

_EXT_TO_SOURCE_FORMAT: dict[str, PresentationSourceFormat] = {
    ".pdf": PresentationSourceFormat.PDF,
    ".ppt": PresentationSourceFormat.PPT,
    ".pptx": PresentationSourceFormat.PPTX,
}
_ALLOWED_PRESENTATION_EXTENSIONS = list(_EXT_TO_SOURCE_FORMAT.keys())

# Rating is a builder/timeline-level concept only — it's stored as a FEEDBACK
# slide with content_json.mode="rating_only" so the existing rating analytics
# (avg_rating / rating_distribution / PDF export) pick it up with zero changes.
_INTERACTION_TYPE_TO_SLIDE_TYPE: dict[TimelineItemType, SlideType] = {
    TimelineItemType.POLL: SlideType.POLL,
    TimelineItemType.QNA: SlideType.QNA,
    TimelineItemType.WORD_CLOUD: SlideType.WORD_CLOUD,
    TimelineItemType.FEEDBACK: SlideType.FEEDBACK,
    TimelineItemType.RATING: SlideType.FEEDBACK,
}


# ── Helpers ─────────────────────────────────────────────────────────────────

async def _verify_ownership(session_id: str, user: User, db: AsyncSession) -> Session:
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session ID format")

    query = select(Session).where(Session.id == session_uuid)
    if user.role != UserRole.SUPER_ADMIN:
        query = query.where(Session.owner_id == user.id)
    result = await db.execute(query)
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


async def _get_timeline_for_session(db: AsyncSession, session_id: uuid.UUID) -> PresentationTimeline:
    # populate_existing forces relationship collections to reload from the DB
    # even if this PresentationTimeline is already in the session's identity
    # map from an earlier query in the same request (e.g. replace_presentation
    # calls this twice) — without it, `.items` would silently keep returning
    # the first call's stale snapshot instead of reflecting inserts/deletes.
    result = await db.execute(
        select(PresentationTimeline)
        .where(PresentationTimeline.session_id == session_id)
        .options(
            selectinload(PresentationTimeline.items).selectinload(PresentationTimelineItem.page),
            selectinload(PresentationTimeline.items).selectinload(PresentationTimelineItem.slide),
        )
        .execution_options(populate_existing=True)
    )
    timeline = result.scalar_one_or_none()
    if not timeline:
        raise HTTPException(status_code=404, detail="Session has no presentation timeline")
    timeline.items.sort(key=lambda i: i.order)
    return timeline


async def _get_owned_item(
    db: AsyncSession, session: Session, item_id: str
) -> PresentationTimelineItem:
    try:
        item_uuid = uuid.UUID(item_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid item ID format")

    result = await db.execute(
        select(PresentationTimelineItem)
        .join(PresentationTimeline, PresentationTimeline.id == PresentationTimelineItem.timeline_id)
        .where(
            PresentationTimelineItem.id == item_uuid,
            PresentationTimeline.session_id == session.id,
        )
        .options(
            selectinload(PresentationTimelineItem.page),
            selectinload(PresentationTimelineItem.slide),
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Timeline item not found")
    return item


async def _process_upload(
    file: UploadFile, user: User, db: AsyncSession, request: Request | None = None
) -> tuple[Presentation, bool]:
    """
    Validate an uploaded deck and turn it into a Presentation + its
    PresentationPage rows. Returns (presentation, was_duplicate). Two paths:

    - Duplicate upload (same owner, same sha256): returns the existing READY
      Presentation untouched — no re-render, no re-storage. This is what
      makes "upload the same file to a second session" reuse the asset
      instead of creating a fifth copy of it on disk.
    - New content: renders THUMBNAILS ONLY (cheap, needed immediately by the
      builder grid) and stores them + the original. Full-resolution pages are
      rendered lazily on first view — see _serve_page_file below — so upload
      stays fast even for 100+ page decks. Nothing is written to storage
      until rendering has already succeeded, so a render failure leaves no
      orphaned files behind.
    """
    settings = get_settings()
    max_bytes = settings.UPLOAD_MAX_MB * 1024 * 1024
    if request is not None:
        try:
            check_content_length(request.headers.get("content-length"), max_bytes)
        except ValueError as exc:
            raise HTTPException(status_code=413, detail=str(exc))

    original_name = Path(file.filename or "presentation.pdf").name or "presentation.pdf"
    ext = Path(original_name).suffix.lower()
    if ext not in _EXT_TO_SOURCE_FORMAT:
        allowed = ", ".join(_ALLOWED_PRESENTATION_EXTENSIONS)
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported presentation format '{ext}'. Allowed: {allowed}",
        )

    content = await file.read()
    try:
        validation = validate_upload(
            content=content,
            original_name=original_name,
            allowed_extensions=_ALLOWED_PRESENTATION_EXTENSIONS,
            max_bytes=max_bytes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    checksum = await asyncio.to_thread(compute_checksum, content)
    dup_result = await db.execute(
        select(Presentation)
        .where(
            Presentation.owner_id == user.id,
            Presentation.checksum == checksum,
            Presentation.status == PresentationStatus.READY,
        )
        .order_by(Presentation.created_at.desc())
        .options(selectinload(Presentation.pages))
        .limit(1)
    )
    duplicate = dup_result.scalar_one_or_none()
    if duplicate is not None:
        logger.info(
            "Duplicate upload detected for owner=%s checksum=%s — reusing presentation %s",
            user.id, checksum, duplicate.id,
        )
        duplicate.orphaned_since = None
        duplicate.last_used_at = datetime.now(timezone.utc)
        return duplicate, True

    conversion_warnings: list[str] = []
    render_source = content
    render_ext = ext
    if ext in {".ppt", ".pptx"}:
        conversion = await asyncio.to_thread(convert_to_pdf_bytes, content, ext)
        conversion_warnings.extend(conversion.warnings)
        if conversion.success and conversion.output_bytes:
            render_source = conversion.output_bytes
            render_ext = ".pdf"

    page_count, (page_width, page_height), count_warnings = await asyncio.to_thread(
        extract_page_count_and_size, render_source, render_ext
    )
    conversion_warnings.extend(count_warnings)

    try:
        check_render_limits(
            page_count, page_width, page_height,
            max_pages=settings.PRESENTATION_MAX_PAGES,
            max_dimension_pt=settings.PRESENTATION_MAX_PAGE_DIMENSION_PT,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    thumbs, thumb_warnings = await asyncio.to_thread(render_all_thumbnails, render_source, render_ext)
    conversion_warnings.extend(thumb_warnings)
    if not thumbs:
        logger.warning(
            "Presentation render failed for owner=%s filename='%s': %s",
            user.id, original_name, conversion_warnings,
        )
        raise HTTPException(
            status_code=422,
            detail="Could not render any pages from the uploaded file. It may be corrupted or password-protected.",
        )

    presentation_id = uuid.uuid4()
    storage = get_storage_backend()
    orig_key = original_key(user.email, user.id, presentation_id, original_name)
    pres_dir = dir_prefix_from_known_key(orig_key, presentation_id)

    await asyncio.to_thread(storage.save, orig_key, content)
    if render_ext == ".pdf" and ext != ".pdf":
        # Persist the PPT/PPTX -> PDF conversion so regenerate and lazy page
        # rendering don't have to re-run LibreOffice on every cache miss.
        await asyncio.to_thread(storage.save, pdf_key_for_dir(pres_dir), render_source)
    for i, thumb_bytes in enumerate(thumbs, start=1):
        await asyncio.to_thread(
            storage.save, thumbnail_key(user.email, user.id, presentation_id, i), thumb_bytes
        )

    presentation = Presentation(
        id=presentation_id,
        owner_id=user.id,
        original_file_name=original_name,
        original_file_url=orig_key,
        original_file_type=validation.actual_mime,
        original_file_size=len(content),
        source_format=_EXT_TO_SOURCE_FORMAT[ext],
        status=PresentationStatus.READY,
        page_count=len(thumbs),
        checksum=checksum,
        page_width=page_width,
        page_height=page_height,
        conversion_warnings=conversion_warnings,
        last_used_at=datetime.now(timezone.utc),
    )
    db.add(presentation)
    await db.flush()

    for i in range(1, len(thumbs) + 1):
        db.add(
            PresentationPage(
                presentation_id=presentation.id,
                page_number=i,
                image_url=page_key(user.email, user.id, presentation_id, i),
                thumbnail_url=thumbnail_key(user.email, user.id, presentation_id, i),
            )
        )
    await db.flush()
    await db.refresh(presentation, attribute_names=["pages"])
    return presentation, False


async def _build_timeline_for_presentation(
    db: AsyncSession, session: Session, presentation: Presentation
) -> PresentationTimeline:
    """Create a fresh PresentationTimeline (one PAGE item per page, in order)
    and attach `presentation` to `session`. Shared by upload and attach."""
    timeline = PresentationTimeline(session_id=session.id, presentation_id=presentation.id)
    db.add(timeline)
    await db.flush()

    pages_sorted = sorted(presentation.pages, key=lambda p: p.page_number)
    for i, page in enumerate(pages_sorted):
        db.add(
            PresentationTimelineItem(
                timeline_id=timeline.id,
                order=i,
                item_type=TimelineItemType.PAGE,
                presentation_page_id=page.id,
            )
        )

    session.presentation_id = presentation.id
    presentation.orphaned_since = None
    presentation.last_used_at = datetime.now(timezone.utc)
    await db.flush()
    return timeline


async def _publish_safe(redis: Redis, channel: str, message: str) -> None:
    """Best-effort Redis publish for live WS updates, called after the DB
    write it announces has already committed — same fail-open policy as
    check_rate_limit (app/rate_limit.py) and app/routers/responses.py, so a
    transient Redis blip doesn't turn an already-successful mutation into a
    client-visible 500."""
    try:
        await redis.publish(channel, message)
    except RedisError:
        logger.warning("redis_publish_failed channel=%s", channel, exc_info=True)


async def _check_presentation_write_rate_limit(request: Request, user: User) -> None:
    redis: Redis = request.app.state.redis
    allowed = await check_rate_limit(
        redis,
        f"rate:presentation_write:{user.id}",
        PRESENTATION_WRITE_RATE_LIMIT,
        PRESENTATION_WRITE_RATE_WINDOW_SECONDS,
    )
    if not allowed:
        raise HTTPException(status_code=429, detail="Too many attempts. Please slow down.")


async def _presentation_visible_via_event(
    db: AsyncSession, user: User, presentation_id: uuid.UUID, event_id: uuid.UUID | None = None
) -> bool:
    """True if `presentation_id` is READY and currently attached to a session
    in an event the caller owns (or, if `event_id` is given, specifically that
    event) — the same widening rule list_my_presentations applies so a caller
    can act on a co-organizer's deck they were shown in the event-scoped
    "Choose Existing Presentation" picker, without granting access to decks
    they were never shown."""
    query = (
        select(Presentation.id)
        .join(Session, Session.presentation_id == Presentation.id)
        .join(Event, Event.id == Session.event_id)
        .where(
            Presentation.id == presentation_id,
            Presentation.status == PresentationStatus.READY,
            Event.owner_id == user.id,
        )
    )
    if event_id is not None:
        query = query.where(Event.id == event_id)
    result = await db.execute(query.limit(1))
    return result.scalar_one_or_none() is not None


async def _is_presentation_referenced(
    db: AsyncSession, presentation_id: uuid.UUID, exclude_session_id: uuid.UUID | None = None
) -> bool:
    """True if any Session currently has this presentation attached
    (Session.presentation_id is the live reference pointer — no separate
    join table needed, a Presentation can be attached to more than one
    session)."""
    query = select(Session.id).where(Session.presentation_id == presentation_id)
    if exclude_session_id is not None:
        query = query.where(Session.id != exclude_session_id)
    result = await db.execute(query.limit(1))
    return result.scalar_one_or_none() is not None


def _new_asset_for_presentation(user: User, session: Session, presentation: Presentation) -> SessionAsset:
    return SessionAsset(
        user_id=user.id,
        session_id=session.id,
        event_id=session.event_id,
        presentation_id=presentation.id,
        file_name=presentation.original_file_name,
        file_url=presentation.original_file_url,
        file_type=presentation.original_file_type,
        file_size=presentation.original_file_size,
    )


def _distribute_interactions_among_pages(
    n_pages: int, interactions: list[PresentationTimelineItem]
) -> list[tuple[str, int]]:
    """
    Interleave `interactions` (kept in their existing relative order) evenly
    among `n_pages` fresh pages. Returns an ordered list of ("page", page_index)
    / ("interaction", interaction_index) tuples describing the new sequence.
    """
    n = len(interactions)
    if n == 0:
        return [("page", i) for i in range(n_pages)]

    assign: dict[int, list[int]] = {}
    for k in range(n):
        gap = round((k + 1) * n_pages / (n + 1))
        assign.setdefault(gap, []).append(k)

    plan: list[tuple[str, int]] = []
    for gap in range(n_pages + 1):
        if gap > 0:
            plan.append(("page", gap - 1))
        for k in assign.get(gap, []):
            plan.append(("interaction", k))
    return plan


def _load_render_source(storage, presentation: Presentation) -> tuple[bytes, str]:
    """Return (bytes, ext) to feed into render_page/render_all_thumbnails for
    `presentation`. PPT/PPTX decks are converted to PDF once and the result is
    cached at pdf/presentation.pdf (see pdf_key_for_dir) — a cache hit skips
    the LibreOffice conversion entirely; a miss converts, persists, and
    returns the fresh PDF. Every other source format renders straight from
    the original file."""
    ext = Path(presentation.original_file_name).suffix.lower()
    if ext not in {".ppt", ".pptx"}:
        return storage.read(presentation.original_file_url), ext

    pdf_cache_key = pdf_key_for_dir(
        dir_prefix_from_known_key(presentation.original_file_url, presentation.id)
    )
    if storage.exists(pdf_cache_key):
        return storage.read(pdf_cache_key), ".pdf"

    original_bytes = storage.read(presentation.original_file_url)
    conversion = convert_to_pdf_bytes(original_bytes, ext)
    if conversion.success and conversion.output_bytes:
        storage.save(pdf_cache_key, conversion.output_bytes)
        return conversion.output_bytes, ".pdf"
    return original_bytes, ext


# Coalesces concurrent lazy-render requests for the same (presentation, page)
# onto a single render instead of every simultaneously-requesting guest (e.g.
# hundreds viewing a slide the instant it's activated) independently invoking
# LibreOffice/PyMuPDF and re-saving the same storage key. Keyed per-process —
# with 2 Uvicorn workers this means at most one redundant render per worker
# instead of one per guest, without introducing cross-process coordination.
# Never cleaned up, but the key space is bounded by total (presentation, page)
# pairs ever viewed, which stays small for the lifetime of a process.
_page_render_locks: dict[tuple[uuid.UUID, int, bool], asyncio.Lock] = {}


def _get_page_render_lock(key: tuple[uuid.UUID, int, bool]) -> asyncio.Lock:
    lock = _page_render_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _page_render_locks[key] = lock
    return lock


async def _serve_page_file(presentation_id: str, page_number: int, thumbnail: bool, db: AsyncSession):
    """
    Serve a rendered page. Thumbnails are always eagerly created at upload
    time (missing = a data problem, 404). Full-resolution pages are rendered
    lazily on first request and cached to disk permanently — every request
    after the first is a straight cache read. The URL is not content-addressed
    and `regenerate_presentation` can replace the bytes behind it in place, so
    the response is NOT marked immutable — max-age is bounded so a client that
    cached the pre-regenerate image picks up the new one within a day.
    """
    try:
        pres_uuid = uuid.UUID(presentation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid presentation ID format")

    result = await db.execute(
        select(PresentationPage).where(
            PresentationPage.presentation_id == pres_uuid,
            PresentationPage.page_number == page_number,
        )
    )
    page = result.scalar_one_or_none()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    # Release the pooled connection now: FastAPI's request-scoped session
    # otherwise keeps it checked out for the rest of this function, including
    # the storage read/lock-wait/render below — under hundreds of concurrent
    # requests for the same page, that would multiply Postgres connection
    # usage far past pool_size for no reason, since nothing here needs the DB
    # again except the rare cache-miss path (which re-acquires as needed).
    # Safe with expire_on_commit=False (app/database.py): `page`'s already-
    # loaded attributes stay usable after commit.
    await db.commit()

    key = page.thumbnail_url if thumbnail else page.image_url
    storage = get_storage_backend()

    # Read directly rather than exists()-then-read(): the steady-state case
    # (page already rendered/cached) is one storage round trip instead of
    # two — for an S3 backend that's one GET instead of a HEAD+GET pair,
    # which matters when hundreds of guests request the same page at once.
    #
    # Uses the dedicated storage-I/O executor (app/storage/__init__.py), not
    # asyncio.to_thread()'s shared default one — see STORAGE_IO_CONCURRENCY's
    # docstring for why: the default executor's ~6 threads (2-vCPU host)
    # queue hundreds of concurrent reads for this exact hot path badly
    # enough to produce multi-second tail latency and, past that, timeouts.
    try:
        img_bytes = await run_in_storage_executor(storage.read, key)
    except FileNotFoundError:
        if thumbnail:
            raise HTTPException(status_code=404, detail="Thumbnail not found on disk")

        lock = _get_page_render_lock((pres_uuid, page_number, thumbnail))
        async with lock:
            # Re-check after acquiring the lock: whoever held it first may
            # have already rendered and saved this exact page while we waited.
            try:
                img_bytes = await run_in_storage_executor(storage.read, key)
            except FileNotFoundError:
                presentation = await db.get(Presentation, page.presentation_id)
                await db.commit()  # same reasoning as above — release before the render itself
                if presentation is None or not await run_in_storage_executor(
                    storage.exists, presentation.original_file_url
                ):
                    raise HTTPException(status_code=404, detail="Original file not found on disk")

                # Unlike the read()s above, nothing catches FileNotFoundError/
                # PermissionError/ConnectionError here on their own — left
                # unhandled, a storage hiccup surfaces as a raw 500 instead
                # of a meaningful status. FileNotFoundError can reach here
                # for real (e.g. the original was deleted from storage after
                # this page's row was created); PermissionError/
                # ConnectionError are FallbackStorageBackend's signal that
                # even its local-disk fallback didn't have this key either
                # (see app/storage/fallback.py) — genuinely transient/infra,
                # not a bad request, hence 503 rather than 404/422.
                try:
                    render_source, render_ext = await run_in_storage_executor(
                        _load_render_source, storage, presentation
                    )
                except FileNotFoundError:
                    raise HTTPException(status_code=404, detail="Original file not found in storage")
                except (PermissionError, ConnectionError) as exc:
                    logger.error(
                        "Storage unavailable while loading render source. presentation=%s page=%d error=%s",
                        presentation_id, page_number, exc, exc_info=True,
                    )
                    raise HTTPException(
                        status_code=503,
                        detail="Storage is temporarily unavailable. Please try again shortly.",
                    )

                try:
                    img_bytes = await run_in_storage_executor(render_page, render_source, render_ext, page_number)
                except Exception as exc:
                    logger.error(
                        "Lazy page render failed. presentation=%s page=%d error=%s",
                        presentation_id, page_number, exc, exc_info=True,
                    )
                    raise HTTPException(
                        status_code=422,
                        detail="Could not render this page. The file may be corrupted.",
                    )

                try:
                    await run_in_storage_executor(storage.save, key, img_bytes)
                except (PermissionError, ConnectionError) as exc:
                    # img_bytes already rendered successfully — serve it now
                    # rather than fail a request over a cache-write hiccup.
                    # The next request just re-renders (self-healing); no
                    # retry loop, no data loss beyond one skipped cache write.
                    logger.warning(
                        "Failed to cache rendered page (will retry on next request). "
                        "presentation=%s page=%d error=%s",
                        presentation_id, page_number, exc,
                    )

    media_type = "image/webp" if key.endswith(".webp") else "image/png"
    return StreamingResponse(
        BytesIO(img_bytes),
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            "Content-Disposition": "inline",
        },
    )


async def _sync_active_slide(db: AsyncSession, session_id: uuid.UUID, slide_id: uuid.UUID | None) -> None:
    """
    The single 'can guests respond' gate (app/routers/responses.py::submit_response
    hard-rejects unless Slide.is_active is true) must always mirror the timeline's
    current position. Clear every slide in the session, then activate at most one.
    """
    await db.execute(update(Slide).where(Slide.session_id == session_id).values(is_active=False))
    if slide_id is not None:
        await db.execute(update(Slide).where(Slide.id == slide_id).values(is_active=True))


# ── Upload / Replace / Regenerate ────────────────────────────────────────────

@router.post(
    "/api/sessions/{session_id}/presentation/upload",
    response_model=PresentationUploadOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_presentation(
    session_id: str,
    file: UploadFile,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _verify_ownership(session_id, user, db)
    await _check_presentation_write_rate_limit(request, user)
    if session.presentation_id is not None:
        raise HTTPException(
            status_code=409, detail="Session already has a presentation — use replace instead"
        )

    presentation, reused_existing = await _process_upload(file, user, db, request)
    await _build_timeline_for_presentation(db, session, presentation)
    db.add(_new_asset_for_presentation(user, session, presentation))

    try:
        await db.commit()
    except IntegrityError:
        # A concurrent upload/attach for this same (presentation-less) session
        # won the race between our check above and this commit — same
        # conflict the check is meant to prevent (PresentationTimeline.session_id
        # is unique).
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="Session already has a presentation — use replace instead"
        )
    timeline = await _get_timeline_for_session(db, session.id)
    return {"presentation": presentation, "timeline": timeline, "reused_existing": reused_existing}


@router.post(
    "/api/sessions/{session_id}/presentation/replace",
    response_model=PresentationUploadOut,
)
async def replace_presentation(
    session_id: str,
    file: UploadFile,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _verify_ownership(session_id, user, db)
    await _check_presentation_write_rate_limit(request, user)
    if session.presentation_id is None:
        raise HTTPException(status_code=404, detail="Session has no presentation to replace")

    old_presentation_id = session.presentation_id
    timeline = await _get_timeline_for_session(db, session.id)

    new_presentation, reused_existing = await _process_upload(file, user, db, request)
    if new_presentation.id == old_presentation_id:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is identical to the current presentation.",
        )
    new_presentation.replaces_presentation_id = old_presentation_id

    # Check reference before mutating session.presentation_id below, so this
    # reflects "is anything OTHER than this session still using the old one."
    old_referenced_elsewhere = await _is_presentation_referenced(
        db, old_presentation_id, exclude_session_id=session.id
    )

    interaction_items = [i for i in timeline.items if i.item_type != TimelineItemType.PAGE]
    old_page_items = [i for i in timeline.items if i.item_type == TimelineItemType.PAGE]
    # ORM-level delete (not a bulk Core delete) so these objects are properly
    # removed from the session's identity map — a bulk `delete()` statement
    # would leave them cached and reappear in the very next selectinload query.
    for old_item in old_page_items:
        await db.delete(old_item)
    await db.flush()

    new_pages = sorted(new_presentation.pages, key=lambda p: p.page_number)
    plan = _distribute_interactions_among_pages(len(new_pages), interaction_items)

    for order_idx, (kind, idx) in enumerate(plan):
        if kind == "page":
            db.add(
                PresentationTimelineItem(
                    timeline_id=timeline.id,
                    order=order_idx,
                    item_type=TimelineItemType.PAGE,
                    presentation_page_id=new_pages[idx].id,
                )
            )
        else:
            interaction_items[idx].order = order_idx

    timeline.presentation_id = new_presentation.id
    timeline.active_timeline_item_id = None
    session.presentation_id = new_presentation.id
    new_presentation.orphaned_since = None
    await _sync_active_slide(db, session.id, None)

    db.add(_new_asset_for_presentation(user, session, new_presentation))

    # The old presentation is a reusable asset — replacing it here must not
    # delete it outright. If nothing else references it, mark it orphaned;
    # the cleanup script deletes it only after the retention window elapses,
    # giving a grace period to recover from an accidental replace.
    if not old_referenced_elsewhere:
        old_presentation = await db.get(Presentation, old_presentation_id)
        if old_presentation is not None and old_presentation.orphaned_since is None:
            old_presentation.orphaned_since = datetime.now(timezone.utc)

    await db.commit()
    refreshed_timeline = await _get_timeline_for_session(db, session.id)
    return {
        "presentation": new_presentation,
        "timeline": refreshed_timeline,
        "reused_existing": reused_existing,
    }


@router.post(
    "/api/sessions/{session_id}/presentation/regenerate",
    response_model=PresentationOut,
)
async def regenerate_presentation(
    session_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Re-render from the stored original file in place — does not restructure
    the timeline. Use Replace to change the deck itself.

    Thumbnails are re-rendered eagerly (cheap, needed immediately by the
    builder grid). Full-resolution pages are NOT re-rendered here — instead
    their cached files are invalidated (deleted) so they lazily re-render
    with the fresh content on next view, same as a first-time upload.
    """
    session = await _verify_ownership(session_id, user, db)
    await _check_presentation_write_rate_limit(request, user)
    if session.presentation_id is None:
        raise HTTPException(status_code=404, detail="Session has no presentation")

    result = await db.execute(
        select(Presentation)
        .where(Presentation.id == session.presentation_id)
        .options(selectinload(Presentation.pages))
    )
    presentation = result.scalar_one()
    # Regenerating overwrites this presentation's stored render artifacts in
    # place, affecting every other session/event that references the same
    # (potentially shared, event-visible) Presentation row — unlike attach,
    # which only links, this requires actual ownership, not just visibility.
    if user.role != UserRole.SUPER_ADMIN and presentation.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Presentation not found")

    storage = get_storage_backend()
    if not await asyncio.to_thread(storage.exists, presentation.original_file_url):
        raise HTTPException(status_code=404, detail="Original file not found on disk")
    render_source, render_ext = await asyncio.to_thread(_load_render_source, storage, presentation)

    thumbs, warnings = await asyncio.to_thread(render_all_thumbnails, render_source, render_ext)
    if warnings:
        logger.warning("Regenerate warnings for presentation %s: %s", presentation.id, warnings)
    if not thumbs:
        raise HTTPException(
            status_code=422,
            detail="Regeneration failed — could not render any pages from the stored file.",
        )

    if len(thumbs) != presentation.page_count:
        logger.warning(
            "Regenerate produced a different page count for presentation %s (had %d, now %d) — "
            "existing timeline is left as-is; use Replace to restructure it.",
            presentation.id, presentation.page_count, len(thumbs),
        )

    pages_by_number = {p.page_number: p for p in presentation.pages}
    for i, thumb_bytes in enumerate(thumbs, start=1):
        page = pages_by_number.get(i)
        if not page:
            continue
        await asyncio.to_thread(storage.save, page.thumbnail_url, thumb_bytes)
        await asyncio.to_thread(storage.delete, page.image_url)  # invalidate cached full-res render — re-renders lazily

    presentation.status = PresentationStatus.READY
    await db.commit()
    await db.refresh(presentation, attribute_names=["pages"])
    return presentation


# ── Get full presentation + timeline (for the builder) ──────────────────────

@router.get(
    "/api/sessions/{session_id}/presentation",
    response_model=PresentationWithTimelineOut,
)
async def get_session_presentation(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _verify_ownership(session_id, user, db)
    if session.presentation_id is None:
        raise HTTPException(status_code=404, detail="Session has no presentation")

    result = await db.execute(
        select(Presentation)
        .where(Presentation.id == session.presentation_id)
        .options(selectinload(Presentation.pages))
    )
    presentation = result.scalar_one()
    timeline = await _get_timeline_for_session(db, session.id)
    return {"presentation": presentation, "timeline": timeline}


# ── Reusable-presentation lifecycle: detach / attach / library / delete ─────
#
# A Presentation is a reusable asset, not something owned exclusively by one
# session. Session.presentation_id is just "what's currently live here" —
# detaching clears that pointer without deleting the underlying Presentation,
# and attach lets a different (presentation-less) session point at an
# existing one. Deletion is only allowed once nothing references it anymore.

@router.post(
    "/api/sessions/{session_id}/presentation/detach",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def detach_presentation(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _verify_ownership(session_id, user, db)
    if session.presentation_id is None:
        raise HTTPException(status_code=404, detail="Session has no presentation")

    presentation_id = session.presentation_id
    timeline_result = await db.execute(
        select(PresentationTimeline).where(PresentationTimeline.session_id == session.id)
    )
    timeline = timeline_result.scalar_one_or_none()
    if timeline is not None:
        await db.delete(timeline)

    session.presentation_id = None
    await _sync_active_slide(db, session.id, None)
    await db.flush()

    if not await _is_presentation_referenced(db, presentation_id):
        presentation = await db.get(Presentation, presentation_id)
        if presentation is not None and presentation.orphaned_since is None:
            presentation.orphaned_since = datetime.now(timezone.utc)

    await db.commit()


@router.post(
    "/api/sessions/{session_id}/presentation/attach/{presentation_id}",
    response_model=PresentationWithTimelineOut,
)
async def attach_presentation(
    session_id: str,
    presentation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _verify_ownership(session_id, user, db)
    if session.presentation_id is not None:
        raise HTTPException(
            status_code=409, detail="Session already has a presentation — detach it first"
        )

    try:
        pres_uuid = uuid.UUID(presentation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid presentation ID format")

    result = await db.execute(
        select(Presentation)
        .where(Presentation.id == pres_uuid)
        .options(selectinload(Presentation.pages))
    )
    presentation = result.scalar_one_or_none()
    if not presentation:
        raise HTTPException(status_code=404, detail="Presentation not found")
    if (
        user.role != UserRole.SUPER_ADMIN
        and presentation.owner_id != user.id
        and not (
            session.event_id is not None
            and await _presentation_visible_via_event(db, user, presentation.id, session.event_id)
        )
    ):
        raise HTTPException(status_code=404, detail="Presentation not found")
    if presentation.status != PresentationStatus.READY:
        raise HTTPException(status_code=409, detail="Presentation is not ready")

    await _build_timeline_for_presentation(db, session, presentation)
    db.add(_new_asset_for_presentation(user, session, presentation))

    await db.commit()
    timeline = await _get_timeline_for_session(db, session.id)
    return {"presentation": presentation, "timeline": timeline}


@router.get("/api/presentations", response_model=list[PresentationLibraryOut])
async def list_my_presentations(
    event_id: str | None = None,
    search: str | None = None,
    sort: Literal["recent", "last_used", "name"] = "recent",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """A user's presentation library — every deck they own, whether currently
    attached to a session, detached, or mid-retention-window after a
    replace. Also the source for the "Choose Existing Presentation" picker:
    passing event_id widens the result to include READY decks already
    attached to any session in that event (owned by anyone), scoped — never
    a global cross-event library."""
    query = select(Presentation)

    if event_id is not None:
        try:
            event_uuid = uuid.UUID(event_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid event ID format")

        event_query = select(Event.id).where(Event.id == event_uuid)
        if user.role != UserRole.SUPER_ADMIN:
            event_query = event_query.where(Event.owner_id == user.id)
        event_exists = (await db.execute(event_query)).scalar_one_or_none()
        if event_exists is None:
            raise HTTPException(status_code=404, detail="Event not found")

        same_event_presentation_ids = select(Session.presentation_id).where(
            Session.event_id == event_uuid, Session.presentation_id.isnot(None)
        )
        query = query.where(
            or_(Presentation.owner_id == user.id, Presentation.id.in_(same_event_presentation_ids)),
            Presentation.status == PresentationStatus.READY,
        )
    elif user.role != UserRole.SUPER_ADMIN:
        query = query.where(Presentation.owner_id == user.id)

    if search:
        query = query.where(Presentation.original_file_name.ilike(f"%{search}%"))

    sort_column = {
        "recent": Presentation.created_at.desc(),
        "last_used": Presentation.last_used_at.desc().nulls_last(),
        "name": Presentation.original_file_name.asc(),
    }[sort]
    query = query.order_by(sort_column)

    result = await db.execute(query)
    presentations = result.scalars().all()

    # A Presentation may now be attached to more than one session; attached_session_id
    # is a convenience hint for the listing (storage_status below is the accurate
    # active/detached signal) — _is_presentation_referenced remains the source of
    # truth for "can this be deleted." Scoped to just the presentation ids we're
    # about to return — not every session on the platform.
    referenced_presentation_ids: set[uuid.UUID] = set()
    attached_session_by_presentation: dict[uuid.UUID, uuid.UUID] = {}
    presentation_ids = [p.id for p in presentations]
    if presentation_ids:
        sessions_result = await db.execute(
            select(Session.id, Session.presentation_id).where(
                Session.presentation_id.in_(presentation_ids)
            )
        )
        for row in sessions_result.all():
            referenced_presentation_ids.add(row.presentation_id)
            attached_session_by_presentation.setdefault(row.presentation_id, row.id)

    return [
        PresentationLibraryOut(
            id=p.id,
            original_file_name=p.original_file_name,
            page_count=p.page_count,
            status=p.status,
            orphaned_since=p.orphaned_since,
            last_used_at=p.last_used_at,
            attached_session_id=attached_session_by_presentation.get(p.id),
            storage_status="active" if p.id in referenced_presentation_ids else "detached",
            created_at=p.created_at,
        )
        for p in presentations
    ]


@router.get("/api/presentations/{presentation_id}/details", response_model=PresentationDetailsOut)
async def get_presentation_details(
    presentation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Rich details for the Presentation Details panel (currently-attached
    deck) and the Preview Dialog (a candidate deck in the reattach picker) —
    same endpoint, same ownership rule for both callers."""
    try:
        pres_uuid = uuid.UUID(presentation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid presentation ID format")

    result = await db.execute(
        select(Presentation, User.email)
        .join(User, User.id == Presentation.owner_id)
        .where(Presentation.id == pres_uuid)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Presentation not found")
    presentation, owner_email = row
    if (
        user.role != UserRole.SUPER_ADMIN
        and presentation.owner_id != user.id
        and not await _presentation_visible_via_event(db, user, presentation.id)
    ):
        raise HTTPException(status_code=404, detail="Presentation not found")

    sessions_result = await db.execute(
        select(Session.id, Session.title, Session.unique_code).where(
            Session.presentation_id == pres_uuid
        )
    )
    attached_sessions = [
        PresentationAttachedSessionOut(id=r.id, title=r.title, unique_code=r.unique_code)
        for r in sessions_result.all()
    ]

    return PresentationDetailsOut(
        id=presentation.id,
        owner_id=presentation.owner_id,
        owner_email=owner_email,
        original_file_name=presentation.original_file_name,
        original_file_size=presentation.original_file_size,
        original_file_type=presentation.original_file_type,
        source_format=presentation.source_format,
        status=presentation.status,
        page_count=presentation.page_count,
        conversion_warnings=presentation.conversion_warnings,
        checksum=presentation.checksum,
        orphaned_since=presentation.orphaned_since,
        last_used_at=presentation.last_used_at,
        created_at=presentation.created_at,
        attached_sessions=attached_sessions,
        storage_status="active" if attached_sessions else "detached",
    )


@router.get("/api/presentations/{presentation_id}/download")
async def download_presentation_original(
    presentation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        pres_uuid = uuid.UUID(presentation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid presentation ID format")

    query = select(Presentation).where(Presentation.id == pres_uuid)
    if user.role != UserRole.SUPER_ADMIN:
        query = query.where(Presentation.owner_id == user.id)
    result = await db.execute(query)
    presentation = result.scalar_one_or_none()
    if not presentation:
        raise HTTPException(status_code=404, detail="Presentation not found")

    storage = get_storage_backend()
    if not await asyncio.to_thread(storage.exists, presentation.original_file_url):
        raise HTTPException(status_code=404, detail="Original file not found on disk")
    content = await asyncio.to_thread(storage.read, presentation.original_file_url)

    return StreamingResponse(
        BytesIO(content),
        media_type=presentation.original_file_type,
        headers={
            "Content-Disposition": f'attachment; filename="{presentation.original_file_name}"'
        },
    )


@router.delete(
    "/api/presentations/{presentation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_presentation(
    presentation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        pres_uuid = uuid.UUID(presentation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid presentation ID format")

    query = select(Presentation).where(Presentation.id == pres_uuid)
    if user.role != UserRole.SUPER_ADMIN:
        query = query.where(Presentation.owner_id == user.id)
    result = await db.execute(query)
    presentation = result.scalar_one_or_none()
    if not presentation:
        raise HTTPException(status_code=404, detail="Presentation not found")

    if await _is_presentation_referenced(db, presentation.id):
        raise HTTPException(
            status_code=409,
            detail="Presentation is attached to a session — detach it first",
        )

    # dir_prefix_from_known_key derives this presentation's own root directory
    # (works for both the old flat-per-uuid disk layout and the new
    # owner-scoped one) by locating presentation.id as a literal path segment
    # — it raises rather than guess if that segment isn't found, so this can
    # never resolve to a shared/ancestor prefix another presentation also
    # lives under. delete_prefix below recursively removes everything under
    # it (original, pdf cache, thumbnails, pages, and any stray temp files) —
    # covering the exact same set of keys an explicit per-key delete loop
    # would, without the redundant extra round-trips.
    owner_dir_prefix = dir_prefix_from_known_key(presentation.original_file_url, presentation.id)

    try:
        await db.execute(delete(Presentation).where(Presentation.id == presentation.id))
        await db.commit()
    except IntegrityError:
        # A concurrent attach created a live reference between our check above
        # and this delete — same conflict the check is meant to prevent.
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Presentation is attached to a session — detach it first",
        )

    storage = get_storage_backend()
    await asyncio.to_thread(storage.delete_prefix, owner_dir_prefix)


# ── Timeline item CRUD ────────────────────────────────────────────────────────

@router.post(
    "/api/sessions/{session_id}/presentation/timeline/items",
    response_model=TimelineItemOut,
    status_code=status.HTTP_201_CREATED,
)
async def insert_timeline_item(
    session_id: str,
    payload: TimelineItemCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _verify_ownership(session_id, user, db)
    timeline = await _get_timeline_for_session(db, session.id)

    position = min(payload.position, len(timeline.items))
    slide_type = _INTERACTION_TYPE_TO_SLIDE_TYPE[payload.item_type]
    content_json = dict(payload.content_json)
    if payload.item_type == TimelineItemType.RATING:
        content_json["mode"] = "rating_only"

    slide = Slide(session_id=session.id, type=slide_type, order=0, content_json=content_json, is_active=False)
    db.add(slide)
    await db.flush()

    await db.execute(
        update(PresentationTimelineItem)
        .where(
            PresentationTimelineItem.timeline_id == timeline.id,
            PresentationTimelineItem.order >= position,
        )
        .values(order=PresentationTimelineItem.order + 1)
    )
    item = PresentationTimelineItem(
        timeline_id=timeline.id,
        order=position,
        item_type=payload.item_type,
        slide_id=slide.id,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item, attribute_names=["slide", "page"])
    return item


@router.patch(
    "/api/sessions/{session_id}/presentation/timeline/items/{item_id}",
    response_model=TimelineItemOut,
)
async def update_timeline_item(
    session_id: str,
    item_id: str,
    payload: TimelineItemUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _verify_ownership(session_id, user, db)
    item = await _get_owned_item(db, session, item_id)
    if item.item_type == TimelineItemType.PAGE or item.slide_id is None:
        raise HTTPException(status_code=400, detail="Cannot edit content of a presentation page")

    content_json = dict(payload.content_json)
    if item.item_type == TimelineItemType.RATING:
        content_json["mode"] = "rating_only"

    await db.execute(
        update(Slide).where(Slide.id == item.slide_id).values(content_json=content_json)
    )
    await db.commit()
    await db.refresh(item, attribute_names=["slide", "page"])
    return item


@router.delete(
    "/api/sessions/{session_id}/presentation/timeline/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_timeline_item(
    session_id: str,
    item_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _verify_ownership(session_id, user, db)
    item = await _get_owned_item(db, session, item_id)
    if item.item_type == TimelineItemType.PAGE:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a presentation page — replace the presentation instead",
        )

    timeline = await db.get(PresentationTimeline, item.timeline_id)
    if timeline and timeline.active_timeline_item_id == item.id:
        timeline.active_timeline_item_id = None
        await _sync_active_slide(db, session.id, None)

    if item.slide_id:
        await db.execute(delete(Slide).where(Slide.id == item.slide_id))
    await db.execute(delete(PresentationTimelineItem).where(PresentationTimelineItem.id == item.id))
    await db.commit()


@router.post(
    "/api/sessions/{session_id}/presentation/timeline/items/reorder",
    response_model=TimelineOut,
)
async def reorder_timeline_items(
    session_id: str,
    payload: TimelineReorderPayload,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _verify_ownership(session_id, user, db)
    timeline = await _get_timeline_for_session(db, session.id)

    by_id = {item.id: item for item in timeline.items}
    if (
        len(payload.item_ids) != len(set(payload.item_ids))
        or set(payload.item_ids) != set(by_id.keys())
    ):
        raise HTTPException(
            status_code=400,
            detail="item_ids must be exactly the session's current timeline items, with no duplicates",
        )

    # Pages are read-only and must keep their original document order —
    # only interactions may be repositioned. Enforced server-side as
    # defense-in-depth beyond the frontend's drag-and-drop restriction.
    original_page_order = [i.id for i in timeline.items if i.item_type == TimelineItemType.PAGE]
    new_page_order = [iid for iid in payload.item_ids if by_id[iid].item_type == TimelineItemType.PAGE]
    if new_page_order != original_page_order:
        raise HTTPException(
            status_code=400,
            detail="Pages must remain in their original document order — only interactions can be repositioned",
        )

    for order_idx, item_id in enumerate(payload.item_ids):
        by_id[item_id].order = order_idx

    await db.commit()
    return await _get_timeline_for_session(db, session.id)


@router.post(
    "/api/sessions/{session_id}/presentation/timeline/activate/{item_id}",
    response_model=TimelineItemOut,
)
async def activate_timeline_item(
    session_id: str,
    item_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _verify_ownership(session_id, user, db)
    item = await _get_owned_item(db, session, item_id)

    await _sync_active_slide(db, session.id, item.slide_id)

    timeline = await db.get(PresentationTimeline, item.timeline_id)
    timeline.active_timeline_item_id = item.id
    await db.commit()
    await db.refresh(item, attribute_names=["slide", "page"])

    out = TimelineItemOut.model_validate(item)
    redis: Redis = request.app.state.redis
    await _publish_safe(
        redis,
        f"session:{session.unique_code}",
        json.dumps(
            {
                "event": "slide_change",
                "data": {
                    "timeline_item_id": str(item.id),
                    "item_type": out.item_type,
                    "page": out.page.model_dump(mode="json") if out.page else None,
                    "slide": out.slide.model_dump(mode="json") if out.slide else None,
                },
            }
        ),
    )
    return item


# ── Page images (no-auth — guests view rendered pages, never the raw file) ──
#
# These routes have no Depends(get_current_user) so guests can view them without
# logging in, but that means presentation_id alone must not be enough to view
# arbitrary content — callers must additionally prove either ownership (token)
# or audience membership in a live session this exact presentation is attached
# to (code == that session's unique_code), mirroring how sessions.py's guest
# join endpoint already gates access on unique_code + is_live.

async def _authorize_presentation_asset(
    pres_uuid: uuid.UUID, token: str | None, code: str | None, db: AsyncSession
) -> None:
    if token:
        try:
            settings = get_settings()
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            user_id = payload.get("sub")
            if user_id:
                result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
                user = result.scalar_one_or_none()
                if user is not None:
                    presentation = await db.get(Presentation, pres_uuid)
                    if presentation is not None and (
                        user.role == UserRole.SUPER_ADMIN or presentation.owner_id == user.id
                    ):
                        return
        except (JWTError, ValueError):
            pass
    if code:
        result = await db.execute(
            select(Session).where(
                Session.unique_code == code,
                Session.presentation_id == pres_uuid,
                Session.is_live.is_(True),
            )
        )
        if result.scalar_one_or_none() is not None:
            return
    raise HTTPException(status_code=401, detail="Not authorized to view this presentation")


@router.get("/api/presentations/{presentation_id}/pages/{page_number}/image")
async def get_presentation_page_image(
    presentation_id: str,
    page_number: int,
    token: str | None = None,
    code: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        pres_uuid = uuid.UUID(presentation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid presentation ID format")
    await _authorize_presentation_asset(pres_uuid, token, code, db)
    return await _serve_page_file(presentation_id, page_number, thumbnail=False, db=db)


@router.get("/api/presentations/{presentation_id}/pages/{page_number}/thumbnail")
async def get_presentation_page_thumbnail(
    presentation_id: str,
    page_number: int,
    token: str | None = None,
    code: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        pres_uuid = uuid.UUID(presentation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid presentation ID format")
    await _authorize_presentation_asset(pres_uuid, token, code, db)
    return await _serve_page_file(presentation_id, page_number, thumbnail=True, db=db)
