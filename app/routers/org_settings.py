"""
Organization Settings / Branding — one-instance-per-organization deployment,
so this is a singleton row (id=1) rather than a multi-tenant settings table.

Public reads (display name + branding asset URLs) are unauthenticated because
guest-facing pages (join screen, session view, screen view) need the favicon
and org name before any login happens. Writes are gated by the existing
get_current_super_admin dependency — no new role/authorization concept.

Uploaded assets go through the same storage abstraction (app/storage/) as
every other file in this app — never raw filesystem access — so they
automatically respect the deployment's S3 prefix (see app/storage/keys.py
and app/config.py::S3_PREFIX).
"""
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_super_admin
from app.database import get_db
from app.models import OrgSettings, User
from app.schemas import OrgDisplayNameUpdate, OrgSettingsAdminOut, OrgSettingsPublicOut
from app.services.file_processing import check_content_length, validate_upload
from app.storage import get_storage_backend, run_in_storage_executor
from app.storage.keys import branding_favicon_key, branding_logo_key

router = APIRouter(tags=["org-settings"])

_LOGO_MAX_BYTES = 2 * 1024 * 1024
_FAVICON_MAX_BYTES = 256 * 1024

_LOGO_CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
_FAVICON_CONTENT_TYPES = {
    ".ico": "image/x-icon",
    ".png": "image/png",
}
# SVG is deliberately not accepted: /api/branding/logo|favicon are public,
# unauthenticated endpoints served with the uploaded file's own content type
# (see _serve_branding_asset). A crafted SVG with an inline <script> executes
# if a browser ever navigates to that URL directly (not just via <img src>),
# which would run in this origin with access to the JWT in localStorage —
# a stored-XSS path even though the upload itself requires SUPER_ADMIN.

# Bundled default assets already shipped in frontend/static/ — branding
# endpoints redirect here rather than duplicating the bytes server-side.
_DEFAULT_LOGO_URL = "/logo-mascot.webp"
_DEFAULT_FAVICON_URL = "/favicon.ico"


async def _get_singleton(db: AsyncSession) -> OrgSettings:
    row = await db.get(OrgSettings, 1)
    if row is None:
        # Defensive fallback only — the Alembic migration seeds this row, so
        # this path is not expected to run in a normal deployment.
        row = OrgSettings(id=1)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


def _public_payload(row: OrgSettings) -> OrgSettingsPublicOut:
    return OrgSettingsPublicOut(
        display_name=row.display_name,
        logo_url="/api/branding/logo",
        favicon_url="/api/branding/favicon",
        updated_at=row.updated_at,
    )


def _admin_payload(row: OrgSettings) -> OrgSettingsAdminOut:
    return OrgSettingsAdminOut(
        **_public_payload(row).model_dump(),
        has_custom_logo=row.logo_key is not None,
        has_custom_favicon=row.favicon_key is not None,
    )


