"""
Guest-facing payload sanitization — shared by the legacy slide-list endpoint
and the new presentation timeline endpoint so both strip raw file paths the
same way. Pure functions, no DB/FastAPI imports.
"""
from app.services.slide_content import sanitize_slide_content_json


# Keys that identify an attached slide file. PATCH bodies from the editor can
# omit them while still intending to keep the existing attachment.
_PRESERVED_FILE_KEYS = (
    "file_url",
    "file_name",
    "file_type",
    "file_page",
    "total_pages",
    "has_file",
)

# Keys only the server writes. `responses_cleared` counts how often the
# moderator cleared a slide's responses (app/routers/responses.py); guests
# compare it with the count recorded when they answered, so a clear they
# missed while disconnected still resets their "already answered" state.
# A client copy may be stale, so client-sent values are always ignored.
RESPONSES_CLEARED_KEY = "responses_cleared"
_SERVER_OWNED_KEYS = (RESPONSES_CLEARED_KEY,)


def without_server_owned_keys(content_json: dict | None) -> dict:
    """Copy of a client-supplied content_json for a NEW slide (e.g. a duplicate) with server-owned keys removed."""
    cj = dict(content_json or {})
    for key in _SERVER_OWNED_KEYS:
        cj.pop(key, None)
    return cj


def strip_slide_content_json(content_json: dict) -> dict:
    """
    Remove raw upload paths and unrevealed quiz answers from a slide's content_json
    before it reaches a guest. Guests only ever see rendered content through the page-image
    endpoints, never the original file path/name, and never see quiz answers pre-reveal.
    Rich text is re-sanitized here too, covering content stored before write-time
    sanitization existed and slides relayed over the moderator's WebSocket.
    """
    cj = sanitize_slide_content_json(content_json)
    if "file_url" in cj:
        cj["has_file"] = True
        del cj["file_url"]
    cj.pop("file_name", None)
    if not cj.get("reveal_answer"):
        cj.pop("correct_answer", None)
    return cj


def merge_slide_content_json(existing: dict | None, incoming: dict | None) -> dict:
    """
    Apply an editor PATCH without dropping persisted file/layout fields the
    client omitted. Does not restore keys the client explicitly sent — except
    server-owned keys, which always keep their stored value.
    """
    merged = dict(incoming or {})
    src = dict(existing or {})
    for key in _PRESERVED_FILE_KEYS:
        if key not in merged and key in src:
            merged[key] = src[key]
    if "layout" not in merged and "layout" in src:
        merged["layout"] = src["layout"]
    for key in _SERVER_OWNED_KEYS:
        if key in src:
            merged[key] = src[key]
        else:
            merged.pop(key, None)
    return merged
