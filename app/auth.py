import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import User, UserRole

settings = get_settings()

# Configure passlib to use bcrypt.
# Note: the "(trapped) error reading bcrypt version" warning is harmless.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash a password using bcrypt (72-byte limit enforced)."""
    pw = str(password)
    pw_bytes = pw.encode("utf-8")
    if len(pw_bytes) > 72:
        pw = pw_bytes[:72].decode("utf-8", errors="ignore")
    try:
        return pwd_context.hash(pw)
    except ValueError as exc:
        if "password cannot be longer than 72 bytes" in str(exc):
            import bcrypt
            raw = pw.encode("utf-8")[:72]
            return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=12)).decode("utf-8")
        raise


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    pw = str(plain)
    pw_bytes = pw.encode("utf-8")
    if len(pw_bytes) > 72:
        pw = pw_bytes[:72].decode("utf-8", errors="ignore")
    try:
        return pwd_context.verify(pw, hashed)
    except (ValueError, AttributeError):
        import bcrypt
        try:
            return bcrypt.checkpw(pw.encode("utf-8")[:72], hashed.encode("utf-8"))
        except Exception:
            return False


# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_access_token(user_id: uuid.UUID) -> str:
    """
    Issue a signed JWT.

    Payload fields:
      sub — user UUID (string)
      exp — expiry timestamp
      iat — issued-at timestamp (used for session invalidation)
      jti — unique token ID (enables per-token traceability)
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": now,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


# ── Session invalidation ──────────────────────────────────────────────────────

_SESSION_INVALIDATION_KEY = "user_sessions_invalidated_before:{user_id}"


async def invalidate_user_sessions(user_id: uuid.UUID, redis, ttl_seconds: int) -> None:
    """
    Mark all currently-issued tokens for user_id as invalid.

    Tokens whose `iat` is before the stored timestamp will be rejected on
    the next authenticated request.  The Redis key expires automatically
    after `ttl_seconds` (set this to ≥ ACCESS_TOKEN_EXPIRE_MINUTES * 60).
    """
    key = _SESSION_INVALIDATION_KEY.format(user_id=user_id)
    await redis.setex(key, ttl_seconds, str(datetime.now(timezone.utc).timestamp()))


# ── Current-user dependency ───────────────────────────────────────────────────

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
    request: Request = None,  # FastAPI injects this; None only in non-HTTP contexts
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # ── Session-invalidation check (Redis) ────────────────────────────────────
    if request is not None:
        redis = getattr(request.app.state, "redis", None)
        if redis is not None:
            try:
                iat = payload.get("iat")
                if iat is not None:
                    inv_key = _SESSION_INVALIDATION_KEY.format(user_id=user_id)
                    invalidated_before = await redis.get(inv_key)
                    if invalidated_before and float(invalidated_before) > float(iat):
                        raise credentials_exception
            except HTTPException:
                raise
            except Exception:
                pass  # Fail open: don't block auth if Redis is temporarily unavailable

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user


async def get_current_super_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required",
        )
    return user
