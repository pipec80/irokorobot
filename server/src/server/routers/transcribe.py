"""Audio endpoint — transcribe speech, generate a response, synthesize it.

Audio contract: WAV · 16000 Hz · mono · int16.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
import logging
import time
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
import httpx

from server import turn_log, vision
from server.audio_contract import validate_wav_contract
from server.cognition.authorization import evaluate_authorization
from server.cognition.controller import ActivePersonResolver, CognitiveController, ConsentResolver
from server.cognition.face_authentication import (
    FaceRequestResolver,
    build_default_face_request_resolver,
    compose_face_then_pin_resolver,
)
from server.cognition.household_tools import HouseholdKnowledgeTools
from server.cognition.identity import ActivePersonContext
from server.cognition.models import CognitiveEvent
from server.cognition.owner_authentication import OwnerRequestResolver, OwnerUnlockService
from server.cognition.response_plan import (
    ResponsePlan,
    SceneDescriptionRequest,
    TextTurnPayload,
    scene_unavailable_plan,
)
from server.dependencies import IdentityTokenDep, OwnerUnlockServiceDep, ResourcesDep
from server.exceptions import AudioContractError, ImageContractError, UploadTooLargeError
from server.memory.consolidation import consolidate_turn
from server.memory.household_authorization import record_authorization_decision
from server.memory.policy_gated_v4_reader import PolicyGatedV4Reader
from server.pipeline import (
    _elapsed_ms,
    _log_pipeline_timing,
    _run_stt,
    _run_tts,
)
from server.schemas import TranscribeResponse, error_responses
from server.settings import settings
from server.streaming import guarantee_terminal_event, stream_pipeline, stream_response_plan
from server.text_turn import (
    ConsolidationScheduler,
    TextTurnResult,
    new_interaction_scope,
    prepare_text_turn,
    process_text_turn,
)
from server.uploads import read_limited_upload

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Audio"])


def _today() -> date:
    """Return the adapter-owned local date for deterministic P0 tools."""
    return date.today()


def _voice_event_from_transcript(message: str) -> CognitiveEvent[TextTurnPayload]:
    """Translate one STT transcript into a fresh typed cognitive event."""
    now = datetime.now(UTC)
    return CognitiveEvent(
        event_id=uuid4(),
        schema_version=1,
        event_type="text.turn",
        occurred_at=now,
        recorded_at=now,
        source="audio.transcribe",
        correlation_id=uuid4(),
        causation_id=None,
        subject_id=None,
        payload=TextTurnPayload(
            message=message,
            conversation_id=new_interaction_scope(),
        ),
    )


@dataclass
class _RequestIdentity:
    """Uniform per-request actor/consent resolver, whichever evidence it used.

    Wraps either the plain PIN resolver (Plan 0026/0027, when face
    authentication is disabled or no frame was supplied) or the composed
    face-then-PIN pair (Plan 0029) behind one shape, so both `/transcribe`
    endpoints can read `.resolve_actor`, `.resolve_consent`, `.consumed`,
    and `.identity_source` without branching on which evidence source
    produced identity.

    Attributes:
        resolve_actor: The actor resolver to hand to the controller — the
            bare PIN resolver, or the composed face-then-PIN pair.
        resolve_consent: The matching consent resolver for `resolve_actor`.
        pin: The underlying PIN resolver, always present, used to report
            `.consumed`/`.identity_source` for the PIN path.
        face: The underlying face resolver, present only when face
            authentication was attempted for this request.
    """

    resolve_actor: ActivePersonResolver
    resolve_consent: ConsentResolver
    pin: OwnerRequestResolver
    face: FaceRequestResolver | None

    @property
    def consumed(self) -> bool:
        """Whether this request consumed a fresh one-use owner PIN unlock grant.

        Reports only the PIN grant's consumption state, unchanged from Plan
        0026/0027's meaning — a face-authenticated turn never touches the PIN
        resolver, so the caller's held token remains valid and must not be
        discarded. Use `identity_source` to learn whether THIS turn was
        face-authenticated instead.
        """
        return self.pin.consumed

    @property
    def identity_source(self) -> Literal["face", "local_unlock"] | None:
        """Which evidence source identified the actor, or `None` for neither."""
        if self.face is not None and self.face.consumed:
            return "face"
        if self.pin.consumed:
            return "local_unlock"
        return None


def _build_request_identity(
    owner_unlock_service: OwnerUnlockService, token: str | None, frame: bytes | None
) -> _RequestIdentity:
    """Compose this request's actor/consent resolver from PIN and optional face evidence.

    Args:
        owner_unlock_service: Lifespan-owned unlock service (Plan 0040).
        token: Optional one-use owner PIN unlock token from the request header.
        frame: Optional webcam frame bytes already read and validated from
            the multipart upload. `None` whenever no frame was supplied, or
            `settings.face_authentication_enabled` is `False` — in either
            case this resolves to exactly the existing PIN-only path
            (Plan 0026/0027).

    Returns:
        A `_RequestIdentity` wrapping either the plain PIN resolver or the
        face-first, PIN-fallback composed pair (Plan 0029).
    """
    pin = owner_unlock_service.for_request(token)
    if not settings.face_authentication_enabled or frame is None:
        return _RequestIdentity(
            resolve_actor=pin.resolve_actor,
            resolve_consent=pin.resolve_consent,
            pin=pin,
            face=None,
        )
    face = build_default_face_request_resolver(frame)
    resolve_actor, resolve_consent = compose_face_then_pin_resolver(face, pin)
    return _RequestIdentity(
        resolve_actor=resolve_actor,
        resolve_consent=resolve_consent,
        pin=pin,
        face=face,
    )


def _logged_voice_actor_resolver(
    request_identity: _RequestIdentity,
) -> ActivePersonResolver:
    """Wrap a request-scoped resolver to preserve the existing actor log line."""

    async def resolve_actor(event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
        actor = await request_identity.resolve_actor(event)
        turn_log.log_actor("voice", actor)
        return actor

    return resolve_actor


def _voice_controller(
    client: httpx.AsyncClient,
    background_tasks: BackgroundTasks,
    *,
    request_identity: _RequestIdentity | None = None,
) -> CognitiveController:
    """Compose the bounded controller used by a public voice turn.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039), closed over
            by the legacy-turn delegate and the consolidation scheduler.
        background_tasks: Queue used to schedule post-turn consolidation.
        request_identity: Optional request-scoped actor/consent resolver —
            the plain PIN resolver, or the composed face-then-PIN pair
            (Plan 0029). When omitted, the controller falls back to its own
            public-unknown defaults.
    """

    async def legacy_turn(message: str, conversation_id: str) -> TextTurnResult:
        """Delegate generic public conversation through the existing text service."""
        return await process_text_turn(
            client,
            message,
            conversation_id,
            schedule_consolidation=_consolidation_scheduler(client, background_tasks),
        )

    if request_identity is None:
        return CognitiveController(
            today=_today,
            legacy_turn=legacy_turn,
            policy_evaluator=evaluate_authorization,
            audit_writer=record_authorization_decision,
            household_tools=HouseholdKnowledgeTools(reader=PolicyGatedV4Reader()),
        )
    return CognitiveController(
        today=_today,
        legacy_turn=legacy_turn,
        active_person_resolver=_logged_voice_actor_resolver(request_identity),
        policy_evaluator=evaluate_authorization,
        audit_writer=record_authorization_decision,
        household_tools=HouseholdKnowledgeTools(reader=PolicyGatedV4Reader()),
        consent_resolver=request_identity.resolve_consent,
    )


def _consolidation_scheduler(
    client: httpx.AsyncClient,
    background_tasks: BackgroundTasks,
) -> ConsolidationScheduler:
    """Adapt FastAPI background tasks to the text service callback.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039) — safe to
            close over here, since the app's lifespan outlives any single
            request's background tasks.
        background_tasks: Queue used to schedule post-turn consolidation.
    """

    def schedule(
        message: str,
        response: str,
        active_person: ActivePersonContext,
    ) -> None:
        background_tasks.add_task(
            consolidate_turn,
            client,
            message,
            response,
            active_person=active_person,
        )

    return schedule


async def _read_audio_upload(audio: UploadFile) -> bytes:
    """Read and validate WAV 16kHz, mono, int16 upload bytes."""
    try:
        audio_bytes = await read_limited_upload(audio, limit=settings.max_audio_upload_bytes)
    except UploadTooLargeError as exc:
        raise HTTPException(
            status_code=413,
            detail=f"Audio too large — max {exc.limit // 1024 // 1024} MB",
        ) from exc
    if not audio_bytes:
        raise HTTPException(status_code=422, detail="Audio file is empty")
    try:
        validate_wav_contract(audio_bytes, max_duration_s=settings.max_audio_duration_s)
    except AudioContractError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return audio_bytes


async def _read_optional_frame(frame: UploadFile) -> bytes:
    """Read and validate one owner-authentication frame against the image contract.

    Duplicated minimally from `routers/vision.py`'s `_read_contract_image` —
    Plan 0029 keeps that router untouched, so this router cannot import from
    it (same pattern Task 4 used in `routers/auth.py`'s `_read_face_image`).

    The caller must only invoke this when `settings.face_authentication_enabled`
    is `True` and a frame was actually supplied — this function always reads
    and validates whatever it is given.

    Image contract: JPEG/PNG/WebP/GIF/BMP · max 1280x720 · ONE frame.

    Args:
        frame: Multipart upload carrying the webcam frame.

    Returns:
        The raw, validated frame bytes.

    Raises:
        HTTPException 413: If the frame exceeds MAX_UPLOAD_BYTES.
        HTTPException 422: If the frame is empty, an unrecognized format,
            fails to decode, or exceeds the 1280x720 contract limit.
    """
    try:
        frame_bytes = await read_limited_upload(frame, limit=settings.max_image_upload_bytes)
    except UploadTooLargeError as exc:
        raise HTTPException(
            status_code=413,
            detail=f"Frame too large — max {exc.limit // 1024 // 1024} MB",
        ) from exc
    if not frame_bytes:
        raise HTTPException(status_code=422, detail="Frame file is empty")
    if not vision.is_known_image_format(frame_bytes):
        raise HTTPException(
            status_code=422,
            detail="Unsupported image format (contract: JPEG/PNG/WebP/GIF/BMP · max 1280x720)",
        )
    try:
        vision.decode_and_validate_image(frame_bytes)
    except ImageContractError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return frame_bytes


@router.post(
    "/transcribe",
    responses=error_responses((413, "Audio or attached frame exceeds the upload size limit")),
)
async def transcribe(
    resources: ResourcesDep,
    owner_unlock_service: OwnerUnlockServiceDep,
    audio: Annotated[UploadFile, File(description="WAV 16kHz mono int16")],
    background_tasks: BackgroundTasks,
    x_iroko_identity_token: IdentityTokenDep = None,
    frame: Annotated[
        UploadFile | None,
        File(
            description="JPEG/PNG/WebP/GIF/BMP · max 1280x720 · optional owner-authentication frame"
        ),
    ] = None,
) -> TranscribeResponse:
    """Transcribe audio, generate a robot response, and synthesize speech.

    Args:
        audio: WAV at 16kHz, mono, int16, within MAX_UPLOAD_BYTES.
        background_tasks: Queue for successful voice-turn consolidation.
        x_iroko_identity_token: Optional one-use owner unlock token. Absent,
            expired, replayed, or malformed tokens resolve to the public
            unknown actor without disclosing which case occurred.
        frame: Optional webcam frame attached for in-request face
            authentication (Plan 0029). Only read and decoded when
            `settings.face_authentication_enabled` is `True` — otherwise
            accepted but completely inert. A malformed or oversized frame
            degrades to no frame instead of failing the turn.

    Returns:
        Existing audio response contract with text, WAV, emotion, timings,
        whether this turn consumed a fresh owner unlock grant, and which
        evidence source (face/local_unlock/none) identified the actor.

    Raises:
        HTTPException: 413 for size, 422 for WAV/speech, or 500 for STT/TTS.
    """
    request_start = time.perf_counter()
    frame_bytes: bytes | None = None
    if settings.face_authentication_enabled and frame is not None:
        try:
            frame_bytes = await _read_optional_frame(frame)
        except HTTPException as exc:
            logger.warning(
                "Owner-authentication frame rejected — continuing without it: %s", exc.detail
            )
    request_identity = _build_request_identity(
        owner_unlock_service, x_iroko_identity_token, frame_bytes
    )
    audio_bytes = await _read_audio_upload(audio)

    text_heard, stt_ms = await _run_stt(audio_bytes, [])

    if not text_heard.strip():
        logger.warning("STT returned empty transcript — audio was silence or too short")
        raise HTTPException(status_code=422, detail="No speech detected in audio")

    event = _voice_event_from_transcript(text_heard)
    controller = _voice_controller(
        resources.http_client, background_tasks, request_identity=request_identity
    )
    decision = await controller.decide(event)

    plan: ResponsePlan
    if isinstance(decision, SceneDescriptionRequest):
        if settings.vision_enabled:
            # V0.5/V1 — a visual question needs a camera frame the classic
            # request did not carry: answer NOW with a short spoken cue and
            # ask the client for one (second round via /vision/respond). The
            # cue phrase covers the VLM latency; this stub turn is not
            # recorded in memory — the real exchange lands in round two.
            logger.info(
                "Scene description requested (%d chars) — requesting a frame",
                len(text_heard),
                extra={"event": "vision.frame_requested", "chars": len(text_heard)},
            )
            audio_base64, duration_ms, tts_ms = await _run_tts(settings.vision_look_phrase)
            total_ms = _elapsed_ms(request_start)
            _log_pipeline_timing("voice.vision-cue", stt_ms, 0, tts_ms, total_ms)
            return TranscribeResponse(
                text_heard=text_heard,
                llm_response=settings.vision_look_phrase,
                audio_base64=audio_base64,
                duration_ms=duration_ms,
                emotion="neutral",
                vision_requested=True,
                stt_ms=stt_ms,
                tts_ms=tts_ms,
                total_ms=total_ms,
                authentication_consumed=request_identity.consumed,
                identity_source=request_identity.identity_source,
            )
        plan = scene_unavailable_plan()
    elif decision is None:
        plan = await controller.handle(event)
    else:
        plan = decision

    turn_log.log_decision("voice", plan)
    audio_base64, duration_ms, tts_ms = await _run_tts(plan.response)

    total_ms = _elapsed_ms(request_start)
    _log_pipeline_timing(f"voice.{plan.source.value}", stt_ms, plan.duration_ms, tts_ms, total_ms)
    return TranscribeResponse(
        text_heard=text_heard,
        llm_response=plan.response,
        audio_base64=audio_base64,
        duration_ms=duration_ms,
        emotion=plan.emotion,
        stt_ms=stt_ms,
        llm_ms=plan.duration_ms,
        tts_ms=tts_ms,
        total_ms=total_ms,
        authentication_consumed=request_identity.consumed,
        identity_source=request_identity.identity_source,
    )


@router.post(
    "/transcribe/stream",
    responses=error_responses((413, "Audio or attached frame exceeds the upload size limit")),
)
async def transcribe_stream(
    resources: ResourcesDep,
    owner_unlock_service: OwnerUnlockServiceDep,
    audio: Annotated[UploadFile, File(description="WAV 16kHz mono int16")],
    background_tasks: BackgroundTasks,
    x_iroko_identity_token: IdentityTokenDep = None,
    frame: Annotated[
        UploadFile | None,
        File(
            description="JPEG/PNG/WebP/GIF/BMP · max 1280x720 · optional owner-authentication frame"
        ),
    ] = None,
) -> StreamingResponse:
    """Transcribe audio and stream the robot's reply sentence by sentence (R3).

    Args:
        audio: WAV at 16kHz, mono, int16, within MAX_UPLOAD_BYTES.
        background_tasks: Queue for successful voice-turn consolidation.
        x_iroko_identity_token: Optional one-use owner unlock token — same
            contract as classic /transcribe (Plan 0027).
        frame: Optional webcam frame attached for in-request face
            authentication (Plan 0029). Only read and decoded when
            `settings.face_authentication_enabled` is `True` — otherwise
            accepted but completely inert. A malformed or oversized frame
            degrades to no frame instead of failing the turn.

    Returns:
        NDJSON events ordered as text, emotion, audio chunks, then timings.
        The terminal `done` event additionally reports whether this turn
        consumed a fresh owner unlock grant and which evidence source
        (face/local_unlock/none) identified the actor.

    Raises:
        HTTPException: 413 for size, 422 for WAV/speech, or 500 for STT.
    """
    request_start = time.perf_counter()
    frame_bytes: bytes | None = None
    if settings.face_authentication_enabled and frame is not None:
        try:
            frame_bytes = await _read_optional_frame(frame)
        except HTTPException as exc:
            logger.warning(
                "Owner-authentication frame rejected — continuing without it: %s", exc.detail
            )
    request_identity = _build_request_identity(
        owner_unlock_service, x_iroko_identity_token, frame_bytes
    )
    audio_bytes = await _read_audio_upload(audio)

    text_heard, stt_ms = await _run_stt(audio_bytes, [])

    if not text_heard.strip():
        logger.warning("STT returned empty transcript — audio was silence or too short")
        raise HTTPException(status_code=422, detail="No speech detected in audio")

    event = _voice_event_from_transcript(text_heard)
    decision = await _voice_controller(
        resources.http_client, background_tasks, request_identity=request_identity
    ).decide(event)
    # Streaming has no second-round frame upload — a scene request always
    # gets the fixed unavailable plan, regardless of VISION_ENABLED.
    plan: ResponsePlan | None = (
        scene_unavailable_plan() if isinstance(decision, SceneDescriptionRequest) else decision
    )
    turn_log.log_decision("stream", plan)
    if plan is not None:
        return StreamingResponse(
            guarantee_terminal_event(
                stream_response_plan(
                    text_heard=event.payload.message,
                    plan=plan,
                    stt_ms=stt_ms,
                    request_start=request_start,
                    authentication_consumed=request_identity.consumed,
                    identity_source=request_identity.identity_source,
                )
            ),
            media_type="application/x-ndjson",
        )

    prepared = await prepare_text_turn(
        resources.http_client,
        event.payload.message,
        event.payload.conversation_id,
    )

    return StreamingResponse(
        guarantee_terminal_event(
            stream_pipeline(
                client=resources.http_client,
                prepared=prepared,
                stt_ms=stt_ms,
                request_start=request_start,
                schedule_consolidation=_consolidation_scheduler(
                    resources.http_client, background_tasks
                ),
            )
        ),
        media_type="application/x-ndjson",
    )
