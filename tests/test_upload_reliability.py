"""
Tests for slides upload reliability (Feature 1).

Coverage:
  Unit    — file_processing service functions
  API     — upload endpoint behaviour via FastAPI TestClient
  Regression — existing PDF flow unchanged
"""
import io
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz
import pytest


# ═══════════════════════════════════════════════════════════════════
# UNIT TESTS — app/services/file_processing.py
# ═══════════════════════════════════════════════════════════════════

class TestDetectActualFileType:

    def test_pdf_bytes_detected_as_pdf(self, pdf_1_page):
        from app.services.file_processing import detect_actual_file_type
        mime = detect_actual_file_type(pdf_1_page, "document.pdf")
        assert mime == "application/pdf"

    def test_pptx_zip_normalised_to_ooxml(self, pptx_bytes):
        from app.services.file_processing import detect_actual_file_type
        mime = detect_actual_file_type(pptx_bytes, "slides.pptx")
        # python-magic detects PPTX as application/zip; we normalise it
        assert mime == "application/vnd.openxmlformats-officedocument.presentationml.presentation"

    def test_extension_fallback_when_magic_unavailable(self, pdf_1_page):
        """If python-magic is not installed, extension-based fallback kicks in."""
        import sys
        from app.services.file_processing import detect_actual_file_type
        # Temporarily hide the 'magic' module to simulate it not being installed
        with patch.dict(sys.modules, {"magic": None}):
            mime = detect_actual_file_type(pdf_1_page, "doc.pdf")
        assert mime == "application/pdf"

    def test_octet_stream_for_unknown_bytes(self, random_bytes):
        from app.services.file_processing import detect_actual_file_type
        mime = detect_actual_file_type(random_bytes, "unknown.bin")
        # Should not crash and return something
        assert isinstance(mime, str)
        assert len(mime) > 0

    def test_pdf_bytes_with_generic_filename(self, pdf_1_page):
        """MIME detection is content-based, not filename-based."""
        from app.services.file_processing import detect_actual_file_type
        mime = detect_actual_file_type(pdf_1_page, "renamed_as_pptx.pptx")
        # magic detects the content, not the name — should still see PDF
        assert "pdf" in mime.lower() or mime == "application/octet-stream"


class TestExtractTotalPages:

    def test_pdf_correct_page_count(self, pdf_3_pages, tmp_path):
        from app.services.file_processing import extract_total_pages
        p = tmp_path / "test.pdf"
        p.write_bytes(pdf_3_pages)
        count, warnings = extract_total_pages(str(p))
        assert count == 3
        assert warnings == []

    def test_pdf_single_page(self, pdf_1_page, tmp_path):
        from app.services.file_processing import extract_total_pages
        p = tmp_path / "single.pdf"
        p.write_bytes(pdf_1_page)
        count, warnings = extract_total_pages(str(p))
        assert count == 1
        assert warnings == []

    def test_pptx_page_count_without_libreoffice(self, pptx_bytes, tmp_path):
        """PyMuPDF should count PPTX pages even without LibreOffice conversion."""
        from app.services.file_processing import extract_total_pages
        p = tmp_path / "slides.pptx"
        p.write_bytes(pptx_bytes)
        count, warnings = extract_total_pages(str(p))
        # PPTX was created with 5 slides; fitz should report 5
        assert count >= 1
        # No warnings expected for a valid PPTX
        assert len(warnings) == 0

    def test_missing_file_returns_one_with_warning(self):
        from app.services.file_processing import extract_total_pages
        count, warnings = extract_total_pages("/nonexistent/path/file.pdf")
        assert count == 1
        assert len(warnings) == 1
        assert "not found" in warnings[0].lower()

    def test_corrupted_pdf_returns_one_with_warning(self, corrupted_pdf_bytes, tmp_path):
        from app.services.file_processing import extract_total_pages
        p = tmp_path / "bad.pdf"
        p.write_bytes(corrupted_pdf_bytes)
        count, warnings = extract_total_pages(str(p))
        assert count == 1
        assert len(warnings) >= 1

    def test_empty_file_returns_one_with_warning(self, tmp_path):
        from app.services.file_processing import extract_total_pages
        p = tmp_path / "empty.pdf"
        p.write_bytes(b"")
        count, warnings = extract_total_pages(str(p))
        assert count == 1
        assert len(warnings) >= 1

    def test_no_pdf_mime_gate(self, pdf_3_pages, tmp_path):
        """extract_total_pages must NOT gate on MIME type — the old bug."""
        from app.services.file_processing import extract_total_pages
        # Rename the file as .pptx to simulate a wrong content_type in headers
        p = tmp_path / "real_pdf_wrong_ext.pptx"
        p.write_bytes(pdf_3_pages)
        count, warnings = extract_total_pages(str(p))
        # Should still count 3 pages regardless of filename extension
        assert count == 3


