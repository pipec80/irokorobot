"""Unit tests for the webcam capture module (image contract V0)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from robot.camera_capture import capture_frame, encode_jpeg, fit_to_contract
from robot.exceptions import CameraError

_JPEG_MAGIC = b"\xff\xd8"


def _frame(width: int, height: int) -> np.ndarray:
    """Return a gray BGR frame of the given size."""
    return np.full((height, width, 3), 128, dtype=np.uint8)


@pytest.mark.unit
def test_fit_to_contract_downscales_full_hd() -> None:
    """A 1920x1080 frame must shrink to fit 1280x720 keeping aspect ratio."""
    fitted = fit_to_contract(_frame(1920, 1080))

    height, width = fitted.shape[:2]
    assert width <= 1280
    assert height <= 720
    assert width / height == pytest.approx(1920 / 1080, rel=0.01)


@pytest.mark.unit
def test_fit_to_contract_never_upscales() -> None:
    """A frame already within the contract must be returned unchanged."""
    frame = _frame(640, 480)

    fitted = fit_to_contract(frame)

    assert fitted.shape == frame.shape


@pytest.mark.unit
def test_fit_to_contract_portrait_frame() -> None:
    """A tall frame is bounded by the height limit (720)."""
    fitted = fit_to_contract(_frame(1080, 1920))

    height, width = fitted.shape[:2]
    assert height <= 720
    assert width <= 1280


@pytest.mark.unit
def test_encode_jpeg_produces_jpeg_bytes() -> None:
    """Encoding must produce non-empty bytes with the JPEG magic marker."""
    jpeg = encode_jpeg(_frame(320, 240))

    assert jpeg.startswith(_JPEG_MAGIC)
    assert len(jpeg) > 100


@pytest.mark.unit
def test_capture_frame_returns_contract_jpeg() -> None:
    """Happy path: an opened camera with a frame yields contract JPEG bytes."""
    cap = MagicMock()
    cap.isOpened.return_value = True
    cap.read.return_value = (True, _frame(1920, 1080))

    with patch("robot.camera_capture.cv2.VideoCapture", return_value=cap):
        jpeg = capture_frame()

    assert jpeg.startswith(_JPEG_MAGIC)
    cap.release.assert_called_once()


@pytest.mark.unit
def test_capture_frame_camera_not_opened_raises() -> None:
    """A camera that cannot open must raise CameraError and still release."""
    cap = MagicMock()
    cap.isOpened.return_value = False

    with (
        patch("robot.camera_capture.cv2.VideoCapture", return_value=cap),
        pytest.raises(CameraError, match="Cannot open"),
    ):
        capture_frame()

    cap.release.assert_called_once()


@pytest.mark.unit
def test_capture_frame_no_frame_raises() -> None:
    """A camera returning no frame must raise CameraError."""
    cap = MagicMock()
    cap.isOpened.return_value = True
    cap.read.return_value = (False, None)

    with (
        patch("robot.camera_capture.cv2.VideoCapture", return_value=cap),
        pytest.raises(CameraError, match="no frame"),
    ):
        capture_frame()
