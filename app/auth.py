import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import User

settings = get_settings()

# Configure passlib to use bcrypt
# Note: The "(trapped) error reading bcrypt version" warning is harmless
# and can be ignored - passlib will still work correctly
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt, ensuring it's within the 72-byte limit."""
    password_str = str(password)
    password_bytes = password_str.encode('utf-8')
    
    # Bcrypt has a 72-byte limit - truncate if necessary
    if len(password_bytes) > 72:
        password_str = password_bytes[:72].decode('utf-8', errors='ignore')
    
    try:
        return pwd_context.hash(password_str)
    except ValueError as e:
        # If passlib fails due to bcrypt issues, use bcrypt directly
        if "password cannot be longer than 72 bytes" in str(e):
            import bcrypt
            # Ensure we're using bytes
            pwd_bytes = password_str.encode('utf-8')[:72]
            salt = bcrypt.gensalt(rounds=12)
            return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')
        raise


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a password against a hash."""
    plain_str = str(plain)
    plain_bytes = plain_str.encode('utf-8')
    
    # Truncate if longer than 72 bytes
    if len(plain_bytes) > 72:
        plain_str = plain_bytes[:72].decode('utf-8', errors='ignore')
    
    try:
        return pwd_context.verify(plain_str, hashed)
    except (ValueError, AttributeError):
        # Fallback to direct bcrypt if passlib fails
        import bcrypt
        try:
            pwd_bytes = plain_str.encode('utf-8')[:72]
            return bcrypt.checkpw(pwd_bytes, hashed.encode('utf-8'))
        except Exception:
            return False


def create_access_token(user_id: uuid.UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
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

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user
