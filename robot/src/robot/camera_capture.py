"""Webcam frame capture — the robot's eye (V0).

Image contract: JPEG · max 1280x720 · quality 85 · ONE frame per request.
The robot only captures and encodes — ALL inference lives in the server,
the same boundary as audio. Frames never touch disk (privacy).
"""

import logging

import cv2
import numpy as np

from robot.exceptions import CameraError

logger = logging.getLogger(__name__)

_MAX_WIDTH = 1280
_MAX_HEIGHT = 720
_JPEG_QUALITY = 85


def fit_to_contract(frame: np.ndarray) -> np.ndarray:
    """Downscale *frame* to fit the image contract, preserving aspect ratio.

    Never upscales: a frame already within 1280x720 is returned as-is.

    Args:
        frame: BGR frame from OpenCV (height x width x channels).

    Returns:
        Frame fitting within 1280x720 — contract: JPEG · max 1280x720.
    """
    height, width = frame.shape[:2]
    scale = min(_MAX_WIDTH / width, _MAX_HEIGHT / height, 1.0)
    if scale >= 1.0:
        return frame
    new_size = (int(width * scale), int(height * scale))
    return cv2.resize(frame, new_size, interpolation=cv2.INTER_AREA)


def encode_jpeg(frame: np.ndarray) -> bytes:
    """Encode a BGR frame as JPEG at the contract quality (85).

    Args:
        frame: BGR frame already fitting within 1280x720.

    Returns:
        JPEG bytes — contract: JPEG · max 1280x720 · quality 85.

    Raises:
        CameraError: If OpenCV fails to encode the frame.
    """
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), _JPEG_QUALITY])
    if not ok:
        raise CameraError("JPEG encoding failed")
    return buf.tobytes()


def capture_frame(device_index: int = 0) -> bytes:
    """Capture ONE frame from the webcam and return contract JPEG bytes.

    Opens the device, grabs a single frame, and releases it immediately —
    the camera is never held open between requests, and the frame lives
    only in memory.

    Args:
        device_index: OpenCV camera index (0 = system default webcam).

    Returns:
        JPEG bytes — contract: JPEG · max 1280x720 · quality 85 · one frame.

    Raises:
        CameraError: If the camera cannot be opened or returns no frame.
    """
    cap = cv2.VideoCapture(device_index)
    try:
        if not cap.isOpened():
            raise CameraError(f"Cannot open camera device {device_index}")
        ok, frame = cap.read()
        if not ok or frame is None:
            raise CameraError(f"Camera device {device_index} returned no frame")
    finally:
        cap.release()
    logger.debug("Frame captured: %dx%d", frame.shape[1], frame.shape[0])
    return encode_jpeg(fit_to_contract(frame))
