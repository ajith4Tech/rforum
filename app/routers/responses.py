import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Response, Slide
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

    # Rate limit: max 10 submissions per guest per slide per minute
    redis: Redis = request.app.state.redis
    rate_key = f"rate:response:{payload.guest_identifier}:{slide_id}"
    count = await redis.incr(rate_key)
    if count == 1:
        await redis.expire(rate_key, 60)
    if count > 10:
        raise HTTPException(status_code=429, detail="Too many responses. Please slow down.")

    response = Response(slide_id=slide_uuid, **payload.model_dump())
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
    db: AsyncSession = Depends(get_db),
):
    try:
        slide_uuid = uuid.UUID(slide_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid slide ID format")
    
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

    response.upvotes += 1
    await db.commit()
    await db.refresh(response)

    # Publish upvote to Redis so all WS clients update the vote count live
    session_code = response.slide.session.unique_code
    out = ResponseOut.model_validate(response)
    await redis.publish(
        f"session:{session_code}",
        json.dumps({"event": "upvote", "data": out.model_dump(mode="json")}),
    )

    return response
