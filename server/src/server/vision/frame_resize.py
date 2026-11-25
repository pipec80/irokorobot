"""Shrink the frame given to the vision model, in memory (Plan 0089 D-12).

The image tokens of ``qwen3-vl`` grow with its pixels, so a smaller frame is a cheaper call. The
API contract still carries up to 1280x720, and the face and voice models still see the full
frame: only the copy sent to the vision model is resized, and it is never stored.
"""

from __future__ import annotations

from io import BytesIO
from typing import Final

from PIL import Image, UnidentifiedImageError

from server.exceptions import ImageContractError

__all__ = ["fit_long_side"]

_JPEG_QUALITY: Final = 85


def fit_long_side(image: bytes, max_side: int) -> bytes:
    """Return *image* with its longest side at most *max_side* pixels, keeping its ratio.

    Args:
        image: Image bytes — JPEG/PNG/WebP/GIF/BMP, max 1280x720, one frame.
        max_side: The longest side allowed, in pixels.

    Returns:
        The same bytes object when the frame already fits (never upscaled); otherwise the frame
        re-encoded as JPEG at quality 85.

    Raises:
        ImageContractError: If the bytes cannot be decoded as an image.
    """
    try:
        with Image.open(BytesIO(image)) as opened:
            width, height = opened.size
            if max(width, height) <= max_side:
                return image
            scale = max_side / max(width, height)
            size = (max(1, round(width * scale)), max(1, round(height * scale)))
            resized = opened.convert("RGB").resize(size, Image.Resampling.LANCZOS)
    # PIL raises ValueError or SyntaxError on some malformed images, beside the usual ones.
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombError,
    ) as exc:
        raise ImageContractError(
            "Image could not be decoded — unsupported or corrupt file"
        ) from exc
    buffer = BytesIO()
    resized.save(buffer, format="JPEG", quality=_JPEG_QUALITY)
    return buffer.getvalue()
