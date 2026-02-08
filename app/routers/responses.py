import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Response, Slide
from app.schemas import ResponseCreate, ResponseOut

router = APIRouter(prefix="/api/slides/{slide_id}/responses", tags=["responses"])


@router.post("/", response_model=ResponseOut, status_code=201)
async def submit_response(
    slide_id: str,
    payload: ResponseCreate,
    db: AsyncSession = Depends(get_db),
):
    # Verify slide exists and is active
    try:
        slide_uuid = uuid.UUID(slide_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid slide ID format")
    
    result = await db.execute(select(Slide).where(Slide.id == slide_uuid))
    slide = result.scalar_one_or_none()
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")
    if not slide.is_active:
        raise HTTPException(status_code=400, detail="Slide is not currently active")

    response = Response(slide_id=slide_uuid, **payload.model_dump())
    db.add(response)
    await db.flush()
    await db.commit()
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
    db: AsyncSession = Depends(get_db),
):
    try:
        slide_uuid = uuid.UUID(slide_id)
        response_uuid = uuid.UUID(response_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID format")
    
    result = await db.execute(
        select(Response).where(Response.id == response_uuid, Response.slide_id == slide_uuid)
    )
    response = result.scalar_one_or_none()
    if not response:
        raise HTTPException(status_code=404, detail="Response not found")

    response.upvotes += 1
    await db.commit()
    return response
