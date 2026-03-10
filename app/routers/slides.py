import os
import subprocess
import uuid
from io import BytesIO
from pathlib import Path

import fitz  # PyMuPDF
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models import Session, SessionAsset, Slide, User, UserRole
from app.schemas import SlideCreate, SlideOut, SlideUpdate

router = APIRouter(prefix="/api/sessions/{session_id}/slides", tags=["slides"])


async def _verify_ownership(
    session_id: str, user: User, db: AsyncSession
) -> Session:
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
        delete(Slide).where(Slide.id == slide_uuid, Slide.session_id == session_uuid)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Slide not found")
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

    settings = get_settings()
    # Strip any directory components from the filename to prevent path traversal
    original_name = Path(file.filename or "upload.bin").name or "upload.bin"
    ext = Path(original_name).suffix.lower()

    # Validate file extension
    if ext not in settings.UPLOAD_ALLOWED_EXTENSIONS:
        allowed = ", ".join(settings.UPLOAD_ALLOWED_EXTENSIONS)
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed. Allowed types: {allowed}",
        )

    content = await file.read()

    # Validate file size
    max_bytes = settings.UPLOAD_MAX_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File size exceeds the {settings.UPLOAD_MAX_MB} MB limit",
        )

    os.makedirs("uploads", exist_ok=True)
    filename = f"{slide_id}_{original_name}"
    file_path = os.path.join("uploads", filename)
    with open(file_path, "wb") as handle:
        handle.write(content)

    content_type = file.content_type or "application/octet-stream"
    file_url = f"/uploads/{filename}"
    file_name = original_name

    # Convert PPT/PPTX to PDF if possible
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

    # ── Create or update SessionAsset record ─────────────
    existing_asset_result = await db.execute(
        select(SessionAsset).where(SessionAsset.slide_id == slide_uuid)
    )
    existing_asset = existing_asset_result.scalar_one_or_none()

    # Fetch the session to get event_id
    session_row = await db.execute(select(Session).where(Session.id == session_uuid))
    session_obj = session_row.scalar_one_or_none()

    if existing_asset:
        existing_asset.file_name = file_name
        existing_asset.file_url = file_url
        existing_asset.file_type = content_type
        existing_asset.file_size = len(content)
    else:
        new_asset = SessionAsset(
            user_id=user.id,
            session_id=session_uuid,
            event_id=session_obj.event_id if session_obj else None,
            slide_id=slide_uuid,
            file_name=file_name,
            file_url=file_url,
            file_type=content_type,
            file_size=len(content),
        )
        db.add(new_asset)

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

    # Resolve to local path and confine to the uploads/ directory
    file_path = file_url.lstrip("/")
    uploads_dir = os.path.realpath("uploads")
    resolved = os.path.realpath(file_path)
    if not resolved.startswith(uploads_dir + os.sep) and resolved != uploads_dir:
        raise HTTPException(status_code=400, detail="Invalid file path")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    try:
        doc = fitz.open(file_path)
    except Exception:
        raise HTTPException(status_code=500, detail="Could not open PDF")

    total = len(doc)

    # Backfill total_pages if it was missing or wrong
    if content_json.get("total_pages") != total:
        content_json["total_pages"] = total
        slide.content_json = dict(content_json)
        await db.commit()

    if page_num < 1 or page_num > total:
        doc.close()
        raise HTTPException(status_code=400, detail=f"Page must be between 1 and {total}")

    page = doc[page_num - 1]
    # Render at 2x for crisp display on phones
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
    img_bytes = pix.tobytes("png")
    doc.close()

    return StreamingResponse(
        BytesIO(img_bytes),
        media_type="image/png",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": "inline",
            "X-Total-Pages": str(total),
        },
    )
