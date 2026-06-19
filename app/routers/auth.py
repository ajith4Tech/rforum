import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import AuditAction, AuditEntity, log_audit
from app.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.config import get_settings
from app.database import get_db
from app.models import PasswordResetToken, SystemSettings, User, UserRole
from app.schemas import (
    ChangePasswordPayload,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    Token,
    UserCreate,
    UserOut,
)
from app.utils import check_rate_limit

router = APIRouter(prefix="/api/auth", tags=["auth"])

_RESET_EXPIRY_MINUTES = 30


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _ua(request: Request) -> str:
    return request.headers.get("User-Agent", "")


def _trace(request: Request) -> str | None:
    return getattr(request.state, "trace_id", None)


# ── GET /me ───────────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserOut)
async def get_me(user: User = Depends(get_current_user)):
    return user


# ── POST /register ────────────────────────────────────────────────────────────

@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, request: Request, db: AsyncSession = Depends(get_db)):
    redis = request.app.state.redis
    if not await check_rate_limit(redis, f"rl:register:{_ip(request)}", 5, 60):
        raise HTTPException(status_code=429, detail="Too many registration attempts. Try again later.")

    # Lock the settings row so concurrent first-registrations serialize.
    result = await db.execute(
        select(SystemSettings).where(SystemSettings.id == 1).with_for_update()
    )
    sys_settings = result.scalar_one_or_none()

    if sys_settings is None:
        raise HTTPException(status_code=503, detail="System not initialized. Please restart the server.")

    count_result = await db.execute(select(func.count()).select_from(User))
    user_count = count_result.scalar_one()
    is_first_user = user_count == 0

    if not is_first_user:
        if sys_settings.invite_code_enabled:
            if payload.invite_code.strip().upper() != sys_settings.invite_code.strip().upper():
                log_audit(
                    AuditAction.INVITE_CODE_REJECTED,
                    AuditEntity.AUTH,
                    ip_address=_ip(request),
                    user_agent=_ua(request),
                    metadata={"email": payload.email},
                    trace_id=_trace(request),
                )
                raise HTTPException(status_code=403, detail="Invalid invite code")

    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    role = UserRole.SUPER_ADMIN if is_first_user else UserRole.USER
    user = User(email=payload.email, hashed_password=hash_password(payload.password), role=role)
    db.add(user)
    await db.flush()

    if is_first_user:
        sys_settings.onboarding_locked = True

    await db.commit()
    await db.refresh(user)

    log_audit(
        AuditAction.SUPER_ADMIN_CREATED if is_first_user else AuditAction.USER_REGISTERED,
        AuditEntity.USER,
        user_id=user.id,
        entity_id=str(user.id),
        ip_address=_ip(request),
        user_agent=_ua(request),
        trace_id=_trace(request),
    )
    return user


# ── POST /login ───────────────────────────────────────────────────────────────

@router.post("/login", response_model=Token)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    redis = request.app.state.redis
    if not await check_rate_limit(redis, f"rl:login:{_ip(request)}", 10, 60):
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")

    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        log_audit(
            AuditAction.LOGIN_FAILED,
            AuditEntity.AUTH,
            ip_address=_ip(request),
            user_agent=_ua(request),
            metadata={"email": form_data.username},
            trace_id=_trace(request),
        )
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled. Contact an administrator.")

    log_audit(
        AuditAction.LOGIN_SUCCESS,
        AuditEntity.AUTH,
        user_id=user.id,
        entity_id=str(user.id),
        ip_address=_ip(request),
        user_agent=_ua(request),
        trace_id=_trace(request),
    )
    return Token(access_token=create_access_token(user.id))


# ── POST /change-password ─────────────────────────────────────────────────────

@router.post("/change-password", status_code=200)
async def change_password(
    payload: ChangePasswordPayload,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")
    user.hashed_password = hash_password(payload.new_password)
    await db.commit()
    return {"message": "Password updated successfully"}


# ── POST /forgot-password ─────────────────────────────────────────────────────

@router.post("/forgot-password")
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    redis = request.app.state.redis
    if not await check_rate_limit(redis, f"rl:forgot:{_ip(request)}", 3, 300):
        raise HTTPException(status_code=429, detail="Too many requests. Try again later.")

    _generic = {"message": "If account exists, a reset link has been generated", "reset_token": None}

    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        return _generic

    # Invalidate all existing tokens for this user before issuing a new one.
    await db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id))

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=_RESET_EXPIRY_MINUTES)

    db.add(PasswordResetToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
    await db.commit()

    log_audit(
        AuditAction.PASSWORD_RESET_REQUESTED,
        AuditEntity.AUTH,
        user_id=user.id,
        entity_id=str(user.id),
        ip_address=_ip(request),
        user_agent=_ua(request),
        trace_id=_trace(request),
    )
    return {"message": "If account exists, a reset link has been generated", "reset_token": raw_token}


# ── POST /reset-password ──────────────────────────────────────────────────────

@router.post("/reset-password")
async def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    redis = request.app.state.redis
    if not await check_rate_limit(redis, f"rl:reset:{_ip(request)}", 5, 300):
        raise HTTPException(status_code=429, detail="Too many requests. Try again later.")

    token_hash = hashlib.sha256(payload.token.strip().encode()).hexdigest()
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used == False,
            PasswordResetToken.expires_at > now,
        )
    )
    reset_token_row = result.scalar_one_or_none()

    if not reset_token_row:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user_result = await db.execute(select(User).where(User.id == reset_token_row.user_id))
    user = user_result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user.hashed_password = hash_password(payload.new_password)
    reset_token_row.used = True
    await db.commit()

    log_audit(
        AuditAction.PASSWORD_RESET_SUCCESS,
        AuditEntity.AUTH,
        user_id=user.id,
        entity_id=str(user.id),
        ip_address=_ip(request),
        user_agent=_ua(request),
        trace_id=_trace(request),
    )
    return {"message": "Password reset successful"}
