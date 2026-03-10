import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import Event, Response, Session, SessionAsset, Slide, SlideType, User, UserRole

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/")
async def get_analytics(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    is_admin = user.role == UserRole.SUPER_ADMIN
    # Admin sees platform-wide stats; regular user sees only their own
    user_id = user.id

    # Total events
    events_q = select(func.count(Event.id))
    if not is_admin:
        events_q = events_q.where(Event.owner_id == user_id)
    total_events_result = await db.execute(events_q)
    total_events = total_events_result.scalar() or 0

    # Total sessions
    sessions_q = select(func.count(Session.id))
    if not is_admin:
        sessions_q = sessions_q.where(Session.owner_id == user_id)
    total_sessions_result = await db.execute(sessions_q)
    total_sessions = total_sessions_result.scalar() or 0

    # Active (live) sessions
    active_q = select(func.count(Session.id)).where(Session.is_live == True)  # noqa: E712
    if not is_admin:
        active_q = active_q.where(Session.owner_id == user_id)
    active_sessions_result = await db.execute(active_q)
    active_sessions = active_sessions_result.scalar() or 0

    # Total unique participants
    participants_q = (
        select(func.count(func.distinct(Response.guest_identifier)))
        .select_from(Response)
        .join(Slide, Slide.id == Response.slide_id)
        .join(Session, Session.id == Slide.session_id)
    )
    if not is_admin:
        participants_q = participants_q.where(Session.owner_id == user_id)
    total_participants_result = await db.execute(participants_q)
    total_participants = total_participants_result.scalar() or 0

    # Slide type distribution
    slide_type_q = (
        select(Slide.type, func.count(Slide.id))
        .join(Session, Session.id == Slide.session_id)
    )
    if not is_admin:
        slide_type_q = slide_type_q.where(Session.owner_id == user_id)
    slide_type_q = slide_type_q.group_by(Slide.type)
    slide_type_result = await db.execute(slide_type_q)
    slide_type_distribution = {
        row[0].value if hasattr(row[0], "value") else str(row[0]): row[1]
        for row in slide_type_result.all()
    }

    # Engagement over time: responses per day for the last 30 days
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)
    engagement_q = (
        select(
            func.date(Response.created_at).label("day"),
            func.count(Response.id).label("count"),
        )
        .select_from(Response)
        .join(Slide, Slide.id == Response.slide_id)
        .join(Session, Session.id == Slide.session_id)
        .where(Response.created_at >= thirty_days_ago)
    )
    if not is_admin:
        engagement_q = engagement_q.where(Session.owner_id == user_id)
    engagement_q = engagement_q.group_by(func.date(Response.created_at)).order_by(func.date(Response.created_at))
    engagement_result = await db.execute(engagement_q)
    engagement_over_time = [
        {"date": str(row.day), "responses": row.count}
        for row in engagement_result.all()
    ]

    # ── Advanced Analytics ────────────────────────────

    # Average rating & rating distribution (from FEEDBACK slides with ratings)
    rating_q = (
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
            Slide.type == SlideType.FEEDBACK,
            Response.rating.isnot(None),
        )
    )
    if not is_admin:
        rating_q = rating_q.where(Session.owner_id == user_id)
    rating_result = await db.execute(rating_q)
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
    session_eng_q = (
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
        .group_by(Session.id, Session.title)
        .order_by(func.count(Response.id).desc())
    )
    if not is_admin:
        session_eng_q = session_eng_q.where(Session.owner_id == user_id)
    session_eng_result = await db.execute(session_eng_q)
    session_engagement = []
    for row in session_eng_result.all():
        session_engagement.append({
            "session_id": str(row.id),
            "title": row.title,
            "total_responses": row.total_responses,
            "unique_participants": row.unique_participants,
            "avg_rating": round(float(row.avg_rating), 2) if row.avg_rating else None,
        })

    # Total slides
    total_slides_q = select(func.count(Slide.id)).join(Session, Session.id == Slide.session_id)
    if not is_admin:
        total_slides_q = total_slides_q.where(Session.owner_id == user_id)
    total_slides_result = await db.execute(total_slides_q)
    total_slides = total_slides_result.scalar() or 0

    # Response counts grouped by slide type
    resp_type_q = (
        select(Slide.type, func.count(Response.id))
        .select_from(Response)
        .join(Slide, Slide.id == Response.slide_id)
        .join(Session, Session.id == Slide.session_id)
        .group_by(Slide.type)
    )
    if not is_admin:
        resp_type_q = resp_type_q.where(Session.owner_id == user_id)
    response_by_type_result = await db.execute(resp_type_q)
    response_counts_by_type = {
        row[0].value if hasattr(row[0], "value") else str(row[0]): row[1]
        for row in response_by_type_result.all()
    }

    # Total responses across all slides
    total_resp_q = (
        select(func.count(Response.id))
        .select_from(Response)
        .join(Slide, Slide.id == Response.slide_id)
        .join(Session, Session.id == Slide.session_id)
    )
    if not is_admin:
        total_resp_q = total_resp_q.where(Session.owner_id == user_id)
    total_responses_result = await db.execute(total_resp_q)
    total_responses = total_responses_result.scalar() or 0

    # Storage used
    storage_q = select(func.coalesce(func.sum(SessionAsset.file_size), 0))
    if not is_admin:
        storage_q = storage_q.where(SessionAsset.user_id == user_id)
    storage_used_bytes = int(await db.scalar(storage_q) or 0)

    return {
        "total_events": total_events,
        "total_sessions": total_sessions,
        "total_slides": total_slides,
        "total_responses": total_responses,
        "active_sessions": active_sessions,
        "total_participants": total_participants,
        "slide_type_distribution": slide_type_distribution,
        "response_counts_by_type": response_counts_by_type,
        "engagement_over_time": engagement_over_time,
        "avg_rating": avg_rating,
        "rating_distribution": rating_distribution,
        "feedback_sentiment": feedback_sentiment,
        "session_engagement": session_engagement,
        "storage_used_bytes": storage_used_bytes,
    }
