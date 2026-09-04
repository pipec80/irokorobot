"""Vision endpoints — scene description, face enrollment, and visual dialogue.

Image contract: JPEG/PNG/WebP/GIF/BMP · max 1280x720 · ONE frame per request.
"""

from datetime import UTC, date, datetime
import logging
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
import httpx

from server import turn_log, vision
from server.cognition.authorization import evaluate_authorization
from server.cognition.controller import CognitiveController
from server.cognition.household_tools import HouseholdKnowledgeTools
from server.cognition.identity import ActivePersonContext, ActivePersonStatus, HouseholdRole
from server.cognition.models import CognitiveEvent, Confidence, ConfidenceBasis, KnowledgeStatus
from server.cognition.response_plan import (
    InformationNeed,
    ResponsePlan,
    ResponseSource,
    SceneDescriptionRequest,
    TextTurnPayload,
    current_perception_plan,
)
from server.exceptions import ImageContractError, UploadTooLargeError, VisionError
from server.memory.household_authorization import record_authorization_decision
from server.memory.policy_gated_v4_reader import PolicyGatedV4Reader
from server.pipeline import _run_tts
from server.resources import ResourcesDep
from server.schemas import (
    TranscribeResponse,
    VisionDescribeResponse,
    VisionEnrollResponse,
    error_responses,
)
from server.settings import settings
from server.text_turn import TextTurnResult, new_interaction_scope, process_text_turn
from server.uploads import read_limited_upload
from server.vision.perception import perceive_scene

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vision", tags=["Vision"])

_BIOMETRIC_ENROLLMENT_UNAVAILABLE = (
    "Face enrollment is temporarily unavailable pending local administration and consent policy."
)


def _today() -> date:
    """Return the adapter-owned local date for deterministic visual tools."""
    return date.today()


def _vision_event_from_question(message: str) -> CognitiveEvent[TextTurnPayload]:
    """Translate one visual question into a fresh typed cognitive event."""
    now = datetime.now(UTC)
    return CognitiveEvent(
        event_id=uuid4(),
        schema_version=1,
        event_type="text.turn",
        occurred_at=now,
        recorded_at=now,
        source="vision.respond",
        correlation_id=uuid4(),
        causation_id=None,
        subject_id=None,
        payload=TextTurnPayload(
            message=message,
            conversation_id=new_interaction_scope(),
        ),
    )


async def _public_unknown_vision_actor(
    event: CognitiveEvent[TextTurnPayload],
) -> ActivePersonContext:
    """Return the safe public visual actor without deriving an identity."""
    actor = ActivePersonContext(
        person_id=None,
        display_name=None,
        status=ActivePersonStatus.UNKNOWN,
        confidence=Confidence(
            score=0.0,
            basis=ConfidenceBasis.NOT_APPLICABLE,
            calibrated=False,
            reason="Public visual dialogue provides no trusted identity evidence",
        ),
        role=HouseholdRole.UNKNOWN,
        evidence=(),
        resolved_at=event.occurred_at,
    )
    turn_log.log_actor("vision", actor)
    return actor


def _vlm_failure_plan() -> ResponsePlan:
    """Build the fixed spoken excuse for a failed VLM call — no second LLM."""
    return ResponsePlan(
        need=InformationNeed.SCENE_DESCRIPTION,
        status=KnowledgeStatus.UNKNOWN,
        source=ResponseSource.CURRENT_PERCEPTION,
        response="Perdón, ahora mismo no pude ver la escena.",
    )


def _vision_controller(client: httpx.AsyncClient) -> CognitiveController:
    """Compose the bounded controller used by one public visual dialogue turn.

    Only `SCENE_DESCRIPTION` may read a frame or call the VLM; every other
    need is a closed, camera-free plan. Generic non-scene conversation
    delegates to legacy text generation with no perception at all — a scene
    description is never injected into the textual LLM.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039), closed over
            by the legacy-turn delegate below.
    """

    async def legacy_turn(message: str, conversation_id: str) -> TextTurnResult:
        """Delegate generic non-scene visual dialogue without any perception."""
        return await process_text_turn(client, message, conversation_id)

    return CognitiveController(
        today=_today,
        legacy_turn=legacy_turn,
        active_person_resolver=_public_unknown_vision_actor,
        policy_evaluator=evaluate_authorization,
        audit_writer=record_authorization_decision,
        household_tools=HouseholdKnowledgeTools(reader=PolicyGatedV4Reader()),
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
    try:
        image_bytes = await read_limited_upload(image, limit=settings.max_image_upload_bytes)
    except UploadTooLargeError as exc:
        raise HTTPException(
            status_code=413,
            detail=f"Image too large — max {exc.limit // 1024 // 1024} MB",
        ) from exc
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


@router.post(
    "/describe",
    responses=error_responses(
        (413, "Image exceeds the upload size limit"),
        (503, "Vision disabled, or the VLM backend is unavailable"),
    ),
)
async def vision_describe(
    resources: ResourcesDep,
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
        description, duration_ms = await vision.describe_image(resources.http_client, image_bytes)
    except VisionError as exc:
        logger.error("Vision describe failed: %s", exc)
        raise HTTPException(status_code=503, detail="Vision backend unavailable") from exc

    return VisionDescribeResponse(description=description, duration_ms=duration_ms)


@router.post(
    "/enroll",
    responses=error_responses((503, "Vision disabled, or biometric enrollment unavailable")),
)
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


@router.post(
    "/respond",
    responses=error_responses((503, "Vision is disabled for a scene-description question")),
)
async def vision_respond(
    resources: ResourcesDep,
    image: Annotated[
        UploadFile, File(description="JPEG/PNG/WebP/GIF/BMP · max 1280x720 · one frame")
    ],
    text: Annotated[str, Form(description="The user's transcribed visual question")],
) -> TranscribeResponse:
    """Answer one typed visual-dialogue turn; only a scene request touches a frame.

    Args:
        image: JPEG/PNG/WebP/GIF/BMP frame, max 1280x720 and upload limit.
            Read and decoded only when the typed resolver classifies this
            turn as a scene description — every other need never touches it.
        text: The user's transcribed question ("¿qué ves?").

    Returns:
        Existing audio response contract with ``vision_requested=False``.

    Raises:
        HTTPException 503: Only for a scene request while vision is disabled.
        HTTPException 422: Empty question, or an invalid frame for a scene
            request.
        HTTPException 500: If TTS fails.
    """
    if not text.strip():
        raise HTTPException(status_code=422, detail="Question text is empty")

    event = _vision_event_from_question(text)
    controller = _vision_controller(resources.http_client)
    decision = await controller.decide(event)

    plan: ResponsePlan
    if isinstance(decision, SceneDescriptionRequest):
        if not settings.vision_enabled:
            raise HTTPException(status_code=503, detail="Vision is disabled (VISION_ENABLED=false)")
        image_bytes = await _read_contract_image(image)
        try:
            description = await perceive_scene(resources.http_client, image_bytes)
            plan = current_perception_plan(description)
        except VisionError as exc:
            # A blind turn still speaks: the character excuses itself (R13 spirit).
            logger.error("Vision perception failed — responding blind: %s", exc)
            plan = _vlm_failure_plan()
    elif decision is None:
        plan = await controller.handle(event)
    else:
        plan = decision

    turn_log.log_decision("vision", plan)
    audio_base64, duration_ms, _tts_ms = await _run_tts(plan.response)

    return TranscribeResponse(
        text_heard=text,
        llm_response=plan.response,
        audio_base64=audio_base64,
        duration_ms=duration_ms,
        emotion=plan.emotion,
    )
