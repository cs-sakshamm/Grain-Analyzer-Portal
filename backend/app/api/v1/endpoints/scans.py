"""Portal read endpoints: latest completed scan, detail and report access."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import (
    CurrentUser,
    get_app_settings,
    request_id,
    require_portal_user,
)
from app.core.config import Settings
from app.db.session import get_db
from app.models.analysis import AgeResult, Measurement, QualityEvaluation, Scan
from app.models.enums import (
    MeasurementBasis,
    QualityVerdict,
    ScanProcessingStatus,
)
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


@router.get("/history", response_model=list[dict])
def scan_history(
    department_id: uuid.UUID | None = Query(default=None),
    batch_code: str | None = Query(default=None),
    device_id: uuid.UUID | None = Query(default=None),
    processing_status: str | None = Query(default=None),
    quality_verdict: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=200),
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
) -> dict:
    resolved = resolve_department_id(
        db,
        user=principal.user,
        memberships=principal.memberships,
        requested_department_id=department_id,
    )
    query = select(Scan).where(Scan.department_id == resolved)

    if batch_code:
        query = query.where(Scan.batch_code.ilike(f"%{batch_code}%"))
    if device_id:
        query = query.where(Scan.device_id == device_id)
    if processing_status:
        query = query.where(Scan.processing_status == processing_status)
    if quality_verdict:
        query = query.where(Scan.quality_verdict == quality_verdict)
    if start_date:
        query = query.where(Scan.analyzed_at >= start_date)
    if end_date:
        query = query.where(Scan.analyzed_at <= end_date)

    total = db.scalar(select(func.count()).select_from(query.subquery()))
    scans = db.scalars(
        query.order_by(Scan.analyzed_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).all()

    result = []
    for scan in scans:
        device = db.get(Device, scan.device_id)
        department = db.get(Department, scan.department_id)
        measurements = db.scalars(
            select(Measurement).where(Measurement.scan_id == scan.id)
        ).all()
        age = db.scalar(select(AgeResult).where(AgeResult.scan_id == scan.id))
        result.append(
            {
                "id": str(scan.id),
                "sample_id": scan.sample_id,
                "batch_code": scan.batch_code,
                "lot_code": scan.lot_code,
                "variety": scan.variety,
                "analyzed_at": scan.analyzed_at.isoformat(),
                "received_at": scan.received_at.isoformat(),
                "processing_status": scan.processing_status.value,
                "quality_verdict": scan.quality_verdict.value if scan.quality_verdict else None,
                "device_id": str(scan.device_id) if device else None,
                "device_uid": device.device_uid if device else None,
                "friendly_name": device.friendly_name if device else None,
                "department_code": department.code if department else None,
                "department_name": department.name if department else None,
                "client_scan_id": scan.client_scan_id,
                "measurements": [
                    {
                        "metric_code": m.metric_code,
                        "value": str(m.value),
                        "unit": m.unit,
                        "basis": m.basis.value,
                        "is_estimated": m.is_estimated,
                    }
                    for m in measurements
                ],
                "age": (
                    {
                        "age_value_months": str(age.age_value_months)
                        if age and age.age_value_months is not None
                        else None,
                        "age_category": age.age_category if age else None,
                        "proportion_percent": str(age.proportion_percent)
                        if age and age.proportion_percent is not None
                        else None,
                        "unit": age.unit if age else None,
                    }
                    if age is not None
                    else None
                ),
            }
        )
    return {
        "items": result,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }

@router.get("/analytics/quality", response_model=dict)
def quality_analytics(
    department_id: uuid.UUID | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
) -> dict:
    resolved = resolve_department_id(
        db,
        user=principal.user,
        memberships=principal.memberships,
        requested_department_id=department_id,
    )
    scan_query = select(Scan).where(Scan.department_id == resolved)
    if start_date:
        scan_query = scan_query.where(Scan.analyzed_at >= start_date)
    if end_date:
        scan_query = scan_query.where(Scan.analyzed_at <= end_date)

    scans = db.scalars(scan_query.order_by(Scan.analyzed_at.desc())).all()

    total_scans = len(scans)
    if total_scans == 0:
        return {
            "total_scans": 0,
            "quality_distribution": {},
            "status_distribution": {},
            "parameter_summary": {},
        }

    quality_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    param_values: dict[str, dict[str, Any]] = {}

    for scan in scans:
        qv = scan.quality_verdict
        if qv:
            quality_counts[qv.value] = quality_counts.get(qv.value, 0) + 1
        ss = scan.processing_status
        if ss:
            status_counts[ss.value] = status_counts.get(ss.value, 0) + 1

        # Aggregate measurements across scans
        meas = db.scalars(
            select(Measurement).where(Measurement.scan_id == scan.id)
        ).all()
        for m in meas:
            code = m.metric_code
            if code not in param_values:
                param_values[code] = {}
            basis_key = f"{m.basis.value}_{m.unit}"
            if basis_key not in param_values[code]:
                param_values[code][basis_key] = {"count": 0, "values": []}
            param_values[code][basis_key]["count"] += 1
            param_values[code][basis_key]["values"].append(float(m.value))

    # Convert values lists to statistics
    for code in param_values:
        for basis in param_values[code]:
            vals = param_values[code][basis]["values"]
            if vals:
                param_values[code][basis]["min"] = min(vals)
                param_values[code][basis]["max"] = max(vals)
                param_values[code][basis]["avg"] = sum(vals) / len(vals)
            del param_values[code][basis]["values"]

    return {
        "total_scans": total_scans,
        "quality_distribution": quality_counts,
        "status_distribution": status_counts,
        "parameter_summary": param_values,
    }


@router.get("/analytics/rice-age", response_model=dict)
def rice_age_analytics(
    department_id: uuid.UUID | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
) -> dict:
    resolved = resolve_department_id(
        db,
        user=principal.user,
        memberships=principal.memberships,
        requested_department_id=department_id,
    )
    scan_query = select(Scan).where(Scan.department_id == resolved)
    if start_date:
        scan_query = scan_query.where(Scan.analyzed_at >= start_date)
    if end_date:
        scan_query = scan_query.where(Scan.analyzed_at <= end_date)

    scans = db.scalars(scan_query.order_by(Scan.analyzed_at.desc())).all()

    results: list[dict] = []
    for scan in scans:
        age = db.scalar(select(AgeResult).where(AgeResult.scan_id == scan.id))
        if age is not None:
            results.append(
                {
                    "scan_id": str(scan.id),
                    "sample_id": scan.sample_id,
                    "batch_code": scan.batch_code,
                    "lot_code": scan.lot_code,
                    "age_value_months": str(age.age_value_months)
                    if age.age_value_months is not None
                    else None,
                    "age_min_months": str(age.age_min_months)
                    if age.age_min_months is not None
                    else None,
                    "age_max_months": str(age.age_max_months)
                    if age.age_max_months is not None
                    else None,
                    "age_category": age.age_category,
                    "proportion_percent": str(age.proportion_percent)
                    if age.proportion_percent is not None
                    else None,
                    "unit": age.unit,
                    "method": age.method,
                    "model_version": age.model_version,
                    "validation_status": age.validation_status.value
                    if age.validation_status
                    else None,
                }
            )

    return {
        "total_scans_with_age": len(results),
        "age_results": results,
    }


@router.get("/analytics/reports", response_model=list[dict])
def report_listing(
    department_id: uuid.UUID | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
) -> dict:
    resolved = resolve_department_id(
        db,
        user=principal.user,
        memberships=principal.memberships,
        requested_department_id=department_id,
    )
    query = select(Scan).where(Scan.department_id == resolved)
    if start_date:
        query = query.where(Scan.analyzed_at >= start_date)
    if end_date:
        query = query.where(Scan.analyzed_at <= end_date)

    scans = db.scalars(query.order_by(Scan.analyzed_at.desc())).all()

    records = []
    for scan in scans:
        report = db.scalar(
            select(ScanFile).where(
                ScanFile.scan_id == scan.id,
                ScanFile.role == "report_pdf",
                ScanFile.upload_status == "verified",
            )
        )
        age = db.scalar(select(AgeResult).where(AgeResult.scan_id == scan.id))
        device = db.get(Device, scan.device_id)
        records.append(
            {
                "scan_id": str(scan.id),
                "sample_id": scan.sample_id,
                "batch_code": scan.batch_code,
                "lot_code": scan.lot_code,
                "analyzed_at": scan.analyzed_at.isoformat(),
                "has_report": report is not None,
                "report_filename": report.original_filename if report else None,
                "age_available": age is not None,
                "quality_verdict": scan.quality_verdict.value
                if scan.quality_verdict
                else None,
                "processing_status": scan.processing_status.value,
                "device_uid": device.device_uid if device else None,
            }
        )
    return {"items": records}


@router.get("/analytics/batch-comparison", response_model=dict)
def batch_comparison(
    department_id: uuid.UUID | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
) -> dict:
    resolved = resolve_department_id(
        db,
        user=principal.user,
        memberships=principal.memberships,
        requested_department_id=department_id,
    )
    scan_query = select(Scan).where(Scan.department_id == resolved)
    if start_date:
        scan_query = scan_query.where(Scan.analyzed_at >= start_date)
    if end_date:
        scan_query = scan_query.where(Scan.analyzed_at <= end_date)

    scans = db.scalars(scan_query.order_by(Scan.analyzed_at.desc())).all()

    # Group scans by batch_code
    batches: dict[str, list[dict]] = {}
    for scan in scans:
        bc = scan.batch_code
        if not bc:
            bc = "unbatched"
        if bc not in batches:
            batches[bc] = []

        measurements = db.scalars(
            select(Measurement).where(Measurement.scan_id == scan.id)
        ).all()
        meas_dict: dict[str, dict[str, Any]] = {}
        for m in measurements:
            basis = m.basis.value
            # Do not compare incompatible measurement bases
            if basis == "count_percent":
                key = "count_percent"
            elif basis == "estimated_mass_percent":
                key = "estimated_mass_percent"
            else:
                key = basis
            if key not in meas_dict:
                meas_dict[key] = []
            meas_dict[key].append(
                {
                    "scan_id": str(scan.id),
                    "sample_id": scan.sample_id,
                    "metric_code": m.metric_code,
                    "value": str(m.value),
                    "unit": m.unit,
                }
            )

        batches[bc].append(
            {
                "scan_id": str(scan.id),
                "sample_id": scan.sample_id,
                "measurements": meas_dict,
            }
        )

    return {"batches": batches}


@router.get("/notifications", response_model=list[dict])
def notification_listing(
    department_id: uuid.UUID | None = Query(default=None),
    unread_only: bool = Query(default=False),
    principal: CurrentUser = Depends(require_portal_user),
    db: Session = Depends(get_db),
) -> dict:
    resolved = resolve_department_id(
        db,
        user=principal.user,
        memberships=principal.memberships,
        requested_department_id=department_id,
    )
    query = select(Notification).where(Notification.department_id == resolved)
    if unread_only:
        query = query.where(Notification.read_at.is_(None))

    notifications = db.scalars(
        query.order_by(Notification.created_at.desc())
    ).all()

    result = []
    for notif in notifications:
        result.append(
            {
                "id": str(notif.id),
                "event_type": notif.event_type,
                "severity": notif.severity,
                "title": notif.title,
                "body": notif.body,
                "created_at": notif.created_at.isoformat(),
                "scan_id": str(notif.scan_id) if notif.scan_id else None,
            }
        )
    return {"items": result}

