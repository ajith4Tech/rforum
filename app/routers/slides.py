import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import Session, Slide, User
from app.schemas import SlideCreate, SlideOut, SlideUpdate

router = APIRouter(prefix="/api/sessions/{session_id}/slides", tags=["slides"])


async def _verify_ownership(
    session_id: str, user: User, db: AsyncSession
) -> Session:
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
    return session


@router.post("/", response_model=SlideOut, status_code=status.HTTP_201_CREATED)
async def create_slide(
    session_id: str,
    payload: SlideCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _verify_ownership(session_id, user, db)

    slide = Slide(session_id=uuid.UUID(session_id), **payload.model_dump())
    db.add(slide)
    await db.flush()
    await db.commit()
    return slide


@router.get("/", response_model=list[SlideOut])
async def list_slides(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _verify_ownership(session_id, user, db)

    session_uuid = uuid.UUID(session_id)
    result = await db.execute(
        select(Slide).where(Slide.session_id == session_uuid).order_by(Slide.order)
    )
    return result.scalars().all()


@router.patch("/{slide_id}", response_model=SlideOut)
async def update_slide(
    session_id: str,
    slide_id: str,
    payload: SlideUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _verify_ownership(session_id, user, db)

    try:
        session_uuid = uuid.UUID(session_id)
        slide_uuid = uuid.UUID(slide_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID format")
    
    result = await db.execute(
        select(Slide).where(Slide.id == slide_uuid, Slide.session_id == session_uuid)
    )
    slide = result.scalar_one_or_none()
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")

    update_data = payload.model_dump(exclude_unset=True)

    # If activating this slide, deactivate all others in the session
    if update_data.get("is_active"):
        await db.execute(
            update(Slide)
            .where(Slide.session_id == session_uuid)
            .values(is_active=False)
        )

    for field, value in update_data.items():
        setattr(slide, field, value)

    await db.commit()
    return slide


@router.delete("/{slide_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_slide(
    session_id: str,
    slide_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _verify_ownership(session_id, user, db)

    try:
        session_uuid = uuid.UUID(session_id)
        slide_uuid = uuid.UUID(slide_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID format")
    
    result = await db.execute(
        select(Slide).where(Slide.id == slide_uuid, Slide.session_id == session_uuid)
    )
    slide = result.scalar_one_or_none()
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")
    await db.delete(slide)
    await db.commit()
