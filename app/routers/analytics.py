import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import Event, Response, Session, SessionAsset, Slide, SlideType, User, UserRole
import io
import csv

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

    # Engagement over time: (Removed timeline analytics as requested)
    engagement_over_time = []


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



@router.get('/event/{event_id}/download')
async def download_event_analytics(
    event_id: str,
    format: str = 'csv',
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        event_uuid = uuid.UUID(event_id)
    except ValueError:
        return JSONResponse({'detail': 'Invalid event ID format'}, status_code=400)

    # Only owner or super-admin can download
    is_admin = user.role == UserRole.SUPER_ADMIN
    # verify event exists and permission
    ev_q = select(Event).where(Event.id == event_uuid)
    ev_res = await db.execute(ev_q)
    ev = ev_res.scalar_one_or_none()
    if not ev:
        return JSONResponse({'detail': 'Event not found'}, status_code=404)
    if not is_admin and ev.owner_id != user.id:
        return JSONResponse({'detail': 'Forbidden'}, status_code=403)

    # Build basic analytics for the event
    # Sessions for event
    sessions_q = select(Session.id, Session.title).where(Session.event_id == event_uuid)
    sessions_res = await db.execute(sessions_q)
    sessions = sessions_res.all()

    # Per-session engagement
    session_eng_q = (
        select(
            Session.id,
            Session.title,
            Session.moderator_name,
            func.count(Response.id).label('total_responses'),
            func.count(func.distinct(Response.guest_identifier)).label('unique_participants'),
            func.count(func.distinct(Slide.id)).label('slide_count'),
            func.avg(
                case(
                    (Slide.type == SlideType.FEEDBACK, Response.rating),
                    else_=None,
                )
            ).label('avg_rating'),
        )
        .select_from(Session)
        .outerjoin(Slide, Slide.session_id == Session.id)
        .outerjoin(Response, Response.slide_id == Slide.id)
        .where(Session.event_id == event_id)
        .group_by(Session.id, Session.title, Session.moderator_name)
        .order_by(func.count(Response.id).desc())
    )
    res = await db.execute(session_eng_q)
    session_rows = res.all()

    # Engagement over time for event (Removed timeline analytics)
    engagement_rows = []

    data = {
        'event': {'id': str(ev.id), 'title': ev.title, 'description': ev.description},
        'sessions': [
            {
                'session_id': str(r[0]),
                'title': r[1],
            }
            for r in sessions
        ],
        'session_engagement': [
            {
                'session_id': str(row.id),
                'title': row.title,
                'moderator_name': row.moderator_name,
                'total_responses': int(row.total_responses or 0),
                'unique_participants': int(row.unique_participants or 0),
                'slide_count': int(row.slide_count or 0),
                'avg_rating': float(row.avg_rating) if row.avg_rating is not None else None,
            }
            for row in session_rows
        ],
        'engagement_over_time': [],
    }

    # Include all responses for the event (grouped by session -> slide)
    resp_q = (
        select(
            Response.id,
            Response.slide_id,
            Response.value,
            Response.guest_identifier,
            Response.name,
            Response.rating,
            Response.created_at,
            Slide.session_id,
            Slide.order,
            Slide.type,
        )
        .select_from(Response)
        .join(Slide, Slide.id == Response.slide_id)
        .join(Session, Session.id == Slide.session_id)
        .where(Session.event_id == event_id)
        .order_by(Slide.session_id, Slide.order, Response.created_at)
    )
    resp_res = await db.execute(resp_q)
    resp_rows = resp_res.all()

    # group responses by session -> slide
    sessions_map: dict = {}
    for r in resp_rows:
        sid = str(r.session_id)
        slide_id = str(r[1])
        if sid not in sessions_map:
            sessions_map[sid] = {'slides': {}, 'responses': []}
        # store slide info
        if slide_id not in sessions_map[sid]['slides']:
            sessions_map[sid]['slides'][slide_id] = {'type': r.type.value if hasattr(r.type, 'value') else str(r.type), 'order': r.order}
        sessions_map[sid]['responses'].append({
            'response_id': str(r[0]),
            'slide_id': slide_id,
            'value': r.value,
            'guest_identifier': r.guest_identifier,
            'name': r.name,
            'rating': r.rating,
            'created_at': str(r.created_at),
        })

    data['responses_by_session'] = []
    for s_id, payload in sessions_map.items():
        data['responses_by_session'].append({'session_id': s_id, 'slides': payload['slides'], 'responses': payload['responses']})

    if format.lower() == 'json':
        return JSONResponse(data)

    # Build CSV
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['Event', ev.title])
    writer.writerow([])
    writer.writerow(['Sessions'])
    writer.writerow(['session_id', 'title'])
    for s in data['sessions']:
        writer.writerow([s['session_id'], s['title']])
    writer.writerow([])
    writer.writerow(['Session Engagement'])
    writer.writerow(['session_id', 'title', 'total_responses', 'unique_participants', 'avg_rating'])
    for s in data['session_engagement']:
        writer.writerow([s['session_id'], s['title'], s['total_responses'], s['unique_participants'], s['avg_rating'] or ''])
    # (Removed timeline section from CSV export)

    # Responses by session (detailed)
    writer.writerow([])
    writer.writerow(['Responses By Session'])
    for sess in data.get('responses_by_session', []):
        writer.writerow([])
        writer.writerow(['Session', sess.get('session_id')])
        # slides
        writer.writerow(['Slides'])
        writer.writerow(['slide_id', 'type', 'order'])
        for sid, sinfo in (sess.get('slides') or {}).items():
            writer.writerow([sid, sinfo.get('type'), sinfo.get('order')])
        writer.writerow([])
        # responses
        writer.writerow(['Responses'])
        writer.writerow(['response_id', 'slide_id', 'value', 'guest_identifier', 'name', 'rating', 'created_at'])
        for r in (sess.get('responses') or []):
            writer.writerow([r.get('response_id'), r.get('slide_id'), r.get('value'), r.get('guest_identifier'), r.get('name') or '', r.get('rating') or '', r.get('created_at')])

    buf.seek(0)
    headers = {
        'Content-Disposition': f'attachment; filename="analytics_event_{event_id}.csv"'
    }
    return StreamingResponse(buf, media_type='text/csv', headers=headers)


