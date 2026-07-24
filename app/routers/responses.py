import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user, get_optional_user
from app.config import get_settings
from app.database import get_db
from app.models import Response, Slide, User, UserRole
from app.schemas import ResponseCreate, ResponseOut

router = APIRouter(prefix="/api/slides/{slide_id}/responses", tags=["responses"])


@router.post("/", response_model=ResponseOut, status_code=201)
async def submit_response(
    slide_id: str,
    payload: ResponseCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    # Verify slide exists and is active
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
    if not slide.is_active:
        raise HTTPException(status_code=400, detail="Slide is not currently active")
    if not slide.session.is_live:
        raise HTTPException(status_code=403, detail="Session is not live")

    # Rate limit: per-guest cap on submissions per slide per minute. guest_identifier
    # is client-supplied, so also cap per-IP-per-slide — otherwise rotating the
    # identifier trivially bypasses the per-guest limit (ballot-stuffing on polls).
    # The per-IP cap is deliberately much higher than the per-guest one: many
    # legitimate guests behind one shared venue/NAT IP submitting to the same
    # slide is the expected case at a live workshop, not the abuse case.
    settings = get_settings()
    redis: Redis = request.app.state.redis
    rate_key = f"rate:response:{payload.guest_identifier}:{slide_id}"
    count = await redis.incr(rate_key)
    if count == 1:
        await redis.expire(rate_key, settings.RESPONSE_RATE_LIMIT_PER_GUEST_WINDOW_SECONDS)
    if count > settings.RESPONSE_RATE_LIMIT_PER_GUEST:
        raise HTTPException(status_code=429, detail="Too many responses. Please slow down.")

    ip_rate_key = f"rate:response_ip:{request.client.host}:{slide_id}"
    ip_count = await redis.incr(ip_rate_key)
    if ip_count == 1:
        await redis.expire(ip_rate_key, settings.RESPONSE_RATE_LIMIT_PER_IP_WINDOW_SECONDS)
    if ip_count > settings.RESPONSE_RATE_LIMIT_PER_IP:
        raise HTTPException(status_code=429, detail="Too many responses. Please slow down.")

    # Default name to "Guest" if empty or None
    response_data = payload.model_dump()
    if not response_data.get("name") or not response_data.get("name").strip():
        response_data["name"] = "Guest"
    else:
        response_data["name"] = response_data["name"].strip()

    response = Response(slide_id=slide_uuid, **response_data)
    db.add(response)
    await db.flush()
    await db.commit()
    await db.refresh(response)

    # Publish to Redis so all WS clients (including moderator) receive this live
    session_code = slide.session.unique_code
    out = ResponseOut.model_validate(response)
    await redis.publish(
        f"session:{session_code}",
        json.dumps({"event": "new_response", "data": out.model_dump(mode="json")}),
    )

    return response


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

    result = await db.execute(
        select(Response)
        .where(Response.slide_id == slide_uuid)
        .order_by(Response.upvotes.desc(), Response.created_at.desc())
    )
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

    # Rate-limit: one upvote per IP per response (stored in Redis)
    redis: Redis = request.app.state.redis
    rate_key = f"upvote:{response_id}:{request.client.host}"
    if await redis.exists(rate_key):
        raise HTTPException(status_code=429, detail="Already upvoted")
    await redis.setex(rate_key, 86400, "1")  # 24-hour window

    result = await db.execute(
        select(Response)
        .where(Response.id == response_uuid, Response.slide_id == slide_uuid)
        .options(selectinload(Response.slide).selectinload(Slide.session))
    )
    response = result.scalar_one_or_none()
    if not response:
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
    await redis.publish(
        f"session:{session_code}",
        json.dumps({"event": "upvote", "data": out.model_dump(mode="json")}),
    )

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

    # Delete all responses for this slide
    await db.execute(delete(Response).where(Response.slide_id == slide_uuid))
    await db.commit()

    # Broadcast clear event to all WS clients
    redis: Redis = request.app.state.redis
    session_code = slide.session.unique_code
    await redis.publish(
        f"session:{session_code}",
        json.dumps({"event": "clear_responses", "data": {"slide_id": str(slide_uuid)}}),
    )

