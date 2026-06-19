from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import SystemSettings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/public")
async def get_public_settings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SystemSettings).where(SystemSettings.id == 1))
    s = result.scalar_one_or_none()

    if s is None:
        return {
            "org_name": "Tech4Good Community",
            "org_logo_url": "/logo-mascot.webp",
            "invite_required": True,
            "onboarding_locked": False,
        }

    return {
        "org_name": s.org_name,
        "org_logo_url": s.org_logo_url,
        "invite_required": s.invite_code_enabled,
        "onboarding_locked": s.onboarding_locked,
    }
