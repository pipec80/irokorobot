"""Integration tests for the quarantined public face-enrollment endpoint."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import cv2
import numpy as np
import pytest
from server.routers import vision as vision_router
from server.settings import settings

from server import llm, vision

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    import httpx

_FAKE_JPEG = cv2.imencode(".jpg", np.zeros((10, 10, 3), dtype=np.uint8))[1].tobytes()


@pytest.fixture(autouse=True)
def _vision_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enable vision and mock LLM to prove public enrollment remains isolated."""
    monkeypatch.setattr(settings, "vision_enabled", True)
    monkeypatch.setattr(llm, "generate_response", AsyncMock())


def _post_enroll(client: TestClient, image: bytes, name: str) -> httpx.Response:
    """POST one image-contract frame and person name."""
    return client.post(
        "/vision/enroll",
        files={"image": ("frame.jpg", image, "image/jpeg")},
        data={"name": name},
    )


@pytest.mark.integration
def test_enroll_endpoint_is_quarantined_before_service(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid public request cannot reach the biometric enrollment service."""
    enroll = AsyncMock()
    monkeypatch.setattr(vision, "enroll_person", enroll)

    response = _post_enroll(client, _FAKE_JPEG, "felipe")

    assert response.status_code == 503
    assert response.json()["detail"] == vision_router._BIOMETRIC_ENROLLMENT_UNAVAILABLE
    enroll.assert_not_awaited()
    llm.generate_response.assert_not_awaited()  # type: ignore[attr-defined]  # AsyncMock


@pytest.mark.integration
def test_enroll_endpoint_hides_service_rejection(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A public caller cannot observe internal enrollment rule outcomes."""
    enroll = AsyncMock(side_effect=AssertionError("service must not run"))
    monkeypatch.setattr(vision, "enroll_person", enroll)

    response = _post_enroll(client, _FAKE_JPEG, "Felipe")

    assert response.status_code == 503
    assert response.json()["detail"] == vision_router._BIOMETRIC_ENROLLMENT_UNAVAILABLE
    enroll.assert_not_awaited()


@pytest.mark.integration
def test_enroll_service_disabled_returns_503(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disabled vision should retain the enrollment 503 response."""
    monkeypatch.setattr(settings, "vision_enabled", False)

    assert _post_enroll(client, _FAKE_JPEG, "Felipe").status_code == 503


@pytest.mark.integration
def test_enroll_endpoint_quarantines_empty_name_without_disclosure(client: TestClient) -> None:
    """The public denial does not validate or expose an attacker-supplied name."""
    response = _post_enroll(client, _FAKE_JPEG, "   ")

    assert response.status_code == 503
    assert response.json()["detail"] == vision_router._BIOMETRIC_ENROLLMENT_UNAVAILABLE
