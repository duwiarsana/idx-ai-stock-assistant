"""Health check endpoint."""

import logging
from fastapi import APIRouter

from app.services.cache_service import cache_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
async def health_check():
    """Application health check."""
    redis_ok = False
    try:
        redis_ok = await cache_service.check_health()
    except Exception:
        pass

    return {
        "status": "healthy",
        "service": "IDX AI Stock Assistant",
        "version": "1.0.0",
        "components": {
            "redis": "connected" if redis_ok else "disconnected",
        },
    }
