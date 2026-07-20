import hmac

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token, get_current_user, hash_password, verify_password
from app.config import get_settings
from app.database import get_db
from app.models import User, UserRole
from app.rate_limit import check_rate_limit
from app.schemas import ChangePasswordPayload, Token, UserCreate, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Generous per-IP limits: this only needs to slow down scripted credential
# stuffing / invite-code guessing, not organic use — many real users can
# legitimately register or log in from behind the same shared/NAT IP.
REGISTER_RATE_LIMIT = 30
REGISTER_RATE_WINDOW_SECONDS = 60
LOGIN_RATE_LIMIT = 30
LOGIN_RATE_WINDOW_SECONDS = 60
CHANGE_PASSWORD_RATE_LIMIT = 30
CHANGE_PASSWORD_RATE_WINDOW_SECONDS = 60


@router.get("/me", response_model=UserOut)
async def get_me(user: User = Depends(get_current_user)):
    return user


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, request: Request, db: AsyncSession = Depends(get_db)):
    redis: Redis = request.app.state.redis
    allowed = await check_rate_limit(
        redis, f"rate:register:{request.client.host}", REGISTER_RATE_LIMIT, REGISTER_RATE_WINDOW_SECONDS
    )
    if not allowed:
        raise HTTPException(status_code=429, detail="Too many registration attempts. Please try again later.")

    settings = get_settings()
    if not hmac.compare_digest(
        payload.invite_code.strip().upper(), settings.INVITE_CODE.strip().upper()
    ):
        raise HTTPException(status_code=403, detail="Invalid invite code")

    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    role = UserRole.USER
    if settings.SUPER_ADMIN_EMAIL and payload.email.strip().lower() == settings.SUPER_ADMIN_EMAIL.strip().lower():
        role = UserRole.SUPER_ADMIN

    user = User(email=payload.email, hashed_password=hash_password(payload.password), role=role)
    db.add(user)
    await db.flush()
    await db.commit()
    # Re-fetch to ensure all fields are available
    await db.refresh(user)
    return user


@router.post("/change-password", status_code=200)
async def change_password(
    payload: ChangePasswordPayload,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    redis: Redis = request.app.state.redis
    allowed = await check_rate_limit(
        redis, f"rate:change_password:{user.id}", CHANGE_PASSWORD_RATE_LIMIT, CHANGE_PASSWORD_RATE_WINDOW_SECONDS
    )
    if not allowed:
        raise HTTPException(status_code=429, detail="Too many attempts. Please try again later.")

    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")
    user.hashed_password = hash_password(payload.new_password)
    await db.commit()
    return {"message": "Password updated successfully"}


@router.post("/login", response_model=Token)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    redis: Redis = request.app.state.redis
    allowed = await check_rate_limit(
        redis, f"rate:login:{request.client.host}", LOGIN_RATE_LIMIT, LOGIN_RATE_WINDOW_SECONDS
    )
    if not allowed:
        raise HTTPException(status_code=429, detail="Too many login attempts. Please try again later.")

    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled. Contact an administrator.")

    token = create_access_token(user.id)
    return Token(access_token=token)
