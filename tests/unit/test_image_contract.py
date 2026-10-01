"""Image contract (Plan 0050): dimensions are bounded before any pixel decode."""

from io import BytesIO

import cv2
from PIL import Image
import pytest
from server.exceptions import ImageContractError
from server.vision.describe import MAX_IMAGE_HEIGHT, MAX_IMAGE_WIDTH, decode_and_validate_image

_EXIF_ORIENTATION_TAG = 0x0112
_ROTATE_90_CW = 6


def _encoded(width: int, height: int, image_format: str = "PNG") -> bytes:
    """Encode one blank RGB image of the given size in memory."""
    buffer = BytesIO()
    Image.new("RGB", (width, height)).save(buffer, format=image_format)
    return buffer.getvalue()


@pytest.mark.unit
def test_oversized_dimensions_are_rejected_before_any_pixel_decode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A small upload declaring a huge frame must never reach cv2.imdecode."""

    def forbidden_decode(*_args: object) -> None:
        pytest.fail("cv2.imdecode ran before the dimension check")

    monkeypatch.setattr(cv2, "imdecode", forbidden_decode)

    with pytest.raises(ImageContractError, match="contract max"):
        decode_and_validate_image(_encoded(MAX_IMAGE_WIDTH + 1, MAX_IMAGE_HEIGHT))


@pytest.mark.unit
@pytest.mark.parametrize("image_format", ["JPEG", "PNG", "WEBP", "GIF", "BMP"])
def test_every_contract_format_at_the_limit_still_validates(image_format: str) -> None:
    """The header check keeps accepting all five contract formats at 1280x720."""
    decode_and_validate_image(_encoded(MAX_IMAGE_WIDTH, MAX_IMAGE_HEIGHT, image_format))


@pytest.mark.unit
def test_bytes_without_an_image_header_are_rejected() -> None:
    """Garbage fails with the contract error, not a raw Pillow exception."""
    with pytest.raises(ImageContractError, match="could not be decoded"):
        decode_and_validate_image(b"definitely not an image")


@pytest.mark.unit
def test_exif_rotation_is_still_bounded_after_decode() -> None:
    """A 1280x720 header rotated to 720x1280 by EXIF is still rejected."""
    image = Image.new("RGB", (MAX_IMAGE_WIDTH, MAX_IMAGE_HEIGHT))
    exif = image.getexif()
    exif[_EXIF_ORIENTATION_TAG] = _ROTATE_90_CW
    buffer = BytesIO()
    image.save(buffer, format="JPEG", exif=exif.tobytes())

    with pytest.raises(ImageContractError, match="contract max"):
        decode_and_validate_image(buffer.getvalue())
