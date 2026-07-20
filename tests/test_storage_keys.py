"""Unit tests for app/storage/keys.py — the single shared helper that builds
every "presentations/<owner>/<id>/..." key, and derives a presentation's root
directory back out of an already-stored key for prefix deletes."""
import uuid

import pytest

from app.storage.keys import (
    dir_prefix_from_known_key,
    original_key,
    owner_dir_name,
    page_key,
    pdf_key,
    pdf_key_for_dir,
    sanitize_username,
    thumbnail_key,
    username_from_email,
)


class TestSanitizeUsername:

    def test_spaces_become_underscores(self):
        assert sanitize_username("Ajith B M") == "Ajith_B_M"

    def test_casing_is_preserved(self):
        assert sanitize_username("Ajith") == "Ajith"

    def test_invalid_characters_are_stripped(self):
        assert sanitize_username("ajith!@#bm") == "ajith_bm"

    def test_duplicate_underscores_collapse(self):
        assert sanitize_username("ajith   b m") == "ajith_b_m"
        assert sanitize_username("ajith__bm") == "ajith_bm"

    def test_leading_trailing_underscores_stripped(self):
        assert sanitize_username("  ajith  ") == "ajith"
        assert sanitize_username("_ajith_") == "ajith"

    def test_empty_input_falls_back_to_user(self):
        assert sanitize_username("") == "user"
        assert sanitize_username("!!!") == "user"


class TestUsernameFromEmail:

    def test_uses_local_part_only(self):
        assert username_from_email("ajith@lyfehardware.com") == "ajith"

    def test_sanitizes_local_part(self):
        assert username_from_email("ajith.b m@example.com") == "ajith_b_m"


class TestOwnerDirName:

    def test_shape_is_username_double_underscore_u_underscore_id(self):
        user_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        assert owner_dir_name("ajith@lyfehardware.com", user_id) == f"ajith__u_{user_id}"


class TestKeyBuilders:

    def setup_method(self):
        self.email = "ajith@lyfehardware.com"
        self.user_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        self.pres_id = uuid.UUID("8ac91d72-0000-0000-0000-000000000000")

    def test_original_key_preserves_filename(self):
        key = original_key(self.email, self.user_id, self.pres_id, "demo.pptx")
        assert key == f"presentations/ajith__u_{self.user_id}/{self.pres_id}/original/demo.pptx"

    def test_pdf_key_is_fixed_filename(self):
        key = pdf_key(self.email, self.user_id, self.pres_id)
        assert key == f"presentations/ajith__u_{self.user_id}/{self.pres_id}/pdf/presentation.pdf"

    def test_thumbnail_and_page_keys_use_zero_padded_page_number(self):
        thumb = thumbnail_key(self.email, self.user_id, self.pres_id, 1)
        page = page_key(self.email, self.user_id, self.pres_id, 12)
        assert thumb.endswith("/thumbnails/page_001.webp")
        assert page.endswith("/pages/page_012.webp")


class TestDirPrefixFromKnownKey:

    def test_current_nested_original_shape(self):
        key = "presentations/ajith__u_42/8ac91d72/original/demo.pptx"
        assert dir_prefix_from_known_key(key, "8ac91d72") == "presentations/ajith__u_42/8ac91d72"

    def test_current_nested_page_shape(self):
        key = "presentations/ajith__u_42/8ac91d72/pages/page_001.webp"
        assert dir_prefix_from_known_key(key, "8ac91d72") == "presentations/ajith__u_42/8ac91d72"

    def test_legacy_flat_original_shape_with_owner_segment(self):
        # Some legacy rows (pre-hierarchy-redesign, per the committed
        # upload code at the time) store "presentations/<owner>/<id>/original<ext>"
        # — one segment shallower than the current "original/<filename>" shape.
        key = "presentations/42/8ac91d72/original.pdf"
        assert dir_prefix_from_known_key(key, "8ac91d72") == "presentations/42/8ac91d72"

    def test_legacy_flat_original_shape_no_owner_segment_with_uploads_prefix(self):
        # The actual shape found in real legacy DB rows: a leading
        # "/uploads/" segment (pre-storage-abstraction convention) and NO
        # owner segment at all — just "presentations/<id>/<file>". Counting
        # a fixed number of leading segments would derive "/uploads/presentations"
        # here (the entire bucket/disk root), which would make delete_prefix
        # wipe every presentation instead of just this one.
        key = "/uploads/presentations/8ac91d72/original.pdf"
        assert dir_prefix_from_known_key(key, "8ac91d72") == "/uploads/presentations/8ac91d72"

    def test_unknown_id_raises_rather_than_guessing(self):
        # If the presentation id isn't actually a path segment in the key,
        # guessing a prefix is unsafe (delete_prefix is destructive) — fail
        # loudly instead.
        key = "presentations/ajith__u_42/8ac91d72/original/demo.pptx"
        with pytest.raises(ValueError):
            dir_prefix_from_known_key(key, "does-not-appear")

    def test_pdf_key_for_dir_matches_pdf_key(self):
        pres_dir = dir_prefix_from_known_key(
            "presentations/ajith__u_42/8ac91d72/original/demo.pptx", "8ac91d72"
        )
        assert pdf_key_for_dir(pres_dir) == "presentations/ajith__u_42/8ac91d72/pdf/presentation.pdf"
