import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user
from app.database import get_db
from app.models import Event, Session, User
from app.schemas import (
    EventCreate,
    EventOut,
    EventPublicOut,
    EventSessionsUpdate,
    EventUpdate,
    EventWithSessions,
)

router = APIRouter(prefix="/api/events", tags=["events"])


def _parse_uuid(value: str, label: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {label} format")


async def _get_event_with_sessions(
    event_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> Event | None:
    result = await db.execute(
        select(Event)
        .options(selectinload(Event.sessions))
        .where(Event.id == event_id, Event.owner_id == user_id)
    )
    return result.unique().scalar_one_or_none()


async def _get_public_event_for_date(
    event_date: date,
    db: AsyncSession,
) -> Event | None:
    result = await db.execute(
        select(Event)
        .options(selectinload(Event.sessions))
        .where(Event.event_date == event_date)
        .order_by(Event.created_at.desc())
    )
    return result.unique().scalars().first()


@router.post("/", response_model=EventWithSessions, status_code=status.HTTP_201_CREATED)
async def create_event(
    payload: EventCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    event = Event(
        owner_id=user.id,
        title=payload.title,
        event_date=payload.event_date,
        description=payload.description,
    )
    db.add(event)
    await db.flush()

    if payload.session_ids:
        await db.execute(
            update(Session)
            .where(Session.id.in_(payload.session_ids), Session.owner_id == user.id)
            .values(event_id=event.id)
        )

    await db.commit()
    await db.refresh(event)
    return await _get_event_with_sessions(event.id, user.id, db)


@router.get("/", response_model=list[EventWithSessions])
async def list_events(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Event)
        .options(selectinload(Event.sessions))
        .where(Event.owner_id == user.id)
        .order_by(Event.event_date.desc())
    )
    return result.unique().scalars().all()


# ── Guest endpoint (no auth) ─────────────────────────
@router.get("/public/today", response_model=dict)
async def get_today_event(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Event)
        .options(selectinload(Event.sessions))
        .where(Event.event_date == date.today(), Event.is_published == True)
        .order_by(Event.created_at.desc())
    )
    event = result.unique().scalars().first()
    if not event:
        raise HTTPException(status_code=404, detail="No event scheduled for today")
    
    sessions = []
    for session in event.sessions:
        sessions.append({
            "id": str(session.id),
            "title": session.title,
            "is_live": session.is_live,
            "unique_code": session.unique_code if session.is_live else None,
        })
    
    return {
        "id": str(event.id),
        "title": event.title,
        "event_date": event.event_date.isoformat(),
        "description": event.description,
        "sessions": sessions,
    }


@router.get("/public", response_model=list[dict])
async def list_public_events(
    event_date: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    target_date = event_date or date.today()
    result = await db.execute(
        select(Event)
        .options(selectinload(Event.sessions))
        .where(Event.event_date == target_date, Event.is_published == True)
        .order_by(Event.created_at.desc())
    )
    events = result.unique().scalars().all()
    payload = []
    for event in events:
        sessions = []
        for session in event.sessions:
            sessions.append({
                "id": str(session.id),
                "title": session.title,
                "is_live": session.is_live,
                "unique_code": session.unique_code if session.is_live else None,
            })
        payload.append({
            "id": str(event.id),
            "title": event.title,
            "event_date": event.event_date.isoformat(),
            "description": event.description,
            "sessions": sessions,
        })
    return payload


@router.get("/{event_id}", response_model=EventWithSessions)
async def get_event(
    event_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    event_uuid = _parse_uuid(event_id, "event ID")
    event = await _get_event_with_sessions(event_uuid, user.id, db)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.patch("/{event_id}", response_model=EventOut)
async def update_event(
    event_id: str,
    payload: EventUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    event_uuid = _parse_uuid(event_id, "event ID")
    result = await db.execute(
        select(Event).where(Event.id == event_uuid, Event.owner_id == user.id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(event, field, value)

    await db.commit()
    return event


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    event_uuid = _parse_uuid(event_id, "event ID")
    result = await db.execute(
        select(Event).where(Event.id == event_uuid, Event.owner_id == user.id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    await db.delete(event)
    await db.commit()


@router.put("/{event_id}/sessions", response_model=EventWithSessions)
async def set_event_sessions(
    event_id: str,
    payload: EventSessionsUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    event_uuid = _parse_uuid(event_id, "event ID")
    event = await _get_event_with_sessions(event_uuid, user.id, db)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Validate all sessions exist and belong to the user
    if payload.session_ids:
        result = await db.execute(
            select(Session).where(Session.id.in_(payload.session_ids), Session.owner_id == user.id)
        )
        found_sessions = result.scalars().all()
        found_ids = {s.id for s in found_sessions}
        missing = [str(sid) for sid in payload.session_ids if sid not in found_ids]
        if missing:
            raise HTTPException(
                status_code=404,
                detail=f"Sessions not found: {', '.join(missing)}",
            )

    # First, detach all sessions not in the new list
    if event.sessions:
        current_ids = {s.id for s in event.sessions}
        keep_ids = set(payload.session_ids)
        to_detach = current_ids - keep_ids
        if to_detach:
            await db.execute(
                update(Session)
                .where(Session.id.in_(to_detach), Session.owner_id == user.id)
                .values(event_id=None)
            )

    # Then, attach the new sessions
    if payload.session_ids:
        await db.execute(
            update(Session)
            .where(Session.id.in_(payload.session_ids), Session.owner_id == user.id)
            .values(event_id=event.id)
        )

    await db.commit()
    return await _get_event_with_sessions(event.id, user.id, db)
