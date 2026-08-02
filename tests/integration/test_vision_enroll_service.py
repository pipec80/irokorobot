"""Integration tests for the transparent face-enrollment endpoint."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import cv2
import numpy as np
import pytest
from server.exceptions import EnrollmentRejectedError
from server.settings import settings
from server.vision import EnrollOutcome

from server import llm, vision

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    import httpx

_FAKE_JPEG = cv2.imencode(".jpg", np.zeros((10, 10, 3), dtype=np.uint8))[1].tobytes()


@pytest.fixture(autouse=True)
def _vision_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enable vision and mock LLM to prove enrollment stays transparent."""
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
def test_enroll_service_happy_path(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A good frame should return identifiers without LLM or TTS."""
    monkeypatch.setattr(
        vision,
        "enroll_person",
        AsyncMock(return_value=EnrollOutcome(name="Felipe", entity_id=7, profile_id=3)),
    )

    response = _post_enroll(client, _FAKE_JPEG, "felipe")

    assert response.status_code == 200
    assert response.json() == {"name": "Felipe", "entity_id": 7, "profile_id": 3}
    llm.generate_response.assert_not_awaited()  # type: ignore[attr-defined]  # AsyncMock


@pytest.mark.integration
def test_enroll_service_rejection_maps_to_422(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Business-rule rejections should retain their machine-readable code."""
    monkeypatch.setattr(
        vision,
        "enroll_person",
        AsyncMock(side_effect=EnrollmentRejectedError("multiple_faces", "Found 3 faces")),
    )

    response = _post_enroll(client, _FAKE_JPEG, "Felipe")

    assert response.status_code == 422
    assert "multiple_faces" in response.json()["detail"]


@pytest.mark.integration
def test_enroll_service_disabled_returns_503(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disabled vision should retain the enrollment 503 response."""
    monkeypatch.setattr(settings, "vision_enabled", False)

    assert _post_enroll(client, _FAKE_JPEG, "Felipe").status_code == 503


@pytest.mark.integration
def test_enroll_service_empty_name_returns_422(client: TestClient) -> None:
    """Whitespace-only names should retain the 422 validation response."""
    assert _post_enroll(client, _FAKE_JPEG, "   ").status_code == 422
