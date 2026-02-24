import os
import subprocess
import uuid
from io import BytesIO
from pathlib import Path

import fitz  # PyMuPDF
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
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


@router.post("/{slide_id}/upload", response_model=SlideOut)
async def upload_content_file(
    session_id: str,
    slide_id: str,
    file: UploadFile,
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

    os.makedirs("uploads", exist_ok=True)
    original_name = file.filename or "upload.bin"
    filename = f"{slide_id}_{original_name}"
    file_path = os.path.join("uploads", filename)
    content = await file.read()
    with open(file_path, "wb") as handle:
        handle.write(content)

    content_type = file.content_type or "application/octet-stream"
    file_url = f"/uploads/{filename}"
    file_name = original_name

    # Convert PPT/PPTX to PDF if possible
    ext = Path(original_name).suffix.lower()
    if ext in {".ppt", ".pptx"}:
        try:
            result = subprocess.run(
                [
                    "libreoffice",
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    "uploads",
                    file_path,
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            pdf_name = f"{Path(file_path).stem}.pdf"
            pdf_path = os.path.join("uploads", pdf_name)
            if os.path.exists(pdf_path):
                file_url = f"/uploads/{pdf_name}"
                file_name = pdf_name
                content_type = "application/pdf"
        except Exception:
            pass

    # Count total pages for PDF files
    total_pages = 1
    final_path = file_url.lstrip("/")
    if content_type == "application/pdf" and os.path.exists(final_path):
        try:
            doc = fitz.open(final_path)
            total_pages = len(doc)
            doc.close()
        except Exception:
            pass

    content_json = dict(slide.content_json or {})
    content_json["file_name"] = file_name
    content_json["file_url"] = file_url
    content_json["file_type"] = content_type
    content_json["file_page"] = 1
    content_json["total_pages"] = total_pages
    slide.content_json = content_json

    await db.commit()
    return slide


@router.get("/{slide_id}/page/{page_num}")
async def get_page_image(
    session_id: str,
    slide_id: str,
    page_num: int,
    db: AsyncSession = Depends(get_db),
):
    """Render a single PDF page as a PNG image. No auth required so guests can view."""
    try:
        slide_uuid = uuid.UUID(slide_id)
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    result = await db.execute(
        select(Slide).where(Slide.id == slide_uuid, Slide.session_id == session_uuid)
    )
    slide = result.scalar_one_or_none()
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")

    content_json = slide.content_json or {}
    file_url = content_json.get("file_url", "")
    if not file_url:
        raise HTTPException(status_code=404, detail="No file attached")

    # Resolve to local path
    file_path = file_url.lstrip("/")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    try:
        doc = fitz.open(file_path)
    except Exception:
        raise HTTPException(status_code=500, detail="Could not open PDF")

    if page_num < 1 or page_num > len(doc):
        doc.close()
        raise HTTPException(status_code=400, detail=f"Page must be between 1 and {len(doc)}")

    page = doc[page_num - 1]
    # Render at 2x for crisp display on phones
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
    img_bytes = pix.tobytes("png")
    doc.close()

    return StreamingResponse(
        BytesIO(img_bytes),
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=3600",
        },
    )
