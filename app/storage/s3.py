"""
S3-backed StorageBackend — same key contract as LocalFilesystemBackend
(app/storage/local.py): callers pass bare keys like
"presentations/<owner>/<id>/original.pdf" and never touch bucket/region/
credentials directly.

Key resolution mirrors LocalFilesystemBackend._resolve exactly (strip a
leading "/" and a legacy "uploads/" segment) so a key is interchangeable
between backends, then prepends `prefix` (S3_PREFIX) the same way
LocalFilesystemBackend joins under `root` (STORAGE_ROOT) — `prefix` is the
bucket-level namespace root, not a duplicate of the "presentations/..."
segment already inside the key.

Transient failures (throttling, 5xx, connection/read timeouts) are retried
with exponential backoff on top of boto3's own built-in retry policy.
NoSuchKey/404 -> FileNotFoundError, AccessDenied -> PermissionError, and
every other failure mode (persistent transient errors after retries, or an
unrecognized/non-transient ClientError such as a misconfigured bucket) ->
ConnectionError — matching the exception contract callers already rely on
for LocalFilesystemBackend, and the three exception types
FallbackStorageBackend treats as "primary unavailable, degrade to local".
"""
import logging
import time
from pathlib import Path

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import (
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)

from app.storage.base import StorageBackend

logger = logging.getLogger(__name__)

_NOT_FOUND_CODES = frozenset({"NoSuchKey", "404"})
_ACCESS_DENIED_CODES = frozenset({
    "AccessDenied", "403",
    "InvalidAccessKeyId", "SignatureDoesNotMatch", "InvalidClientTokenId", "ExpiredToken",
})
_TRANSIENT_CODES = frozenset({
    "RequestTimeout", "RequestTimeTooSkewed", "SlowDown", "InternalError",
    "ServiceUnavailable", "Throttling", "ThrottlingException",
    "500", "502", "503", "504",
})

_MAX_KEYS_PER_DELETE_BATCH = 1000


