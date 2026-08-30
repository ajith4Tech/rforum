from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

import enum


class SlideType(str, enum.Enum):
    POLL = "POLL"
    QNA = "QNA"
    FEEDBACK = "FEEDBACK"
    CONTENT = "CONTENT"
    WORD_CLOUD = "WORD_CLOUD"


class UserRole(str, enum.Enum):
    USER = "USER"
    SUPER_ADMIN = "SUPER_ADMIN"


class PresentationStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class PresentationSourceFormat(str, enum.Enum):
    PDF = "PDF"
    PPT = "PPT"
    PPTX = "PPTX"


class TimelineItemType(str, enum.Enum):
    PAGE = "PAGE"
    POLL = "POLL"
    QNA = "QNA"
    WORD_CLOUD = "WORD_CLOUD"
    FEEDBACK = "FEEDBACK"
    RATING = "RATING"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=True, name="userrole"),
        nullable=False,
        default=UserRole.USER,
        server_default=UserRole.USER.value,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    sessions: Mapped[list["Session"]] = relationship(back_populates="owner")
    events: Mapped[list["Event"]] = relationship(back_populates="owner")
    session_assets: Mapped[list["SessionAsset"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    owner: Mapped["User"] = relationship(back_populates="events")
    sessions: Mapped[list["Session"]] = relationship(back_populates="event")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="SET NULL"), nullable=True, index=True
    )
    unique_code: Mapped[str] = mapped_column(
        String(9), unique=True, nullable=False
    )  # e.g. ABCD-1234
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    moderator_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    speaker_names: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_live: Mapped[bool] = mapped_column(Boolean, default=False)
    qr_visible: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    # Optional link to a Presentation. NULL for every legacy session — the sole flag
    # the backend/frontend use to pick between the legacy slide-list flow and the
    # new Presentation Timeline flow.
    presentation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("presentations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    owner: Mapped["User"] = relationship(back_populates="sessions")
    event: Mapped[Event | None] = relationship(back_populates="sessions")
    slides: Mapped[list["Slide"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="Slide.order"
    )
    questions: Mapped[list["Question"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    feedbacks: Mapped[list["Feedback"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    presentation: Mapped["Presentation | None"] = relationship(foreign_keys=[presentation_id])
    timeline: Mapped["PresentationTimeline | None"] = relationship(
        back_populates="session", cascade="all, delete-orphan", uselist=False
    )


class Slide(Base):
    __tablename__ = "slides"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[SlideType] = mapped_column(
        Enum(SlideType, native_enum=True), nullable=False
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)

    session: Mapped["Session"] = relationship(back_populates="slides")
    responses: Mapped[list["Response"]] = relationship(
        back_populates="slide", cascade="all, delete-orphan"
    )


class Response(Base):
    __tablename__ = "responses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slide_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("slides.id", ondelete="CASCADE"), nullable=False, index=True
    )
    value: Mapped[str] = mapped_column(Text, nullable=False)
    guest_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    upvotes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    slide: Mapped["Slide"] = relationship(back_populates="responses")


class Poll(Base):
    __tablename__ = "polls"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    question: Mapped[str] = mapped_column(String(255), nullable=False)

    options: Mapped[list["PollOption"]] = relationship(
        back_populates="poll", cascade="all, delete-orphan"
    )


class PollOption(Base):
    __tablename__ = "poll_options"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    poll_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("polls.id", ondelete="CASCADE"), nullable=False
    )
    option_text: Mapped[str] = mapped_column(String(255), nullable=False)

    poll: Mapped["Poll"] = relationship(back_populates="options")


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)

    session: Mapped["Session"] = relationship(back_populates="questions")


class SessionAsset(Base):
    """Tracks every file uploaded by a user (linked to a slide/session/event)."""
    __tablename__ = "session_assets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="SET NULL"), nullable=True, index=True
    )
    slide_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("slides.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Set when this asset is the immutable original file behind a Presentation.
    # Destructive asset actions (replace/delete) must refuse when this is set —
    # those flows go through the presentations router instead. Never filtered/
    # joined on directly (only set on insert), so no index here.
    presentation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("presentations.id", ondelete="SET NULL"), nullable=True
    )
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_type: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="session_assets")
    session: Mapped["Session | None"] = relationship(foreign_keys=[session_id])
    event: Mapped["Event | None"] = relationship(foreign_keys=[event_id])
    presentation: Mapped["Presentation | None"] = relationship(foreign_keys=[presentation_id])


class Feedback(Base):
    __tablename__ = "feedbacks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    feedback: Mapped[str] = mapped_column(Text, nullable=False)

    session: Mapped["Session"] = relationship(back_populates="feedbacks")


class Presentation(Base):
    """
    An uploaded deck, immutable once processed. "Replacing" a presentation never
    mutates this row — it creates a new Presentation linked via replaces_presentation_id.
    """
    __tablename__ = "presentations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    original_file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    original_file_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    original_file_type: Mapped[str] = mapped_column(String(255), nullable=False)
    original_file_size: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    source_format: Mapped[PresentationSourceFormat] = mapped_column(
        Enum(PresentationSourceFormat, native_enum=True, name="presentationsourceformat"),
        nullable=False,
    )
    status: Mapped[PresentationStatus] = mapped_column(
        Enum(PresentationStatus, native_enum=True, name="presentationstatus"),
        nullable=False,
        default=PresentationStatus.PENDING,
        server_default=PresentationStatus.PENDING.value,
    )
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    replaces_presentation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("presentations.id", ondelete="SET NULL"), nullable=True
    )
    # sha256 of the original upload's bytes. Used to detect duplicate uploads by
    # the same owner so we can reuse the existing Presentation instead of
    # re-rendering/re-storing identical content. NULL on rows created before
    # this column existed — they simply never dedup-match, which is safe.
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    page_width: Mapped[float | None] = mapped_column(Float, nullable=True)
    page_height: Mapped[float | None] = mapped_column(Float, nullable=True)
    conversion_warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # Set the moment no Session.presentation_id references this row anymore
    # (on detach/replace). Cleared if it's re-attached before the retention
    # window elapses. NULL means "currently referenced" or "not yet swept".
    orphaned_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Refreshed on upload, dedup-reuse, replace, and attach — surfaced in the
    # Presentation Details panel. NULL means never used since creation.
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    owner: Mapped["User"] = relationship(foreign_keys=[owner_id])
    pages: Mapped[list["PresentationPage"]] = relationship(
        back_populates="presentation",
        cascade="all, delete-orphan",
        order_by="PresentationPage.page_number",
    )

    __table_args__ = (
        Index("ix_presentations_owner_checksum", "owner_id", "checksum"),
    )


