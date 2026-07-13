import random
import string
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user
from app.database import get_db
from app.models import Event, PresentationTimeline, PresentationTimelineItem, Session, User, UserRole
from app.schemas import SessionCreate, SessionOut, SessionUpdate, SessionWithSlides, TimelineOut
from app.services.guest_view import strip_slide_content_json

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _generate_code() -> str:
    chars = string.ascii_uppercase + string.digits
    part1 = "".join(random.choices(chars, k=4))
    part2 = "".join(random.choices(chars, k=4))
    return f"{part1}-{part2}"


@router.post("/", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: SessionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    is_admin = user.role == UserRole.SUPER_ADMIN
    event_query = select(Event).where(Event.id == payload.event_id)
    if not is_admin:
        event_query = event_query.where(Event.owner_id == user.id)
    result = await db.execute(event_query)
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    code = _generate_code()
    # Ensure uniqueness
    while (await db.execute(select(Session).where(Session.unique_code == code))).scalar_one_or_none():
        code = _generate_code()

    session = Session(
        owner_id=user.id,
        title=payload.title,
        moderator_name=payload.moderator_name,
        speaker_names=payload.speaker_names,
        unique_code=code,
        event_id=payload.event_id,
    )
    db.add(session)
    await db.flush()
    await db.commit()
    return session


@router.get("/", response_model=list[SessionOut])
async def list_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Session).order_by(Session.created_at.desc())
    if user.role != UserRole.SUPER_ADMIN:
        query = query.where(Session.owner_id == user.id)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{session_id}", response_model=SessionWithSlides)
async def get_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session ID format")

    query = (
        select(Session)
        .options(selectinload(Session.slides))
        .where(Session.id == session_uuid)
    )
    if user.role != UserRole.SUPER_ADMIN:
        query = query.where(Session.owner_id == user.id)
    result = await db.execute(query)
    session = result.unique().scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/code/{code}", response_model=SessionWithSlides)
async def get_session_by_code(
    code: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Session)
        .options(selectinload(Session.slides))
        .where(Session.unique_code == code)
    )
    if user.role != UserRole.SUPER_ADMIN:
        query = query.where(Session.owner_id == user.id)
    result = await db.execute(query)
    session = result.unique().scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.patch("/{session_id}", response_model=SessionOut)
async def update_session(
    session_id: str,
    payload: SessionUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(session, field, value)
    await db.commit()
    return session


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session ID format")
    
    stmt = delete(Session).where(Session.id == session_uuid)
    if user.role != UserRole.SUPER_ADMIN:
        stmt = stmt.where(Session.owner_id == user.id)
    result = await db.execute(stmt)
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.commit()


# ── Guest endpoint (no auth) ─────────────────────────
@router.get("/join/{code}")
async def join_session(code: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Session)
        .options(
            selectinload(Session.slides),
            selectinload(Session.timeline)
            .selectinload(PresentationTimeline.items)
            .selectinload(PresentationTimelineItem.slide),
            selectinload(Session.timeline)
            .selectinload(PresentationTimeline.items)
            .selectinload(PresentationTimelineItem.page),
        )
        .where(Session.unique_code == code, Session.is_live == True)
    )
    session = result.unique().scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or not live")

    # Strip private file paths from guest-facing response
    data = SessionWithSlides.model_validate(session)
    for s in data.slides:
        s.content_json = strip_slide_content_json(s.content_json)

    payload = data.model_dump(mode="json")

    if session.presentation_id and session.timeline:
        timeline_out = TimelineOut.model_validate(session.timeline)
        for item in timeline_out.items:
            if item.slide is not None:
                item.slide.content_json = strip_slide_content_json(item.slide.content_json)
        payload["timeline"] = timeline_out.model_dump(mode="json")
    else:
        payload["timeline"] = None

    return payload
