"""Audio endpoint — transcribe speech, generate a response, synthesize it.

Audio contract: WAV · 16000 Hz · mono · int16.
"""

import logging
import time
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from server import vision
from server.audio_contract import validate_wav_contract
from server.exceptions import AudioContractError
from server.memory.consolidation import consolidate_turn
from server.pipeline import (
    _elapsed_ms,
    _entity_hotwords,
    _log_pipeline_timing,
    _run_stt,
    _run_tts,
)
from server.schemas import TranscribeResponse
from server.settings import settings
from server.streaming import stream_pipeline
from server.text_turn import (
    ConsolidationScheduler,
    prepare_text_turn,
    process_text_turn,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Audio"])


def _consolidation_scheduler(
    background_tasks: BackgroundTasks,
) -> ConsolidationScheduler:
    """Adapt FastAPI background tasks to the text service callback."""

    def schedule(message: str, response: str) -> None:
        background_tasks.add_task(consolidate_turn, message, response)

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
) -> TranscribeResponse:
    """Transcribe audio, generate a robot response, and synthesize speech.

    Args:
        audio: WAV at 16kHz, mono, int16, within MAX_UPLOAD_BYTES.
        background_tasks: Queue for successful voice-turn consolidation.

    Returns:
        Existing audio response contract with text, WAV, emotion, and timings.

    Raises:
        HTTPException: 413 for size, 422 for WAV/speech, or 500 for STT/TTS.
    """
    request_start = time.perf_counter()
    audio_bytes = await _read_audio_upload(audio)

    # STT runs before the memory context is built, so known names are
    # fetched separately here to bias Whisper.
    hotwords = await _entity_hotwords()

    text_heard, stt_ms = await _run_stt(audio_bytes, hotwords)

    if not text_heard.strip():
        logger.warning("STT returned empty transcript — audio was silence or too short")
        raise HTTPException(status_code=422, detail="No speech detected in audio")

    # V0.5/V1 — visual question OR explicit face-enroll phrase detected:
    # answer NOW with a short spoken cue and ask the client for a frame
    # (second round via /vision/respond). The cue phrase covers the VLM
    # latency; this stub turn is not recorded in memory — the real
    # exchange lands in round two.
    if settings.vision_enabled and (
        vision.wants_vision(text_heard) or vision.wants_enroll(text_heard) is not None
    ):
        logger.info("Visual intent detected: %r — requesting a frame", text_heard[:60])
        audio_base64, duration_ms, tts_ms = await _run_tts(settings.vision_look_phrase)
        total_ms = _elapsed_ms(request_start)
        _log_pipeline_timing(stt_ms, 0, tts_ms, total_ms)
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
        )

    turn = await process_text_turn(
        text_heard,
        settings.voice_conversation_id,
        schedule_consolidation=_consolidation_scheduler(background_tasks),
    )
    audio_base64, duration_ms, tts_ms = await _run_tts(turn.response)

    total_ms = _elapsed_ms(request_start)
    _log_pipeline_timing(stt_ms, turn.duration_ms, tts_ms, total_ms)
    return TranscribeResponse(
        text_heard=text_heard,
        llm_response=turn.response,
        audio_base64=audio_base64,
        duration_ms=duration_ms,
        emotion=turn.emotion,
        stt_ms=stt_ms,
        llm_ms=turn.duration_ms,
        tts_ms=tts_ms,
        total_ms=total_ms,
    )


@router.post("/transcribe/stream")
async def transcribe_stream(
    audio: Annotated[UploadFile, File(description="WAV 16kHz mono int16")],
    background_tasks: BackgroundTasks,
) -> StreamingResponse:
    """Transcribe audio and stream the robot's reply sentence by sentence (R3).

    Args:
        audio: WAV at 16kHz, mono, int16, within MAX_UPLOAD_BYTES.
        background_tasks: Queue for successful voice-turn consolidation.

    Returns:
        NDJSON events ordered as text, emotion, audio chunks, then timings.

    Raises:
        HTTPException: 413 for size, 422 for WAV/speech, or 500 for STT.
    """
    request_start = time.perf_counter()
    audio_bytes = await _read_audio_upload(audio)

    hotwords = await _entity_hotwords()
    text_heard, stt_ms = await _run_stt(audio_bytes, hotwords)

    if not text_heard.strip():
        logger.warning("STT returned empty transcript — audio was silence or too short")
        raise HTTPException(status_code=422, detail="No speech detected in audio")

    prepared = await prepare_text_turn(
        text_heard,
        settings.voice_conversation_id,
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
