import json
import uuid
from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, EmailStr, field_validator, Field

from app.models import (
    PresentationSourceFormat,
    PresentationStatus,
    SlideType,
    TimelineItemType,
    UserRole,
)

# Generous but bounded — blocks a malicious/misbehaving client from storing
# multi-MB JSON blobs per slide/timeline item (the DB column itself is
# unbounded JSON, so this is the only size guard in the stack).
_MAX_CONTENT_JSON_BYTES = 100_000


def _check_content_json_size(value: dict | None) -> dict | None:
    if value is not None and len(json.dumps(value)) > _MAX_CONTENT_JSON_BYTES:
        raise ValueError(f"content_json exceeds the {_MAX_CONTENT_JSON_BYTES // 1000}KB limit")
    return value


# ── Auth ──────────────────────────────────────────────
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    invite_code: str
    # Only required to claim SUPER_ADMIN via the SUPER_ADMIN_EMAIL bootstrap
    # (app/routers/auth.py::register) — ignored for ordinary registrations.
    super_admin_bootstrap_token: str | None = None

    @field_validator('password')
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v


class ChangePasswordPayload(BaseModel):
    current_password: str
    new_password: str

    @field_validator('new_password')
    @classmethod
    def new_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserRoleUpdate(BaseModel):
    role: UserRole


