"""Health check routes."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Basic health check endpoint."""
    return {"status": "ok", "service": "aegis"}


@router.get("/health/ready")
async def readiness_check() -> dict[str, str]:
    """Readiness check — verifies database is connected."""
    # TODO: actually check DB connectivity
    return {"status": "ready"}
