"""
Shared storage-key builder for Presentation assets.

Every call site that needs to construct a *new* key (upload, regenerate,
lazy PDF-cache) goes through this module rather than formatting the
"presentations/..." shape inline — this is the one place the on-disk/S3
hierarchy is defined. Call sites that only need to *read back* a key
already stored in the DB (download, page serving, cleanup) never
reconstruct paths — they use the literal value from the row, or, when they
need the presentation's root directory for a prefix delete,
`dir_prefix_from_known_key` derives it from that same literal value so
they never need to re-derive the owner directory name.

Layout:
    presentations/<sanitized_username>__u_<user_id>/<presentation_id>/
        original/<original_filename>
        pdf/presentation.pdf            (persisted PPT/PPTX -> PDF conversion cache)
        thumbnails/page_NNN.webp
        pages/page_NNN.webp
"""
import re

_INVALID_CHARS_RE = re.compile(r"[^A-Za-z0-9_]+")
_MULTI_UNDERSCORE_RE = re.compile(r"_+")


def sanitize_username(raw: str) -> str:
    """Spaces -> underscores, strip anything else invalid, collapse repeats.
    Casing is preserved deliberately (not lowercased)."""
    spaced = raw.strip().replace(" ", "_")
    cleaned = _INVALID_CHARS_RE.sub("_", spaced)
    collapsed = _MULTI_UNDERSCORE_RE.sub("_", cleaned).strip("_")
    return collapsed or "user"


def username_from_email(email: str) -> str:
    """The User model has no display-name field, only `email` — the local
    part (before '@') is the closest stand-in for a "username"."""
    local_part = (email or "").split("@", 1)[0]
    return sanitize_username(local_part)


def owner_dir_name(email: str, user_id) -> str:
    return f"{username_from_email(email)}__u_{user_id}"


def presentation_dir(email: str, user_id, presentation_id) -> str:
    return f"presentations/{owner_dir_name(email, user_id)}/{presentation_id}"


def original_key(email: str, user_id, presentation_id, original_filename: str) -> str:
    return f"{presentation_dir(email, user_id, presentation_id)}/original/{original_filename}"


def pdf_key_for_dir(pres_dir: str) -> str:
    return f"{pres_dir}/pdf/presentation.pdf"


def pdf_key(email: str, user_id, presentation_id) -> str:
    return pdf_key_for_dir(presentation_dir(email, user_id, presentation_id))


def thumbnail_key(email: str, user_id, presentation_id, page_number: int) -> str:
    return f"{presentation_dir(email, user_id, presentation_id)}/thumbnails/page_{page_number:03d}.webp"


def page_key(email: str, user_id, presentation_id, page_number: int) -> str:
    return f"{presentation_dir(email, user_id, presentation_id)}/pages/page_{page_number:03d}.webp"


def dir_prefix_from_known_key(key: str, presentation_id) -> str:
    """Given any literal key already stored in the DB for a presentation
    (original_file_url, or a page's image_url/thumbnail_url) plus that
    presentation's own id, return the presentation's root directory, e.g.
    "presentations/<owner>/<id>".

    Locates `presentation_id` as a literal path segment rather than
    counting a fixed number of segments from the front. Segment-counting
    is not safe: legacy rows are not all shaped the same way (some carry a
    leading "/uploads/" segment, some have no owner segment at all — the
    on-disk/DB reality predates the current owner-scoped hierarchy and
    isn't uniform), so a fixed offset silently derives the wrong prefix
    for whichever shape isn't current. Since `delete_prefix` on that
    prefix is destructive, a wrong-but-plausible-looking prefix (e.g. the
    bucket root) is far worse than a loud failure — raises ValueError
    rather than guessing if the id segment isn't found.

    Lets callers (delete, cleanup) get a prefix for a defense-in-depth
    sweep without looking up the owner's email again."""
    pres_id_str = str(presentation_id)
    parts = key.split("/")
    try:
        idx = parts.index(pres_id_str)
    except ValueError:
        raise ValueError(
            f"presentation_id {pres_id_str!r} not found as a path segment in "
            f"key {key!r} — refusing to guess a directory prefix for "
            "delete_prefix (a wrong guess could delete unrelated data)"
        )
    return "/".join(parts[: idx + 1])
