"""Portal read endpoints: latest completed scan, detail and report access."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import (
    CurrentUser,
    get_app_settings,
    request_id,
    require_portal_user,
)
from app.core.config import Settings
from app.db.session import get_db
from app.services import portal_service
from app.services.authorization import resolve_department_id
from app.services.portal_service import ADVISORY
from app.storage import StoragePort, get_storage

router = APIRouter(prefix="/scans", tags=["scans"])


def _has_membership(principal: CurrentUser, department_id: uuid.UUID) -> bool:
    return any(context.department.id == department_id for context in principal.memberships)


@router.get("/latest", response_model=None)
def latest_scan(
    response: Response,
    department_id: uuid.UUID | None = Query(default=None),
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
) -> dict | None:
    resolved = resolve_department_id(
        db,
        user=principal.user,
        memberships=principal.memberships,
        requested_department_id=department_id,
    )
    scan = portal_service.latest_completed_scan(db, resolved)
    if scan is None:
        response.status_code = status.HTTP_204_NO_CONTENT
        return None
    return portal_service.scan_detail(db, scan)


@router.get("/{scan_id}", response_model=None)
def scan_detail(
    scan_id: uuid.UUID,
    request: Request,
    department_id: uuid.UUID | None = Query(default=None),
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
) -> dict:
    resolved = resolve_department_id(
        db,
        user=principal.user,
        memberships=principal.memberships,
        requested_department_id=department_id,
    )
    scan = portal_service.get_scan_for_department(db, scan_id, resolved)
    portal_service.audit_cross_department_read(
        db,
        user=principal.user,
        scan=scan,
        has_membership=_has_membership(principal, scan.department_id),
        action="scan.cross_department_read",
        request_id=request_id(request),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return portal_service.scan_detail(db, scan)


@router.get("/{scan_id}/report", response_model=None)
def report_metadata(
    scan_id: uuid.UUID,
    request: Request,
    department_id: uuid.UUID | None = Query(default=None),
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> dict:
    resolved = resolve_department_id(
        db,
        user=principal.user,
        memberships=principal.memberships,
        requested_department_id=department_id,
    )
    scan = portal_service.get_scan_for_department(db, scan_id, resolved)
    record = portal_service.report_file(db, scan)
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.storage_signed_url_ttl_seconds)
    portal_service.audit_cross_department_read(
        db,
        user=principal.user,
        scan=scan,
        has_membership=_has_membership(principal, scan.department_id),
        action="report.download_issued",
        request_id=request_id(request),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return {
        "url": f"{settings.api_v1_prefix}/scans/{scan.id}/report/download",
        "expires_at": expires_at.isoformat(),
        "filename": record.original_filename,
        "size_bytes": record.size_bytes,
        "sha256": record.sha256,
        "advisory": ADVISORY,
    }


@router.get("/{scan_id}/report/download", response_model=None)
def download_report(
    scan_id: uuid.UUID,
    request: Request,
    department_id: uuid.UUID | None = Query(default=None),
    disposition: str = Query(default="attachment", pattern="^(attachment|inline)$"),
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
    storage: StoragePort = Depends(get_storage),
) -> Response:
    resolved = resolve_department_id(
        db,
        user=principal.user,
        memberships=principal.memberships,
        requested_department_id=department_id,
    )
    scan = portal_service.get_scan_for_department(db, scan_id, resolved)
    record = portal_service.report_file(db, scan)
    payload = portal_service.read_report_bytes(storage, record)
    portal_service.audit_cross_department_read(
        db,
        user=principal.user,
        scan=scan,
        has_membership=_has_membership(principal, scan.department_id),
        action="report.downloaded",
        request_id=request_id(request),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return Response(
        content=payload,
        media_type=record.mime_type,
        headers={
            "Content-Disposition": (
                f"{disposition}; filename*=UTF-8''{quote(record.original_filename)}"
            ),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )
