import logging
from functools import lru_cache

from app.config import get_settings
from app.storage.base import StorageBackend
from app.storage.fallback import FallbackStorageBackend
from app.storage.local import LocalFilesystemBackend
from app.storage.s3 import S3StorageBackend

__all__ = [
    "StorageBackend",
    "LocalFilesystemBackend",
    "S3StorageBackend",
    "FallbackStorageBackend",
    "get_storage_backend",
]

logger = logging.getLogger(__name__)


@lru_cache
def get_storage_backend() -> StorageBackend:
    settings = get_settings()
    backend = settings.STORAGE_BACKEND.lower()

    if backend == "local":
        return LocalFilesystemBackend(root=settings.STORAGE_ROOT)

    if backend == "s3":
        s3 = S3StorageBackend(
            bucket=settings.S3_BUCKET,
            region=settings.S3_REGION,
            prefix=settings.S3_PREFIX,
            endpoint_url=settings.S3_ENDPOINT or None,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
            max_retries=settings.S3_MAX_RETRIES,
        )
        local = LocalFilesystemBackend(root=settings.STORAGE_ROOT)
        logger.info(
            "storage_backend_selected backend=s3 bucket=%s region=%s prefix=%s fallback=local",
            settings.S3_BUCKET, settings.S3_REGION, settings.S3_PREFIX,
        )
        return FallbackStorageBackend(primary=s3, secondary=local)

    raise NotImplementedError(
        f"Storage backend '{settings.STORAGE_BACKEND}' is not implemented. "
        "Implement it as a StorageBackend subclass (see app/storage/base.py) "
        "and wire it in here."
    )
