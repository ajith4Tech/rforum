import random
import string
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user
from app.database import get_db
from app.models import Session, User
from app.schemas import SessionCreate, SessionOut, SessionUpdate, SessionWithSlides

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
    code = _generate_code()
    # Ensure uniqueness
    while (await db.execute(select(Session).where(Session.unique_code == code))).scalar_one_or_none():
        code = _generate_code()

    session = Session(owner_id=user.id, title=payload.title, unique_code=code)
    db.add(session)
    await db.flush()
    await db.commit()
    return session


@router.get("/", response_model=list[SessionOut])
async def list_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Session).where(Session.owner_id == user.id).order_by(Session.created_at.desc())
    )
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
    
    result = await db.execute(
        select(Session)
        .options(selectinload(Session.slides))
        .where(Session.id == session_uuid, Session.owner_id == user.id)
    )
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
    
    result = await db.execute(
        select(Session).where(Session.id == session_uuid, Session.owner_id == user.id)
    )
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
    
    result = await db.execute(
        select(Session).where(Session.id == session_uuid, Session.owner_id == user.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.delete(session)
    await db.commit()


# ── Guest endpoint (no auth) ─────────────────────────
@router.get("/join/{code}", response_model=SessionWithSlides)
async def join_session(code: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Session)
        .options(selectinload(Session.slides))
        .where(Session.unique_code == code, Session.is_live == True)
    )
    session = result.unique().scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or not live")

    # Strip private file paths from guest-facing response
    data = SessionWithSlides.model_validate(session)
    for s in data.slides:
        cj = dict(s.content_json)
        if "file_url" in cj:
            cj["has_file"] = True
            del cj["file_url"]
        cj.pop("file_name", None)
        s.content_json = cj
    return data
