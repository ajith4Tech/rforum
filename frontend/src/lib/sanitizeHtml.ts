/**
 * Allowlist sanitizer for slide rich text (content_json.body / body2) before
 * it is rendered with {@html} or loaded into a contenteditable editor.
 *
 * The server already sanitizes on save and on every guest/projector payload
 * (app/services/slide_content.py); this is the same allowlist applied again in
 * the browser as defence in depth — e.g. for content stored before server-side
 * sanitization existed, which the moderator's own views still receive as-is.
 *
 * The input is parsed into an inert DOMParser document (scripts never run,
 * images never load there) and a new tree is rebuilt from it containing only
 * allowlisted elements and attributes, so nothing outside the allowlist can
 * survive serialization.
 */

const ALLOWED_TAGS = new Set([
  'p', 'div', 'br', 'hr', 'span', 'font',
  'b', 'strong', 'i', 'em', 'u', 's', 'strike', 'sub', 'sup',
  'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'blockquote', 'pre', 'code', 'a'
]);
// Dropped together with everything inside them, not just the tag itself.
const DROP_CONTENT_TAGS = new Set([
  'script', 'style', 'template', 'noscript', 'iframe', 'object', 'embed',
  'svg', 'math', 'textarea', 'select', 'title', 'head', 'xmp', 'noembed',
  'noframes', 'plaintext'
]);
const ALIGN_TAGS = new Set(['p', 'div', 'h1', 'h2', 'h3', 'h4']);
const VOID_TAGS = new Set(['br', 'hr']);
// Same cap as the server (MAX_NESTING_DEPTH): deeper elements are unwrapped,
// keeping their text. Also bounds this function's recursion.
const MAX_NESTING_DEPTH = 64;

const STYLE_PROPERTIES = new Set([
  'color', 'background-color', 'background', 'font-size', 'font-family',
  'font-weight', 'font-style', 'text-decoration', 'text-decoration-line',
  'text-align', 'padding', 'border-radius'
]);
const STYLE_VALUE_RE = /^[#a-zA-Z0-9\s.,%()'"-]+$/;
const STYLE_FUNCTIONS = new Set(['rgb', 'rgba', 'hsl', 'hsla']);
const CSS_FUNCTION_RE = /([a-zA-Z-]+)\s*\(/g;
const COLOR_RE = /^(#[0-9a-fA-F]{3,8}|[a-zA-Z]{1,30})$/;
const FONT_FACE_RE = /^[a-zA-Z0-9 ,'"-]{1,200}$/;
const URL_SCHEME_RE = /^([a-z][a-z0-9+.-]*):/;
const SAFE_URL_SCHEMES = new Set(['http', 'https', 'mailto']);
// eslint-disable-next-line no-control-regex
const URL_IGNORED_CHARS_RE = /[\u0000- \u007f-\u009f]+/g;

function safeUrl(value: string): string | null {
  const compact = value.replace(URL_IGNORED_CHARS_RE, '').toLowerCase();
  if (!compact) return null;
  const scheme = compact.match(URL_SCHEME_RE);
  if (scheme && !SAFE_URL_SCHEMES.has(scheme[1])) return null;
  return value.trim();
}

function safeStyle(value: string): string | null {
  const kept: string[] = [];
  for (const declaration of value.split(';')) {
    const colon = declaration.indexOf(':');
    if (colon === -1) continue;
    const prop = declaration.slice(0, colon).trim().toLowerCase();
    const val = declaration.slice(colon + 1).trim();
    if (!STYLE_PROPERTIES.has(prop) || !val || !STYLE_VALUE_RE.test(val)) continue;
    const lowered = val.toLowerCase();
    if (lowered.includes('url') || lowered.includes('expression') || lowered.includes('javascript')) continue;
    const functions = [...val.matchAll(CSS_FUNCTION_RE)].map((m) => m[1].toLowerCase());
    if (functions.some((fn) => !STYLE_FUNCTIONS.has(fn))) continue;
    kept.push(`${prop}: ${val}`);
  }
  return kept.length ? `${kept.join('; ')};` : null;
}

function copyAllowedAttributes(source: Element, target: Element, tag: string) {
  for (const { name, value } of Array.from(source.attributes)) {
    const attr = name.toLowerCase();
    const trimmed = value.trim();
    if (attr === 'style') {
      const style = safeStyle(value);
      if (style) target.setAttribute('style', style);
    } else if (tag === 'a' && attr === 'href') {
      const url = safeUrl(value);
      if (url) target.setAttribute('href', url);
    } else if (tag === 'font' && attr === 'color' && COLOR_RE.test(trimmed)) {
      target.setAttribute('color', trimmed);
    } else if (tag === 'font' && attr === 'face' && FONT_FACE_RE.test(trimmed)) {
      target.setAttribute('face', trimmed);
    } else if (tag === 'font' && attr === 'size' && /^[1-7]$/.test(trimmed)) {
      target.setAttribute('size', trimmed);
    } else if (ALIGN_TAGS.has(tag) && attr === 'align' && /^(left|center|right|justify)$/i.test(trimmed)) {
      target.setAttribute('align', trimmed.toLowerCase());
    }
  }
  if (tag === 'a' && target.hasAttribute('href')) {
    target.setAttribute('rel', 'noopener noreferrer');
    target.setAttribute('target', '_blank');
  }
}

function appendClean(source: Node, target: Node, doc: Document, depth: number) {
  for (const child of Array.from(source.childNodes)) {
    if (child.nodeType === Node.TEXT_NODE) {
      target.appendChild(doc.createTextNode(child.textContent || ''));
      continue;
    }
    if (child.nodeType !== Node.ELEMENT_NODE) continue; // comments, processing instructions…
    const el = child as Element;
    const tag = el.localName.toLowerCase();
    // Only HTML-namespace elements; foreign (SVG/MathML) content never passes.
    if (DROP_CONTENT_TAGS.has(tag) || el.namespaceURI !== 'http://www.w3.org/1999/xhtml') continue;
    if (!ALLOWED_TAGS.has(tag) || (depth >= MAX_NESTING_DEPTH && !VOID_TAGS.has(tag))) {
      // Unknown wrapper (e.g. <img>, <form>, custom tags) or nested too deep:
      // keep its text, drop the element.
      appendClean(el, target, doc, depth);
      continue;
    }
    const clean = doc.createElement(tag);
    copyAllowedAttributes(el, clean, tag);
    appendClean(el, clean, doc, depth + 1);
    target.appendChild(clean);
  }
}

function escapeText(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/** Returns `html` reduced to the slide-editor allowlist ('' for non-strings). */
export function sanitizeRichHtml(html: unknown): string {
  if (typeof html !== 'string' || !html) return '';
  if (typeof DOMParser === 'undefined') {
    // No DOM (server-side rendering): fall back to plain, fully escaped text.
    return escapeText(html.replace(/<[^>]*>/g, ' '));
  }
  const doc = new DOMParser().parseFromString(html, 'text/html');
  const container = doc.createElement('div');
  appendClean(doc.body, container, doc, 0);
  return container.innerHTML;
}
