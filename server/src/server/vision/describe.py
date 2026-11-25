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
from io import BytesIO
import logging
import time

import httpx
import numpy as np
from PIL import Image, UnidentifiedImageError

from server.exceptions import ImageContractError, LLMError, VisionError
from server.llm_transport import ChatMessage, OllamaMetrics, ollama_chat_measured
from server.settings import settings
from server.vision.frame_resize import fit_long_side

logger = logging.getLogger(__name__)

_DESCRIBE_PROMPT = (
    "Describe en español lo que ves en la imagen, en dos o tres frases "
    "cortas y naturales. Sin listas, sin encabezados, sin inglés. "
    "Describe solo evidencia visible: objetos, colores, formas, posiciones "
    "y acciones observables. Si algo no se distingue con claridad, dilo "
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

_DESCRIBE_FAILED = "vision.describe_failed"
_SCENE_TEMPERATURE = 0.3

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


def _check_dimensions(width: int, height: int) -> None:
    """Raise when a frame exceeds the 1280x720 contract bound."""
    if width > MAX_IMAGE_WIDTH or height > MAX_IMAGE_HEIGHT:
        raise ImageContractError(
            f"Image is {width}x{height} — contract max is {MAX_IMAGE_WIDTH}x{MAX_IMAGE_HEIGHT}"
        )


def _header_dimensions(image: bytes) -> tuple[int, int]:
    """Read ``(width, height)`` from the image header without decoding pixels."""
    try:
        with Image.open(BytesIO(image)) as header:
            return header.size
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ImageContractError(
            "Image could not be decoded — unsupported or corrupt file"
        ) from exc


def decode_and_validate_image(image: bytes) -> None:
    """Validate *image* against the contract's dimension limits.

    The declared width and height are read from the header and bounded BEFORE
    any pixel is decoded, so a few kilobytes cannot ask for hundreds of
    megabytes of frame. The frame is then decoded once to prove it is a
    genuine, well-formed image, and its decoded size is checked again because
    an EXIF rotation can swap the axes.

    Args:
        image: Raw upload bytes — contract: JPEG/PNG/WebP/GIF/BMP · max
            1280x720 · one frame.

    Raises:
        ImageContractError: If the header cannot be read, the bytes fail to
            decode, or the width/height exceeds the contract limit.

    Note:
        ``vision.faces`` decodes the frame again later for face inference.
        Avoiding that double decode is a valid follow-up optimization.
    """
    _check_dimensions(*_header_dimensions(image))
    # Lazy: cv2 is heavy and only needed when vision actually runs.
    import cv2  # noqa: PLC0415

    frame = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ImageContractError("Image could not be decoded — unsupported or corrupt file")
    height, width = frame.shape[:2]
    _check_dimensions(width, height)


def image_size(image: bytes) -> tuple[int | None, int | None]:
    """Return ``(width, height)`` from the image header, or ``(None, None)`` when unreadable.

    Args:
        image: Image bytes — JPEG/PNG/WebP/GIF/BMP, max 1280x720; never decoded past the header.
    """
    try:
        width, height = _header_dimensions(image)
    except ImageContractError:
        return None, None
    return width, height


def vlm_options(temperature: float, num_predict: int | None) -> dict[str, float]:
    """Build a vision call's Ollama options: a key only for each setting that is set (D-12).

    Args:
        temperature: The call's own temperature, always sent.
        num_predict: The call's token cap, or ``None`` for Ollama's own.
    """
    options: dict[str, float] = {"temperature": temperature}
    if settings.vlm_num_ctx is not None:
        options["num_ctx"] = settings.vlm_num_ctx
    if num_predict is not None:
        options["num_predict"] = num_predict
    return options


def vlm_frame(image: bytes) -> bytes:
    """Return the frame as the vision model gets it: shrunk only when ``VLM_IMAGE_MAX_SIDE`` is set.

    Args:
        image: The turn's frame — JPEG/PNG/WebP/GIF/BMP, max 1280x720, one frame.

    Raises:
        ImageContractError: If a resize is asked for and the bytes are not an image.
    """
    max_side = settings.vlm_image_max_side
    return image if max_side is None else fit_long_side(image, max_side)


def log_vision_metrics(capability: str, image: bytes, metrics: OllamaMetrics) -> None:
    """Log what one good vision answer cost: Ollama's numbers and the image's size (D-11).

    Args:
        capability: ``"scene"`` or ``"reading"``.
        image: The frame sent (only its header is read, for its pixel size).
        metrics: The answer's ``OllamaMetrics``.
    """
    width, height = image_size(image)
    logger.info(
        "Vision metrics: capability=%s size=%sx%s load_ms=%s prompt_eval=%s/%sms eval=%s/%sms "
        "total_ms=%s",
        capability,
        width,
        height,
        metrics.load_ms,
        metrics.prompt_eval_count,
        metrics.prompt_eval_ms,
        metrics.eval_count,
        metrics.eval_ms,
        metrics.total_ms,
        extra={
            "event": "vision.metrics",
            "capability": capability,
            "width": width,
            "height": height,
            "load_ms": metrics.load_ms,
            "prompt_eval_count": metrics.prompt_eval_count,
            "prompt_eval_ms": metrics.prompt_eval_ms,
            "eval_count": metrics.eval_count,
            "eval_ms": metrics.eval_ms,
            "total_ms": metrics.total_ms,
        },
    )


def log_vision_failure(event: str, cause: str, image: bytes) -> None:
    """Log why one vision call failed: an exception's class or a closed cause, never a text.

    Args:
        event: ``"vision.describe_failed"`` or ``"vision.read_failed"``.
        cause: The exception's class name, ``"nothing_described"`` or ``"nothing_read"``.
        image: The frame sent (only its header is read, for its pixel size).
    """
    width, height = image_size(image)
    logger.warning(
        "Vision call failed: %s cause=%s size=%sx%s",
        event,
        cause,
        width,
        height,
        extra={"event": event, "cause": cause, "width": width, "height": height},
    )


async def describe_image(client: httpx.AsyncClient, image: bytes) -> tuple[str, int]:
    """Describe ONE camera frame using the VLM served by Ollama.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039) — never
            constructed here.
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
    image = vlm_frame(image)
    message: ChatMessage = {
        "role": "user",
        "content": _DESCRIBE_PROMPT,
        "images": [base64.b64encode(image).decode("ascii")],
    }
    t0 = time.perf_counter()
    try:
        description, metrics = await ollama_chat_measured(
            client,
            [message],
            model=settings.vlm_model,
            options=vlm_options(_SCENE_TEMPERATURE, settings.vlm_num_predict_scene),
            timeout=settings.ollama_timeout_s,
            keep_alive=settings.vlm_keep_alive,
        )
    except httpx.HTTPError as exc:
        log_vision_failure(_DESCRIBE_FAILED, type(exc).__name__, image)
        raise VisionError(f"VLM backend unavailable ({settings.vlm_model}): {exc}") from exc
    except LLMError as exc:
        log_vision_failure(_DESCRIBE_FAILED, type(exc).__name__, image)
        raise VisionError(f"VLM returned an unexpected response: {exc}") from exc
    description = description.strip()
    if not description:
        log_vision_failure(_DESCRIBE_FAILED, "nothing_described", image)
        raise VisionError("VLM returned an empty description")
    log_vision_metrics("scene", image, metrics)
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
