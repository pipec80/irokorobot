"""System endpoints — liveness and health checks."""

from fastapi import APIRouter, HTTPException, Request

from server import db, stt, tts
from server.schemas import HealthResponse, ReadyResponse
from server.settings import settings

router = APIRouter(tags=["System"])


@router.get("/health")
async def health() -> HealthResponse:
    """Liveness check — returns ok when the server is up and models are loaded."""
    return HealthResponse(vision_enabled=settings.vision_enabled)


@router.get("/ready")
async def ready(request: Request) -> ReadyResponse:
    """Readiness check — 200 only once the lifespan and every mandatory local
    resource are confirmed, cheaply, with no network or model call (Plan 0040).

    Distinct from `/health`: liveness proves the process answers requests;
    readiness proves it can actually serve one. `MEMORY_ENABLED=false` never
    opens a database connection, so the DB probe only runs when memory is on.
    Vision is always optional and is never part of this check.

    Args:
        request: Raw ASGI request, used only to read `app.state.ready`.

    Returns:
        `ReadyResponse` on success.

    Raises:
        HTTPException: 503 if the lifespan has not completed successfully,
            or a mandatory resource is not currently loaded/open.
    """
    if not getattr(request.app.state, "ready", False):
        raise HTTPException(status_code=503, detail="Lifespan has not completed")
    if not stt.is_loaded():
        raise HTTPException(status_code=503, detail="STT model not loaded")
    if not tts.is_loaded():
        raise HTTPException(status_code=503, detail="TTS voice not loaded")
    if settings.memory_enabled and not db.is_open():
        raise HTTPException(status_code=503, detail="Database not open")
    return ReadyResponse()
