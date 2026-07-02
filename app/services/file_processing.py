"""
File processing service — upload validation, MIME detection, PDF conversion, page extraction.

All functions are pure (no FastAPI imports, no DB access) so they are independently testable.
Routers import from here; they convert ValueError → HTTPException.
"""
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import fitz

logger = logging.getLogger(__name__)

# ── LibreOffice availability ───────────────────────────────────────────────────

def _find_libreoffice() -> str | None:
    """Locate the LibreOffice binary at import time."""
    for candidate in ("libreoffice", "libreoffice7.6", "libreoffice7.5", "libreoffice24.8"):
        cmd = shutil.which(candidate)
        if cmd:
            return cmd
    return None


LIBREOFFICE_CMD: str | None = _find_libreoffice()

if LIBREOFFICE_CMD:
    logger.info("LibreOffice found at '%s'. PPT/PPTX conversion enabled.", LIBREOFFICE_CMD)
else:
    logger.warning(
        "LibreOffice not found. PPT/PPTX files will be rendered directly by PyMuPDF "
        "(single-format fallback, no proper slide conversion). "
        "To enable full conversion: apt-get install -y libreoffice-headless"
    )

# ── Constants ──────────────────────────────────────────────────────────────────

# OOXML/ODF formats that are ZIP archives — magic correctly detects them as application/zip
_ZIP_BASED_EXTENSIONS: frozenset[str] = frozenset({
    ".pptx", ".docx", ".xlsx", ".odp", ".odt", ".ods",
})

# Extension → canonical MIME mapping (used for normalisation after magic detection)
_EXT_TO_MIME: dict[str, str] = {
    ".pdf":  "application/pdf",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".ppt":  "application/vnd.ms-powerpoint",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc":  "application/msword",
    ".txt":  "text/plain",
    ".odp":  "application/vnd.oasis.opendocument.presentation",
    ".odt":  "application/vnd.oasis.opendocument.text",
}

# MIME types that should never be allowed regardless of extension
_DANGEROUS_MIMES: frozenset[str] = frozenset({
    "application/x-dosexec",
    "application/x-elf",
    "application/x-executable",
    "application/x-sharedlib",
    "application/x-shellscript",
    "text/x-shellscript",
    "application/javascript",
    "text/javascript",
    "application/x-mach-binary",
    "application/x-msdownload",
})

# Manual magic-byte patterns to catch executables even when libmagic detection is ambiguous.
# These are checked against the first bytes of the file before any MIME detection.
_DANGEROUS_MAGIC_HEADERS: tuple[tuple[bytes, str], ...] = (
    (b"\x7fELF",          "ELF binary (Linux/Unix executable)"),
    (b"MZ",               "PE/COFF binary (Windows executable)"),
    (b"\xca\xfe\xba\xbe", "Mach-O fat binary (macOS)"),
    (b"\xce\xfa\xed\xfe", "Mach-O 32-bit LE (macOS)"),
    (b"\xcf\xfa\xed\xfe", "Mach-O 64-bit LE (macOS)"),
    (b"#!/",              "shell script"),
    (b"#! /",             "shell script"),
)

# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class ConversionResult:
    attempted: bool = False
    success: bool = False
    output_path: str | None = None
    converted_type: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    actual_mime: str
    warnings: list[str] = field(default_factory=list)


# ── Public API ─────────────────────────────────────────────────────────────────

