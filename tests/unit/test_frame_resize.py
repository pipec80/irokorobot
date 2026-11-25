"""Plan 0089 D-12: the frame sent to the vision model can be made smaller, never larger."""

from io import BytesIO

from PIL import Image
import pytest
from server.exceptions import ImageContractError
from server.vision.frame_resize import fit_long_side

pytestmark = pytest.mark.unit


def _jpeg(width: int, height: int) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format="JPEG")
    return buffer.getvalue()


def _size(image: bytes) -> tuple[int, int]:
    with Image.open(BytesIO(image)) as opened:
        return opened.size


def test_a_wide_frame_is_cut_to_its_long_side_keeping_the_ratio() -> None:
    assert _size(fit_long_side(_jpeg(1280, 720), 512)) == (512, 288)


def test_a_tall_frame_is_cut_by_its_height() -> None:
    assert _size(fit_long_side(_jpeg(360, 640), 320)) == (180, 320)


def test_a_frame_already_small_enough_is_returned_untouched() -> None:
    image = _jpeg(640, 360)

    assert fit_long_side(image, 768) is image


def test_an_invalid_image_raises_the_contract_error() -> None:
    with pytest.raises(ImageContractError):
        fit_long_side(b"\xff\xd8not-an-image", 512)