async def _handle_branding_upload(
    *,
    file: UploadFile,
    admin: User,
    db: AsyncSession,
    allowed_content_types: dict[str, str],
    max_bytes: int,
    key_builder,
    key_field: str,
    content_type_field: str,
) -> OrgSettingsAdminOut:
    original_name = Path(file.filename or "").name
    ext = Path(original_name).suffix.lower()
    if ext not in allowed_content_types:
        allowed = ", ".join(sorted(allowed_content_types))
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' is not allowed. Allowed types: {allowed}",
        )

    content = await file.read()
    try:
        validate_upload(
            content=content,
            original_name=original_name or f"file{ext}",
            allowed_extensions=list(allowed_content_types),
            max_bytes=max_bytes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    row = await _get_singleton(db)
    storage = get_storage_backend()
    new_key = key_builder(ext)
    old_key = getattr(row, key_field)

    await run_in_storage_executor(storage.save, new_key, content)
    if old_key and old_key != new_key:
        await run_in_storage_executor(storage.delete, old_key)

    setattr(row, key_field, new_key)
    setattr(row, content_type_field, allowed_content_types[ext])
    row.updated_by_user_id = admin.id
    await db.commit()
    await db.refresh(row)
    return _admin_payload(row)


async def _handle_branding_delete(
    *, admin: User, db: AsyncSession, key_field: str, content_type_field: str
) -> OrgSettingsAdminOut:
    row = await _get_singleton(db)
    old_key = getattr(row, key_field)
    if old_key:
        storage = get_storage_backend()
        await run_in_storage_executor(storage.delete, old_key)
        setattr(row, key_field, None)
        setattr(row, content_type_field, None)
        row.updated_by_user_id = admin.id
        await db.commit()
        await db.refresh(row)
    return _admin_payload(row)


async def _serve_branding_asset(db: AsyncSession, key_field: str, default_url: str) -> Response:
    row = await _get_singleton(db)
    key = getattr(row, key_field)
    if not key:
        return RedirectResponse(url=default_url, status_code=302)

    storage = get_storage_backend()
    try:
        content = await run_in_storage_executor(storage.read, key)
    except FileNotFoundError:
        return RedirectResponse(url=default_url, status_code=302)

    content_type_field = "logo_content_type" if key_field == "logo_key" else "favicon_content_type"
    media_type = getattr(row, content_type_field) or "application/octet-stream"
    return Response(content=content, media_type=media_type)


# ── Public ────────────────────────────────────────────────────────────────

@router.get("/api/settings/org", response_model=OrgSettingsPublicOut)
async def get_public_org_settings(db: AsyncSession = Depends(get_db)):
    return _public_payload(await _get_singleton(db))


@router.get("/api/branding/logo")
async def get_org_logo(db: AsyncSession = Depends(get_db)):
    return await _serve_branding_asset(db, "logo_key", _DEFAULT_LOGO_URL)


@router.get("/api/branding/favicon")
async def get_org_favicon(db: AsyncSession = Depends(get_db)):
    return await _serve_branding_asset(db, "favicon_key", _DEFAULT_FAVICON_URL)


# ── Admin ─────────────────────────────────────────────────────────────────

@router.get("/api/admin/settings/org", response_model=OrgSettingsAdminOut)
async def get_admin_org_settings(
    admin: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    return _admin_payload(await _get_singleton(db))


@router.patch("/api/admin/settings/org", response_model=OrgSettingsAdminOut)
async def update_org_display_name(
    payload: OrgDisplayNameUpdate,
    admin: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    row = await _get_singleton(db)
    row.display_name = payload.display_name
    row.updated_by_user_id = admin.id
    await db.commit()
    await db.refresh(row)
    return _admin_payload(row)


@router.put("/api/admin/settings/org/logo", response_model=OrgSettingsAdminOut)
async def upload_org_logo(
    request: Request,
    file: UploadFile = File(...),
    admin: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        check_content_length(request.headers.get("content-length"), _LOGO_MAX_BYTES)
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    return await _handle_branding_upload(
        file=file,
        admin=admin,
        db=db,
        allowed_content_types=_LOGO_CONTENT_TYPES,
        max_bytes=_LOGO_MAX_BYTES,
        key_builder=branding_logo_key,
        key_field="logo_key",
        content_type_field="logo_content_type",
    )


@router.delete("/api/admin/settings/org/logo", response_model=OrgSettingsAdminOut)
async def delete_org_logo(
    admin: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _handle_branding_delete(
        admin=admin, db=db, key_field="logo_key", content_type_field="logo_content_type"
    )


@router.put("/api/admin/settings/org/favicon", response_model=OrgSettingsAdminOut)
async def upload_org_favicon(
    request: Request,
    file: UploadFile = File(...),
    admin: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        check_content_length(request.headers.get("content-length"), _FAVICON_MAX_BYTES)
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    return await _handle_branding_upload(
        file=file,
        admin=admin,
        db=db,
        allowed_content_types=_FAVICON_CONTENT_TYPES,
        max_bytes=_FAVICON_MAX_BYTES,
        key_builder=branding_favicon_key,
        key_field="favicon_key",
        content_type_field="favicon_content_type",
    )


@router.delete("/api/admin/settings/org/favicon", response_model=OrgSettingsAdminOut)
async def delete_org_favicon(
    admin: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _handle_branding_delete(
        admin=admin, db=db, key_field="favicon_key", content_type_field="favicon_content_type"
    )
