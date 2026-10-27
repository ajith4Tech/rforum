import json
import logging
import math
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi import Response as HTTPResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user, get_optional_user
from app.config import get_settings
from app.database import get_db
from app.models import Response, Slide, User, UserRole
from app.rate_limit import check_rate_limit
from app.schemas import ResponseCreate, ResponseModerationUpdate, ResponseOut, ResponseSubmitOut
from app.services.guest_view import RESPONSES_CLEARED_KEY

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/slides/{slide_id}/responses", tags=["responses"])


async def _publish_safe(redis: Redis, channel: str, message: str) -> None:
    """Best-effort Redis publish for live WS updates — always called AFTER
    the DB write it announces has already committed, so a transient Redis
    failure here must not turn an already-successful mutation into a
    client-visible error. Same fail-open policy as check_rate_limit
    (app/rate_limit.py); clients just miss one live update instead of
    getting a false 500 for a response/upvote/clear that actually succeeded."""
    try:
        await redis.publish(channel, message)
    except RedisError:
        logger.warning("redis_publish_failed channel=%s", channel, exc_info=True)


# Optional client-chosen key making a submission safe to retry (guests queue
# responses on their device while offline and resend them on reconnect; a
# request whose reply was lost may also have been stored already).
IDEMPOTENCY_HEADER = "Idempotency-Key"
_IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{8,100}$")
# Fixed namespace for deriving response ids from idempotency keys — never change it,
# or retries of submissions made before the change would no longer deduplicate.
_RESPONSE_ID_NAMESPACE = uuid.UUID("6f1d2c3e-8a4b-4f7e-9c21-5d0b7e3a9f14")


def _idempotent_response_id(slide_uuid: uuid.UUID, guest_identifier: str, key: str) -> uuid.UUID:
    """Deterministic Response.id for a keyed submission. Retries of the same
    submission map to the same primary key, so the database itself rejects
    the duplicate — no schema change, and still correct when Redis is down.
    Scoped by slide and guest so one guest's key can never match (or replay)
    another guest's response."""
    return uuid.uuid5(_RESPONSE_ID_NAMESPACE, f"{slide_uuid}:{guest_identifier}:{key}")


async def _find_replay(db: AsyncSession, response_id: uuid.UUID, slide_uuid: uuid.UUID) -> Response | None:
    result = await db.execute(
        select(Response).where(Response.id == response_id, Response.slide_id == slide_uuid)
    )
    return result.scalar_one_or_none()


def _parse_clear_count(value: object) -> int:
    # Same rule as the clear's SQL increment: missing or non-numeric counts as 0.
    try:
        return max(int(str(value)), 0) if value is not None else 0
    except ValueError:
        return 0


async def _lock_clear_count(db: AsyncSession, slide_uuid: uuid.UUID) -> int:
    """The slide's responses_cleared count, read under a FOR SHARE lock on the
    slide row that is held until this transaction ends.

    A clear first updates that row (conflicting with the share lock), then
    deletes the slide's responses. So a clear either committed before this
    read — anything this request stores comes after it and is reported with
    the new count — or waits until this request's transaction ends and then
    deletes what it stored, which was reported with the count from before
    that clear. Either way the reported count tells the guest whether their
    answer predates a clear. Concurrent submissions' share locks don't
    conflict with each other.
    """
    value = await db.scalar(
        select(Slide.content_json[RESPONSES_CLEARED_KEY].astext)
        .where(Slide.id == slide_uuid)
        .with_for_update(read=True)
    )
    return _parse_clear_count(value)


def _submit_out(response: Response, cleared_count: int) -> ResponseSubmitOut:
    return ResponseSubmitOut(**ResponseOut.model_validate(response).model_dump(), responses_cleared=cleared_count)


# Bumps content_json.responses_cleared in a single statement evaluated against
# the row's latest committed version (an UPDATE waits for, then re-reads, a row
# another transaction is changing), so no other key is overwritten and no
# concurrent edit can be lost. The column is JSON, so it round-trips through
# jsonb for jsonb_set. A missing or non-numeric counter counts as 0, and
# non-object content is treated as {}.
_INCREMENT_CLEAR_COUNT_SQL = text("""
    UPDATE slides
    SET content_json = jsonb_set(
        CASE WHEN json_typeof(content_json) = 'object' THEN content_json::jsonb ELSE '{}'::jsonb END,
        ARRAY[CAST(:key AS text)],
        to_jsonb(
            CASE WHEN (content_json ->> CAST(:key AS text)) ~ '^[0-9]{1,9}$'
                 THEN (content_json ->> CAST(:key AS text))::int
                 ELSE 0
            END + 1
        )
    )::json
    WHERE id = :slide_id
    RETURNING (content_json ->> CAST(:key AS text))::int
""")


