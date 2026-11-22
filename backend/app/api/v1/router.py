"""Aggregate router for API v1.

Only health endpoints exist in Phase 1. Device, portal and admin routers are added as
their contracts are implemented; see ``docs/api/API_CONTRACT.md``.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import admin, auth, device_auth, device_scans, health, scans

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(admin.router)
api_router.include_router(device_auth.router)
api_router.include_router(device_scans.router)
api_router.include_router(scans.router)
