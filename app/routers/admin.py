"""
Admin router – endpoints accessible only to SUPER_ADMIN users.

Capabilities:
- List / delete users
- Change user roles
- List / delete any session (moderation)
- List / delete any event (moderation)
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_super_admin
from app.database import get_db
from app.models import Event, Session, SessionAsset, User, UserRole
from app.schemas import UserAdminOut, UserOut, UserRoleUpdate


class UserActiveUpdate(BaseModel):
    is_active: bool


router = APIRouter(prefix="/api/admin", tags=["admin"])


# ── Users ────────────────────────────────────────────────────────────────────

@router.get("/users", response_model=list[UserAdminOut])
async def list_users(
    admin: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Return all registered users with their session/event counts."""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()

    # Fetch counts per user in bulk
    sessions_count_rows = await db.execute(
        select(Session.owner_id, func.count(Session.id).label("cnt"))
        .group_by(Session.owner_id)
    )
    sessions_map = {row.owner_id: row.cnt for row in sessions_count_rows}

    events_count_rows = await db.execute(
        select(Event.owner_id, func.count(Event.id).label("cnt"))
        .group_by(Event.owner_id)
    )
    events_map = {row.owner_id: row.cnt for row in events_count_rows}

    out = []
    for u in users:
        data = UserAdminOut.model_validate(u)
        data.sessions_count = sessions_map.get(u.id, 0)
        data.events_count = events_map.get(u.id, 0)
        out.append(data)
    return out


@router.get("/users/{user_id}", response_model=UserAdminOut)
async def get_user(
    user_id: str,
    admin: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    sessions_count = await db.scalar(
        select(func.count(Session.id)).where(Session.owner_id == uid)
    ) or 0
    events_count = await db.scalar(
        select(func.count(Event.id)).where(Event.owner_id == uid)
    ) or 0

    data = UserAdminOut.model_validate(user)
    data.sessions_count = sessions_count
    data.events_count = events_count
    return data


@router.patch("/users/{user_id}/role", response_model=UserOut)
async def update_user_role(
    user_id: str,
    payload: UserRoleUpdate,
    admin: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Promote or demote a user's role. Super admin cannot demote themselves."""
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    if uid == admin.id:
        raise HTTPException(status_code=400, detail="Cannot change your own role")

    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.role = payload.role
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/users/{user_id}/active", response_model=UserOut)
async def update_user_active(
    user_id: str,
    payload: UserActiveUpdate,
    admin: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Enable or disable a user account. Super admin cannot disable themselves."""
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    if uid == admin.id:
        raise HTTPException(status_code=400, detail="Cannot disable your own account")

    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = payload.is_active
    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    admin: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Permanently delete a user and all their owned content
    (sessions, slides, events cascade via FK).
    Super admin cannot delete themselves.
    """
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    if uid == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    result = await db.execute(delete(User).where(User.id == uid))
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="User not found")
    await db.commit()


# ── Sessions (moderation) ─────────────────────────────────────────────────────

@router.get("/sessions", response_model=list[dict])
async def list_all_sessions(
    admin: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """List every session across all users."""
    result = await db.execute(select(Session).order_by(Session.created_at.desc()))
    sessions = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "owner_id": str(s.owner_id),
            "event_id": str(s.event_id) if s.event_id else None,
            "unique_code": s.unique_code,
            "title": s.title,
            "is_live": s.is_live,
            "created_at": s.created_at.isoformat(),
        }
        for s in sessions
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_any_session(
    session_id: str,
    admin: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Force-delete any session (moderation)."""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session ID")

    result = await db.execute(delete(Session).where(Session.id == sid))
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.commit()


# ── Events (moderation) ───────────────────────────────────────────────────────

@router.get("/events", response_model=list[dict])
async def list_all_events(
    admin: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """List every event across all users."""
    result = await db.execute(select(Event).order_by(Event.created_at.desc()))
    events = result.scalars().all()
    return [
        {
            "id": str(e.id),
            "owner_id": str(e.owner_id),
            "title": e.title,
            "event_date": e.event_date.isoformat(),
            "description": e.description,
            "is_published": e.is_published,
            "created_at": e.created_at.isoformat(),
        }
        for e in events
    ]


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_any_event(
    event_id: str,
    admin: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Force-delete any event (moderation)."""
    try:
        eid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid event ID")

    result = await db.execute(delete(Event).where(Event.id == eid))
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Event not found")
    await db.commit()


# ── Storage (moderation) ────────────────────────────────────────────────

@router.get("/storage")
async def admin_get_storage(
    admin: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Return platform-wide total storage and per-user breakdown (top 20)."""
    total = int(await db.scalar(
        select(func.coalesce(func.sum(SessionAsset.file_size), 0))
    ) or 0)

    asset_count = int(await db.scalar(
        select(func.count(SessionAsset.id))
    ) or 0)

    rows = await db.execute(
        select(
            User.id,
            User.email,
            func.coalesce(func.sum(SessionAsset.file_size), 0).label("total_bytes"),
            func.count(SessionAsset.id).label("asset_count"),
        )
        .outerjoin(SessionAsset, SessionAsset.user_id == User.id)
        .group_by(User.id, User.email)
        .order_by(func.coalesce(func.sum(SessionAsset.file_size), 0).desc())
        .limit(20)
    )

    top_users = [
        {
            "user_id": str(row.id),
            "email": row.email,
            "total_bytes": int(row.total_bytes),
            "asset_count": int(row.asset_count),
        }
        for row in rows.all()
    ]

    return {"total_bytes": total, "asset_count": asset_count, "top_users": top_users}
