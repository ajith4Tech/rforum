from fastapi import APIRouter, UploadFile, Form, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import Slide
import uuid
import shutil

router = APIRouter(prefix="/slides", tags=["slides"])

@router.post("/upload")
async def upload_slide(
    session_id: str = Form(...),
    title: str = Form(...),
    file: UploadFile = Form(...),
    db: AsyncSession = Depends(get_db),
):
    slide_id = uuid.uuid4()
    file_location = f"uploads/{slide_id}_{file.filename}"
    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    slide = Slide(id=slide_id, session_id=session_id, title=title, file_path=file_location)
    db.add(slide)
    await db.commit()
    return {"slide_id": slide_id, "title": title, "file_path": file_location}

@router.get("/present/{slide_id}")
async def present_slide(slide_id: str, db: AsyncSession = Depends(get_db)):
    slide = await db.get(Slide, slide_id)
    if not slide:
        return {"error": "Slide not found"}
    return {"slide_id": slide.id, "title": slide.title, "file_path": slide.file_path}