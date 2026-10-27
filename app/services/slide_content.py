"""
Slide content_json safety rules shared by every write path (legacy slide
create/update, presentation-timeline insert/update) and every audience read
path (join payloads, WebSocket slide_change relays). Pure functions, no
DB/FastAPI imports.

Rich text: content slides store editor HTML in `body` / `body2`, which guest
phones and the projector render as HTML. It is reduced to an allowlist of the
formatting the slide editors actually produce (document.execCommand output:
headings, paragraphs, lists, bold/italic/underline, links, <font>/<span style>
for font, size and colour). Output is rebuilt from scratch — every text node
and attribute value is re-escaped and only allowlisted tag/attribute names are
ever emitted — so the result is safe regardless of how malformed the input is.
The frontend applies the same allowlist again before rendering
(frontend/src/lib/sanitizeHtml.ts) for content stored before this existed.

Every API write path sanitizes, but some writers copy `body` through untouched
(file-attachment updates, scripts/repair_uploaded_slides.py, direct SQL), so
audience payloads are sanitized again on read. That read path runs on every
guest join, hence the bounded per-process cache below: output depends only on
the input string, so a cached result is exactly what re-sanitizing would give.
"""
import re
import threading
from collections import OrderedDict
from html.parser import HTMLParser

RICH_TEXT_KEYS = ("body", "body2")

_ALLOWED_TAGS = frozenset({
    "p", "div", "br", "hr", "span", "font",
    "b", "strong", "i", "em", "u", "s", "strike", "sub", "sup",
    "ul", "ol", "li", "h1", "h2", "h3", "h4", "blockquote", "pre", "code", "a",
})
_VOID_TAGS = frozenset({"br", "hr"})
# Dropped together with everything inside them, not just the tag itself.
_DROP_CONTENT_TAGS = frozenset({
    "script", "style", "template", "noscript", "iframe", "object", "embed",
    "svg", "math", "textarea", "select", "title", "head", "xmp", "noembed",
    "noframes", "plaintext",
})
_ALIGN_TAGS = frozenset({"p", "div", "h1", "h2", "h3", "h4"})
# Deepest allowed element nesting. Editor output stays far below this; deeper
# start tags are dropped (their text is kept), which bounds the output and the
# work per tag no matter how the input is shaped.
MAX_NESTING_DEPTH = 64

_STYLE_PROPERTIES = frozenset({
    "color", "background-color", "background", "font-size", "font-family",
    "font-weight", "font-style", "text-decoration", "text-decoration-line",
    "text-align", "padding", "border-radius",
})
_STYLE_VALUE_RE = re.compile(r"^[#a-zA-Z0-9\s.,%()'\"\-]+$")
_STYLE_FUNCTIONS = frozenset({"rgb", "rgba", "hsl", "hsla"})
_CSS_FUNCTION_RE = re.compile(r"([a-zA-Z-]+)\s*\(")
_COLOR_RE = re.compile(r"^(#[0-9a-fA-F]{3,8}|[a-zA-Z]{1,30})$")
_FONT_FACE_RE = re.compile(r"^[a-zA-Z0-9 ,'\"\-]{1,200}$")
_URL_SCHEME_RE = re.compile(r"^([a-z][a-z0-9+.\-]*):")
_SAFE_URL_SCHEMES = frozenset({"http", "https", "mailto"})
_URL_IGNORED_CHARS_RE = re.compile(r"[\x00-\x20\x7f-\x9f]+")


def _escape_text(value: str) -> str:
    # Mirrors browser innerHTML serialization (incl. &nbsp;) so editor content
    # round-trips without spurious differences.
    return (
        value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace("\xa0", "&nbsp;")
    )


def _escape_attr(value: str) -> str:
    return (
        value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")
        .replace(">", "&gt;").replace("\xa0", "&nbsp;")
    )