class UserAdminOut(UserOut):
    """Extended user info for admin views."""
    sessions_count: int = 0
    events_count: int = 0


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Session ───────────────────────────────────────────
class SessionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    event_id: uuid.UUID
    moderator_name: str | None = Field(None, max_length=255)
    speaker_names: list[str] = Field(default_factory=list)

    @field_validator("speaker_names")
    @classmethod
    def clean_speaker_names(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in value:
            name = item.strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(name)
        return cleaned[:20]

    @field_validator("moderator_name")
    @classmethod
    def clean_moderator_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = value.strip()
        return cleaned or None


class SessionUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    is_live: bool | None = None
    moderator_name: str | None = Field(None, max_length=255)
    speaker_names: list[str] | None = None

    @field_validator("speaker_names")
    @classmethod
    def clean_speaker_names(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in value:
            name = item.strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(name)
        return cleaned[:20]

    @field_validator("moderator_name")
    @classmethod
    def clean_moderator_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = value.strip()
        return cleaned or None


class SessionOut(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    event_id: uuid.UUID | None = None
    unique_code: str
    title: str
    moderator_name: str | None = None
    speaker_names: list[str] = Field(default_factory=list)
    is_live: bool
    presentation_id: uuid.UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionWithSlides(SessionOut):
    slides: list["SlideOut"] = Field(default_factory=list)


class SessionPublicOut(BaseModel):
    id: uuid.UUID
    title: str
    is_live: bool
    unique_code: str | None = None

    model_config = {"from_attributes": True}


class PaginatedSessions(BaseModel):
    items: list[SessionOut]
    total: int
    limit: int
    offset: int
    has_more: bool


# ── Event ────────────────────────────────────────────
class EventCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    event_date: date
    description: str | None = Field(None, max_length=10_000)


class EventUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    event_date: date | None = None
    description: str | None = Field(None, max_length=10_000)
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
    sessions: list[SessionOut] = Field(default_factory=list)


class PaginatedEvents(BaseModel):
    items: list[EventWithSessions]
    total: int
    limit: int
    offset: int
    has_more: bool


class EventPublicOut(BaseModel):
    id: uuid.UUID
    title: str
    event_date: date
    description: str | None = None
    sessions: list[SessionPublicOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class EventSessionsUpdate(BaseModel):
    session_ids: list[uuid.UUID] = Field(default_factory=list)


# ── Slide ─────────────────────────────────────────────
class SlideCreate(BaseModel):
    type: SlideType
    order: int = 0
    content_json: dict = {}

    model_config = {"use_enum_values": True}

    _check_content_json_size = field_validator("content_json")(_check_content_json_size)


class SlideUpdate(BaseModel):
    order: int | None = None
    content_json: dict | None = None
    is_active: bool | None = None

    _check_content_json_size = field_validator("content_json")(_check_content_json_size)


class SlideOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    type: SlideType
    order: int
    content_json: dict
    is_active: bool

    model_config = {"from_attributes": True, "use_enum_values": True}


class UploadMeta(BaseModel):
    """Metadata about the upload processing pipeline, returned only by upload endpoints."""
    conversion_attempted: bool
    conversion_success: bool
    converted_file_type: str | None
    warnings: list[str]


class SlideUploadOut(SlideOut):
    """SlideOut extended with upload pipeline metadata."""
    upload_meta: UploadMeta


# ── Presentation ──────────────────────────────────────
# Note: raw file paths (original_file_url, page image/thumbnail paths) are never
# serialized — like legacy slide content_json.file_url, they're internal server
# paths. The browser only ever hits the page-image endpoints, which resolve
# presentation_id + page_number to a file server-side (mirrors slides.py's
# no-auth page-render pattern).

class PresentationPageOut(BaseModel):
    id: uuid.UUID
    presentation_id: uuid.UUID
    page_number: int

    model_config = {"from_attributes": True}


class PresentationOut(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    original_file_name: str
    original_file_type: str
    original_file_size: int
    source_format: PresentationSourceFormat
    status: PresentationStatus
    page_count: int
    replaces_presentation_id: uuid.UUID | None = None
    checksum: str | None = None
    page_width: float | None = None
    page_height: float | None = None
    conversion_warnings: list[str] = Field(default_factory=list)
    orphaned_since: datetime | None = None
    last_used_at: datetime | None = None
    created_at: datetime
    pages: list[PresentationPageOut] = Field(default_factory=list)

    model_config = {"from_attributes": True, "use_enum_values": True}


class PresentationLibraryOut(BaseModel):
    """Lightweight listing row for a user's presentation library — no page list."""
    id: uuid.UUID
    original_file_name: str
    page_count: int
    status: PresentationStatus
    orphaned_since: datetime | None = None
    last_used_at: datetime | None = None
    attached_session_id: uuid.UUID | None = None
    storage_status: Literal["active", "detached"]
    created_at: datetime

    model_config = {"from_attributes": True, "use_enum_values": True}


class PresentationAttachedSessionOut(BaseModel):
    id: uuid.UUID
    title: str
    unique_code: str

    model_config = {"from_attributes": True}


class PresentationDetailsOut(BaseModel):
    """Rich details payload backing both the Presentation Details panel (for a
    session's currently-attached deck) and the Preview Dialog (for a candidate
    deck in the reattach picker) — same shape, same ownership rule for both."""
    id: uuid.UUID
    owner_id: uuid.UUID
    owner_email: str
    original_file_name: str
    original_file_size: int
    original_file_type: str
    source_format: PresentationSourceFormat
    status: PresentationStatus
    page_count: int
    conversion_warnings: list[str] = Field(default_factory=list)
    checksum: str | None = None
    orphaned_since: datetime | None = None
    last_used_at: datetime | None = None
    created_at: datetime
    attached_sessions: list[PresentationAttachedSessionOut] = Field(default_factory=list)
    storage_status: Literal["active", "detached"]

    model_config = {"from_attributes": True, "use_enum_values": True}


class TimelineItemOut(BaseModel):
    id: uuid.UUID
    timeline_id: uuid.UUID
    order: int
    item_type: TimelineItemType
    page: PresentationPageOut | None = None
    slide: SlideOut | None = None

    model_config = {"from_attributes": True, "use_enum_values": True}


class TimelineOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    presentation_id: uuid.UUID
    active_timeline_item_id: uuid.UUID | None = None
    items: list[TimelineItemOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class SessionWithPresentation(SessionOut):
    """Full session payload for the Presentation Builder / moderator view."""
    presentation: PresentationOut | None = None
    timeline: TimelineOut | None = None


class TimelineItemCreate(BaseModel):
    """Insert a new interaction into the timeline. Pages are never created this way —
    they only come from uploading/replacing a Presentation."""
    item_type: TimelineItemType
    position: int = Field(..., ge=0)
    content_json: dict = {}

    @field_validator("item_type")
    @classmethod
    def not_a_page(cls, value: TimelineItemType) -> TimelineItemType:
        if value == TimelineItemType.PAGE:
            raise ValueError("Cannot insert a PAGE item directly — pages come from the presentation file")
        return value

    _check_content_json_size = field_validator("content_json")(_check_content_json_size)


class TimelineItemUpdate(BaseModel):
    """Edit an interaction's content. Delegates to the underlying Slide.content_json."""
    content_json: dict

    _check_content_json_size = field_validator("content_json")(_check_content_json_size)


class TimelineReorderPayload(BaseModel):
    """Full new ordering, expressed as the complete ordered list of item ids."""
    item_ids: list[uuid.UUID] = Field(..., min_length=1)


class PresentationWithTimelineOut(BaseModel):
    presentation: PresentationOut
    timeline: TimelineOut


class PresentationUploadOut(BaseModel):
    """Upload/replace response — adds reused_existing so the frontend can show
    "this presentation already exists, reusing existing assets" instead of a
    generic success message."""
    presentation: PresentationOut
    timeline: TimelineOut
    reused_existing: bool


# ── Response ──────────────────────────────────────────
class ResponseCreate(BaseModel):
    value: str = Field(..., min_length=1, max_length=2000)
    guest_identifier: str = Field(..., min_length=1, max_length=100)
    name: str | None = Field(None, max_length=100)
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


# ── Session Assets ────────────────────────────────────
class SessionAssetOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    session_id: uuid.UUID | None = None
    event_id: uuid.UUID | None = None
    slide_id: uuid.UUID | None = None
    presentation_id: uuid.UUID | None = None
    file_name: str
    file_url: str
    file_type: str
    file_size: int
    uploaded_at: datetime
    # Denormalized titles populated by the router
    session_title: str | None = None
    event_title: str | None = None

    model_config = {"from_attributes": True}


# ── Organization Settings / Branding ──────────────────
class OrgSettingsPublicOut(BaseModel):
    """Safe, unauthenticated-readable branding info — never includes storage
    keys, credentials, or any other internal detail."""
    display_name: str
    logo_url: str
    favicon_url: str
    updated_at: datetime


class OrgSettingsAdminOut(OrgSettingsPublicOut):
    """Same public shape, plus whether a custom asset is currently set — lets
    the Admin page show a "Remove" action without exposing the storage key."""
    has_custom_logo: bool
    has_custom_favicon: bool


class OrgDisplayNameUpdate(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=120)

    @field_validator("display_name")
    @classmethod
    def trim_and_require_nonempty(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Organization name cannot be empty")
        return cleaned


# ── WebSocket Messages ───────────────────────────────
class WSMessage(BaseModel):
    event: str
    data: dict = {}
