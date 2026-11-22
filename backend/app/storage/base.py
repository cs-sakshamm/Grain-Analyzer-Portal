"""StoragePort: the only filesystem/object-storage surface services may use.

Keys are generated server-side (``scans/<department>/<scan>/<role>/<file>.<ext>``).
Callers never supply a path, and adapters reject traversal defensively.
"""

from __future__ import annotations

from typing import Protocol


class StorageError(Exception):
    """Storage backend failure; mapped to 503 by the API."""


class StoragePort(Protocol):
    backend: str

    def save(self, key: str, data: bytes, *, content_type: str) -> None: ...

    def load(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...

    def exists(self, key: str) -> bool: ...

    def presigned_put(self, key: str, *, content_type: str, expires_in: int) -> str | None:
        """Return a direct-upload URL, or ``None`` when the backend streams through the API."""

    def presigned_get(self, key: str, *, expires_in: int) -> str | None:
        """Return a download URL, or ``None`` when the backend streams through the API."""
