import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import Event, Response, Session, Slide, SlideType, User

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/")
async def get_analytics(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = user.id

    # Total events
    total_events_result = await db.execute(
        select(func.count(Event.id)).where(Event.owner_id == user_id)
    )
    total_events = total_events_result.scalar() or 0

    # Total sessions
    total_sessions_result = await db.execute(
        select(func.count(Session.id)).where(Session.owner_id == user_id)
    )
    total_sessions = total_sessions_result.scalar() or 0

    # Active (live) sessions
    active_sessions_result = await db.execute(
        select(func.count(Session.id)).where(
            Session.owner_id == user_id, Session.is_live == True  # noqa: E712
        )
    )
    active_sessions = active_sessions_result.scalar() or 0

    # Total unique participants (unique guest identifiers across all responses
    # on slides owned by this user's sessions)
    total_participants_result = await db.execute(
        select(func.count(func.distinct(Response.guest_identifier)))
        .select_from(Response)
        .join(Slide, Slide.id == Response.slide_id)
        .join(Session, Session.id == Slide.session_id)
        .where(Session.owner_id == user_id)
    )
    total_participants = total_participants_result.scalar() or 0

    # Slide type distribution
    slide_type_result = await db.execute(
        select(Slide.type, func.count(Slide.id))
        .join(Session, Session.id == Slide.session_id)
        .where(Session.owner_id == user_id)
        .group_by(Slide.type)
    )
    slide_type_distribution = {
        row[0].value if hasattr(row[0], "value") else str(row[0]): row[1]
        for row in slide_type_result.all()
    }

    # Engagement over time: responses per day for the last 30 days
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)
    engagement_result = await db.execute(
        select(
            func.date(Response.created_at).label("day"),
            func.count(Response.id).label("count"),
        )
        .select_from(Response)
        .join(Slide, Slide.id == Response.slide_id)
        .join(Session, Session.id == Slide.session_id)
        .where(Session.owner_id == user_id, Response.created_at >= thirty_days_ago)
        .group_by(func.date(Response.created_at))
        .order_by(func.date(Response.created_at))
    )
    engagement_over_time = [
        {"date": str(row.day), "responses": row.count}
        for row in engagement_result.all()
    ]

    # ── Advanced Analytics ────────────────────────────

    # Average rating & rating distribution (from FEEDBACK slides with ratings)
    rating_result = await db.execute(
        select(
            func.avg(Response.rating),
            func.count(Response.id),
            func.sum(case((Response.rating == 1, 1), else_=0)),
            func.sum(case((Response.rating == 2, 1), else_=0)),
            func.sum(case((Response.rating == 3, 1), else_=0)),
            func.sum(case((Response.rating == 4, 1), else_=0)),
            func.sum(case((Response.rating == 5, 1), else_=0)),
        )
        .select_from(Response)
        .join(Slide, Slide.id == Response.slide_id)
        .join(Session, Session.id == Slide.session_id)
        .where(
            Session.owner_id == user_id,
            Slide.type == SlideType.FEEDBACK,
            Response.rating.isnot(None),
        )
    )
    rating_row = rating_result.one()
    avg_rating = round(float(rating_row[0]), 2) if rating_row[0] else None
    total_ratings = int(rating_row[1] or 0)
    rating_distribution = {
        str(i): int(rating_row[i + 1] or 0) for i in range(1, 6)
    }

    # Feedback sentiment: positive (4-5), neutral (3), negative (1-2)
    positive = (rating_distribution.get("4", 0) or 0) + (rating_distribution.get("5", 0) or 0)
    neutral = rating_distribution.get("3", 0) or 0
    negative = (rating_distribution.get("1", 0) or 0) + (rating_distribution.get("2", 0) or 0)
    feedback_sentiment = {
        "positive": positive,
        "neutral": neutral,
        "negative": negative,
        "total": total_ratings,
    }

    # Per-session engagement: responses, unique participants, avg feedback rating
    session_eng_result = await db.execute(
        select(
            Session.id,
            Session.title,
            func.count(Response.id).label("total_responses"),
            func.count(func.distinct(Response.guest_identifier)).label("unique_participants"),
            func.avg(
                case(
                    (Slide.type == SlideType.FEEDBACK, Response.rating),
                    else_=None,
                )
            ).label("avg_rating"),
        )
        .select_from(Session)
        .outerjoin(Slide, Slide.session_id == Session.id)
        .outerjoin(Response, Response.slide_id == Slide.id)
        .where(Session.owner_id == user_id)
        .group_by(Session.id, Session.title)
        .order_by(func.count(Response.id).desc())
    )
    session_engagement = []
    for row in session_eng_result.all():
        session_engagement.append({
            "session_id": str(row.id),
            "title": row.title,
            "total_responses": row.total_responses,
            "unique_participants": row.unique_participants,
            "avg_rating": round(float(row.avg_rating), 2) if row.avg_rating else None,
        })

    return {
        "total_events": total_events,
        "total_sessions": total_sessions,
        "active_sessions": active_sessions,
        "total_participants": total_participants,
        "slide_type_distribution": slide_type_distribution,
        "engagement_over_time": engagement_over_time,
        "avg_rating": avg_rating,
        "rating_distribution": rating_distribution,
        "feedback_sentiment": feedback_sentiment,
        "session_engagement": session_engagement,
    }
