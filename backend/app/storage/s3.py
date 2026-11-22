"""Private S3-compatible object storage adapter.

boto3 is imported lazily so installations that use local storage do not need it at
import time. Objects are never public: downloads use short-lived presigned URLs issued
only after the API has authorized the caller.
"""

from __future__ import annotations

from typing import Any

from app.storage.base import StorageError


class S3Storage:
    backend = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        region: str | None,
        endpoint_url: str | None = None,
    ) -> None:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - misconfiguration
            raise StorageError("boto3 is required for S3 storage") from exc

        if not bucket:
            raise StorageError("storage_s3_bucket is required for S3 storage")
        self.bucket = bucket
        self._client: Any = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url,
            config=Config(signature_version="s3v4"),
        )

    def save(self, key: str, data: bytes, *, content_type: str) -> None:
        try:
            self._client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                ServerSideEncryption="AES256",
            )
        except Exception as exc:  # pragma: no cover - provider failure
            raise StorageError("could not persist object") from exc

    def load(self, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()
        except Exception as exc:  # pragma: no cover - provider failure
            raise StorageError("object unavailable") from exc

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self.bucket, Key=key)
        except Exception as exc:  # pragma: no cover - provider failure
            raise StorageError("could not delete object") from exc

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:  # pragma: no cover - provider failure
            return False

    def presigned_put(self, key: str, *, content_type: str, expires_in: int) -> str | None:
        try:
            return self._client.generate_presigned_url(
                "put_object",
                Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
                ExpiresIn=expires_in,
            )
        except Exception as exc:  # pragma: no cover - provider failure
            raise StorageError("could not create upload target") from exc

    def presigned_get(self, key: str, *, expires_in: int) -> str | None:
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires_in,
            )
        except Exception as exc:  # pragma: no cover - provider failure
            raise StorageError("could not create download target") from exc