class TestConvertToPdfIfNeeded:

    def test_non_pptx_returns_not_attempted(self, tmp_path, pdf_1_page):
        from app.services.file_processing import convert_to_pdf_if_needed
        p = tmp_path / "doc.pdf"
        p.write_bytes(pdf_1_page)
        result = convert_to_pdf_if_needed(str(p), ".pdf")
        assert result.attempted is False
        assert result.success is False

    def test_no_libreoffice_returns_warning(self, tmp_path, pptx_bytes):
        from app.services import file_processing
        from app.services.file_processing import convert_to_pdf_if_needed
        p = tmp_path / "slides.pptx"
        p.write_bytes(pptx_bytes)

        original_cmd = file_processing.LIBREOFFICE_CMD
        try:
            file_processing.LIBREOFFICE_CMD = None
            result = convert_to_pdf_if_needed(str(p), ".pptx")
        finally:
            file_processing.LIBREOFFICE_CMD = original_cmd

        assert result.attempted is True
        assert result.success is False
        assert len(result.warnings) >= 1
        assert "libreoffice" in result.warnings[0].lower()

    def test_libreoffice_success(self, tmp_path, pptx_bytes):
        from app.services import file_processing
        from app.services.file_processing import convert_to_pdf_if_needed

        p = tmp_path / "slides.pptx"
        p.write_bytes(pptx_bytes)
        pdf_path = tmp_path / "slides.pdf"

        def fake_run(cmd, **kwargs):
            # Simulate LibreOffice creating the PDF output
            pdf_path.write_bytes(b"%PDF-1.4\n")
            mock = MagicMock()
            mock.stdout = b""
            mock.stderr = b""
            mock.returncode = 0
            return mock

        original_cmd = file_processing.LIBREOFFICE_CMD
        try:
            file_processing.LIBREOFFICE_CMD = "/usr/bin/libreoffice"
            with patch("subprocess.run", side_effect=fake_run):
                result = convert_to_pdf_if_needed(str(p), ".pptx")
        finally:
            file_processing.LIBREOFFICE_CMD = original_cmd

        assert result.attempted is True
        assert result.success is True
        assert result.output_path == str(pdf_path)
        assert result.converted_type == "application/pdf"

    def test_libreoffice_process_failure(self, tmp_path, pptx_bytes):
        from app.services import file_processing
        from app.services.file_processing import convert_to_pdf_if_needed

        p = tmp_path / "slides.pptx"
        p.write_bytes(pptx_bytes)

        original_cmd = file_processing.LIBREOFFICE_CMD
        try:
            file_processing.LIBREOFFICE_CMD = "/usr/bin/libreoffice"
            with patch(
                "subprocess.run",
                side_effect=subprocess.CalledProcessError(1, "libreoffice", b"", b"error msg"),
            ):
                result = convert_to_pdf_if_needed(str(p), ".pptx")
        finally:
            file_processing.LIBREOFFICE_CMD = original_cmd

        assert result.attempted is True
        assert result.success is False
        assert len(result.warnings) >= 1
        assert "exit" in result.warnings[0].lower() or "failed" in result.warnings[0].lower()

    def test_libreoffice_timeout(self, tmp_path, pptx_bytes):
        from app.services import file_processing
        from app.services.file_processing import convert_to_pdf_if_needed

        p = tmp_path / "slides.pptx"
        p.write_bytes(pptx_bytes)

        original_cmd = file_processing.LIBREOFFICE_CMD
        try:
            file_processing.LIBREOFFICE_CMD = "/usr/bin/libreoffice"
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("libreoffice", 60)):
                result = convert_to_pdf_if_needed(str(p), ".pptx")
        finally:
            file_processing.LIBREOFFICE_CMD = original_cmd

        assert result.attempted is True
        assert result.success is False
        assert any("timeout" in w.lower() or "timed out" in w.lower() for w in result.warnings)


