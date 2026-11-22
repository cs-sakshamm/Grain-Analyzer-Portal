"""Audit trail writer.

Rows are inserted, never updated or deleted. Callers own the transaction: a mutation
and its audit row must commit together.
"""

from __future__ import annotations

import ipaddress
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.enums import AuditActorType


def normalise_ip(value: str | None) -> str | None:
    """Return a valid IP literal or ``None`` (TestClient uses a non-IP host string)."""

    if not value:
        return None
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def record_audit(
    db: Session,
    *,
    action: str,
    actor_type: AuditActorType,
    actor_user_id: uuid.UUID | None = None,
    actor_device_id: uuid.UUID | None = None,
    department_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        action=action,
        actor_type=actor_type,
        actor_user_id=actor_user_id,
        actor_device_id=actor_device_id,
        department_id=department_id,
        target_type=target_type,
        target_id=target_id,
        ip_address=normalise_ip(ip_address),
        user_agent=(user_agent or "")[:1000] or None,
        request_id=request_id,
        meta=metadata or {},
    )
    db.add(entry)
    return entry
