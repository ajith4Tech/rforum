"""
Filesystem-backed StorageBackend.

Key resolution is backward-compatible with the pre-redesign convention of
storing a literal "/uploads/..." disk path in the database: a leading "/"
and a leading "uploads/" segment are stripped before joining with `root`, so
old rows (whose *_url columns hold that old shape) and new rows (which store
a bare key like "presentations/<owner>/<id>/original.pdf") resolve to the
same files through one code path — no data migration needed.
"""
import os
import shutil
from pathlib import Path

from app.storage.base import StorageBackend


class LocalFilesystemBackend(StorageBackend):
    def __init__(self, root: str = "uploads"):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        k = key.lstrip("/")
        if k.startswith("uploads/"):
            k = k[len("uploads/"):]
        candidate = (self.root / k).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError(f"Storage key resolves outside root: {key!r}")
        return candidate

    def save(self, key: str, content: bytes) -> None:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with open(tmp_path, "wb") as handle:
            handle.write(content)
        os.replace(tmp_path, path)

    def read(self, key: str) -> bytes:
        path = self._resolve(key)
        with open(path, "rb") as handle:
            return handle.read()

    def exists(self, key: str) -> bool:
        try:
            return self._resolve(key).is_file()
        except ValueError:
            return False

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    def delete_prefix(self, prefix: str) -> None:
        path = self._resolve(prefix)
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            path.unlink()

    def size(self, key: str) -> int:
        return self._resolve(key).stat().st_size

    def path_for(self, key: str) -> Path:
        """Public escape hatch for the migration script (mirrors
        S3StorageBackend.object_key_for), which needs the literal on-disk
        path to stream-hash a file without loading it fully into memory."""
        return self._resolve(key)

    def list_keys(self, prefix: str) -> list[str]:
        path = self._resolve(prefix)
        if path.is_file():
            return [str(path.relative_to(self.root)).replace(os.sep, "/")]
        if not path.is_dir():
            return []
        return sorted(
            str(p.relative_to(self.root)).replace(os.sep, "/")
            for p in path.rglob("*")
            if p.is_file()
        )
