"""
FallbackStorageBackend — composite backend enabling gradual S3 migration.

Every new write goes to `primary` (S3). Reads/existence/size checks consult
`primary` first, falling back to `secondary` (local disk) when the key isn't
there yet (this is what lets presentations uploaded before the S3
switchover keep being served with zero data migration, exactly like the
"uploads/" backward-compat handled inside LocalFilesystemBackend itself) —
and also when `primary` itself is unreachable or misconfigured
(PermissionError from a bad IAM policy, ConnectionError from a network
blip/throttling). Falling back only on FileNotFoundError and letting those
two propagate would mean an S3 outage or credentials issue turns into a
hard failure on every single presentation request instead of degrading to
"served from local until S3 recovers" — defeating the point of a fallback
backend. Deletes and prefix-deletes apply to both, so a presentation
removed via the API never leaves orphaned bytes in whichever backend it
happened to live in.
"""
import logging

from app.storage.base import StorageBackend

logger = logging.getLogger(__name__)

# Conditions under which `primary` (S3) is treated as "doesn't have it (yet)
# or can't be reached" and reads fall back to `secondary` (local) instead of
# raising: key genuinely absent, credentials/policy don't allow access, or
# the backend couldn't be reached at all.
_FALLBACK_TRIGGERS = (FileNotFoundError, PermissionError, ConnectionError)


class FallbackStorageBackend(StorageBackend):
    def __init__(self, primary: StorageBackend, secondary: StorageBackend):
        self.primary = primary
        self.secondary = secondary

    def save(self, key: str, content: bytes) -> None:
        self.primary.save(key, content)

    def read(self, key: str) -> bytes:
        try:
            return self.primary.read(key)
        except FileNotFoundError:
            logger.debug("storage_fallback_read key=%s", key)
            return self.secondary.read(key)
        except (PermissionError, ConnectionError) as exc:
            logger.warning("storage_primary_unavailable_read key=%s error=%s", key, exc)
            return self.secondary.read(key)

    def exists(self, key: str) -> bool:
        try:
            if self.primary.exists(key):
                return True
        except (PermissionError, ConnectionError) as exc:
            logger.warning("storage_primary_unavailable_exists key=%s error=%s", key, exc)
            return self.secondary.exists(key)
        return self.secondary.exists(key)

    def delete(self, key: str) -> None:
        try:
            self.primary.delete(key)
        except (PermissionError, ConnectionError) as exc:
            logger.warning("storage_primary_unavailable_delete key=%s error=%s", key, exc)
        self.secondary.delete(key)

    def delete_prefix(self, prefix: str) -> None:
        try:
            self.primary.delete_prefix(prefix)
        except (PermissionError, ConnectionError) as exc:
            logger.warning("storage_primary_unavailable_delete_prefix prefix=%s error=%s", prefix, exc)
        self.secondary.delete_prefix(prefix)

    def size(self, key: str) -> int:
        try:
            return self.primary.size(key)
        except FileNotFoundError:
            return self.secondary.size(key)
        except (PermissionError, ConnectionError) as exc:
            logger.warning("storage_primary_unavailable_size key=%s error=%s", key, exc)
            return self.secondary.size(key)

    def list_keys(self, prefix: str) -> list[str]:
        try:
            primary_keys = set(self.primary.list_keys(prefix))
        except (PermissionError, ConnectionError) as exc:
            logger.warning("storage_primary_unavailable_list_keys prefix=%s error=%s", prefix, exc)
            primary_keys = set()
        keys = primary_keys
        keys.update(self.secondary.list_keys(prefix))
        return sorted(keys)
