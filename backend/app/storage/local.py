"""Local filesystem adapter for development and tests.

Files live outside any web root; the API is the only reader. Writes are atomic so a
crash cannot leave a half-written attachment that later appears complete.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from app.storage.base import StorageError


class LocalStorage:
    backend = "local"

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise StorageError("invalid storage key")
        return candidate

    def save(self, key: str, data: bytes, *, content_type: str) -> None:
        path = self._path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".upload-")
            with os.fdopen(handle, "wb") as stream:
                stream.write(data)
            os.replace(temp_name, path)
        except OSError as exc:  # pragma: no cover - environment failure
            raise StorageError("could not persist object") from exc

    def load(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except OSError as exc:
            raise StorageError("object unavailable") from exc

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink(missing_ok=True)
        except OSError as exc:  # pragma: no cover - environment failure
            raise StorageError("could not delete object") from exc

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def presigned_put(self, key: str, *, content_type: str, expires_in: int) -> str | None:
        return None

    def presigned_get(self, key: str, *, expires_in: int) -> str | None:
        return None
