"""Shared image-upload reader (Plan 0050): one place enforces size, format and contract."""

import ast
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image
import pytest
from server.routers.image_upload import read_contract_image
from server.settings import settings

import server

_ROUTERS = Path(server.__file__).resolve().parent / "routers"
_VALIDATION_CALLS = {"decode_and_validate_image", "is_known_image_format"}


def _upload(data: bytes) -> UploadFile:
    """Wrap raw bytes as the multipart part a client would send."""
    return UploadFile(file=BytesIO(data), filename="upload")


def _png(width: int, height: int) -> bytes:
    """Encode one blank PNG of the given size in memory."""
    buffer = BytesIO()
    Image.new("RGB", (width, height)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.unit
async def test_a_contract_image_is_returned_untouched() -> None:
    data = _png(64, 48)

    assert await read_contract_image(_upload(data)) == data


@pytest.mark.unit
@pytest.mark.parametrize("noun", ["Image", "Frame"])
async def test_an_oversized_upload_is_413_and_names_the_resource(
    monkeypatch: pytest.MonkeyPatch, noun: str
) -> None:
    monkeypatch.setattr(settings, "max_image_upload_bytes", 10)

    with pytest.raises(HTTPException) as caught:
        await read_contract_image(_upload(b"x" * 11), noun=noun)

    assert caught.value.status_code == 413
    assert str(caught.value.detail).startswith(f"{noun} too large")


@pytest.mark.unit
async def test_an_empty_upload_is_422() -> None:
    with pytest.raises(HTTPException) as caught:
        await read_contract_image(_upload(b""), noun="Frame")

    assert caught.value.status_code == 422
    assert caught.value.detail == "Frame file is empty"


@pytest.mark.unit
async def test_an_unknown_format_is_422() -> None:
    with pytest.raises(HTTPException) as caught:
        await read_contract_image(_upload(b"not an image at all"))

    assert caught.value.status_code == 422
    assert "Unsupported image format" in str(caught.value.detail)


@pytest.mark.unit
async def test_an_over_limit_image_is_422() -> None:
    with pytest.raises(HTTPException) as caught:
        await read_contract_image(_upload(_png(1281, 720)))

    assert caught.value.status_code == 422
    assert "contract max" in str(caught.value.detail)


@pytest.mark.unit
def test_no_router_validates_uploaded_images_on_its_own() -> None:
    """Routers reach the image contract only through the shared reader."""
    offenders = [
        path.name
        for path in sorted(_ROUTERS.glob("*.py"))
        if path.name != "image_upload.py"
        and any(
            isinstance(node, ast.Attribute) and node.attr in _VALIDATION_CALLS
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        )
    ]

    assert offenders == []
