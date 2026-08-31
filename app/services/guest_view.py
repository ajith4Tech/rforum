"""
Guest-facing payload sanitization — shared by the legacy slide-list endpoint
and the new presentation timeline endpoint so both strip raw file paths the
same way. Pure functions, no DB/FastAPI imports.
"""


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


def strip_slide_content_json(content_json: dict) -> dict:
    """
    Remove raw upload paths from a slide's content_json before it reaches a
    guest. Guests only ever see rendered content through the page-image
    endpoints, never the original file path/name.
    """
    cj = dict(content_json or {})
    if "file_url" in cj:
        cj["has_file"] = True
        del cj["file_url"]
    cj.pop("file_name", None)
    return cj


def merge_slide_content_json(existing: dict | None, incoming: dict | None) -> dict:
    """
    Apply an editor PATCH without dropping persisted file/layout fields the
    client omitted. Does not restore keys the client explicitly sent.
    """
    merged = dict(incoming or {})
    src = dict(existing or {})
    for key in _PRESERVED_FILE_KEYS:
        if key not in merged and key in src:
            merged[key] = src[key]
    if "layout" not in merged and "layout" in src:
        merged["layout"] = src["layout"]
    return merged
