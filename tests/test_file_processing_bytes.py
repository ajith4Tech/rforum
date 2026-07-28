"""Unit tests for the bytes-oriented file_processing functions added for the
storage-backed Presentation pipeline (compute_checksum, render_thumbnail,
render_page, render_all_thumbnails, extract_page_count_and_size,
convert_to_pdf_bytes). The existing path-based functions are untouched and
already covered by tests/test_upload_reliability.py."""
import hashlib

import pytest


class TestComputeChecksum:

    def test_matches_hashlib_sha256(self, pdf_1_page):
        from app.services.file_processing import compute_checksum
        assert compute_checksum(pdf_1_page) == hashlib.sha256(pdf_1_page).hexdigest()

    def test_identical_bytes_same_checksum(self, pdf_3_pages):
        from app.services.file_processing import compute_checksum
        assert compute_checksum(pdf_3_pages) == compute_checksum(pdf_3_pages)

    def test_different_bytes_different_checksum(self, pdf_1_page, pdf_3_pages):
        from app.services.file_processing import compute_checksum
        assert compute_checksum(pdf_1_page) != compute_checksum(pdf_3_pages)


class TestExtractPageCountAndSize:

    def test_pdf_page_count(self, pdf_3_pages):
        from app.services.file_processing import extract_page_count_and_size
        count, (w, h), warnings = extract_page_count_and_size(pdf_3_pages, ".pdf")
        assert count == 3
        assert w > 0 and h > 0
        assert warnings == []

    def test_corrupted_pdf_falls_back_to_one(self, corrupted_pdf_bytes):
        from app.services.file_processing import extract_page_count_and_size
        count, (w, h), warnings = extract_page_count_and_size(corrupted_pdf_bytes, ".pdf")
        assert count == 1
        assert len(warnings) >= 1

    def test_pptx_page_count(self, pptx_bytes):
        from app.services.file_processing import extract_page_count_and_size
        count, (w, h), warnings = extract_page_count_and_size(pptx_bytes, ".pptx")
        assert count >= 1
        assert warnings == []


class TestRenderThumbnailAndPage:

    def test_render_thumbnail_returns_webp_bytes(self, pdf_1_page):
        from app.services.file_processing import render_thumbnail
        thumb = render_thumbnail(pdf_1_page, ".pdf", 1)
        assert isinstance(thumb, bytes)
        assert len(thumb) > 0

    def test_render_page_larger_than_thumbnail(self, pdf_1_page):
        """Full-res render (2x) must produce more bytes than the thumbnail (0.4x)."""
        from app.services.file_processing import render_page, render_thumbnail
        thumb = render_thumbnail(pdf_1_page, ".pdf", 1)
        full = render_page(pdf_1_page, ".pdf", 1)
        assert len(full) >= len(thumb)

    def test_render_out_of_range_page_raises(self, pdf_1_page):
        from app.services.file_processing import render_page
        with pytest.raises(ValueError):
            render_page(pdf_1_page, ".pdf", 5)


class TestRenderAllThumbnails:

    def test_one_thumbnail_per_page(self, pdf_3_pages):
        from app.services.file_processing import render_all_thumbnails
        thumbs, warnings = render_all_thumbnails(pdf_3_pages, ".pdf")
        assert len(thumbs) == 3
        assert all(isinstance(t, bytes) and len(t) > 0 for t in thumbs)
        assert warnings == []

    def test_corrupted_file_returns_empty_list(self, corrupted_pdf_bytes):
        from app.services.file_processing import render_all_thumbnails
        thumbs, warnings = render_all_thumbnails(corrupted_pdf_bytes, ".pdf")
        assert thumbs == []
        assert len(warnings) >= 1

    def test_empty_bytes_returns_empty_list(self):
        from app.services.file_processing import render_all_thumbnails
        thumbs, warnings = render_all_thumbnails(b"", ".pdf")
        assert thumbs == []
        assert len(warnings) >= 1


class TestCheckRenderLimits:
    """check_render_limits() — added to reject an oversized/oddly-dimensioned
    deck (app/routers/presentations.py::_process_upload) before the
    expensive render_all_thumbnails() pass runs."""

    def test_within_limits_does_not_raise(self):
        from app.services.file_processing import check_render_limits
        check_render_limits(10, 612.0, 792.0, max_pages=300, max_dimension_pt=20000.0)

    def test_page_count_over_limit_raises(self):
        from app.services.file_processing import check_render_limits
        with pytest.raises(ValueError, match="pages"):
            check_render_limits(301, 612.0, 792.0, max_pages=300, max_dimension_pt=20000.0)

    def test_page_count_at_limit_does_not_raise(self):
        from app.services.file_processing import check_render_limits
        check_render_limits(300, 612.0, 792.0, max_pages=300, max_dimension_pt=20000.0)

    def test_width_over_limit_raises(self):
        from app.services.file_processing import check_render_limits
        with pytest.raises(ValueError, match="page size"):
            check_render_limits(1, 20001.0, 792.0, max_pages=300, max_dimension_pt=20000.0)

    def test_height_over_limit_raises(self):
        from app.services.file_processing import check_render_limits
        with pytest.raises(ValueError, match="page size"):
            check_render_limits(1, 612.0, 20001.0, max_pages=300, max_dimension_pt=20000.0)


class TestConvertToPdfBytes:

    def test_non_pptx_not_attempted(self, pdf_1_page):
        from app.services.file_processing import convert_to_pdf_bytes
        result = convert_to_pdf_bytes(pdf_1_page, ".pdf")
        assert result.attempted is False

    def test_no_libreoffice_returns_warning_no_output_bytes(self, pptx_bytes):
        from app.services import file_processing
        from app.services.file_processing import convert_to_pdf_bytes

        original_cmd = file_processing.LIBREOFFICE_CMD
        try:
            file_processing.LIBREOFFICE_CMD = None
            result = convert_to_pdf_bytes(pptx_bytes, ".pptx")
        finally:
            file_processing.LIBREOFFICE_CMD = original_cmd

        assert result.attempted is True
        assert result.success is False
        assert result.output_bytes is None

    def test_libreoffice_success_returns_output_bytes(self, pptx_bytes, tmp_path):
        from unittest.mock import MagicMock, patch

        from app.services import file_processing
        from app.services.file_processing import convert_to_pdf_bytes

        def fake_run(cmd, **kwargs):
            # cmd's --outdir/file args mirror convert_to_pdf_if_needed's real
            # invocation; write the expected output next to the input file.
            outdir = cmd[cmd.index("--outdir") + 1]
            input_path = cmd[-1]
            from pathlib import Path
            stem = Path(input_path).stem
            (Path(outdir) / f"{stem}.pdf").write_bytes(b"%PDF-1.4\nconverted\n")
            mock = MagicMock()
            mock.stdout = b""
            mock.stderr = b""
            mock.returncode = 0
            return mock

        original_cmd = file_processing.LIBREOFFICE_CMD
        try:
            file_processing.LIBREOFFICE_CMD = "/usr/bin/libreoffice"
            with patch("subprocess.run", side_effect=fake_run):
                result = convert_to_pdf_bytes(pptx_bytes, ".pptx")
        finally:
            file_processing.LIBREOFFICE_CMD = original_cmd

        assert result.success is True
        assert result.output_bytes == b"%PDF-1.4\nconverted\n"
