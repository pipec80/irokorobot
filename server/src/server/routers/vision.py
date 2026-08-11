"""Vision endpoints — scene description, face enrollment, and visual dialogue.

Image contract: JPEG/PNG/WebP/GIF/BMP · max 1280x720 · ONE frame per request.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from server import vision
from server.exceptions import (
    BrainMemoryError,
    EnrollmentRejectedError,
    ImageContractError,
    VisionError,
)
from server.pipeline import _run_tts
from server.schemas import TranscribeResponse, VisionDescribeResponse, VisionEnrollResponse
from server.settings import settings
from server.text_turn import new_interaction_scope, process_text_turn
from server.vision.perception import perceive_scene

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Vision"])


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
    """Enroll one person's face — the transparent enrollment service (V1.1).

    Args:
        image: Image frame per the image contract (webcam frame or photo).
        name: Person name — reuses the memory entity when already known.

    Returns:
        VisionEnrollResponse with the stored name, entity and profile ids.

    Raises:
        HTTPException: 503 for backends, 413 for size, or 422 for rejection.
    """
    if not settings.vision_enabled:
        raise HTTPException(status_code=503, detail="Vision is disabled (VISION_ENABLED=false)")
    if not name.strip():
        raise HTTPException(status_code=422, detail="Name is empty")

    image_bytes = await _read_contract_image(image)

    try:
        outcome = await vision.enroll_person(name, image_bytes)
    except EnrollmentRejectedError as exc:
        raise HTTPException(status_code=422, detail=f"{exc.code}: {exc}") from exc
    except VisionError as exc:
        logger.error("Enrollment failed — vision backend: %s", exc)
        raise HTTPException(status_code=503, detail="Vision backend unavailable") from exc
    except BrainMemoryError as exc:
        logger.error("Enrollment failed — memory backend: %s", exc)
        raise HTTPException(status_code=503, detail="Memory backend unavailable") from exc

    return VisionEnrollResponse(
        name=outcome.name, entity_id=outcome.entity_id, profile_id=outcome.profile_id
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

    # Explicit enrollment remains separate from unresolved scene dialogue.
    enroll_name = vision.wants_enroll(text)
    try:
        if enroll_name is not None:
            perception = await vision.enroll_from_frame(enroll_name, image_bytes)
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