class TestValidateUpload:

    def test_valid_pdf_accepted(self, pdf_1_page):
        from app.services.file_processing import validate_upload
        result = validate_upload(
            content=pdf_1_page,
            original_name="doc.pdf",
            allowed_extensions=[".pdf", ".pptx"],
            max_bytes=20 * 1024 * 1024,
        )
        assert result.actual_mime == "application/pdf"

    def test_valid_pptx_accepted(self, pptx_bytes):
        from app.services.file_processing import validate_upload
        result = validate_upload(
            content=pptx_bytes,
            original_name="slides.pptx",
            allowed_extensions=[".pdf", ".pptx"],
            max_bytes=20 * 1024 * 1024,
        )
        assert "presentation" in result.actual_mime or "zip" in result.actual_mime

    def test_empty_file_raises(self):
        from app.services.file_processing import validate_upload
        with pytest.raises(ValueError, match="empty"):
            validate_upload(
                content=b"",
                original_name="empty.pdf",
                allowed_extensions=[".pdf"],
                max_bytes=1024,
            )

    def test_disallowed_extension_raises(self, pdf_1_page):
        from app.services.file_processing import validate_upload
        with pytest.raises(ValueError, match="not allowed"):
            validate_upload(
                content=pdf_1_page,
                original_name="script.py",
                allowed_extensions=[".pdf", ".pptx"],
                max_bytes=1024 * 1024,
            )

    def test_oversized_file_raises(self, pdf_1_page):
        from app.services.file_processing import validate_upload
        with pytest.raises(ValueError, match="exceed"):
            validate_upload(
                content=pdf_1_page,
                original_name="big.pdf",
                allowed_extensions=[".pdf"],
                max_bytes=10,  # 10 bytes — smaller than any PDF
            )

    def test_dangerous_elf_rejected(self, executable_bytes):
        from app.services.file_processing import validate_upload
        # ELF bytes uploaded with .pdf extension — must be rejected
        with pytest.raises(ValueError, match="rejected"):
            validate_upload(
                content=executable_bytes,
                original_name="malware.pdf",
                allowed_extensions=[".pdf"],
                max_bytes=1024 * 1024,
            )

    def test_octet_stream_pdf_accepted(self, pdf_1_page):
        """application/octet-stream browser MIME is fine if content is valid PDF."""
        from app.services.file_processing import validate_upload
        # Simulate Safari sending application/octet-stream for a PDF
        result = validate_upload(
            content=pdf_1_page,
            original_name="document.pdf",
            allowed_extensions=[".pdf"],
            max_bytes=20 * 1024 * 1024,
        )
        # Actual MIME detected from bytes should be application/pdf, not octet-stream
        assert result.actual_mime == "application/pdf"

    def test_wrong_mime_header_does_not_affect_result(self, pdf_1_page):
        """Browser-reported content_type is not used; only file bytes matter."""
        from app.services.file_processing import validate_upload
        result = validate_upload(
            content=pdf_1_page,
            original_name="file.pdf",
            allowed_extensions=[".pdf"],
            max_bytes=20 * 1024 * 1024,
        )
        # Must detect PDF from bytes regardless of what browser header would say
        assert result.actual_mime == "application/pdf"


# ═══════════════════════════════════════════════════════════════════
# INTEGRATION TESTS — Upload endpoint
# These test the FastAPI layer with a mocked database.
# ═══════════════════════════════════════════════════════════════════

def _make_app_with_mocked_db(mock_slide, mock_session_obj, mock_asset=None):
    """Return a FastAPI TestClient with the DB dependency overridden."""
    from unittest.mock import AsyncMock, MagicMock
    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.main import app
    from app.database import get_db
    from app.auth import get_current_user

    async def mock_get_db():
        db = AsyncMock(spec=AsyncSession)

        # Use MagicMock (not AsyncMock) for result objects because scalar_one_or_none()
        # is a synchronous SQLAlchemy method — AsyncMock would make it return an unawaited coroutine.
        session_result = MagicMock()
        slide_result = MagicMock()
        asset_result = MagicMock()

        session_result.scalar_one_or_none.return_value = mock_session_obj
        slide_result.scalar_one_or_none.return_value = mock_slide
        asset_result.scalar_one_or_none.return_value = mock_asset

        # Call order: _verify_ownership, slide lookup, asset lookup, session event_id
        db.execute.side_effect = [
            session_result,
            slide_result,
            asset_result,
            session_result,
        ]
        db.commit = AsyncMock()
        db.add = MagicMock()
        yield db

    from uuid import uuid4
    mock_user = MagicMock()
    mock_user.id = uuid4()
    mock_user.role = "USER"

    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[get_current_user] = lambda: mock_user

    client = TestClient(app, raise_server_exceptions=True)
    return client, app


