from functools import lru_cache

from app.config import get_settings
from app.storage.base import StorageBackend
from app.storage.local import LocalFilesystemBackend

__all__ = ["StorageBackend", "LocalFilesystemBackend", "get_storage_backend"]


@lru_cache
def get_storage_backend() -> StorageBackend:
    settings = get_settings()
    if settings.STORAGE_BACKEND == "local":
        return LocalFilesystemBackend(root=settings.STORAGE_ROOT)
    raise NotImplementedError(
        f"Storage backend '{settings.STORAGE_BACKEND}' is not implemented. "
        "Implement it as a StorageBackend subclass (see app/storage/base.py) "
        "and wire it in here."
    )