class PresentationPage(Base):
    """A single rendered page of a Presentation. Immutable once created."""
    __tablename__ = "presentation_pages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    presentation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("presentations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    image_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    thumbnail_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    presentation: Mapped["Presentation"] = relationship(back_populates="pages")


class PresentationTimeline(Base):
    """
    Ordering container for a session's presentation flow. One per session
    (session_id is unique). active_timeline_item_id is the sole "what's live
    right now" pointer for presentation sessions.
    """
    __tablename__ = "presentation_timelines"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    presentation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("presentations.id", ondelete="RESTRICT"), nullable=False
    )
    # Circular reference to presentation_timeline_items — resolved via ALTER TABLE
    # (use_alter=True) since that table's rows reference this table's id too.
    active_timeline_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("presentation_timeline_items.id", ondelete="SET NULL", use_alter=True, name="fk_timeline_active_item"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    session: Mapped["Session"] = relationship(back_populates="timeline")
    presentation: Mapped["Presentation"] = relationship(foreign_keys=[presentation_id])
    items: Mapped[list["PresentationTimelineItem"]] = relationship(
        back_populates="timeline",
        cascade="all, delete-orphan",
        order_by="PresentationTimelineItem.order",
        foreign_keys="PresentationTimelineItem.timeline_id",
    )
    active_item: Mapped["PresentationTimelineItem | None"] = relationship(
        foreign_keys=[active_timeline_item_id], post_update=True,
    )


class PresentationTimelineItem(Base):
    """
    One ordered slot in a PresentationTimeline: either a read-only Presentation
    page, or an interactive item backed by a normal Slide row (reused as-is so
    Response storage, analytics, and PDF export need no changes). Exactly one of
    presentation_page_id / slide_id is set, matching item_type.
    """
    __tablename__ = "presentation_timeline_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    timeline_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("presentation_timelines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    item_type: Mapped[TimelineItemType] = mapped_column(
        Enum(TimelineItemType, native_enum=True, name="timelineitemtype"), nullable=False
    )
    presentation_page_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("presentation_pages.id", ondelete="CASCADE"), nullable=True
    )
    slide_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("slides.id", ondelete="CASCADE"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    timeline: Mapped["PresentationTimeline"] = relationship(
        back_populates="items", foreign_keys=[timeline_id],
    )
    page: Mapped["PresentationPage | None"] = relationship(foreign_keys=[presentation_page_id])
    slide: Mapped["Slide | None"] = relationship(foreign_keys=[slide_id])


DEFAULT_ORG_DISPLAY_NAME = "Your Organization"


class OrgSettings(Base):
    """
    Singleton row (id is always 1) holding this Rforum instance's organization
    identity — display name, logo, favicon. This is a one-instance-per-org
    deployment (see deploy/helm/rforum), so there is exactly one organization
    per database and this table never grows past one row (enforced by the
    id=1 check constraint, not just application logic).
    """
    __tablename__ = "org_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_name: Mapped[str] = mapped_column(
        String(120), nullable=False, default=DEFAULT_ORG_DISPLAY_NAME
    )
    # Storage keys (see app/storage/keys.py::branding_logo_key/branding_favicon_key),
    # not raw URLs — resolved through the storage abstraction the same way
    # Presentation assets are. NULL means "no custom asset uploaded; serve
    # the bundled default".
    logo_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    logo_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    favicon_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    favicon_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        CheckConstraint("id = 1", name="org_settings_singleton"),
    )