def detect_actual_file_type(content: bytes, filename: str = "") -> str:
    """
    Detect the actual MIME type from raw file bytes using python-magic.

    Returns the canonical MIME type string. Falls back to extension-based
    detection if python-magic is unavailable or detection fails.

    PPTX/DOCX/ODP files are ZIP archives; when magic returns 'application/zip'
    for a known ZIP-based extension, we normalise to the proper OOXML/ODF type.
    """
    detected: str | None = None
    ext = Path(filename).suffix.lower()

    try:
        import magic as _magic  # lazy import so the module loads without it
        detected = _magic.from_buffer(content, mime=True)
    except ImportError:
        logger.debug("python-magic not available; using extension fallback for %s", filename)
    except Exception as exc:
        logger.warning("MIME detection failed for '%s': %s", filename, exc)

    if detected is None:
        # Extension-based fallback
        return _EXT_TO_MIME.get(ext, "application/octet-stream")

    # Normalise ZIP detection for OOXML/ODF formats
    if detected == "application/zip" and ext in _ZIP_BASED_EXTENSIONS:
        canonical = _EXT_TO_MIME.get(ext)
        if canonical:
            logger.debug(
                "Normalised 'application/zip' → '%s' based on extension '%s'", canonical, ext
            )
            return canonical

    return detected


def validate_upload(
    content: bytes,
    original_name: str,
    allowed_extensions: list[str],
    max_bytes: int,
) -> ValidationResult:
    """
    Validate uploaded file content against policy rules.

    Returns ValidationResult containing the server-detected MIME type (not
    the browser-reported one) and any non-fatal warnings.

    Raises ValueError with a human-readable message on hard failures:
    - empty file
    - disallowed extension
    - file too large
    - dangerous content type detected
    """
    warnings: list[str] = []

    if len(content) == 0:
        raise ValueError("Uploaded file is empty.")

    ext = Path(original_name).suffix.lower()
    if ext not in allowed_extensions:
        allowed = ", ".join(sorted(allowed_extensions))
        raise ValueError(f"File type '{ext}' is not allowed. Allowed types: {allowed}")

    if len(content) > max_bytes:
        limit_mb = max_bytes // (1024 * 1024)
        actual_mb = len(content) / (1024 * 1024)
        raise ValueError(
            f"File size {actual_mb:.1f} MB exceeds the {limit_mb} MB limit."
        )

    # Belt-and-suspenders: check raw magic bytes before MIME detection
    for header_bytes, description in _DANGEROUS_MAGIC_HEADERS:
        if content[:len(header_bytes)] == header_bytes:
            logger.error(
                "Upload rejected — dangerous magic bytes detected. "
                "filename='%s' detected_as='%s'",
                original_name, description,
            )
            raise ValueError(
                f"File content rejected: detected {description} content."
            )

    actual_mime = detect_actual_file_type(content, original_name)

    if actual_mime in _DANGEROUS_MIMES:
        logger.error(
            "Upload rejected — dangerous MIME detected. filename='%s' detected_mime='%s'",
            original_name, actual_mime,
        )
        raise ValueError(
            f"File content rejected: detected type '{actual_mime}' is not permitted."
        )

    return ValidationResult(actual_mime=actual_mime, warnings=warnings)


