"""Session Assets router – CRUD for uploaded files with storage tracking."""
import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models import Event, Session, SessionAsset, Slide, User
from app.schemas import SessionAssetOut
from app.services.file_processing import (
    check_content_length,
    convert_to_pdf_if_needed,
    extract_total_pages,
    validate_upload,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/assets", tags=["session_assets"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _remove_file(file_url: str | None) -> None:
    """Silently remove file from disk if it exists."""
    if not file_url:
        return
    path = file_url.lstrip("/")
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


async def _get_owned_asset(asset_id: str, user: User, db: AsyncSession) -> SessionAsset:
    try:
        asset_uuid = uuid.UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid asset ID")

    result = await db.execute(
        select(SessionAsset).where(
            SessionAsset.id == asset_uuid,
            SessionAsset.user_id == user.id,
        )
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/")
async def list_assets(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all assets uploaded by the current user with session/event context."""
    rows = await db.execute(
        select(
            SessionAsset,
            Session.title.label("session_title"),
            Event.title.label("event_title"),
        )
        .outerjoin(Session, Session.id == SessionAsset.session_id)
        .outerjoin(Event, Event.id == SessionAsset.event_id)
        .where(SessionAsset.user_id == user.id)
        .order_by(SessionAsset.uploaded_at.desc())
    )
    out = []
    for asset, session_title, event_title in rows.all():
        d = SessionAssetOut.model_validate(asset).model_dump()
        d["session_title"] = session_title
        d["event_title"] = event_title
        # Serialize UUIDs to strings for JSON
        for k, v in d.items():
            if isinstance(v, uuid.UUID):
                d[k] = str(v)
        out.append(d)
    return out


@router.get("/storage")
async def get_storage(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return current user's total storage usage in bytes."""
    total = await db.scalar(
        select(func.coalesce(func.sum(SessionAsset.file_size), 0))
        .where(SessionAsset.user_id == user.id)
    ) or 0
    asset_count = await db.scalar(
        select(func.count(SessionAsset.id))
        .where(SessionAsset.user_id == user.id)
    ) or 0
    return {"user_id": str(user.id), "total_bytes": int(total), "asset_count": int(asset_count)}


@router.put("/{asset_id}/file", response_model=SessionAssetOut)
async def replace_asset_file(
    asset_id: str,
    file: UploadFile,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Replace the file for an existing asset and update the linked slide if any."""
    asset = await _get_owned_asset(asset_id, user, db)
    if asset.presentation_id is not None:
        raise HTTPException(
            status_code=409,
            detail="This asset is a Presentation's original file — use the presentation's replace endpoint instead.",
        )

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

    actual_mime = validation.actual_mime
    logger.info(
        "Asset replace started. user=%s asset=%s filename='%s' size=%d detected_mime='%s'",
        user.id, asset_id, original_name, len(content), actual_mime,
    )

    # Remove old file from disk
    _remove_file(asset.file_url)

    os.makedirs("uploads", exist_ok=True)
    filename = f"{asset_id}_{original_name}"
    file_path = os.path.join("uploads", filename)
    with open(file_path, "wb") as fh:
        fh.write(content)

    content_type = actual_mime
    file_url = f"/uploads/{filename}"
    file_name = original_name

    # ── Convert PPT/PPTX → PDF ────────────────────────────
    conversion = convert_to_pdf_if_needed(file_path, ext)
    if conversion.warnings:
        logger.warning(
            "Asset replace conversion warnings. asset=%s: %s",
            asset_id, "; ".join(conversion.warnings),
        )

    if conversion.success and conversion.output_path:
        pdf_basename = os.path.basename(conversion.output_path)
        file_url = f"/uploads/{pdf_basename}"
        file_name = pdf_basename
        content_type = conversion.converted_type or "application/pdf"

    # ── Extract page count (works for ALL fitz-supported types) ──
    final_path = file_url.lstrip("/")
    total_pages, page_warnings = extract_total_pages(final_path)
    if page_warnings:
        logger.warning(
            "Asset replace page count warnings. asset=%s: %s",
            asset_id, "; ".join(page_warnings),
        )

    logger.info(
        "Asset replace complete. asset=%s file='%s' type='%s' pages=%d",
        asset_id, file_name, content_type, total_pages,
    )

    # Update linked slide content_json if any
    if asset.slide_id:
        slide_result = await db.execute(select(Slide).where(Slide.id == asset.slide_id))
        slide = slide_result.scalar_one_or_none()
        if slide:
            cj = dict(slide.content_json or {})
            cj["file_name"] = file_name
            cj["file_url"] = file_url
            cj["file_type"] = content_type
            cj["file_page"] = 1
            cj["total_pages"] = total_pages
            slide.content_json = cj

    asset.file_name = file_name
    asset.file_url = file_url
    asset.file_type = content_type
    asset.file_size = len(content)

    await db.commit()
    await db.refresh(asset)
    return asset


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    asset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an asset: remove file from disk, delete linked slide, delete the record."""
    asset = await _get_owned_asset(asset_id, user, db)
    if asset.presentation_id is not None:
        raise HTTPException(
            status_code=409,
            detail="This asset is a Presentation's original file and cannot be deleted from here.",
        )

    _remove_file(asset.file_url)

    if asset.slide_id:
        await db.execute(delete(Slide).where(Slide.id == asset.slide_id))

    await db.execute(delete(SessionAsset).where(SessionAsset.id == asset.id))
    await db.commit()
