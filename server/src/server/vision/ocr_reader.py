"""Read the text in front of the camera with a dedicated OCR (Plan 0090, ADR 0041 decision 1).

RapidOCR (its default PP-OCRv6 small models, which cover Spanish, on ONNX Runtime and the CPU)
reads the turn's frame as taken. A grayscale and local-contrast step was measured and dropped
(Plan 0090 decision 9 as amended): it gained a handwritten word but misread a digit of a real
bill's total. The frame is decoded and read in memory
and never stored or logged; only counts and durations are logged. A failure is a ``VisionError``
the route speaks as «No pude leerlo…»: the vision model is never called instead.

Image contract: JPEG/PNG/WebP/GIF/BMP · max 1280x720 · ONE frame per request.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import logging
import re
import time
from typing import Any, Final

import cv2
import numpy as np

from server.exceptions import VisionError
from server.request_context import run_in_executor_with_context

logger = logging.getLogger(__name__)

__all__ = ["decode_frame", "ocr_read_text"]

# The multilingual model can return characters of another script (CJK, Hangul, kana) on a smudge;
# Piper would read them as noise.
_OTHER_SCRIPT: Final = re.compile(r"[⺀-鿿가-힯豈-﫿＀-￯]+")
# One engine and one thread: an ONNX session reading two frames at once is not needed here.
_executor = ThreadPoolExecutor(max_workers=1)
_engine: Any = None  # Any: rapidocr.RapidOCR, imported lazily and shipped without type hints


def decode_frame(image: bytes) -> np.ndarray:
    """Decode *image* as the BGR frame the engine reads, unchanged.

    Args:
        image: The turn's frame (JPEG/PNG/WebP/GIF/BMP).

    Raises:
        VisionError: If the frame cannot be decoded.
    """
    decoded = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
    if decoded is None:
        raise VisionError("the frame could not be decoded")
    return decoded


def _load_engine() -> Any:  # noqa: ANN401 - rapidocr ships no type hints
    """Build RapidOCR with its default models; they load on the first read (about 8 s)."""
    from rapidocr import RapidOCR  # noqa: PLC0415 - heavy import, only when reading is used

    return RapidOCR()


def _read_lines(frame: np.ndarray) -> list[str]:
    """Run the engine on *frame* in the executor's thread; the lines in reading order."""
    global _engine  # noqa: PLW0603
    if _engine is None:
        _engine = _load_engine()
    result = _engine(frame)
    return [str(text) for text in (result.txts or ())]


def _clean(lines: list[str]) -> str:
    kept = (" ".join(_OTHER_SCRIPT.sub("", line).split()) for line in lines)
    return "\n".join(line for line in kept if line)


async def ocr_read_text(image: bytes) -> str:
    """Return the text the OCR reads in one camera frame, one line per text line.

    Args:
        image: The turn's frame, already validated by the route; read in memory, never kept.

    Returns:
        The text read, without characters of another script.

    Raises:
        VisionError: If the frame cannot be decoded, the engine fails or nothing is read.
    """
    frame = decode_frame(image)
    start = time.perf_counter()
    try:
        lines = await run_in_executor_with_context(_executor, lambda: _read_lines(frame))
    except Exception as exc:  # the engine's boundary: any failure is a failed reading
        logger.warning(
            "OCR reading failed (%s)",
            type(exc).__name__,
            extra={"event": "vision.ocr_failed", "cause": type(exc).__name__},
        )
        raise VisionError(f"OCR reading failed ({type(exc).__name__})") from exc
    text = _clean(lines)
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    logger.info(
        "Text read by the OCR (%d lines, %d chars, %d ms)",
        len(lines),
        len(text),
        elapsed_ms,
        extra={"event": "vision.ocr_read", "lines": len(lines), "ms": elapsed_ms},
    )
    if not text:
        raise VisionError("OCR read no text")
    return text
