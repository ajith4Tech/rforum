"""Tests for app/storage/__init__.py::get_storage_backend() — picks
LocalFilesystemBackend vs an S3-primary FallbackStorageBackend based on
Settings.STORAGE_BACKEND (settable via STORAGE_BACKEND or STORAGE_PROVIDER
env vars), and must keep working for "local" with zero config changes."""
import pytest
from moto import mock_aws

from app.config import Settings
from app.storage import get_storage_backend
from app.storage.fallback import FallbackStorageBackend
from app.storage.local import LocalFilesystemBackend
from app.storage.s3 import S3StorageBackend

# DATABASE_URL/SECRET_KEY/INVITE_CODE/CORS_ORIGINS have no insecure default
# (app/config.py) and must be supplied explicitly whenever a test builds a
# Settings() with _env_file=None — these values are never used for anything
# beyond satisfying that requirement in these storage-selection tests.
_REQUIRED_SETTINGS = dict(
    DATABASE_URL="postgresql+asyncpg://test:test@localhost/test",
    SECRET_KEY="test-secret-key",
    INVITE_CODE="TEST-CODE",
    CORS_ORIGINS=["http://testserver"],
)


@pytest.fixture(autouse=True)
def _clear_cache(monkeypatch):
    # Several other test modules do `os.environ.setdefault("STORAGE_BACKEND", "local")`
    # at import time to keep app startup off real S3 during collection, and that
    # mutation outlives their own tests for the rest of the process. Since
    # Settings.STORAGE_BACKEND accepts either STORAGE_BACKEND or STORAGE_PROVIDER
    # via AliasChoices, an ambient os-env value for either name — left behind by
    # an earlier test module, on top of whatever's in this machine's .env — can
    # silently outrank the STORAGE_BACKEND kwarg these tests construct Settings()
    # with. Clearing both here (auto-restored by monkeypatch after the test) keeps
    # this file's backend-selection assertions independent of run order and of the
    # developer's local .env.
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("STORAGE_PROVIDER", raising=False)
    get_storage_backend.cache_clear()
    yield
    get_storage_backend.cache_clear()


def _patch_settings(monkeypatch, settings):
    import app.storage as storage_module

    monkeypatch.setattr(storage_module, "get_settings", lambda: settings)


class TestLocalBackendSelection:

    def test_default_settings_select_local_backend(self, monkeypatch, tmp_path):
        settings = Settings(_env_file=None, **_REQUIRED_SETTINGS, STORAGE_ROOT=str(tmp_path / "uploads"))
        _patch_settings(monkeypatch, settings)
        backend = get_storage_backend()
        assert isinstance(backend, LocalFilesystemBackend)

    def test_storage_backend_local_case_insensitive(self, monkeypatch, tmp_path):
        settings = Settings(_env_file=None, **_REQUIRED_SETTINGS, STORAGE_BACKEND="LOCAL", STORAGE_ROOT=str(tmp_path / "uploads"))
        _patch_settings(monkeypatch, settings)
        assert isinstance(get_storage_backend(), LocalFilesystemBackend)


class TestS3BackendSelection:

    def test_storage_provider_s3_selects_fallback_backend_with_s3_primary(self, monkeypatch, tmp_path):
        with mock_aws():
            import boto3

            boto3.client("s3", region_name="eu-north-1").create_bucket(
                Bucket="rforum-uploads-test",
                CreateBucketConfiguration={"LocationConstraint": "eu-north-1"},
            )
            settings = Settings(
                _env_file=None,
                **_REQUIRED_SETTINGS,
                STORAGE_BACKEND="s3",
                STORAGE_ROOT=str(tmp_path / "uploads"),
                S3_BUCKET="rforum-uploads-test",
                S3_REGION="eu-north-1",
                S3_PREFIX="presentations",
            )
            _patch_settings(monkeypatch, settings)

            backend = get_storage_backend()

            assert isinstance(backend, FallbackStorageBackend)
            assert isinstance(backend.primary, S3StorageBackend)
            assert isinstance(backend.secondary, LocalFilesystemBackend)

    def test_env_var_storage_provider_binds_to_storage_backend_field(self, monkeypatch):
        monkeypatch.setenv("STORAGE_PROVIDER", "s3")
        monkeypatch.delenv("STORAGE_BACKEND", raising=False)
        settings = Settings(_env_file=None, **_REQUIRED_SETTINGS)
        assert settings.STORAGE_BACKEND == "s3"


class TestUnknownBackend:

    def test_unknown_backend_raises_not_implemented(self, monkeypatch, tmp_path):
        settings = Settings(_env_file=None, **_REQUIRED_SETTINGS, STORAGE_BACKEND="azure", STORAGE_ROOT=str(tmp_path / "uploads"))
        _patch_settings(monkeypatch, settings)
        with pytest.raises(NotImplementedError):
            get_storage_backend()
