"""Tests for app/storage/s3.py — S3StorageBackend, mocked via moto (no real
AWS calls, no network). Mirrors the contract asserted in
tests/test_storage_backend.py for LocalFilesystemBackend so both backends
are proven interchangeable."""
import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from app.storage.s3 import S3StorageBackend

REGION = "eu-north-1"
BUCKET = "rforum-uploads-test"


@pytest.fixture
def s3_env():
    with mock_aws():
        boto3.client("s3", region_name=REGION).create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": REGION},
        )
        yield


@pytest.fixture
def backend(s3_env):
    return S3StorageBackend(bucket=BUCKET, region=REGION, prefix="presentations")


class TestSaveReadExists:

    def test_save_then_read_round_trips(self, backend):
        backend.save("presentations/owner1/p1/original.pdf", b"hello world")
        assert backend.read("presentations/owner1/p1/original.pdf") == b"hello world"

    def test_exists_false_for_missing_key(self, backend):
        assert backend.exists("nowhere/nothing.png") is False

    def test_exists_true_after_save(self, backend):
        backend.save("k.webp", b"x")
        assert backend.exists("k.webp") is True

    def test_read_missing_key_raises_file_not_found(self, backend):
        with pytest.raises(FileNotFoundError):
            backend.read("nowhere/nothing.png")

    def test_save_overwrites_existing_key(self, backend):
        backend.save("k.webp", b"first")
        backend.save("k.webp", b"second")
        assert backend.read("k.webp") == b"second"

    def test_size_matches_content_length(self, backend):
        backend.save("k.webp", b"12345")
        assert backend.size("k.webp") == 5

    def test_size_missing_key_raises_file_not_found(self, backend):
        with pytest.raises(FileNotFoundError):
            backend.size("nowhere.webp")


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

    def test_delete_prefix_does_not_match_sibling_with_shared_prefix_string(self, backend):
        """Regression guard for the classic S3 prefix-matching bug: deleting
        prefix "p1" must not also delete "p10/..." just because the raw
        string "p1" is a substring of "p10"."""
        backend.save("presentations/owner1/p1/original.pdf", b"x")
        backend.save("presentations/owner1/p10/original.pdf", b"sibling")

        backend.delete_prefix("presentations/owner1/p1")

        assert backend.exists("presentations/owner1/p1/original.pdf") is False
        assert backend.exists("presentations/owner1/p10/original.pdf") is True


class TestListKeys:

    def test_list_keys_returns_logical_keys_without_bucket_prefix(self, backend):
        backend.save("presentations/owner1/p1/original.pdf", b"x")
        backend.save("presentations/owner1/p1/thumbs/0001.webp", b"y")

        keys = backend.list_keys("presentations/owner1/p1")

        assert set(keys) == {
            "presentations/owner1/p1/original.pdf",
            "presentations/owner1/p1/thumbs/0001.webp",
        }

    def test_list_keys_empty_for_missing_prefix(self, backend):
        assert backend.list_keys("presentations/owner1/nope") == []

    def test_list_keys_paginates_beyond_a_single_page(self, backend):
        for i in range(5):
            backend.save(f"presentations/owner1/p1/pages/{i:04d}.webp", b"x")
        keys = backend.list_keys("presentations/owner1/p1")
        assert len(keys) == 5


class TestBucketPrefixSeparationFromLogicalKey:

    def test_prefix_is_bucket_namespace_root_not_duplicated_in_logical_key(self, s3_env):
        """S3_PREFIX plays the same role STORAGE_ROOT does for local disk —
        it's the bucket-level namespace root, so the physical object key is
        f"{prefix}/{key}", not a de-duplicated merge."""
        backend = S3StorageBackend(bucket=BUCKET, region=REGION, prefix="presentations")
        backend.save("presentations/owner1/p1/original.pdf", b"x")

        raw = boto3.client("s3", region_name=REGION).get_object(
            Bucket=BUCKET, Key="presentations/presentations/owner1/p1/original.pdf"
        )
        assert raw["Body"].read() == b"x"

    def test_empty_prefix_uses_key_as_is(self, s3_env):
        backend = S3StorageBackend(bucket=BUCKET, region=REGION, prefix="")
        backend.save("presentations/owner1/p1/original.pdf", b"x")

        raw = boto3.client("s3", region_name=REGION).get_object(
            Bucket=BUCKET, Key="presentations/owner1/p1/original.pdf"
        )
        assert raw["Body"].read() == b"x"


class TestLegacyKeyCompat:

    def test_legacy_leading_slash_and_uploads_prefix_resolves(self, backend):
        backend.save("presentations/abc/page_p1.png", b"legacy-bytes")
        assert backend.read("/uploads/presentations/abc/page_p1.png") == b"legacy-bytes"
        assert backend.exists("/uploads/presentations/abc/page_p1.png") is True


class TestErrorHandling:

    def test_access_denied_raises_permission_error(self, backend, monkeypatch):
        def deny(*args, **kwargs):
            raise ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "denied"}}, "HeadObject"
            )

        monkeypatch.setattr(backend._client, "head_object", deny)
        with pytest.raises(PermissionError):
            backend.exists("k.webp")

    def test_transient_error_is_retried_then_succeeds(self, backend, monkeypatch):
        calls = {"n": 0}
        real_put = backend._client.put_object

        def flaky_put(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] < 2:
                raise ClientError(
                    {"Error": {"Code": "SlowDown", "Message": "slow down"}}, "PutObject"
                )
            return real_put(*args, **kwargs)

        monkeypatch.setattr(backend._client, "put_object", flaky_put)
        backend.save("k.webp", b"eventually ok")
        assert calls["n"] == 2
        assert backend.read("k.webp") == b"eventually ok"

    def test_persistent_transient_error_raises_connection_error_after_max_retries(self, backend, monkeypatch):
        def always_slow_down(*args, **kwargs):
            raise ClientError(
                {"Error": {"Code": "SlowDown", "Message": "slow down"}}, "PutObject"
            )

        monkeypatch.setattr(backend._client, "put_object", always_slow_down)
        monkeypatch.setattr(backend, "max_retries", 2)
        with pytest.raises(ConnectionError):
            backend.save("k.webp", b"x")

    def test_non_transient_client_error_is_normalized_to_connection_error(self, backend, monkeypatch):
        """A non-transient, non-404, non-403 ClientError (e.g. a misconfigured
        bucket) must still normalize to ConnectionError — not propagate as a
        raw botocore exception — so FallbackStorageBackend can catch it and
        degrade to local storage instead of the request crashing outright."""
        def bad_request(*args, **kwargs):
            raise ClientError(
                {"Error": {"Code": "InvalidBucketName", "Message": "bad bucket"}}, "PutObject"
            )

        monkeypatch.setattr(backend._client, "put_object", bad_request)
        with pytest.raises(ConnectionError):
            backend.save("k.webp", b"x")


class TestHead:

    def test_head_returns_size_and_etag(self, backend):
        backend.save("k.webp", b"12345")
        head = backend.head("k.webp")
        assert head["size"] == 5
        assert head["etag"]

    def test_head_returns_none_for_missing_key(self, backend):
        assert backend.head("nope.webp") is None