def convert_to_pdf_if_needed(file_path: str, ext: str) -> ConversionResult:
    """
    Attempt LibreOffice conversion of PPT/PPTX → PDF.

    Always returns a ConversionResult; never raises. If LibreOffice is absent
    or conversion fails, the result is returned with success=False and the
    failure reason in warnings so callers can proceed with the original file.
    """
    result = ConversionResult()

    if ext not in {".ppt", ".pptx"}:
        return result  # Not a conversion candidate

    result.attempted = True

    if not LIBREOFFICE_CMD:
        msg = (
            "LibreOffice is not installed — PPT/PPTX conversion skipped. "
            "PyMuPDF will render the original file directly. "
            "Install libreoffice-headless to enable proper PDF conversion."
        )
        result.warnings.append(msg)
        logger.warning("Conversion skipped for '%s': %s", file_path, msg)
        return result

    uploads_dir = str(Path(file_path).parent)
    try:
        proc = subprocess.run(
            [
                LIBREOFFICE_CMD, "--headless",
                "--convert-to", "pdf",
                "--outdir", uploads_dir,
                file_path,
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
        )

        expected_pdf = os.path.join(uploads_dir, f"{Path(file_path).stem}.pdf")
        if os.path.exists(expected_pdf):
            result.success = True
            result.output_path = expected_pdf
            result.converted_type = "application/pdf"
            logger.info("Converted '%s' → '%s'", file_path, expected_pdf)
        else:
            stdout = proc.stdout.decode(errors="replace").strip()
            stderr = proc.stderr.decode(errors="replace").strip()
            msg = (
                f"LibreOffice ran but expected output '{expected_pdf}' was not found. "
                "Original file will be used."
            )
            result.warnings.append(msg)
            logger.warning(
                "Conversion output missing. file='%s' expected='%s' stdout=%r stderr=%r",
                file_path, expected_pdf, stdout, stderr,
            )

    except subprocess.TimeoutExpired:
        msg = "LibreOffice conversion timed out after 60 s. Original file will be used."
        result.warnings.append(msg)
        logger.error("Conversion timed out for '%s'", file_path, exc_info=True)

    except subprocess.CalledProcessError as exc:
        stdout = exc.stdout.decode(errors="replace").strip()
        stderr = exc.stderr.decode(errors="replace").strip()
        msg = (
            f"LibreOffice exited with code {exc.returncode}. "
            "Original file will be used."
        )
        result.warnings.append(msg)
        logger.error(
            "Conversion failed. file='%s' exit=%d stdout=%r stderr=%r",
            file_path, exc.returncode, stdout, stderr,
        )

    except FileNotFoundError:
        msg = "LibreOffice binary not found at conversion time. Original file will be used."
        result.warnings.append(msg)
        logger.error(
            "LibreOffice binary missing at conversion time for '%s'", file_path, exc_info=True,
        )

    except Exception as exc:
        msg = f"Unexpected error during conversion: {exc}. Original file will be used."
        result.warnings.append(msg)
        logger.error("Unexpected conversion error for '%s'", file_path, exc_info=True)

    return result


def extract_total_pages(file_path: str) -> tuple[int, list[str]]:
    """
    Extract page count from a file using PyMuPDF.

    Works for PDF, PPTX, PPT, DOCX, ODT, ODP, and all other fitz-supported
    formats. Does NOT restrict to application/pdf — the MIME type gate that
    caused the original bug is intentionally absent here.

    Returns (total_pages, warnings). Never raises; on any failure returns
    (1, [warning_message]) so callers can proceed safely.
    """
    warnings: list[str] = []

    if not os.path.exists(file_path):
        msg = f"File not found, cannot count pages: '{file_path}'"
        warnings.append(msg)
        logger.warning(msg)
        return 1, warnings

    doc = None
    try:
        doc = fitz.open(file_path)
        total = len(doc)
        if total < 1:
            msg = f"File opened but reported {total} pages; defaulting to 1."
            warnings.append(msg)
            logger.warning("Page count anomaly for '%s': %s", file_path, msg)
            return 1, warnings
        logger.debug("Counted %d pages in '%s'", total, file_path)
        return total, warnings

    except fitz.EmptyFileError:
        msg = "File is empty and cannot be opened for page counting."
        warnings.append(msg)
        logger.warning("Empty file at '%s': %s", file_path, msg)

    except fitz.FileDataError as exc:
        msg = f"File may be corrupted or password-protected: {exc}"
        warnings.append(msg)
        logger.warning("FileDataError for '%s': %s", file_path, exc)

    except Exception as exc:
        msg = f"Unexpected error counting pages: {exc}"
        warnings.append(msg)
        logger.warning("extract_total_pages failed for '%s'", file_path, exc_info=True)

    finally:
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass

    return 1, warnings


def libreoffice_status() -> dict:
    """
    Return a dict describing conversion capability — used for health checks
    and startup logging.
    """
    return {
        "available": LIBREOFFICE_CMD is not None,
        "path": LIBREOFFICE_CMD,
        "message": (
            "PPT/PPTX → PDF conversion enabled."
            if LIBREOFFICE_CMD
            else (
                "LibreOffice not found. PPT/PPTX files rendered via PyMuPDF fallback. "
                "Install libreoffice-headless for full conversion support."
            )
        ),
    }