@router.get('/session/{session_id}/download')
async def download_session_analytics(
    session_id: str,
    format: str = 'csv',
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        return JSONResponse({'detail': 'Invalid session ID format'}, status_code=400)

    is_admin = user.role == UserRole.SUPER_ADMIN
    # verify session and permission
    s_q = select(Session).where(Session.id == session_uuid)
    s_res = await db.execute(s_q)
    session_obj = s_res.scalar_one_or_none()
    if not session_obj:
        return JSONResponse({'detail': 'Session not found'}, status_code=404)
    if not is_admin and session_obj.owner_id != user.id:
        return JSONResponse({'detail': 'Forbidden'}, status_code=403)

    # gather responses grouped by slide. content_json is included so callers
    # (e.g. the PDF report) can render question/option text without a second
    # request to the legacy /slides endpoint, which 409s for presentation-first
    # sessions (see app/routers/slides.py::_ensure_not_presentation_session).
    slides_q = (
        select(Slide.id, Slide.type, Slide.order, Slide.content_json)
        .where(Slide.session_id == session_uuid)
        .order_by(Slide.order)
    )
    slides_res = await db.execute(slides_q)
    slides = slides_res.all()

    responses = []
    slide_ids = [s[0] for s in slides]
    if slide_ids:
        resp_q = (
            select(Response.id, Response.slide_id, Response.value, Response.guest_identifier, Response.name, Response.rating, Response.created_at)
            .where(Response.slide_id.in_(slide_ids))
            .order_by(Response.created_at)
        )
        resp_res = await db.execute(resp_q)
        responses = resp_res.all()

    data = {
        'session': {'id': str(session_obj.id), 'title': session_obj.title},
        'slides': [
            {
                'slide_id': str(s[0]),
                'type': s[1].value if hasattr(s[1], 'value') else str(s[1]),
                'order': s[2],
                'content_json': s[3] or {},
            }
            for s in slides
        ],
        'responses': [
            {
                'response_id': str(r[0]),
                'slide_id': str(r[1]),
                'value': r[2],
                'guest_identifier': r[3],
                'name': r[4],
                'rating': r[5],
                'created_at': str(r[6]),
            }
            for r in responses
        ],
    }

    if format.lower() == 'json':
        return JSONResponse(data)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['Session', session_obj.title])
    writer.writerow([])
    writer.writerow(['Slides'])
    writer.writerow(['slide_id', 'type', 'order'])
    for sl in data['slides']:
        writer.writerow([sl['slide_id'], sl['type'], sl['order']])
    writer.writerow([])
    writer.writerow(['Responses'])
    writer.writerow(['response_id', 'slide_id', 'value', 'guest_identifier', 'name', 'rating', 'created_at'])
    for r in data['responses']:
        writer.writerow([r['response_id'], r['slide_id'], r['value'], r['guest_identifier'], r['name'] or '', r['rating'] or '', r['created_at']])

    buf.seek(0)
    headers = {'Content-Disposition': f'attachment; filename="analytics_session_{session_id}.csv"'}
    return StreamingResponse(buf, media_type='text/csv', headers=headers)
