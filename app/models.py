from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text, func
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
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="SET NULL"), nullable=True
    )
    unique_code: Mapped[str] = mapped_column(
        String(9), unique=True, nullable=False
    )  # e.g. ABCD-1234
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    moderator_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    speaker_names: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_live: Mapped[bool] = mapped_column(Boolean, default=False)
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


class Slide(Base):
    __tablename__ = "slides"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
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
        UUID(as_uuid=True), ForeignKey("slides.id", ondelete="CASCADE"), nullable=False
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
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="SET NULL"), nullable=True
    )
    slide_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("slides.id", ondelete="SET NULL"), nullable=True
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