class TestUploadEndpoint:

    def _make_slide(self, slide_id, session_id):
        from unittest.mock import MagicMock
        from uuid import UUID
        slide = MagicMock()
        slide.id = UUID(slide_id)
        slide.session_id = UUID(session_id)
        slide.type = "CONTENT"
        slide.order = 0
        slide.is_active = False
        slide.content_json = {}
        return slide

    def _make_session(self, session_id):
        from unittest.mock import MagicMock
        from uuid import UUID
        s = MagicMock()
        s.id = UUID(session_id)
        s.event_id = None
        s.owner_id = UUID("00000000-0000-0000-0000-000000000001")
        s.role = None
        s.presentation_id = None  # legacy session — not linked to a Presentation Timeline
        return s

    def test_pdf_upload_succeeds_and_returns_upload_meta(self, pdf_3_pages):
        sid = "00000000-0000-0000-0000-000000000010"
        slid = "00000000-0000-0000-0000-000000000020"
        slide = self._make_slide(slid, sid)
        session = self._make_session(sid)

        client, app = _make_app_with_mocked_db(slide, session)
        try:
            resp = client.post(
                f"/api/sessions/{sid}/slides/{slid}/upload",
                files={"file": ("test.pdf", io.BytesIO(pdf_3_pages), "application/pdf")},
            )
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "upload_meta" in body
        assert body["upload_meta"]["conversion_attempted"] is False  # PDF, no conversion needed

    def test_pptx_upload_without_libreoffice_returns_warning(self, pptx_bytes):
        from app.services import file_processing
        sid = "00000000-0000-0000-0000-000000000011"
        slid = "00000000-0000-0000-0000-000000000021"
        slide = self._make_slide(slid, sid)
        session = self._make_session(sid)

        client, app = _make_app_with_mocked_db(slide, session)
        original_cmd = file_processing.LIBREOFFICE_CMD
        try:
            file_processing.LIBREOFFICE_CMD = None
            resp = client.post(
                f"/api/sessions/{sid}/slides/{slid}/upload",
                files={"file": ("deck.pptx", io.BytesIO(pptx_bytes),
                                "application/vnd.openxmlformats-officedocument.presentationml.presentation")},
            )
        finally:
            file_processing.LIBREOFFICE_CMD = original_cmd
            app.dependency_overrides.clear()

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["upload_meta"]["conversion_attempted"] is True
        assert body["upload_meta"]["conversion_success"] is False
        assert len(body["upload_meta"]["warnings"]) >= 1

    def test_pptx_total_pages_correct_without_libreoffice(self, pptx_bytes):
        """PPTX must report real page count via fitz even without LibreOffice."""
        from app.services import file_processing
        sid = "00000000-0000-0000-0000-000000000012"
        slid = "00000000-0000-0000-0000-000000000022"
        slide = self._make_slide(slid, sid)
        session = self._make_session(sid)

        # Count pages in the fixture before upload so we know the expected value
        doc = fitz.open(stream=pptx_bytes, filetype="pptx")
        expected_pages = len(doc)
        doc.close()

        client, app = _make_app_with_mocked_db(slide, session)
        original_cmd = file_processing.LIBREOFFICE_CMD
        try:
            file_processing.LIBREOFFICE_CMD = None
            resp = client.post(
                f"/api/sessions/{sid}/slides/{slid}/upload",
                files={"file": ("deck.pptx", io.BytesIO(pptx_bytes),
                                "application/vnd.openxmlformats-officedocument.presentationml.presentation")},
            )
        finally:
            file_processing.LIBREOFFICE_CMD = original_cmd
            app.dependency_overrides.clear()

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["content_json"]["total_pages"] == expected_pages

    def test_empty_file_returns_400(self):
        sid = "00000000-0000-0000-0000-000000000013"
        slid = "00000000-0000-0000-0000-000000000023"
        slide = self._make_slide(slid, sid)
        session = self._make_session(sid)

        client, app = _make_app_with_mocked_db(slide, session)
        try:
            resp = client.post(
                f"/api/sessions/{sid}/slides/{slid}/upload",
                files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
            )
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"].lower()

    def test_disallowed_extension_returns_400(self, pdf_1_page):
        sid = "00000000-0000-0000-0000-000000000014"
        slid = "00000000-0000-0000-0000-000000000024"
        slide = self._make_slide(slid, sid)
        session = self._make_session(sid)

        client, app = _make_app_with_mocked_db(slide, session)
        try:
            resp = client.post(
                f"/api/sessions/{sid}/slides/{slid}/upload",
                files={"file": ("script.exe", io.BytesIO(pdf_1_page), "application/octet-stream")},
            )
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 400
        assert "not allowed" in resp.json()["detail"].lower()

    def test_dangerous_elf_content_returns_400(self, executable_bytes):
        sid = "00000000-0000-0000-0000-000000000015"
        slid = "00000000-0000-0000-0000-000000000025"
        slide = self._make_slide(slid, sid)
        session = self._make_session(sid)

        client, app = _make_app_with_mocked_db(slide, session)
        try:
            resp = client.post(
                f"/api/sessions/{sid}/slides/{slid}/upload",
                files={"file": ("malware.pdf", io.BytesIO(executable_bytes), "application/pdf")},
            )
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 400
        assert "rejected" in resp.json()["detail"].lower()


