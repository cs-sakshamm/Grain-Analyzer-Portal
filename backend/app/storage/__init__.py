"""Storage adapter selection."""

from __future__ import annotations

from fastapi import Request

from app.core.config import Settings
from app.storage.base import StorageError, StoragePort
from app.storage.local import LocalStorage
from app.storage.s3 import S3Storage


def build_storage(settings: Settings) -> StoragePort:
    if settings.storage_backend == "s3":
        return S3Storage(
            bucket=settings.storage_s3_bucket or "",
            region=settings.storage_s3_region,
            endpoint_url=settings.storage_s3_endpoint_url,
        )
    return LocalStorage(settings.storage_local_root)


def get_storage(request: Request) -> StoragePort:
    """FastAPI dependency resolved lazily from application state (overridable in tests)."""

    storage = getattr(request.app.state, "storage", None)
    if storage is None:
        storage = build_storage(request.app.state.settings)
        request.app.state.storage = storage
    return storage


__all__ = ["StorageError", "StoragePort", "build_storage", "get_storage"]
