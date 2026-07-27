"""
Guest-facing payload sanitization — shared by the legacy slide-list endpoint
and the new presentation timeline endpoint so both strip raw file paths the
same way. Pure functions, no DB/FastAPI imports.
"""


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