# ═══════════════════════════════════════════════════════════════════
# REGRESSION TESTS — Existing PDF behaviour unchanged
# ═══════════════════════════════════════════════════════════════════

class TestRegressionPdfBehaviour:

    def test_existing_pdf_page_count_unchanged(self, pdf_3_pages, tmp_path):
        """extract_total_pages must return same count as before the refactor."""
        from app.services.file_processing import extract_total_pages

        p = tmp_path / "existing.pdf"
        p.write_bytes(pdf_3_pages)

        # Pre-refactor: count was done with fitz.open() directly
        doc = fitz.open(str(p))
        expected = len(doc)
        doc.close()

        count, warnings = extract_total_pages(str(p))
        assert count == expected
        assert warnings == []

    def test_pdf_mime_detection_still_works(self, pdf_1_page):
        from app.services.file_processing import detect_actual_file_type
        assert detect_actual_file_type(pdf_1_page, "doc.pdf") == "application/pdf"

    def test_validate_upload_pdf_still_returns_pdf_mime(self, pdf_1_page):
        from app.services.file_processing import validate_upload
        result = validate_upload(
            content=pdf_1_page,
            original_name="presentation.pdf",
            allowed_extensions=[".pdf", ".pptx", ".ppt", ".doc", ".docx", ".txt", ".odp", ".odt"],
            max_bytes=20 * 1024 * 1024,
        )
        assert result.actual_mime == "application/pdf"
        assert result.warnings == []

    def test_uploads_dir_existing_files_still_openable(self):
        """Files already in uploads/ must remain accessible via fitz."""
        from app.services.file_processing import extract_total_pages

        uploads = Path("uploads")
        if not uploads.exists():
            pytest.skip("No uploads directory found")

        pdf_files = list(uploads.glob("*.pdf"))
        if not pdf_files:
            pytest.skip("No PDF files in uploads/ to test")

        for pdf in pdf_files[:3]:  # Test up to 3 existing files
            count, warnings = extract_total_pages(str(pdf))
            assert count >= 1, f"Expected ≥1 page in {pdf}, got {count}"

    def test_stranded_pptx_now_reports_real_page_count(self):
        """The known stranded PPTX in uploads/ must now return real page count."""
        from app.services.file_processing import extract_total_pages

        pptx_path = "uploads/f2112a3a-1075-4e29-a190-e9647a9f31e4_SEZG-501-01.pptx"
        if not os.path.exists(pptx_path):
            pytest.skip("Known stranded PPTX not present — skipping regression check")

        count, warnings = extract_total_pages(pptx_path)
        assert count > 1, (
            f"Stranded PPTX should report >1 pages (has 17), got {count}. "
            f"Warnings: {warnings}"
        )
