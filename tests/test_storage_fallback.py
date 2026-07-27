"""Tests for app/storage/fallback.py — FallbackStorageBackend, the composite
that lets STORAGE_PROVIDER=s3 serve presentations uploaded before the S3
switchover from local disk with zero data migration."""
import pytest

from app.storage.fallback import FallbackStorageBackend
from app.storage.local import LocalFilesystemBackend


class _RecordingBackend(LocalFilesystemBackend):
    """Local backend that records every read()/exists()/size() call so tests
    can assert the primary is always consulted first (no unnecessary calls
    against the secondary)."""

    def __init__(self, root):
        super().__init__(root=root)
        self.read_calls = []
        self.exists_calls = []

    def read(self, key):
        self.read_calls.append(key)
        return super().read(key)

    def exists(self, key):
        self.exists_calls.append(key)
        return super().exists(key)


@pytest.fixture
def primary(tmp_path):
    return _RecordingBackend(root=str(tmp_path / "primary"))


@pytest.fixture
def secondary(tmp_path):
    return _RecordingBackend(root=str(tmp_path / "secondary"))


@pytest.fixture
def backend(primary, secondary):
    return FallbackStorageBackend(primary=primary, secondary=secondary)


class TestWritesGoToPrimary:

    def test_save_only_writes_primary(self, backend, primary, secondary):
        backend.save("k.webp", b"x")
        assert primary.exists("k.webp") is True
        assert secondary.exists("k.webp") is False


class TestReadsFallBackToSecondary:

    def test_read_from_primary_when_present(self, backend, primary):
        primary.save("k.webp", b"from-primary")
        assert backend.read("k.webp") == b"from-primary"

    def test_read_falls_back_to_secondary_when_absent_from_primary(self, backend, secondary):
        secondary.save("legacy/k.webp", b"from-secondary")
        assert backend.read("legacy/k.webp") == b"from-secondary"

    def test_primary_takes_precedence_when_key_exists_in_both(self, backend, primary, secondary):
        primary.save("k.webp", b"new")
        secondary.save("k.webp", b"old")
        assert backend.read("k.webp") == b"new"

    def test_missing_from_both_raises_file_not_found(self, backend):
        with pytest.raises(FileNotFoundError):
            backend.read("nowhere.webp")

    def test_size_falls_back_to_secondary(self, backend, secondary):
        secondary.save("legacy/k.webp", b"12345")
        assert backend.size("legacy/k.webp") == 5


class TestExists:

    def test_exists_true_if_in_either_backend(self, backend, primary, secondary):
        primary.save("in_primary.webp", b"x")
        secondary.save("in_secondary.webp", b"y")
        assert backend.exists("in_primary.webp") is True
        assert backend.exists("in_secondary.webp") is True
        assert backend.exists("neither.webp") is False


class TestDeleteAppliesToBoth:

    def test_delete_removes_key_from_both_backends(self, backend, primary, secondary):
        primary.save("k.webp", b"x")
        secondary.save("k.webp", b"y")
        backend.delete("k.webp")
        assert primary.exists("k.webp") is False
        assert secondary.exists("k.webp") is False

    def test_delete_prefix_removes_from_both_backends(self, backend, primary, secondary):
        primary.save("presentations/p1/original.pdf", b"x")
        secondary.save("presentations/p1/original.pdf", b"y")
        backend.delete_prefix("presentations/p1")
        assert primary.exists("presentations/p1/original.pdf") is False
        assert secondary.exists("presentations/p1/original.pdf") is False


class TestListKeys:

    def test_list_keys_unions_both_backends_without_duplicates(self, backend, primary, secondary):
        primary.save("presentations/p1/original.pdf", b"x")
        primary.save("presentations/p1/thumbs/0001.webp", b"y")
        secondary.save("presentations/p1/original.pdf", b"stale-duplicate")
        secondary.save("presentations/p2/original.pdf", b"legacy-only")

        keys = backend.list_keys("presentations")

        assert keys == sorted({
            "presentations/p1/original.pdf",
            "presentations/p1/thumbs/0001.webp",
            "presentations/p2/original.pdf",
        })


class _UnreachableBackend(LocalFilesystemBackend):
    """Simulates a misconfigured/unreachable S3 primary — every read-path
    method raises instead of ever completing, exactly what a bad bucket name
    or a denied IAM policy looks like from the app's point of view."""

    def __init__(self, root, exc_type):
        super().__init__(root=root)
        self._exc_type = exc_type

    def read(self, key):
        raise self._exc_type("primary unreachable")

    def exists(self, key):
        raise self._exc_type("primary unreachable")

    def size(self, key):
        raise self._exc_type("primary unreachable")

    def list_keys(self, prefix):
        raise self._exc_type("primary unreachable")


@pytest.mark.parametrize("exc_type", [PermissionError, ConnectionError])
class TestPrimaryUnavailableFallsBackRatherThanRaising:
    """The whole point of a fallback backend is to survive the primary being
    unreachable — a bad bucket name, revoked/missing IAM permissions, a
    network blip. Falling back only on FileNotFoundError (key genuinely
    absent) and letting PermissionError/ConnectionError propagate would turn
    exactly those failure modes into a hard outage for every presentation
    request instead of degrading to "served from local for now"."""

    def test_read_falls_back_when_primary_unreachable(self, secondary, exc_type, tmp_path):
        backend = FallbackStorageBackend(
            primary=_UnreachableBackend(root=str(tmp_path / "primary"), exc_type=exc_type),
            secondary=secondary,
        )
        secondary.save("k.webp", b"from-secondary")
        assert backend.read("k.webp") == b"from-secondary"

    def test_exists_falls_back_when_primary_unreachable(self, secondary, exc_type, tmp_path):
        backend = FallbackStorageBackend(
            primary=_UnreachableBackend(root=str(tmp_path / "primary"), exc_type=exc_type),
            secondary=secondary,
        )
        secondary.save("k.webp", b"y")
        assert backend.exists("k.webp") is True
        assert backend.exists("missing.webp") is False

    def test_size_falls_back_when_primary_unreachable(self, secondary, exc_type, tmp_path):
        backend = FallbackStorageBackend(
            primary=_UnreachableBackend(root=str(tmp_path / "primary"), exc_type=exc_type),
            secondary=secondary,
        )
        secondary.save("k.webp", b"12345")
        assert backend.size("k.webp") == 5

    def test_list_keys_falls_back_when_primary_unreachable(self, secondary, exc_type, tmp_path):
        backend = FallbackStorageBackend(
            primary=_UnreachableBackend(root=str(tmp_path / "primary"), exc_type=exc_type),
            secondary=secondary,
        )
        secondary.save("presentations/p1/original.pdf", b"legacy-only")
        assert backend.list_keys("presentations") == ["presentations/p1/original.pdf"]
