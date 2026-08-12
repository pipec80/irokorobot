"""Integration tests for POST /vision/describe (V0) with Ollama mocked."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import cv2
import numpy as np
import pytest
from server.exceptions import VisionError
from server.routers import vision as vision_router
from server.settings import settings

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi.testclient import TestClient
    import httpx

    PostFn = Callable[[TestClient, bytes], httpx.Response]


def _encode(frame: np.ndarray, ext: str = ".jpg") -> bytes:
    """Encode a numpy BGR frame to real, decodable image bytes."""
    ok, buf = cv2.imencode(ext, frame)
    assert ok
    return buf.tobytes()


# A tiny but genuinely decodable JPEG — validation now decodes the frame
# (PROMPT B3), so magic bytes alone are no longer enough for these tests.
_FAKE_JPEG = _encode(np.zeros((10, 10, 3), dtype=np.uint8))

# A JPEG whose magic bytes are valid but the rest of the file is garbage —
# cv2.imdecode must fail to decode it.
_TRUNCATED_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64

# Bytes that do not match any recognized image format's magic bytes.
_UNKNOWN_FORMAT = b"\x00\x01\x02\x03" + b"garbage" * 8


@pytest.fixture
def vision_on(monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[misc]
    """Enable the vision kill-switch for one test."""
    monkeypatch.setattr(settings, "vision_enabled", True)


def _post_image(client: TestClient, payload: bytes) -> httpx.Response:
    """POST *payload* as an image upload to /vision/describe."""
    return client.post(
        "/vision/describe",
        files={"image": ("frame.jpg", payload, "image/jpeg")},
    )


def _post_enroll(client: TestClient, payload: bytes) -> httpx.Response:
    """POST *payload* as an image upload to /vision/enroll."""
    return client.post(
        "/vision/enroll",
        files={"image": ("frame.jpg", payload, "image/jpeg")},
        data={"name": "Felipe"},
    )


@pytest.mark.integration
def test_enroll_is_quarantined_without_calling_enrollment(
    client: TestClient, vision_on: None
) -> None:
    """Public enrollment must fail safely before it touches biometric storage."""
    with patch(
        "server.routers.vision.vision.enroll_person",
        new_callable=AsyncMock,
    ) as enroll:
        response = _post_enroll(client, _FAKE_JPEG)

    assert response.status_code == 503
    assert response.json()["detail"] == vision_router._BIOMETRIC_ENROLLMENT_UNAVAILABLE
    enroll.assert_not_awaited()


def _post_respond(client: TestClient, payload: bytes) -> httpx.Response:
    """POST *payload* as an image upload to /vision/respond."""
    return client.post(
        "/vision/respond",
        files={"image": ("frame.jpg", payload, "image/jpeg")},
        data={"text": "¿qué ves?"},
    )


# These endpoints read the upload before serving their normal response. Public
# enrollment is deliberately excluded because it is quarantined before any
# image read or biometric write.
_IMAGE_VALIDATING_VISION_POSTS = (_post_image, _post_respond)


@pytest.mark.integration
def test_describe_disabled_returns_503(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """With VISION_ENABLED=false the endpoint answers 503 without touching
    the VLM. Set explicitly — settings also reads the developer's .env."""
    monkeypatch.setattr(settings, "vision_enabled", False)

    resp = _post_image(client, _FAKE_JPEG)

    assert resp.status_code == 503
    assert "disabled" in resp.json()["detail"]


@pytest.mark.integration
def test_describe_happy_path(client: TestClient, vision_on: None) -> None:
    """A JPEG frame returns the VLM description and its duration."""
    with patch(
        "server.vision.describe_image",
        new_callable=AsyncMock,
        return_value=("Veo una naranja sobre la mesa.", 1234),
    ):
        resp = _post_image(client, _FAKE_JPEG)

    assert resp.status_code == 200
    data = resp.json()
    assert data["description"] == "Veo una naranja sobre la mesa."
    assert data["duration_ms"] == 1234


@pytest.mark.integration
def test_describe_vlm_down_returns_503(client: TestClient, vision_on: None) -> None:
    """A dead VLM backend degrades to 503 — the server never crashes."""
    with patch(
        "server.vision.describe_image",
        new_callable=AsyncMock,
        side_effect=VisionError("connection refused"),
    ):
        resp = _post_image(client, _FAKE_JPEG)

    assert resp.status_code == 503
    assert "unavailable" in resp.json()["detail"]


@pytest.mark.integration
def test_describe_empty_image_returns_422(client: TestClient, vision_on: None) -> None:
    """An empty upload violates the contract."""
    resp = _post_image(client, b"")

    assert resp.status_code == 422


@pytest.mark.integration
def test_describe_unknown_format_returns_422(client: TestClient, vision_on: None) -> None:
    """Bytes matching no known magic byte (HEIC, garbage) violate the contract."""
    resp = _post_image(client, _UNKNOWN_FORMAT)

    assert resp.status_code == 422
    assert "format" in resp.json()["detail"].lower()


@pytest.mark.integration
@pytest.mark.parametrize("post", _IMAGE_VALIDATING_VISION_POSTS)
def test_truncated_image_returns_422_on_image_processing_endpoints(
    client: TestClient, vision_on: None, post: PostFn
) -> None:
    """Valid magic bytes but undecodable content returns 422 before processing."""
    resp = post(client, _TRUNCATED_JPEG)

    assert resp.status_code == 422
    assert "decode" in resp.json()["detail"].lower()


@pytest.mark.integration
def test_image_1281x720_returns_422(client: TestClient, vision_on: None) -> None:
    """One pixel over the width limit violates the contract."""
    oversized = _encode(np.zeros((720, 1281, 3), dtype=np.uint8))

    resp = _post_image(client, oversized)

    assert resp.status_code == 422
    assert "1280x720" in resp.json()["detail"]


@pytest.mark.integration
def test_image_1280x721_returns_422(client: TestClient, vision_on: None) -> None:
    """One pixel over the height limit violates the contract."""
    oversized = _encode(np.zeros((721, 1280, 3), dtype=np.uint8))

    resp = _post_image(client, oversized)

    assert resp.status_code == 422
    assert "1280x720" in resp.json()["detail"]


@pytest.mark.integration
def test_image_exactly_1280x720_passes_validation(client: TestClient, vision_on: None) -> None:
    """Exactly the contract's max dimensions is accepted, not rejected."""
    exact = _encode(np.zeros((720, 1280, 3), dtype=np.uint8))

    with patch(
        "server.vision.describe_image",
        new_callable=AsyncMock,
        return_value=("Veo una habitación vacía.", 42),
    ):
        resp = _post_image(client, exact)

    assert resp.status_code == 200


@pytest.mark.integration
def test_real_png_passes_format_and_decode_validation(client: TestClient, vision_on: None) -> None:
    """A genuine PNG (not just JPEG) is accepted by the widened contract."""
    png_bytes = _encode(np.zeros((10, 10, 3), dtype=np.uint8), ext=".png")

    with patch(
        "server.vision.describe_image",
        new_callable=AsyncMock,
        return_value=("Veo una habitación vacía.", 42),
    ):
        resp = _post_image(client, png_bytes)

    assert resp.status_code == 200
