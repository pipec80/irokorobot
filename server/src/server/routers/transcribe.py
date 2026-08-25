"""Audio endpoint — transcribe speech, generate a response, synthesize it.

Audio contract: WAV · 16000 Hz · mono · int16.
"""

from datetime import UTC, date, datetime
import logging
import time
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, Header, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from server import turn_log
from server.audio_contract import validate_wav_contract
from server.cognition.authorization import evaluate_authorization
from server.cognition.controller import ActivePersonResolver, CognitiveController
from server.cognition.household_tools import HouseholdKnowledgeTools
from server.cognition.identity import ActivePersonContext
from server.cognition.models import CognitiveEvent
from server.cognition.owner_authentication import OwnerRequestResolver, owner_unlock_service
from server.cognition.response_plan import (
    ResponsePlan,
    SceneDescriptionRequest,
    TextTurnPayload,
    scene_unavailable_plan,
)
from server.exceptions import AudioContractError
from server.memory.consolidation import consolidate_turn
from server.memory.household_authorization import record_authorization_decision
from server.memory.policy_gated_v4_reader import PolicyGatedV4Reader
from server.pipeline import (
    _elapsed_ms,
    _log_pipeline_timing,
    _run_stt,
    _run_tts,
)
from server.schemas import TranscribeResponse
from server.settings import settings
from server.streaming import stream_pipeline, stream_response_plan
from server.text_turn import (
    ConsolidationScheduler,
    TextTurnResult,
    new_interaction_scope,
    prepare_text_turn,
    process_text_turn,
)

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


def _logged_voice_actor_resolver(
    request_identity: OwnerRequestResolver,
) -> ActivePersonResolver:
    """Wrap a request-scoped resolver to preserve the existing actor log line."""

    async def resolve_actor(event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
        actor = await request_identity.resolve_actor(event)
        turn_log.log_actor("voice", actor)
        return actor

    return resolve_actor


def _voice_controller(
    background_tasks: BackgroundTasks,
    *,
    request_identity: OwnerRequestResolver | None = None,
) -> CognitiveController:
    """Compose the bounded controller used by a public voice turn.

    Args:
        background_tasks: Queue used to schedule post-turn consolidation.
        request_identity: Optional request-scoped owner grant resolver. When
            omitted, the controller falls back to its own public-unknown
            defaults.
    """

    async def legacy_turn(message: str, conversation_id: str) -> TextTurnResult:
        """Delegate generic public conversation through the existing text service."""
        return await process_text_turn(
            message,
            conversation_id,
            schedule_consolidation=_consolidation_scheduler(background_tasks),
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
    background_tasks: BackgroundTasks,
) -> ConsolidationScheduler:
    """Adapt FastAPI background tasks to the text service callback."""

    def schedule(
        message: str,
        response: str,
        active_person: ActivePersonContext,
    ) -> None:
        background_tasks.add_task(
            consolidate_turn,
            message,
            response,
            active_person=active_person,
        )

    return schedule


async def _read_audio_upload(audio: UploadFile) -> bytes:
    """Read and validate WAV 16kHz, mono, int16 upload bytes."""
    audio_bytes = await audio.read()
    if len(audio_bytes) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Audio too large — max {settings.max_upload_bytes // 1024 // 1024} MB",
        )
    if not audio_bytes:
        raise HTTPException(status_code=422, detail="Audio file is empty")
    try:
        validate_wav_contract(audio_bytes)
    except AudioContractError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return audio_bytes


@router.post("/transcribe")
async def transcribe(
    audio: Annotated[UploadFile, File(description="WAV 16kHz mono int16")],
    background_tasks: BackgroundTasks,
    x_iroko_identity_token: Annotated[str | None, Header(alias="X-Iroko-Identity-Token")] = None,
) -> TranscribeResponse:
    """Transcribe audio, generate a robot response, and synthesize speech.

    Args:
        audio: WAV at 16kHz, mono, int16, within MAX_UPLOAD_BYTES.
        background_tasks: Queue for successful voice-turn consolidation.
        x_iroko_identity_token: Optional one-use owner unlock token. Absent,
            expired, replayed, or malformed tokens resolve to the public
            unknown actor without disclosing which case occurred.

    Returns:
        Existing audio response contract with text, WAV, emotion, timings,
        and whether this turn consumed a fresh owner unlock grant.

    Raises:
        HTTPException: 413 for size, 422 for WAV/speech, or 500 for STT/TTS.
    """
    request_start = time.perf_counter()
    request_identity = owner_unlock_service.for_request(x_iroko_identity_token)
    audio_bytes = await _read_audio_upload(audio)

    text_heard, stt_ms = await _run_stt(audio_bytes, [])

    if not text_heard.strip():
        logger.warning("STT returned empty transcript — audio was silence or too short")
        raise HTTPException(status_code=422, detail="No speech detected in audio")

    event = _voice_event_from_transcript(text_heard)
    controller = _voice_controller(background_tasks, request_identity=request_identity)
    decision = await controller.decide(event)

    plan: ResponsePlan
    if isinstance(decision, SceneDescriptionRequest):
        if settings.vision_enabled:
            # V0.5/V1 — a visual question needs a camera frame the classic
            # request did not carry: answer NOW with a short spoken cue and
            # ask the client for one (second round via /vision/respond). The
            # cue phrase covers the VLM latency; this stub turn is not
            # recorded in memory — the real exchange lands in round two.
            logger.info("Scene description requested: %r — requesting a frame", text_heard[:60])
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
    )