class S3StorageBackend(StorageBackend):
    def __init__(
        self,
        bucket: str,
        region: str,
        prefix: str = "",
        endpoint_url: str | None = None,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        max_retries: int = 3,
        max_pool_connections: int = 10,
    ):
        if not bucket:
            raise ValueError("S3StorageBackend requires a non-empty bucket name")

        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.max_retries = max(1, max_retries)

        client_kwargs: dict = {
            "region_name": region,
            "config": BotoConfig(
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=5,
                read_timeout=30,
                # botocore's own default here is 10, regardless of how many
                # threads are actually issuing concurrent requests through
                # this one client. urllib3 doesn't block callers once that's
                # exhausted (block=False) — it just stops reusing/pooling
                # connections beyond this count, paying a fresh TLS
                # handshake per "overflow" request instead. Passed in by the
                # caller (app/storage/__init__.py::get_storage_backend) to
                # match STORAGE_IO_CONCURRENCY, so raising the dedicated
                # storage-I/O thread pool's size doesn't just relocate the
                # same class of bottleneck to this pool instead.
                max_pool_connections=max_pool_connections,
            ),
        }
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url
        if aws_access_key_id and aws_secret_access_key:
            client_kwargs["aws_access_key_id"] = aws_access_key_id
            client_kwargs["aws_secret_access_key"] = aws_secret_access_key

        self._client = boto3.client("s3", **client_kwargs)

    # ── Key resolution ──────────────────────────────────────────────────────

    def _object_key(self, key: str) -> str:
        k = key.lstrip("/")
        if k.startswith("uploads/"):
            k = k[len("uploads/"):]
        if not k:
            raise ValueError(f"Storage key resolves to empty object key: {key!r}")
        if ".." in Path(k).parts:
            raise ValueError(f"Storage key resolves outside root: {key!r}")
        return f"{self.prefix}/{k}" if self.prefix else k

    def _prefix_key(self, prefix: str) -> str:
        """Like _object_key, but boundary-safe for prefix listing/deletion —
        a trailing '/' stops "p1" from matching sibling "p10/...", the same
        directory-boundary guarantee LocalFilesystemBackend gets for free
        from real filesystem paths."""
        object_key = self._object_key(prefix) if prefix.lstrip("/") else self.prefix
        if object_key and not object_key.endswith("/"):
            object_key += "/"
        return object_key

    def _logical_key(self, object_key: str) -> str:
        """Inverse of _object_key — strip the bucket-level prefix back off so
        callers only ever see keys in the shape they passed in."""
        if self.prefix and object_key.startswith(f"{self.prefix}/"):
            return object_key[len(self.prefix) + 1:]
        return object_key

    # ── Retry helper ────────────────────────────────────────────────────────

    def _with_retry(self, func, description: str):
        delay = 0.5
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return func()
            except (EndpointConnectionError, ConnectTimeoutError, ReadTimeoutError) as exc:
                last_exc = exc
                logger.warning(
                    "s3_transient_network_error op=%s attempt=%d/%d error=%s",
                    description, attempt, self.max_retries, exc,
                )
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code", "")
                if code in _NOT_FOUND_CODES:
                    raise FileNotFoundError(f"S3 key not found (op={description})") from exc
                if code in _ACCESS_DENIED_CODES:
                    raise PermissionError(
                        f"S3 access denied (op={description}, bucket={self.bucket})"
                    ) from exc
                if code not in _TRANSIENT_CODES:
                    # Not a recognized transient code (e.g. a misconfigured
                    # bucket/region) — retrying won't help, but this must
                    # still degrade to local via FallbackStorageBackend
                    # rather than crash the request with a raw botocore
                    # exception the fallback layer doesn't know how to
                    # catch. Normalize it the same way an exhausted-retry
                    # transient failure is normalized below.
                    logger.error(
                        "s3_operation_failed op=%s code=%s error=%s",
                        description, code, exc,
                    )
                    raise ConnectionError(
                        f"S3 operation '{description}' failed (code={code}): {exc}"
                    ) from exc
                last_exc = exc
                logger.warning(
                    "s3_transient_client_error op=%s attempt=%d/%d code=%s",
                    description, attempt, self.max_retries, code,
                )
            if attempt < self.max_retries:
                time.sleep(delay)
                delay *= 2

        logger.error(
            "s3_operation_failed_after_retries op=%s attempts=%d error=%s",
            description, self.max_retries, last_exc,
        )
        raise ConnectionError(
            f"S3 operation '{description}' failed after {self.max_retries} attempts: {last_exc}"
        ) from last_exc

    # ── StorageBackend interface ────────────────────────────────────────────

    def save(self, key: str, content: bytes) -> None:
        object_key = self._object_key(key)
        self._with_retry(
            lambda: self._client.put_object(Bucket=self.bucket, Key=object_key, Body=content),
            description=f"put_object:{object_key}",
        )
        logger.info("s3_object_saved bucket=%s key=%s bytes=%d", self.bucket, object_key, len(content))

    def read(self, key: str) -> bytes:
        object_key = self._object_key(key)
        response = self._with_retry(
            lambda: self._client.get_object(Bucket=self.bucket, Key=object_key),
            description=f"get_object:{object_key}",
        )
        return response["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            object_key = self._object_key(key)
        except ValueError:
            return False
        try:
            self._with_retry(
                lambda: self._client.head_object(Bucket=self.bucket, Key=object_key),
                description=f"head_object:{object_key}",
            )
            return True
        except FileNotFoundError:
            return False

    def delete(self, key: str) -> None:
        object_key = self._object_key(key)
        self._with_retry(
            lambda: self._client.delete_object(Bucket=self.bucket, Key=object_key),
            description=f"delete_object:{object_key}",
        )

    def delete_prefix(self, prefix: str) -> None:
        object_prefix = self._prefix_key(prefix)
        keys = self._list_object_keys(object_prefix)
        for i in range(0, len(keys), _MAX_KEYS_PER_DELETE_BATCH):
            batch = keys[i:i + _MAX_KEYS_PER_DELETE_BATCH]
            self._with_retry(
                lambda batch=batch: self._client.delete_objects(
                    Bucket=self.bucket,
                    Delete={"Objects": [{"Key": k} for k in batch], "Quiet": True},
                ),
                description=f"delete_objects:{object_prefix}",
            )
        logger.info("s3_prefix_deleted bucket=%s prefix=%s count=%d", self.bucket, object_prefix, len(keys))

    def size(self, key: str) -> int:
        object_key = self._object_key(key)
        response = self._with_retry(
            lambda: self._client.head_object(Bucket=self.bucket, Key=object_key),
            description=f"head_object:{object_key}",
        )
        return response["ContentLength"]

    def list_keys(self, prefix: str) -> list[str]:
        object_prefix = self._prefix_key(prefix)
        return [
            self._logical_key(k)
            for k in self._list_object_keys(object_prefix)
        ]

    # ── Internal ─────────────────────────────────────────────────────────

    def _list_object_keys(self, object_prefix: str) -> list[str]:
        keys: list[str] = []
        continuation_token: str | None = None
        while True:
            kwargs = {"Bucket": self.bucket, "Prefix": object_prefix}
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token
            response = self._with_retry(
                lambda kwargs=kwargs: self._client.list_objects_v2(**kwargs),
                description=f"list_objects_v2:{object_prefix}",
            )
            keys.extend(obj["Key"] for obj in response.get("Contents", []))
            if response.get("IsTruncated"):
                continuation_token = response.get("NextContinuationToken")
            else:
                break
        return keys

    def check_bucket_access(self) -> None:
        """Preflight check for scripts (migration, cleanup) that want to fail
        fast on a misconfigured bucket name or missing IAM permissions,
        rather than discovering it deep into a per-object operation.
        head_object can't be reused for this — a HEAD on a missing key
        inside an existing bucket and a HEAD against a bucket that doesn't
        exist at all both come back as a bodyless 404 with no way to tell
        them apart, so a bucket that's simply misspelled would silently
        read as "every object in it happens to be absent" instead of
        raising. Calls HeadBucket directly instead, which does distinguish
        them (404 truly missing vs. 403 exists-but-inaccessible). Raises
        FileNotFoundError / PermissionError / ConnectionError, same
        contract as the rest of this backend."""
        self._with_retry(
            lambda: self._client.head_bucket(Bucket=self.bucket),
            description=f"head_bucket:{self.bucket}",
        )

    def object_key_for(self, key: str) -> str:
        """Public escape hatch for the migration script, which needs to know
        the literal bucket object key (to compare against, e.g., ETag)."""
        return self._object_key(key)

    def head(self, key: str) -> dict | None:
        """S3-specific extra (not part of the StorageBackend interface — ETag
        and last-modified have no local-filesystem equivalent exposed by this
        interface): {"size", "etag", "last_modified"} for `key`, or None if
        absent. Used by the migration script to verify an already-uploaded
        object without downloading it, and by the cleanup service's S3
        orphan sweep to apply the same in-flight-upload grace period the
        local disk-orphan sweep uses."""
        object_key = self._object_key(key)
        try:
            response = self._with_retry(
                lambda: self._client.head_object(Bucket=self.bucket, Key=object_key),
                description=f"head_object:{object_key}",
            )
        except FileNotFoundError:
            return None
        return {
            "size": response["ContentLength"],
            "etag": response["ETag"].strip('"'),
            "last_modified": response["LastModified"],
        }
