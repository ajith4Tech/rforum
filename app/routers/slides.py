import json
import logging
import os
import uuid
from io import BytesIO
from pathlib import Path

import fitz  # PyMuPDF
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt
from redis.asyncio import Redis
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models import Session, SessionAsset, Slide, User, UserRole
from app.schemas import SlideCreate, SlideOut, SlideUpdate, SlideUploadOut, UploadMeta
from app.services.file_processing import (
    check_content_length,
    convert_to_pdf_if_needed,
    extract_total_pages,
    validate_upload,
)

logger = logging.getLogger(__name__)

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


def _ensure_not_presentation_session(session: Session) -> None:
    """
    Legacy slide CRUD has no presentation-timeline awareness — operating on a
    presentation-linked session's slides here would desync the timeline
    (e.g. orphaning a PresentationTimelineItem.slide_id). Presentation sessions
    must go through app/routers/presentations.py instead.
    """
    if session.presentation_id is not None:
        raise HTTPException(
            status_code=409,
            detail="This session uses the Presentation Timeline — manage its content via the presentation endpoints, not the legacy slide API.",
        )


@router.post("/", response_model=SlideOut, status_code=status.HTTP_201_CREATED)
async def create_slide(
    session_id: str,
    payload: SlideCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _verify_ownership(session_id, user, db)
    _ensure_not_presentation_session(session)

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
    session = await _verify_ownership(session_id, user, db)
    _ensure_not_presentation_session(session)

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
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _verify_ownership(session_id, user, db)
    _ensure_not_presentation_session(session)

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
    
    # Broadcast slide change to all WebSocket clients
    if update_data.get("is_active"):
        # Reload slide with session info for broadcast
        result = await db.execute(
            select(Slide)
            .where(Slide.id == slide_uuid)
            .options(selectinload(Slide.session))
        )
        slide_with_session = result.scalar_one()
        
        redis: Redis = request.app.state.redis
        session_code = slide_with_session.session.unique_code
        out = SlideOut.model_validate(slide_with_session)
        payload_data = {
            "event": "slide_change",
            "data": {
                "slide": out.model_dump(mode="json"),
                "activation": True
            }
        }
        await redis.publish(
            f"session:{session_code}",
            json.dumps(payload_data)
        )
    
    return slide


@router.delete("/{slide_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_slide(
    session_id: str,
    slide_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _verify_ownership(session_id, user, db)
    _ensure_not_presentation_session(session)

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


@router.post("/{slide_id}/upload", response_model=SlideUploadOut)
async def upload_content_file(
    session_id: str,
    slide_id: str,
    file: UploadFile,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _verify_ownership(session_id, user, db)
    _ensure_not_presentation_session(session)

    try:
        session_uuid = uuid.UUID(session_id)
        slide_uuid = uuid.UUID(slide_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    db_result = await db.execute(
        select(Slide).where(Slide.id == slide_uuid, Slide.session_id == session_uuid)
    )
    slide = db_result.scalar_one_or_none()
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")

    settings = get_settings()
    max_bytes = settings.UPLOAD_MAX_MB * 1024 * 1024
    try:
        check_content_length(request.headers.get("content-length"), max_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc))

    original_name = Path(file.filename or "upload.bin").name or "upload.bin"
    ext = Path(original_name).suffix.lower()
    content = await file.read()

    # ── Validate (extension, size, MIME) ─────────────────
    try:
        validation = validate_upload(
            content=content,
            original_name=original_name,
            allowed_extensions=settings.UPLOAD_ALLOWED_EXTENSIONS,
            max_bytes=max_bytes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    all_warnings: list[str] = list(validation.warnings)
    actual_mime = validation.actual_mime

    logger.info(
        "Upload started. user=%s slide=%s filename='%s' size=%d detected_mime='%s'",
        user.id, slide_id, original_name, len(content), actual_mime,
    )

    # ── Persist raw file ──────────────────────────────────
    os.makedirs("uploads", exist_ok=True)
    filename = f"{slide_id}_{original_name}"
    file_path = os.path.join("uploads", filename)
    with open(file_path, "wb") as handle:
        handle.write(content)

    file_url = f"/uploads/{filename}"
    file_name = original_name
    # Use server-detected MIME, not the browser-reported content_type
    content_type = actual_mime

    # ── Convert PPT/PPTX → PDF ────────────────────────────
    conversion = convert_to_pdf_if_needed(file_path, ext)
    all_warnings.extend(conversion.warnings)

    if conversion.success and conversion.output_path:
        pdf_basename = os.path.basename(conversion.output_path)
        file_url = f"/uploads/{pdf_basename}"
        file_name = pdf_basename
        content_type = conversion.converted_type or "application/pdf"

    # ── Extract page count (works for ALL fitz-supported types) ──
    final_path = file_url.lstrip("/")
    total_pages, page_warnings = extract_total_pages(final_path)
    all_warnings.extend(page_warnings)

    if total_pages == 1 and page_warnings:
        logger.warning(
            "Page count defaulted to 1 for slide=%s file='%s' warnings=%s",
            slide_id, final_path, page_warnings,
        )

    logger.info(
        "Upload complete. slide=%s file='%s' type='%s' pages=%d "
        "conversion_attempted=%s conversion_success=%s warnings=%d",
        slide_id, file_name, content_type, total_pages,
        conversion.attempted, conversion.success, len(all_warnings),
    )

    # ── Update slide content_json ─────────────────────────
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

    # Build response: validate slide via SlideOut first, then extend with upload metadata
    upload_meta = UploadMeta(
        conversion_attempted=conversion.attempted,
        conversion_success=conversion.success,
        converted_file_type=conversion.converted_type,
        warnings=all_warnings,
    )
    slide_data = SlideOut.model_validate(slide).model_dump()
    return SlideUploadOut(upload_meta=upload_meta, **slide_data)


async def _authorize_slide_asset(
    session_uuid: uuid.UUID, token: str | None, code: str | None, db: AsyncSession
) -> None:
    """
    Mirrors app/routers/presentations.py::_authorize_presentation_asset — this
    endpoint has no Depends(get_current_user) so guests can view without
    logging in, but session_id+slide_id alone must not be enough: callers must
    prove either ownership (token) or audience membership in this exact live
    session (code == its unique_code).
    """
    if token:
        try:
            settings = get_settings()
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            user_id = payload.get("sub")
            if user_id:
                result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
                user = result.scalar_one_or_none()
                if user is not None:
                    session = await db.get(Session, session_uuid)
                    if session is not None and (
                        user.role == UserRole.SUPER_ADMIN or session.owner_id == user.id
                    ):
                        return
        except (JWTError, ValueError):
            pass
    if code:
        result = await db.execute(
            select(Session).where(
                Session.id == session_uuid,
                Session.unique_code == code,
                Session.is_live.is_(True),
            )
        )
        if result.scalar_one_or_none() is not None:
            return
    raise HTTPException(status_code=401, detail="Not authorized to view this slide")


@router.get("/{slide_id}/page/{page_num}")
async def get_page_image(
    session_id: str,
    slide_id: str,
    page_num: int,
    token: str | None = None,
    code: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Render a single PDF page as a PNG image. No login required so guests can view."""
    try:
        slide_uuid = uuid.UUID(slide_id)
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    await _authorize_slide_asset(session_uuid, token, code, db)

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
    except fitz.EmptyFileError:
        logger.error("Page render failed — empty file: slide=%s file='%s'", slide_id, file_path)
        raise HTTPException(status_code=422, detail="File is empty and cannot be rendered.")
    except fitz.FileDataError as exc:
        logger.error(
            "Page render failed — file corrupt or encrypted: slide=%s file='%s' error=%s",
            slide_id, file_path, exc,
        )
        raise HTTPException(
            status_code=422,
            detail="File cannot be rendered. It may be corrupted or password-protected.",
        )
    except Exception as exc:
        logger.error(
            "Page render failed — unexpected error: slide=%s file='%s'",
            slide_id, file_path, exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Could not open file for rendering.")

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
