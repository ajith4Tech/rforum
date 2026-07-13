"""
Storage backend abstraction — every persisted presentation asset (original
file, thumbnail, rendered page) is addressed by a key, not a filesystem path.
Business logic (app/routers/presentations.py, app/services/file_processing.py)
never touches the filesystem directly; it only calls this interface, so the
backend is swappable (local today, S3/MinIO/R2 later) without touching a
single call site.
"""
from abc import ABC, abstractmethod


class StorageBackend(ABC):
    @abstractmethod
    def save(self, key: str, content: bytes) -> None:
        """Write `content` to `key`, creating any intermediate structure needed."""

    @abstractmethod
    def read(self, key: str) -> bytes:
        """Read the full contents of `key`. Raises FileNotFoundError if absent."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete `key` if present. Silently no-ops if it doesn't exist."""

    @abstractmethod
    def delete_prefix(self, prefix: str) -> None:
        """Delete every key under `prefix` (e.g. a whole presentation's directory)."""

    @abstractmethod
    def size(self, key: str) -> int:
        """Size in bytes of `key`. Raises FileNotFoundError if absent."""
