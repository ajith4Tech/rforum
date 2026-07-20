"""_remove_file (app/routers/session_assets.py) resolves and confines any
file_url to the uploads/ directory before deleting — pure-function unit
tests, no DB/HTTP harness needed."""
import os

import pytest


@pytest.fixture
def isolated_uploads(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("uploads", exist_ok=True)
    return tmp_path


def test_removes_file_inside_uploads(isolated_uploads):
    from app.routers.session_assets import _remove_file

    target = isolated_uploads / "uploads" / "asset123_deck.pdf"
    target.write_bytes(b"data")

    _remove_file("/uploads/asset123_deck.pdf")

    assert not target.exists()


def test_refuses_to_remove_a_path_traversal_escape(isolated_uploads):
    from app.routers.session_assets import _remove_file

    outside_file = isolated_uploads / "secret.txt"
    outside_file.write_bytes(b"do not delete me")

    _remove_file("/uploads/../secret.txt")

    assert outside_file.exists()


def test_missing_file_url_is_a_noop(isolated_uploads):
    from app.routers.session_assets import _remove_file

    _remove_file(None)
    _remove_file("")