def _safe_url(value: str) -> str | None:
    compact = _URL_IGNORED_CHARS_RE.sub("", value).lower()
    if not compact:
        return None
    match = _URL_SCHEME_RE.match(compact)
    if match and match.group(1) not in _SAFE_URL_SCHEMES:
        return None
    return value.strip()


def _safe_style(value: str) -> str | None:
    kept = []
    for declaration in value.split(";"):
        if ":" not in declaration:
            continue
        prop, val = declaration.split(":", 1)
        prop = prop.strip().lower()
        val = val.strip()
        if prop not in _STYLE_PROPERTIES or not val or not _STYLE_VALUE_RE.match(val):
            continue
        lowered = val.lower()
        if "url" in lowered or "expression" in lowered or "javascript" in lowered:
            continue
        if any(fn.lower() not in _STYLE_FUNCTIONS for fn in _CSS_FUNCTION_RE.findall(val)):
            continue
        kept.append(f"{prop}: {val}")
    return "; ".join(kept) + ";" if kept else None


def _clean_attrs(tag: str, attrs: list[tuple[str, str | None]]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for name, raw in attrs:
        name = name.lower()
        value = raw or ""
        if name == "style":
            style = _safe_style(value)
            if style:
                out.append(("style", style))
        elif tag == "a" and name == "href":
            url = _safe_url(value)
            if url:
                out.append(("href", url))
        elif tag == "font" and name == "color" and _COLOR_RE.match(value.strip()):
            out.append(("color", value.strip()))
        elif tag == "font" and name == "face" and _FONT_FACE_RE.match(value.strip()):
            out.append(("face", value.strip()))
        elif tag == "font" and name == "size" and value.strip() in {"1", "2", "3", "4", "5", "6", "7"}:
            out.append(("size", value.strip()))
        elif tag in _ALIGN_TAGS and name == "align" and value.strip().lower() in {"left", "center", "right", "justify"}:
            out.append(("align", value.strip().lower()))
    if tag == "a" and any(name == "href" for name, _ in out):
        out.append(("rel", "noopener noreferrer"))
        out.append(("target", "_blank"))
    return out


class _AllowlistBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        # Stack of emitted, still-open tags plus a per-name count of it, so
        # "is this tag open?" is O(1) and every tag is pushed/popped at most
        # once — linear overall, even for adversarial unbalanced input.
        self.open_tags: list[str] = []
        self.open_counts: dict[str, int] = {}
        # Allowed start tags dropped at MAX_NESTING_DEPTH; their end tags are
        # swallowed instead of closing an outer tag of the same name.
        self.dropped_counts: dict[str, int] = {}
        self.skip_depth = 0

    def _start(self, tag: str, attrs: list[tuple[str, str | None]], self_closing: bool) -> None:
        tag = tag.lower()
        if tag in _DROP_CONTENT_TAGS:
            if not self_closing:
                self.skip_depth += 1
            return
        if self.skip_depth or tag not in _ALLOWED_TAGS:
            return
        is_void = tag in _VOID_TAGS
        if not is_void and len(self.open_tags) >= MAX_NESTING_DEPTH:
            self.dropped_counts[tag] = self.dropped_counts.get(tag, 0) + 1
            return
        rendered = "".join(f' {name}="{_escape_attr(value)}"' for name, value in _clean_attrs(tag, attrs))
        self.parts.append(f"<{tag}{rendered}>")
        if not is_void:
            self.open_tags.append(tag)
            self.open_counts[tag] = self.open_counts.get(tag, 0) + 1

    def handle_starttag(self, tag, attrs):
        self._start(tag, attrs, False)

    def handle_startendtag(self, tag, attrs):
        self._start(tag, attrs, True)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in _DROP_CONTENT_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if self.dropped_counts.get(tag):
            self.dropped_counts[tag] -= 1
            return
        if not self.open_counts.get(tag):
            return
        while self.open_tags:
            closing = self.open_tags.pop()
            self.open_counts[closing] -= 1
            self.parts.append(f"</{closing}>")
            if closing == tag:
                break

    def handle_data(self, data):
        if not self.skip_depth:
            self.parts.append(_escape_text(data))

    def result(self) -> str:
        self.close()
        return "".join(self.parts) + "".join(f"</{tag}>" for tag in reversed(self.open_tags))


def _sanitize_uncached(value: str) -> str:
    builder = _AllowlistBuilder()
    builder.feed(value)
    return builder.result()


# Bounded LRU of input -> sanitized output (sizes counted in characters).
# content_json is capped at 100 KB per slide, so any single body fits; the
# whole cache stays a few MB per worker process.
_CACHE_MAX_CHARS = 4_000_000
_cache: "OrderedDict[str, str]" = OrderedDict()
_cache_chars = 0
_cache_lock = threading.Lock()


def sanitize_rich_html(value: object) -> str:
    """Return `value` reduced to the slide-editor HTML allowlist ('' for non-strings)."""
    global _cache_chars
    if not isinstance(value, str) or not value:
        return ""
    with _cache_lock:
        cached = _cache.get(value)
        if cached is not None:
            _cache.move_to_end(value)
            return cached
    result = _sanitize_uncached(value)
    size = len(value) + len(result)
    if size <= _CACHE_MAX_CHARS // 8:
        with _cache_lock:
            if value not in _cache:
                _cache[value] = result
                _cache_chars += size
                while _cache_chars > _CACHE_MAX_CHARS and _cache:
                    old_key, old_value = _cache.popitem(last=False)
                    _cache_chars -= len(old_key) + len(old_value)
    return result


def sanitize_slide_content_json(content_json: dict | None) -> dict:
    """Copy of `content_json` with its rich-text fields sanitized."""
    cj = dict(content_json or {})
    for key in RICH_TEXT_KEYS:
        if key in cj and cj[key] is not None:
            cj[key] = sanitize_rich_html(cj[key])
    return cj


def is_quiz_content(content_json: dict | None) -> bool:
    cj = content_json or {}
    return str(cj.get("interaction_type") or "").upper() == "QUIZ" or str(cj.get("mode") or "").lower() == "quiz"


def valid_quiz_answer(content_json: dict | None) -> str:
    """The quiz's correct answer when it identifies exactly one option, else ''.

    The answer is stored as option text, so it is only meaningful when it
    matches one option exactly (a duplicate-text match is ambiguous).
    Mirrored by frontend/src/lib/quiz.ts.
    """
    cj = content_json or {}
    answer = cj.get("correct_answer")
    options = cj.get("options")
    if not isinstance(answer, str) or answer == "" or not isinstance(options, list):
        return ""
    return answer if options.count(answer) == 1 else ""


def quiz_content_error(content_json: dict | None, existing: dict | None = None) -> str | None:
    """Why a quiz configuration may not be saved, or None when it is valid.

    Rules (same in both editors, see frontend/src/lib/quiz.ts):
      - The answer may be empty ("not chosen yet") while the answer is hidden.
      - Revealing requires a valid answer — otherwise every guest would be
        told they were wrong.
      - A non-empty answer must match exactly one option. The one exception is
        a legacy record whose stored answer was already invalid and is left
        unchanged, so such a quiz can still be edited or have its answer
        hidden; it can never be revealed until a valid answer is marked.
    """
    cj = content_json or {}
    if not is_quiz_content(cj):
        return None
    answer = valid_quiz_answer(cj)
    if cj.get("reveal_answer") and not answer:
        return "Mark which option is the correct answer before revealing it."
    stored = cj.get("correct_answer")
    if stored is None or stored == "" or answer:
        return None
    previous = existing or {}
    if is_quiz_content(previous) and stored == previous.get("correct_answer") and not valid_quiz_answer(previous):
        return None
    return "The quiz's correct answer must match exactly one of its options."
