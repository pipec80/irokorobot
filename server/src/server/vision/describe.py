"""Scene description via a local VLM served by Ollama (V0).

Image contract: JPEG/PNG/WebP/GIF/BMP · max 1280x720 · ONE frame per
request. Frames are processed in memory and discarded — they NEVER
persist (privacy, docs/audit/05 §5). In V0 the description is not stored
in memory either.

JPEG quality 85 is an encoding *recommendation* for producers (the
robot's own camera client) to keep uploads small — it is not, and cannot
be, a property the server verifies from the bytes it receives.
"""

from __future__ import annotations

import base64
import logging
import time

import httpx
import numpy as np

from server.exceptions import ImageContractError, VisionError
from server.settings import settings

logger = logging.getLogger(__name__)

_DESCRIBE_PROMPT = (
    "Describe en español lo que ves en la imagen, en dos o tres frases "
    "cortas y naturales. Sin listas, sin encabezados, sin inglés. "
    "Describe solo evidencia visible: objetos, colores, formas, posiciones "
    "y acciones observables. Si algo no se distingue con claridad, decilo "
    "explícitamente en vez de adivinar. No afirmes la identidad de ninguna "
    "persona, ni su género, relación con otras personas, intención, "
    "emoción o estado mental — nada de eso se puede ver. No afirmes qué "
    "hay dentro de un contenedor cerrado ni de un objeto que no se pueda "
    "ver directamente."
)

# Magic-byte signatures for every format the image contract accepts.
# Cheap first line of defense before the (heavier) real decode below.
# HEIC is deliberately NOT recognized here — see PROMPT B3 scope note.
_JPEG_MAGIC = b"\xff\xd8"  # JPEG SOI marker
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_GIF_MAGICS = (b"GIF87a", b"GIF89a")
_BMP_MAGIC = b"BM"
_RIFF_MAGIC = b"RIFF"  # WebP wraps a RIFF container...
_WEBP_MAGIC = b"WEBP"  # ...tagged WEBP at byte offset 8.

#: Contract dimension limits — width/height in pixels.
MAX_IMAGE_WIDTH = 1280
MAX_IMAGE_HEIGHT = 720

#: Perception block injected when the eye failed — the robot apologizes
#: out loud instead of going silent (same philosophy as R13).
PERCEPTION_FAILED = (
    "Tu visión falló en este momento: no pudiste ver nada. "
    "Discúlpate brevemente y con humor, sin tecnicismos."
)


def is_known_image_format(image: bytes) -> bool:
    """Return ``True`` when *image* starts with a recognized magic byte.

    Cheap, format-only pre-check — does not decode or validate
    dimensions. Recognizes JPEG, PNG, GIF, BMP and WebP (everything
    ``cv2.imdecode`` supports natively). HEIC is intentionally not
    recognized.

    Args:
        image: Raw upload bytes to check against the image contract
            (JPEG/PNG/WebP/GIF/BMP · max 1280x720).
    """
    if image.startswith(_JPEG_MAGIC):
        return True
    if image.startswith(_PNG_MAGIC):
        return True
    if image.startswith(_GIF_MAGICS):
        return True
    if image.startswith(_BMP_MAGIC):
        return True
    return image[:4] == _RIFF_MAGIC and image[8:12] == _WEBP_MAGIC


def decode_and_validate_image(image: bytes) -> None:
    """Decode *image* and enforce the contract's dimension limits.

    This is the real (not just magic-byte) validation: it decodes the
    frame once to prove it is a genuine, well-formed image within the
    contract's 1280x720 bound.

    Args:
        image: Raw upload bytes — contract: JPEG/PNG/WebP/GIF/BMP · max
            1280x720 · one frame.

    Raises:
        ImageContractError: If the bytes fail to decode as an image, or
            the decoded width/height exceeds the contract limit.

    Note:
        This decodes the frame purely to validate it; ``vision.faces``
        decodes it again later for face inference. Avoiding that double
        decode is a valid follow-up optimization — out of scope here
        (PROMPT B3, item 6).
    """
    # Lazy: cv2 is heavy and only needed when vision actually runs.
    import cv2  # noqa: PLC0415

    frame = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ImageContractError("Image could not be decoded — unsupported or corrupt file")
    height, width = frame.shape[:2]
    if width > MAX_IMAGE_WIDTH or height > MAX_IMAGE_HEIGHT:
        raise ImageContractError(
            f"Image is {width}x{height} — contract max is {MAX_IMAGE_WIDTH}x{MAX_IMAGE_HEIGHT}"
        )


async def describe_image(image: bytes) -> tuple[str, int]:
    """Describe ONE camera frame using the VLM served by Ollama.

    Args:
        image: Image bytes — contract: JPEG/PNG/WebP/GIF/BMP, max
            1280x720, one frame. Processed in memory and discarded, never
            persisted.

    Returns:
        Tuple ``(description, duration_ms)`` — Spanish description and
        VLM inference time in milliseconds.

    Raises:
        VisionError: If the VLM backend is unreachable, errors out, or
            returns an empty/unexpected response.
    """
    payload = {
        "model": settings.vlm_model,
        "messages": [
            {
                "role": "user",
                "content": _DESCRIBE_PROMPT,
                "images": [base64.b64encode(image).decode("ascii")],
            }
        ],
        "stream": False,
        "options": {"temperature": 0.3},
    }
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=settings.ollama_timeout_s) as client:
            resp = await client.post(f"{settings.ollama_url}/api/chat", json=payload)
            resp.raise_for_status()
            description = str(resp.json()["message"]["content"]).strip()
    except httpx.HTTPError as exc:
        raise VisionError(f"VLM backend unavailable ({settings.vlm_model}): {exc}") from exc
    except (KeyError, ValueError) as exc:
        raise VisionError(f"VLM returned an unexpected response: {exc}") from exc
    if not description:
        raise VisionError("VLM returned an empty description")
    duration_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        "Scene described in %d ms (%d chars)",
        duration_ms,
        len(description),
        extra={
            "event": "vision.described",
            "duration_ms": duration_ms,
            "chars": len(description),
        },
    )
    return description, duration_ms
