"""Device scan ingestion endpoints (contract §3.2–3.6)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.deps import CurrentDevice, get_app_settings, get_current_device, request_id
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.ratelimit import scan_limiter
from app.db.session import get_db
from app.schemas.scan import (
    AttachmentPrepare,
    AttachmentTarget,
    DevicePayload,
    FinalizeResult,
    ScanAccepted,
    ScanStatus,
    UploadResult,
)
from app.services import scan_service
from app.services.scan_service import DeviceContext
from app.storage import StoragePort, get_storage

router = APIRouter(prefix="/device", tags=["device"])


def _ctx(request: Request, device: CurrentDevice) -> DeviceContext:
    return DeviceContext(
        device_id=device.device.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        request_id=request_id(request),
    )


@router.post(
    "/scans",
    response_model=ScanAccepted,
    status_code=status.HTTP_201_CREATED,
)
async def submit_scan(
    request: Request,
    response: Response,
    device: CurrentDevice = Depends(get_current_device),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> ScanAccepted:
    allowed, retry_after = scan_limiter.check(
        f"scan:{device.device.id}", limit=30, window_seconds=60
    )
    if not allowed:
        raise AppError(
            429,
            ErrorCode.RATE_LIMITED,
            "Too many scan submissions.",
            headers={"Retry-After": str(retry_after)},
        )

    body = await request.body()
    if len(body) > settings.max_scan_payload_bytes:
        raise AppError(413, ErrorCode.FILE_TOO_LARGE, "The payload exceeds the configured limit.")
    try:
        raw: dict[str, Any] = json.loads(body)
    except json.JSONDecodeError as exc:
        raise AppError(
            400, ErrorCode.VALIDATION_ERROR, "The request body is not valid JSON."
        ) from exc
    if not isinstance(raw, dict):
        raise AppError(422, ErrorCode.VALIDATION_ERROR, "The payload must be a JSON object.")
    try:
        payload = DevicePayload.model_validate(raw)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc

    result = scan_service.submit_scan(
        db, settings, device.device, payload, raw, _ctx(request, device)
    )
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return result


@router.post(
    "/scans/{scan_id}/attachments/prepare",
    response_model=AttachmentTarget,
)
def prepare_attachment(
    scan_id: uuid.UUID,
    payload: AttachmentPrepare,
    request: Request,
    device: CurrentDevice = Depends(get_current_device),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
    storage: StoragePort = Depends(get_storage),
) -> AttachmentTarget:
    record, url, expires_at = scan_service.prepare_attachment(
        db,
        settings,
        storage,
        device.device,
        scan_id,
        role=payload.role,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
        sha256=payload.sha256,
        filename=payload.filename,
        ctx=_ctx(request, device),
    )
    return AttachmentTarget(
        upload_id=record.id,
        method="PUT",
        url=url,
        headers={"Content-Type": record.mime_type},
        expires_at=expires_at,
    )


@router.put(
    "/scans/{scan_id}/files/{upload_id}",
    response_model=UploadResult,
    status_code=status.HTTP_201_CREATED,
)
async def upload_file(
    scan_id: uuid.UUID,
    upload_id: uuid.UUID,
    request: Request,
    device: CurrentDevice = Depends(get_current_device),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
    storage: StoragePort = Depends(get_storage),
) -> UploadResult:
    body = await request.body()
    content_type = request.headers.get("content-type", "")
    return scan_service.store_upload(
        db,
        settings,
        storage,
        device.device,
        scan_id,
        upload_id,
        body=body,
        content_type=content_type,
        ctx=_ctx(request, device),
    )


@router.post("/scans/{scan_id}/finalize", response_model=FinalizeResult)
def finalize_scan(
    scan_id: uuid.UUID,
    request: Request,
    device: CurrentDevice = Depends(get_current_device),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> FinalizeResult:
    return scan_service.finalize_scan(db, settings, device.device, scan_id, _ctx(request, device))


@router.get("/scans/{scan_id}/status", response_model=ScanStatus)
def scan_status(
    scan_id: uuid.UUID,
    device: CurrentDevice = Depends(get_current_device),
    db: Session = Depends(get_db),
) -> ScanStatus:
    scan = scan_service.get_owned_scan(db, scan_id, device.device)
    attachments = [
        {"role": record.role.value, "upload_status": record.upload_status.value}
        for record in scan.files
    ]
    return ScanStatus(
        scan_id=scan.id,
        client_scan_id=scan.client_scan_id,
        processing_status=scan.processing_status,
        quality_verdict=scan.quality_verdict,
        failure_code=scan.failure_code,
        failure_detail=scan.failure_detail,
        received_at=scan.received_at,
        finalized_at=scan.finalized_at,
        attachments=attachments,
    )
