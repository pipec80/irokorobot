"""System endpoints — liveness and health checks."""

from fastapi import APIRouter

from server.schemas import HealthResponse
from server.settings import settings

router = APIRouter(tags=["System"])


@router.get("/health")
async def health() -> HealthResponse:
    """Liveness check — returns ok when the server is up and models are loaded."""
    return HealthResponse(vision_enabled=settings.vision_enabled)
