"""Vision endpoints — scene description, face enrollment, and visual dialogue.

Image contract: JPEG/PNG/WebP/GIF/BMP · max 1280x720 · ONE frame per request.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from server import vision
from server.exceptions import ImageContractError, VisionError
from server.pipeline import _run_tts
from server.schemas import TranscribeResponse, VisionDescribeResponse, VisionEnrollResponse
from server.settings import settings
from server.text_turn import new_interaction_scope, process_text_turn
from server.vision.perception import perceive_scene

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Vision"])

_BIOMETRIC_ENROLLMENT_UNAVAILABLE = (
    "Face enrollment is temporarily unavailable pending local administration and consent policy."
)


async def _read_contract_image(image: UploadFile) -> bytes:
    """Read an upload and validate it against the image contract.

    Image contract: JPEG/PNG/WebP/GIF/BMP · max 1280x720 · ONE frame.

    Args:
        image: Multipart upload from a vision endpoint.

    Returns:
        The raw, validated image bytes.

    Raises:
        HTTPException 413: If the image exceeds MAX_UPLOAD_BYTES.
        HTTPException 422: If the image is empty, an unrecognized format,
            fails to decode, or exceeds the 1280x720 contract limit.
    """
    image_bytes = await image.read()
    if len(image_bytes) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Image too large — max {settings.max_upload_bytes // 1024 // 1024} MB",
        )
    if not image_bytes:
        raise HTTPException(status_code=422, detail="Image file is empty")
    if not vision.is_known_image_format(image_bytes):
        raise HTTPException(
            status_code=422,
            detail="Unsupported image format (contract: JPEG/PNG/WebP/GIF/BMP · max 1280x720)",
        )
    try:
        vision.decode_and_validate_image(image_bytes)
    except ImageContractError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return image_bytes


@router.post("/vision/describe")
async def vision_describe(
    image: Annotated[
        UploadFile, File(description="JPEG/PNG/WebP/GIF/BMP · max 1280x720 · one frame")
    ],
) -> VisionDescribeResponse:
    """Describe one camera frame using the local VLM (V0).

    Args:
        image: JPEG/PNG/WebP/GIF/BMP frame, max 1280x720 and upload limit.

    Returns:
        Spanish description and inference duration.

    Raises:
        HTTPException: 503 for backend, 413 for size, or 422 for image contract.
    """
    if not settings.vision_enabled:
        raise HTTPException(status_code=503, detail="Vision is disabled (VISION_ENABLED=false)")

    image_bytes = await _read_contract_image(image)

    try:
        description, duration_ms = await vision.describe_image(image_bytes)
    except VisionError as exc:
        logger.error("Vision describe failed: %s", exc)
        raise HTTPException(status_code=503, detail="Vision backend unavailable") from exc

    return VisionDescribeResponse(description=description, duration_ms=duration_ms)


@router.post("/vision/enroll")
async def vision_enroll(
    image: Annotated[
        UploadFile, File(description="JPEG/PNG/WebP/GIF/BMP · max 1280x720 · one frame")
    ],
    name: Annotated[str, Form(description="Person name to enroll")],
) -> VisionEnrollResponse:
    """Reject public face enrollment until local policy exists.

    Args:
        image: Image frame per the image contract (webcam frame or photo).
        name: Person name — reuses the memory entity when already known.

    Returns:
        This endpoint does not create or attach a biometric profile.

    Raises:
        HTTPException: 503 while public enrollment is quarantined.
    """
    if not settings.vision_enabled:
        raise HTTPException(status_code=503, detail="Vision is disabled (VISION_ENABLED=false)")

    # Keep the public multipart contract stable without reading either value.
    del image, name
    raise HTTPException(
        status_code=503,
        detail=_BIOMETRIC_ENROLLMENT_UNAVAILABLE,
    )


@router.post("/vision/respond")
async def vision_respond(
    image: Annotated[
        UploadFile, File(description="JPEG/PNG/WebP/GIF/BMP · max 1280x720 · one frame")
    ],
    text: Annotated[str, Form(description="The user's transcribed visual question")],
) -> TranscribeResponse:
    """Answer a visual question in character: frame + question → spoken reply.

    Args:
        image: JPEG/PNG/WebP/GIF/BMP frame, max 1280x720 and upload limit.
        text: The user's transcribed question ("¿qué ves?").

    Returns:
        Existing audio response contract with ``vision_requested=False``.

    Raises:
        HTTPException 503: If vision is disabled.
        HTTPException 413/422: Image or question contract violation.
        HTTPException 500: If TTS fails.
    """
    if not settings.vision_enabled:
        raise HTTPException(status_code=503, detail="Vision is disabled (VISION_ENABLED=false)")
    if not text.strip():
        raise HTTPException(status_code=422, detail="Question text is empty")

    image_bytes = await _read_contract_image(image)

    # Public enrollment is quarantined until P0.5 defines local administration,
    # consent, and authorization. A phrase is not proof of either.
    enrollment_requested = vision.wants_enroll(text) is not None
    try:
        if enrollment_requested:
            perception = _BIOMETRIC_ENROLLMENT_UNAVAILABLE
        else:
            perception = await perceive_scene(image_bytes)
    except VisionError as exc:
        # A blind turn still speaks: the character excuses itself (R13 spirit).
        logger.error("Vision perception failed — responding blind: %s", exc)
        perception = vision.PERCEPTION_FAILED

    turn = await process_text_turn(
        text,
        new_interaction_scope(),
        perception=perception,
    )
    audio_base64, duration_ms, _tts_ms = await _run_tts(turn.response)

    return TranscribeResponse(
        text_heard=text,
        llm_response=turn.response,
        audio_base64=audio_base64,
        duration_ms=duration_ms,
        emotion=turn.emotion,
    )
