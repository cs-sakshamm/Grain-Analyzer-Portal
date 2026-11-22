"""Shared API error envelope and domain exceptions.

Every error response uses the shape documented in ``docs/api/API_CONTRACT.md``::

    {"error": {"code": ..., "message": ..., "details": ..., "request_id": ...}}

Messages are safe for end users. Internal detail is logged, never returned.
"""

from __future__ import annotations

from typing import Any


class ErrorCode:
    """Stable machine-readable error codes shared with the frontend."""

    VALIDATION_ERROR = "validation_error"
    NOT_FOUND = "not_found"
    FORBIDDEN = "forbidden"
    UNAUTHORIZED = "unauthorized"
    CONFLICT = "conflict"
    RATE_LIMITED = "rate_limited"
    INVALID_CREDENTIALS = "invalid_credentials"
    SCAN_CONFLICT = "scan_conflict"
    MISSING_ATTACHMENTS = "missing_attachments"
    FILE_TOO_LARGE = "file_too_large"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    DEPARTMENT_REQUIRED = "department_required"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    INTERNAL_ERROR = "internal_error"


def error_body(
    *,
    code: str,
    message: str,
    request_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the single allowed error envelope."""

    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": request_id,
        }
    }


class AppError(Exception):
    """Domain error carrying the HTTP status and public error code."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        self.headers = headers


def conflict(code: str, message: str, **details: Any) -> AppError:
    return AppError(status_code=409, code=code, message=message, details=details)


def not_found(message: str = "The requested resource was not found.") -> AppError:
    return AppError(status_code=404, code=ErrorCode.NOT_FOUND, message=message)


def forbidden(message: str = "You do not have access to this resource.") -> AppError:
    return AppError(status_code=403, code=ErrorCode.FORBIDDEN, message=message)
