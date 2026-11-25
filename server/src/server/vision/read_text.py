"""Read the text in front of the camera with the local VLM (Plan 0088 D-17, ADR 0034 decision 5).

One fixed prompt asks for the visible text only. The frame is the turn's own (the one the voice
routes carry for face authentication), processed in memory and never stored or logged.
"""

from __future__ import annotations

import base64
import logging
from typing import TYPE_CHECKING, Final

import httpx

from server.exceptions import LLMError, VisionError
from server.llm_transport import ollama_chat_measured
from server.settings import settings
from server.vision.describe import log_vision_failure, log_vision_metrics, vlm_frame, vlm_options

if TYPE_CHECKING:
    from server.llm_transport import ChatMessage

logger = logging.getLogger(__name__)

__all__ = ["READ_PROMPT", "read_text"]

#: The one prompt of a reading: the visible text, word for word, and nothing else.
READ_PROMPT: Final = (
    "Escribe exactamente el texto que se ve en la imagen, palabra por palabra, en el orden en "
    "que aparece. No describas la imagen, no expliques nada y no agregues nada. Si no se ve "
    "ningún texto, no escribas nada."
)
_TEMPERATURE: Final = 0.0
_READ_FAILED: Final = "vision.read_failed"


async def read_text(client: httpx.AsyncClient, image: bytes) -> str:
    """Return the text the VLM reads in one camera frame.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039).
        image: The turn's frame — JPEG/PNG/WebP/GIF/BMP, max 1280x720, already validated by the
            route. Processed in memory and discarded, never persisted.

    Returns:
        The text read, stripped.

    Raises:
        VisionError: If the VLM is unreachable, fails, times out or reads nothing.
    """
    image = await vlm_frame(image, _READ_FAILED)
    message: ChatMessage = {
        "role": "user",
        "content": READ_PROMPT,
        "images": [base64.b64encode(image).decode("ascii")],
    }
    try:
        text, metrics = await ollama_chat_measured(
            client,
            [message],
            model=settings.vlm_model,
            options=vlm_options(_TEMPERATURE, settings.vlm_num_predict_reading),
            timeout=settings.ollama_timeout_s,
            keep_alive=settings.vlm_keep_alive,
        )
    except (httpx.HTTPError, LLMError) as exc:
        log_vision_failure(_READ_FAILED, type(exc).__name__, image)
        raise VisionError(f"VLM reading failed ({type(exc).__name__})") from exc
    text = text.strip()
    if not text:
        log_vision_failure(_READ_FAILED, "nothing_read", image)
        raise VisionError("VLM read no text")
    log_vision_metrics("reading", image, metrics)
    logger.info("Text read by the camera (%d chars)", len(text), extra={"event": "vision.read"})
    return text
