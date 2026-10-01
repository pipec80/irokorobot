"""One reader for every image upload: size, format and the 1280x720 contract (Plan 0050).

Image contract: JPEG/PNG/WebP/GIF/BMP · max 1280x720 · ONE frame.
"""

from fastapi import HTTPException, UploadFile

from server import vision
from server.exceptions import ImageContractError, UploadTooLargeError
from server.settings import settings
from server.uploads import read_limited_upload

_BYTES_PER_MB = 1024 * 1024


async def read_contract_image(upload: UploadFile, *, noun: str = "Image") -> bytes:
    """Read an upload and validate it against the image contract.

    Args:
        upload: Multipart file part carrying one image or camera frame.
        noun: How the part is called in error details (``"Image"`` or
            ``"Frame"``).

    Returns:
        The raw, validated image bytes.

    Raises:
        HTTPException: 413 if the part exceeds ``MAX_IMAGE_UPLOAD_BYTES``; 422
            if it is empty, an unrecognized format, fails to decode, or
            exceeds the 1280x720 contract limit.
    """
    try:
        data = await read_limited_upload(upload, limit=settings.max_image_upload_bytes)
    except UploadTooLargeError as exc:
        raise HTTPException(
            status_code=413,
            detail=f"{noun} too large — max {exc.limit // _BYTES_PER_MB} MB",
        ) from exc
    if not data:
        raise HTTPException(status_code=422, detail=f"{noun} file is empty")
    if not vision.is_known_image_format(data):
        raise HTTPException(
            status_code=422,
            detail="Unsupported image format (contract: JPEG/PNG/WebP/GIF/BMP · max 1280x720)",
        )
    try:
        vision.decode_and_validate_image(data)
    except ImageContractError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return data
