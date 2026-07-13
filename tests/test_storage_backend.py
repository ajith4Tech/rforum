"""Tests for app/storage — the StorageBackend abstraction used by the
Presentation asset pipeline. Pure filesystem tests, no DB/FastAPI needed."""
import pytest

from app.storage.local import LocalFilesystemBackend


@pytest.fixture
def backend(tmp_path):
    return LocalFilesystemBackend(root=str(tmp_path / "uploads"))


class TestSaveReadExists:

    def test_save_then_read_round_trips(self, backend):
        backend.save("presentations/owner1/p1/original.pdf", b"hello world")
        assert backend.read("presentations/owner1/p1/original.pdf") == b"hello world"

    def test_save_creates_intermediate_directories(self, backend):
        backend.save("a/b/c/d.webp", b"x")
        assert backend.exists("a/b/c/d.webp")

    def test_exists_false_for_missing_key(self, backend):
        assert backend.exists("nowhere/nothing.png") is False

    def test_read_missing_key_raises(self, backend):
        with pytest.raises(FileNotFoundError):
            backend.read("nowhere/nothing.png")

    def test_save_overwrites_existing_key(self, backend):
        backend.save("k.webp", b"first")
        backend.save("k.webp", b"second")
        assert backend.read("k.webp") == b"second"

    def test_size_matches_content_length(self, backend):
        backend.save("k.webp", b"12345")
        assert backend.size("k.webp") == 5


class TestDelete:

    def test_delete_removes_key(self, backend):
        backend.save("k.webp", b"x")
        backend.delete("k.webp")
        assert backend.exists("k.webp") is False

    def test_delete_missing_key_is_noop(self, backend):
        backend.delete("never/existed.webp")  # must not raise

    def test_delete_prefix_removes_whole_directory(self, backend):
        backend.save("presentations/owner1/p1/original.pdf", b"x")
        backend.save("presentations/owner1/p1/thumbs/0001.webp", b"y")
        backend.save("presentations/owner1/p1/pages/0001.webp", b"z")
        backend.save("presentations/owner1/p2/original.pdf", b"other")  # sibling, must survive

        backend.delete_prefix("presentations/owner1/p1")

        assert backend.exists("presentations/owner1/p1/original.pdf") is False
        assert backend.exists("presentations/owner1/p1/thumbs/0001.webp") is False
        assert backend.exists("presentations/owner1/p2/original.pdf") is True


class TestBackwardCompatibleKeyResolution:
    """
    Pre-redesign rows stored a literal '/uploads/...' disk path in the DB.
    New rows store a bare key. Both must resolve to the same file through
    the same backend with zero data migration.
    """

    def test_legacy_leading_slash_and_uploads_prefix_resolves(self, tmp_path):
        backend = LocalFilesystemBackend(root=str(tmp_path / "uploads"))
        backend.save("presentations/abc/page_p1.png", b"legacy-bytes")
        assert backend.read("/uploads/presentations/abc/page_p1.png") == b"legacy-bytes"
        assert backend.exists("/uploads/presentations/abc/page_p1.png") is True

    def test_new_style_bare_key_resolves(self, tmp_path):
        backend = LocalFilesystemBackend(root=str(tmp_path / "uploads"))
        backend.save("/uploads/presentations/owner1/p1/original.pdf", b"new-bytes")
        assert backend.read("presentations/owner1/p1/original.pdf") == b"new-bytes"


class TestPathTraversalGuard:

    def test_traversal_via_dotdot_is_rejected(self, backend):
        with pytest.raises(ValueError):
            backend.save("../../etc/passwd", b"pwned")

    def test_exists_returns_false_rather_than_raise_for_traversal(self, backend):
        assert backend.exists("../../etc/passwd") is False
