"""Integration test for GET /health.

Does not enter the FastAPI lifespan context, so Whisper and Piper models are
NOT loaded. This keeps the test fast and independent of the homelab filesystem.
"""

from fastapi.testclient import TestClient
import pytest
from server.settings import settings


@pytest.mark.integration
def test_health_returns_ok(client: TestClient) -> None:
    """Status is always "ok"; vision_enabled is forced False here — the
    local real .env may enable vision, so pin it for a deterministic
    default-shape assertion (see test_health_reports_vision_enabled_from_settings
    for the True case)."""
    original = settings.vision_enabled
    settings.vision_enabled = False  # type: ignore[misc]  # runtime override
    try:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "vision_enabled": False}
    finally:
        settings.vision_enabled = original  # type: ignore[misc]  # restore


@pytest.mark.integration
def test_health_content_type_is_json(client: TestClient) -> None:
    response = client.get("/health")
    assert response.headers["content-type"].startswith("application/json")


@pytest.mark.integration
def test_health_reports_vision_enabled_from_settings(client: TestClient) -> None:
    """The robot's F-08 startup guard reads this field — it must reflect settings live."""
    original = settings.vision_enabled
    settings.vision_enabled = True  # type: ignore[misc]  # runtime override
    try:
        response = client.get("/health")
        assert response.json()["vision_enabled"] is True
    finally:
        settings.vision_enabled = original  # type: ignore[misc]  # restore
