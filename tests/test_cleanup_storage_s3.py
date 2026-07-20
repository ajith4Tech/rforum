"""Tests for scripts/cleanup_storage.py::_sweep_s3_orphans — the S3
equivalent of the local disk-orphan sweep, active only when the configured
storage backend has an S3 primary (STORAGE_PROVIDER=s3)."""
import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from app.storage.fallback import FallbackStorageBackend
from app.storage.local import LocalFilesystemBackend
from app.storage.s3 import S3StorageBackend

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "cleanup_storage.py"
REGION = "eu-north-1"
BUCKET = "rforum-uploads-test"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("cleanup_storage", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cleanup = _load_script_module()


@pytest.fixture
def s3_backend():
    with mock_aws():
        boto3.client("s3", region_name=REGION).create_bucket(
            Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION},
        )
        yield S3StorageBackend(bucket=BUCKET, region=REGION, prefix="presentations")


@pytest.fixture
def fallback_backend(s3_backend, tmp_path):
    return FallbackStorageBackend(
        primary=s3_backend, secondary=LocalFilesystemBackend(root=str(tmp_path / "uploads"))
    )


def _make_old(monkeypatch, s3_backend, hours=2):
    real_head = s3_backend.head

    def stale_head(key):
        result = real_head(key)
        if result is not None:
            result["last_modified"] = datetime.now(timezone.utc) - timedelta(hours=hours)
        return result

    monkeypatch.setattr(s3_backend, "head", stale_head)


class TestSweepS3Orphans:

    def test_no_op_for_local_only_backend(self, tmp_path):
        local_only = LocalFilesystemBackend(root=str(tmp_path / "uploads"))
        removed = cleanup._sweep_s3_orphans(known_ids=set(), storage=local_only, dry_run=False)
        assert removed == 0

    def test_known_presentation_is_never_touched(self, fallback_backend, s3_backend):
        pres_id = "11111111-1111-1111-1111-111111111111"
        s3_backend.save(f"presentations/owner1/{pres_id}/original.pdf", b"x")

        removed = cleanup._sweep_s3_orphans(known_ids={pres_id}, storage=fallback_backend, dry_run=False)

        assert removed == 0
        assert s3_backend.exists(f"presentations/owner1/{pres_id}/original.pdf") is True

    def test_recent_unknown_prefix_is_left_alone(self, fallback_backend, s3_backend):
        pres_id = "22222222-2222-2222-2222-222222222222"
        s3_backend.save(f"presentations/owner1/{pres_id}/original.pdf", b"x")

        removed = cleanup._sweep_s3_orphans(known_ids=set(), storage=fallback_backend, dry_run=False)

        assert removed == 0  # within the 1h grace period — could be an in-flight upload
        assert s3_backend.exists(f"presentations/owner1/{pres_id}/original.pdf") is True

    def test_old_unknown_prefix_is_removed(self, fallback_backend, s3_backend, monkeypatch):
        pres_id = "33333333-3333-3333-3333-333333333333"
        s3_backend.save(f"presentations/owner1/{pres_id}/original.pdf", b"x")
        s3_backend.save(f"presentations/owner1/{pres_id}/thumbs/0001.webp", b"y")
        _make_old(monkeypatch, s3_backend)

        removed = cleanup._sweep_s3_orphans(known_ids=set(), storage=fallback_backend, dry_run=False)

        assert removed == 1
        assert s3_backend.exists(f"presentations/owner1/{pres_id}/original.pdf") is False
        assert s3_backend.exists(f"presentations/owner1/{pres_id}/thumbs/0001.webp") is False

    def test_dry_run_reports_but_does_not_delete(self, fallback_backend, s3_backend, monkeypatch):
        pres_id = "44444444-4444-4444-4444-444444444444"
        s3_backend.save(f"presentations/owner1/{pres_id}/original.pdf", b"x")
        _make_old(monkeypatch, s3_backend)

        removed = cleanup._sweep_s3_orphans(known_ids=set(), storage=fallback_backend, dry_run=True)

        assert removed == 1
        assert s3_backend.exists(f"presentations/owner1/{pres_id}/original.pdf") is True

    def test_sibling_presentation_with_shared_uuid_prefix_string_survives(
        self, fallback_backend, s3_backend, monkeypatch
    ):
        old_id = "55555555-5555-5555-5555-555555555555"
        s3_backend.save(f"presentations/owner1/{old_id}/original.pdf", b"x")
        _make_old(monkeypatch, s3_backend)

        removed = cleanup._sweep_s3_orphans(
            known_ids={old_id}, storage=fallback_backend, dry_run=False,
        )
        assert removed == 0
        assert s3_backend.exists(f"presentations/owner1/{old_id}/original.pdf") is True