@router.post("/transcribe/stream")
async def transcribe_stream(
    audio: Annotated[UploadFile, File(description="WAV 16kHz mono int16")],
    background_tasks: BackgroundTasks,
    x_iroko_identity_token: Annotated[str | None, Header(alias="X-Iroko-Identity-Token")] = None,
) -> StreamingResponse:
    """Transcribe audio and stream the robot's reply sentence by sentence (R3).

    Args:
        audio: WAV at 16kHz, mono, int16, within MAX_UPLOAD_BYTES.
        background_tasks: Queue for successful voice-turn consolidation.
        x_iroko_identity_token: Optional one-use owner unlock token — same
            contract as classic /transcribe (Plan 0027).

    Returns:
        NDJSON events ordered as text, emotion, audio chunks, then timings.
        The terminal `done` event additionally reports whether this turn
        consumed a fresh owner unlock grant.

    Raises:
        HTTPException: 413 for size, 422 for WAV/speech, or 500 for STT.
    """
    request_start = time.perf_counter()
    request_identity = owner_unlock_service.for_request(x_iroko_identity_token)
    audio_bytes = await _read_audio_upload(audio)

    text_heard, stt_ms = await _run_stt(audio_bytes, [])

    if not text_heard.strip():
        logger.warning("STT returned empty transcript — audio was silence or too short")
        raise HTTPException(status_code=422, detail="No speech detected in audio")

    event = _voice_event_from_transcript(text_heard)
    decision = await _voice_controller(background_tasks, request_identity=request_identity).decide(
        event
    )
    # Streaming has no second-round frame upload — a scene request always
    # gets the fixed unavailable plan, regardless of VISION_ENABLED.
    plan: ResponsePlan | None = (
        scene_unavailable_plan() if isinstance(decision, SceneDescriptionRequest) else decision
    )
    turn_log.log_decision("stream", plan)
    if plan is not None:
        return StreamingResponse(
            stream_response_plan(
                text_heard=event.payload.message,
                plan=plan,
                stt_ms=stt_ms,
                request_start=request_start,
                authentication_consumed=request_identity.consumed,
            ),
            media_type="application/x-ndjson",
        )

    prepared = await prepare_text_turn(
        event.payload.message,
        event.payload.conversation_id,
    )

    return StreamingResponse(
        stream_pipeline(
            prepared=prepared,
            stt_ms=stt_ms,
            request_start=request_start,
            schedule_consolidation=_consolidation_scheduler(background_tasks),
        ),
        media_type="application/x-ndjson",
    )
