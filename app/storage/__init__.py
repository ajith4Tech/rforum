import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
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
    "STORAGE_IO_CONCURRENCY",
    "run_in_storage_executor",
]

logger = logging.getLogger(__name__)

# Sized to comfortably cover one live workshop's ~500-guest page-image burst
# with headroom, matching the sizing convention already used for
# JOIN_RATE_LIMIT/WS_CONNECT_RATE_LIMIT/RESPONSE_RATE_LIMIT_PER_IP
# (app/config.py) — not an arbitrary number. Also used as S3StorageBackend's
# max_pool_connections (app/storage/s3.py) so the two don't reintroduce the
# same class of bottleneck at a different layer.
STORAGE_IO_CONCURRENCY = 600

# asyncio.to_thread()/loop.run_in_executor(None, ...) all share ONE
# process-wide default executor sized at min(32, cpu_count()+4) — just 6
# threads on a 2-vCPU host (confirmed: cpython's ThreadPoolExecutor.__init__).
# That's fine for occasional one-off blocking calls, but
# app/routers/presentations.py::_serve_page_file can see hundreds of guests
# independently reading the very same small S3 object at once (e.g. a slide
# the moderator just activated, or a k6 workshop-scale load test) — with
# only 6 threads, request #495 queues behind 494 others even though each
# individual read takes tens of milliseconds, producing multi-second tail
# latency and, past that, client-side timeouts/resets and (via retry
# exhaustion under the extra load) a share of real 5xx. A dedicated,
# workshop-sized pool for storage I/O removes that queueing without
# touching the default executor every other blocking call in the app
# still shares.
STORAGE_IO_EXECUTOR = ThreadPoolExecutor(
    max_workers=STORAGE_IO_CONCURRENCY, thread_name_prefix="storage-io"
)


async def run_in_storage_executor(func, /, *args):
    """Runs a blocking storage call (StorageBackend.read/exists/save/etc.,
    or the render helpers in app/services/file_processing.py) on the
    dedicated pool above instead of asyncio's shared default executor. Use
    this instead of asyncio.to_thread() for any storage/render call reachable
    from a request path that can see high fan-out concurrency."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(STORAGE_IO_EXECUTOR, func, *args)


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
            max_pool_connections=STORAGE_IO_CONCURRENCY,
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
