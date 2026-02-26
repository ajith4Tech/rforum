import uuid
from datetime import date, datetime
from pydantic import BaseModel, EmailStr, field_validator

from app.models import SlideType


# ── Auth ──────────────────────────────────────────────
class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Session ───────────────────────────────────────────
class SessionCreate(BaseModel):
    title: str


class SessionUpdate(BaseModel):
    title: str | None = None
    is_live: bool | None = None


class SessionOut(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    event_id: uuid.UUID | None = None
    unique_code: str
    title: str
    is_live: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionWithSlides(SessionOut):
    slides: list["SlideOut"] = []


class SessionPublicOut(BaseModel):
    id: uuid.UUID
    title: str
    is_live: bool
    unique_code: str | None = None

    model_config = {"from_attributes": True}


# ── Event ────────────────────────────────────────────
class EventCreate(BaseModel):
    title: str
    event_date: date
    description: str | None = None
    session_ids: list[uuid.UUID] = []


class EventUpdate(BaseModel):
    title: str | None = None
    event_date: date | None = None
    description: str | None = None
    is_published: bool | None = None


class EventOut(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    title: str
    event_date: date
    description: str | None = None
    is_published: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class EventWithSessions(EventOut):
    sessions: list[SessionOut] = []


class EventPublicOut(BaseModel):
    id: uuid.UUID
    title: str
    event_date: date
    description: str | None = None
    sessions: list[SessionPublicOut] = []

    model_config = {"from_attributes": True}


class EventSessionsUpdate(BaseModel):
    session_ids: list[uuid.UUID] = []


# ── Slide ─────────────────────────────────────────────
class SlideCreate(BaseModel):
    type: SlideType
    order: int = 0
    content_json: dict = {}
    
    model_config = {"use_enum_values": True}


class SlideUpdate(BaseModel):
    order: int | None = None
    content_json: dict | None = None
    is_active: bool | None = None


class SlideOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    type: SlideType
    order: int
    content_json: dict
    is_active: bool

    model_config = {"from_attributes": True}


# ── Response ──────────────────────────────────────────
class ResponseCreate(BaseModel):
    value: str
    guest_identifier: str
    name: str | None = None
    rating: int | None = None

    @field_validator("rating")
    @classmethod
    def validate_rating(cls, value: int | None) -> int | None:
        if value is None:
            return value
        if value < 1 or value > 5:
            raise ValueError("rating must be between 1 and 5")
        return value


class ResponseOut(BaseModel):
    id: uuid.UUID
    slide_id: uuid.UUID
    value: str
    guest_identifier: str
    name: str | None = None
    rating: int | None = None
    upvotes: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── WebSocket Messages ───────────────────────────────
class WSMessage(BaseModel):
    event: str
    data: dict = {}
