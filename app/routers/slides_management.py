import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, Form
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import Slide, User
import uuid
import shutil

router = APIRouter(prefix="/slides", tags=["slides"])

ALLOWED_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp'}
UPLOADS_DIR = Path("uploads").resolve()


@router.post("/upload")
async def upload_slide(
    session_id: str = Form(...),
    title: str = Form(...),
    file: UploadFile = Form(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Validate file extension
    original_name = Path(file.filename).name  # strips directory components
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type '{ext}' not allowed")

    slide_id = uuid.uuid4()
    safe_filename = f"{slide_id}{ext}"
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    file_location = UPLOADS_DIR / safe_filename

    # Confirm resolved path is inside uploads dir (path traversal guard)
    if not str(file_location).startswith(str(UPLOADS_DIR)):
        raise HTTPException(status_code=400, detail="Invalid file path")

    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    slide = Slide(id=slide_id, session_id=session_id, title=title, file_path=safe_filename)
    db.add(slide)
    await db.commit()
    return {"slide_id": slide_id, "title": title}


@router.get("/present/{slide_id}")
async def present_slide(
    slide_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        slide_uuid = uuid.UUID(slide_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid slide ID")
    slide = await db.get(Slide, slide_uuid)
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")
    return {"slide_id": slide.id, "title": slide.title}