@router.post("/", response_model=ResponseSubmitOut, status_code=201)
async def submit_response(
    slide_id: str,
    payload: ResponseCreate,
    request: Request,
    http_response: HTTPResponse,
    db: AsyncSession = Depends(get_db),
):
    # Verify slide exists and is active
    try:
        slide_uuid = uuid.UUID(slide_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid slide ID format")

    # Taken first so the replay check below and the insert are both
    # consistent with the reported clear count (see _lock_clear_count).
    cleared_count = await _lock_clear_count(db, slide_uuid)

    idempotency_key = request.headers.get(IDEMPOTENCY_HEADER)
    response_id: uuid.UUID | None = None
    if idempotency_key is not None:
        if not _IDEMPOTENCY_KEY_RE.match(idempotency_key):
            raise HTTPException(status_code=422, detail=f"Invalid {IDEMPOTENCY_HEADER} header")
        response_id = _idempotent_response_id(slide_uuid, payload.guest_identifier, idempotency_key)
        # Checked before the active/live/rate-limit gates: a retry of a
        # submission that was already stored must report success even if the
        # presenter has since moved on, and must not burn rate-limit budget.
        existing = await _find_replay(db, response_id, slide_uuid)
        if existing is not None:
            http_response.status_code = status.HTTP_200_OK
            http_response.headers["Idempotent-Replay"] = "true"
            return _submit_out(existing, cleared_count)

    result = await db.execute(
        select(Slide).where(Slide.id == slide_uuid).options(selectinload(Slide.session))
    )
    slide = result.scalar_one_or_none()
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")
    if not slide.is_active:
        raise HTTPException(status_code=400, detail="Slide is not currently active")
    if not slide.session.is_live:
        raise HTTPException(status_code=403, detail="Session is not live")

    content_json = slide.content_json or {}
    interaction_type = str(content_json.get("interaction_type") or "").upper()
    mode = str(content_json.get("mode") or "").lower()
    is_scale = interaction_type == "SCALE" or mode == "scale"

    # Rate limit: per-guest cap on submissions per slide per minute. guest_identifier
    # is client-supplied, so also cap per-IP-per-slide — otherwise rotating the
    # identifier trivially bypasses the per-guest limit (ballot-stuffing on polls).
    # The per-IP cap is deliberately much higher than the per-guest one: many
    # legitimate guests behind one shared venue/NAT IP submitting to the same
    # slide is the expected case at a live workshop, not the abuse case.
    #
    # Uses the shared check_rate_limit() helper (app/rate_limit.py) rather than
    # a hand-rolled incr/expire pair, so a transient Redis error fails OPEN
    # here too, consistent with the join and WS-connect rate limits — this
    # used to be its own ad-hoc incr/expire with no error handling, so a
    # Redis blip during a live workshop would have turned every response
    # submission into a hard 500 instead of just skipping the rate check.
    settings = get_settings()
    redis: Redis = request.app.state.redis

    guest_allowed = await check_rate_limit(
        redis,
        f"rate:response:{payload.guest_identifier}:{slide_id}",
        settings.RESPONSE_RATE_LIMIT_PER_GUEST,
        settings.RESPONSE_RATE_LIMIT_PER_GUEST_WINDOW_SECONDS,
    )
    if not guest_allowed:
        raise HTTPException(status_code=429, detail="Too many responses. Please slow down.")

    ip_allowed = await check_rate_limit(
        redis,
        f"rate:response_ip:{request.client.host}:{slide_id}",
        settings.RESPONSE_RATE_LIMIT_PER_IP,
        settings.RESPONSE_RATE_LIMIT_PER_IP_WINDOW_SECONDS,
    )
    if not ip_allowed:
        raise HTTPException(status_code=429, detail="Too many responses. Please slow down.")

    # Default name to "Guest" if empty or None
    response_data = payload.model_dump()

    if is_scale:
        min_value = content_json.get("min", 1)
        max_value = content_json.get("max", 10)
        step_value = content_json.get("step", 1)
        try:
            min_num = float(min_value)
            max_num = float(max_value)
            step_num = float(step_value)
            selected = float(response_data.get("value"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="scale value must be numeric")
        # float() accepts "nan"/"inf": NaN slips past both range comparisons
        # below and then crashes round() in the step check (500).
        if not all(math.isfinite(n) for n in (min_num, max_num, step_num, selected)):
            raise HTTPException(status_code=422, detail="scale value must be numeric")

        if min_num > max_num:
            min_num, max_num = max_num, min_num

        if selected < min_num or selected > max_num:
            raise HTTPException(
                status_code=422,
                detail=f"scale value must be between {min_num:g} and {max_num:g}",
            )

        if step_num > 0:
            step_offset = (selected - min_num) / step_num
            if not math.isclose(step_offset, round(step_offset), rel_tol=0, abs_tol=1e-9):
                raise HTTPException(
                    status_code=422,
                    detail=f"scale value must follow step {step_num:g}",
                )

        # Scale submissions should not be treated as FEEDBACK rating(1-5).
        response_data["rating"] = None
    elif response_data.get("rating") is not None:
        rating = response_data["rating"]
        if rating < 1 or rating > 5:
            raise HTTPException(status_code=422, detail="rating must be between 1 and 5")

    if not response_data.get("name") or not response_data.get("name").strip():
        response_data["name"] = "Guest"
    else:
        response_data["name"] = response_data["name"].strip()

    response = Response(slide_id=slide_uuid, **response_data)
    if response_id is not None:
        response.id = response_id
    db.add(response)
    try:
        await db.flush()
        await db.commit()
    except IntegrityError:
        # A concurrent retry of the same keyed submission inserted it first.
        await db.rollback()
        if response_id is None:
            raise
        # The rollback released the share lock: re-take it before looking up
        # the stored copy, so the reported count still matches it.
        cleared_count = await _lock_clear_count(db, slide_uuid)
        existing = await _find_replay(db, response_id, slide_uuid)
        if existing is None:
            raise
        http_response.status_code = status.HTTP_200_OK
        http_response.headers["Idempotent-Replay"] = "true"
        return _submit_out(existing, cleared_count)
    # No db.refresh() needed here: expire_on_commit=False (app/database.py)
    # keeps flush()'s already-populated values (id/upvotes are Python-side
    # defaults; created_at is filled in via Postgres RETURNING on flush)
    # valid across the commit — a refresh would just be a redundant SELECT
    # on the highest-frequency guest write path in the app.

    # Publish to Redis so all WS clients (including moderator) receive this live
    session_code = slide.session.unique_code
    out = ResponseOut.model_validate(response)
    await _publish_safe(
        redis,
        f"session:{session_code}",
        json.dumps({"event": "new_response", "data": out.model_dump(mode="json")}),
    )

    return _submit_out(response, cleared_count)


@router.get("/", response_model=list[ResponseOut])
async def list_responses(
    slide_id: str,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        slide_uuid = uuid.UUID(slide_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid slide ID format")

    result = await db.execute(
        select(Slide).where(Slide.id == slide_uuid).options(selectinload(Slide.session))
    )
    slide = result.scalar_one_or_none()
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")

    # The moderator dashboard fetches this with no live-session restriction
    # (they must see responses while composing, before going live, and after
    # ending). Anyone else — guests, screens — only gets results for a live
    # session, matching the join-flow access model everywhere else.
    is_owner_or_admin = user is not None and (
        user.role == UserRole.SUPER_ADMIN or slide.session.owner_id == user.id
    )
    if not is_owner_or_admin and not slide.session.is_live:
        raise HTTPException(status_code=403, detail="Session is not live")

    query = select(Response).where(Response.slide_id == slide_uuid)
    # Hidden responses are moderator-only — this is also what every guest and
    # projector reconnect/resync refetches, so a hidden response can't come back.
    if not is_owner_or_admin:
        query = query.where(Response.is_hidden.is_(False))
    result = await db.execute(query.order_by(Response.upvotes.desc(), Response.created_at.desc()))
    return result.scalars().all()


@router.post("/{response_id}/upvote", response_model=ResponseOut)
async def upvote_response(
    slide_id: str,
    response_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        slide_uuid = uuid.UUID(slide_id)
        response_uuid = uuid.UUID(response_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    # Rate-limit: one upvote per IP per response (stored in Redis). Fails
    # open on a Redis error, same policy as check_rate_limit
    # (app/rate_limit.py) — a transient Redis blip shouldn't turn into a
    # hard failure on every upvote attempt.
    redis: Redis = request.app.state.redis
    rate_key = f"upvote:{response_id}:{request.client.host}"
    try:
        already_upvoted = await redis.exists(rate_key)
    except RedisError:
        logger.warning("upvote_dedupe_check_failed key=%s — failing open", rate_key, exc_info=True)
        already_upvoted = False
    if already_upvoted:
        raise HTTPException(status_code=429, detail="Already upvoted")
    try:
        await redis.setex(rate_key, 86400, "1")  # 24-hour window
    except RedisError:
        logger.warning("upvote_dedupe_write_failed key=%s", rate_key, exc_info=True)

    result = await db.execute(
        select(Response)
        .where(Response.id == response_uuid, Response.slide_id == slide_uuid)
        .options(selectinload(Response.slide).selectinload(Slide.session))
    )
    response = result.scalar_one_or_none()
    if not response or response.is_hidden:
        raise HTTPException(status_code=404, detail="Response not found")
    if not response.slide.session.is_live:
        raise HTTPException(status_code=403, detail="Session is not live")

    # Atomic at the DB level — `response.upvotes += 1` here would read-modify-write
    # in Python, losing an increment when two upvotes for the same response commit
    # concurrently (a real scenario: a poll going viral gets simultaneous upvotes
    # from different IPs, each allowed by the per-IP dedupe above).
    await db.execute(
        update(Response).where(Response.id == response_uuid).values(upvotes=Response.upvotes + 1)
    )
    await db.commit()
    await db.refresh(response, attribute_names=["upvotes"])

    # Publish upvote to Redis so all WS clients update the vote count live
    session_code = response.slide.session.unique_code
    out = ResponseOut.model_validate(response)
    await _publish_safe(
        redis,
        f"session:{session_code}",
        json.dumps({"event": "upvote", "data": out.model_dump(mode="json")}),
    )

    return response


@router.patch("/{response_id}", response_model=ResponseOut)
async def moderate_response(
    slide_id: str,
    response_id: str,
    payload: ResponseModerationUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Hide or unhide one response (session owner or super admin only)."""
    try:
        slide_uuid = uuid.UUID(slide_id)
        response_uuid = uuid.UUID(response_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    result = await db.execute(
        select(Response)
        .where(Response.id == response_uuid, Response.slide_id == slide_uuid)
        .options(selectinload(Response.slide).selectinload(Slide.session))
    )
    response = result.scalar_one_or_none()
    if not response:
        raise HTTPException(status_code=404, detail="Response not found")
    session = response.slide.session
    if user.role != UserRole.SUPER_ADMIN and session.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to moderate responses")

    if response.is_hidden != payload.is_hidden:
        response.is_hidden = payload.is_hidden
        await db.commit()

    # Hiding tells every client to drop it; unhiding re-announces it exactly
    # like a fresh submission, which every client already merges by id.
    out = ResponseOut.model_validate(response)
    if payload.is_hidden:
        message = {"event": "response_hidden", "data": {"slide_id": str(slide_uuid), "id": str(response_uuid)}}
    else:
        message = {"event": "new_response", "data": out.model_dump(mode="json")}
    redis: Redis = request.app.state.redis
    await _publish_safe(redis, f"session:{session.unique_code}", json.dumps(message))

    return response


@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
async def clear_responses(
    slide_id: str,
    user: User = Depends(get_current_user),
    request: Request = ...,
    db: AsyncSession = Depends(get_db),
):
    """Clear all responses for a slide (moderator only)."""
    try:
        slide_uuid = uuid.UUID(slide_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid slide ID format")

    # Get the slide and verify ownership
    result = await db.execute(
        select(Slide)
        .where(Slide.id == slide_uuid)
        .options(selectinload(Slide.session))
    )
    slide = result.scalar_one_or_none()
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")
    
    # Verify user is the session owner (or a super admin, consistent with every other router)
    if user.role != UserRole.SUPER_ADMIN and slide.session.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to clear responses")

    # Bump the slide's clear counter, then delete its responses, in one
    # transaction. Guests compare the counter (part of every join/resync
    # payload) with the one returned when they answered, so one who missed the
    # live event below can still answer again after reconnecting.
    # The increment is atomic and touches only that key (see
    # _INCREMENT_CLEAR_COUNT_SQL), and it comes FIRST: its row lock makes
    # in-flight submissions finish before the delete (or wait for this clear),
    # and moderator edits lock the same row before reading it.
    cleared_count = await db.scalar(
        _INCREMENT_CLEAR_COUNT_SQL, {"key": RESPONSES_CLEARED_KEY, "slide_id": slide_uuid}
    )
    await db.execute(delete(Response).where(Response.slide_id == slide_uuid))
    await db.commit()

    # Broadcast clear event to all WS clients
    redis: Redis = request.app.state.redis
    session_code = slide.session.unique_code
    await _publish_safe(
        redis,
        f"session:{session_code}",
        json.dumps({
            "event": "clear_responses",
            "data": {"slide_id": str(slide_uuid), RESPONSES_CLEARED_KEY: cleared_count},
        }),
    )

