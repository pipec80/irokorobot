"""Sentence-streaming orchestration for POST /transcribe/stream (R3).

Kept out of routers/transcribe.py and pipeline.py (200-line file limit);
the classic /transcribe pipeline stays untouched. Emits NDJSON — one line
per event, see schemas_streaming.py — so the robot can play the first
sentence's audio while the LLM still generates the rest of the reply.

Vision-intent turns (V0.5) are intentionally not handled here — that
stub-turn branch stays exclusive to classic /transcribe; the robot only
routes plain voice turns through streaming (see app.py's robot_streaming flag).
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
import logging

from server import llm, llm_streaming, tts
from server.cognition.response_plan import ResponsePlan
from server.exceptions import LLMError
from server.pipeline import _elapsed_ms, _log_pipeline_timing
from server.schemas_streaming import (
    StreamAudioEvent,
    StreamDoneEvent,
    StreamEmotionEvent,
    StreamTextHeardEvent,
)
from server.sentences import split_first_sentence
from server.settings import settings
from server.text_turn import (
    ConsolidationScheduler,
    PreparedTextTurn,
    record_text_turn,
)

logger = logging.getLogger(__name__)


@dataclass
class _StreamState:
    """Mutable accumulator threaded through the streaming helpers below."""

    emotion: str | None = None
    response_parts: list[str] = field(default_factory=list)
    tts_ms_total: int = 0
    recordable: bool = True


async def _text_deltas(inputs: PreparedTextTurn) -> AsyncIterator[str]:
    """Yield "EMOTION:xxx\\n"-tagged text deltas, uniform across providers.

    Local Ollama streams token-by-token through ``llm_streaming``. The shared
    emotion-tag protocol keeps the sentence-splitting loop provider-agnostic.
    """
    async for delta in llm_streaming.generate_response_stream(
        inputs.message,
        context=inputs.context,
        history=inputs.history,
        onboarding=inputs.onboarding,
        onboarding_slot=inputs.onboarding_slot,
        user_emotion=inputs.user_emotion,
        active_person=inputs.active_person,
    ):
        yield delta


async def _synthesize_sentence(sentence: str, state: _StreamState) -> str:
    """Synthesize one sentence, update state, and return its NDJSON line."""
    audio_base64, duration_ms = await tts.synthesize(sentence)
    state.response_parts.append(sentence)
    state.tts_ms_total += duration_ms
    event = StreamAudioEvent(text=sentence, audio_base64=audio_base64, duration_ms=duration_ms)
    return event.model_dump_json() + "\n"


async def _consume_llm_stream(
    inputs: PreparedTextTurn,
    state: _StreamState,
) -> AsyncIterator[str]:
    """Consume LLM deltas, emit emotion once known, synthesize each sentence.

    The ``EMOTION:xxx\\n`` tag is only recognized once the buffer contains a
    full first line (see ``parse_streaming_emotion``). If the LLM stream ends
    before that ``\\n`` ever arrives — the model ignored the tag instruction,
    or the response was cut off mid-tag — ``state.emotion`` is still ``None``
    once this async for loop exhausts. That case is handled below the loop:
    the mandatory emotion event is emitted with the fallback value, and a
    buffer that looks like a truncated tag attempt is discarded instead of
    being spoken as if it were a normal sentence.
    """
    buffer = ""
    async for delta in _text_deltas(inputs):
        buffer += delta
        if state.emotion is None:
            parsed = llm_streaming.parse_streaming_emotion(buffer)
            if parsed is None:
                continue
            state.emotion, buffer = parsed
            yield StreamEmotionEvent(value=state.emotion).model_dump_json() + "\n"
        while (split := split_first_sentence(buffer)) is not None:
            sentence, buffer = split
            yield await _synthesize_sentence(sentence, state)

    tail = buffer.strip()
    if state.emotion is None:
        # Stream exhausted without ever completing the emotion tag line.
        # Fall back to neutral and emit the event before any audio, to keep
        # the documented text_heard -> emotion -> audio* -> done order.
        state.emotion = llm.FALLBACK_EMOTION
        yield StreamEmotionEvent(value=state.emotion).model_dump_json() + "\n"
        if tail.upper().startswith("EMOTION"):
            logger.warning("Streamed reply ended mid emotion tag — discarding: %r", tail)
            state.recordable = False
            return
    if tail:
        yield await _synthesize_sentence(tail, state)


async def _emit_fallback(state: _StreamState) -> AsyncIterator[str]:
    """Speak the local fallback phrase — mirrors pipeline._run_llm's degrade path."""
    if state.emotion is None:
        state.emotion = "neutral"
        yield StreamEmotionEvent(value=state.emotion).model_dump_json() + "\n"
    yield await _synthesize_sentence(settings.llm_fallback_phrase, state)


async def stream_response_plan(
    *,
    text_heard: str,
    plan: ResponsePlan,
    stt_ms: int,
    request_start: float,
) -> AsyncIterator[str]:
    """Render an already-authorized plan without LLM or memory work.

    Yields:
        NDJSON text, emotion, one 16kHz mono int16 WAV audio response, and
        final timing events.
    """
    yield StreamTextHeardEvent(value=text_heard).model_dump_json() + "\n"
    yield StreamEmotionEvent(value=plan.emotion).model_dump_json() + "\n"
    audio_base64, duration_ms = await tts.synthesize(plan.response)
    yield (
        StreamAudioEvent(
            text=plan.response,
            audio_base64=audio_base64,
            duration_ms=duration_ms,
        ).model_dump_json()
        + "\n"
    )
    total_ms = _elapsed_ms(request_start)
    _log_pipeline_timing(stt_ms, plan.duration_ms, duration_ms, total_ms)
    yield (
        StreamDoneEvent(
            stt_ms=stt_ms,
            llm_ms=plan.duration_ms,
            tts_ms=duration_ms,
            total_ms=total_ms,
        ).model_dump_json()
        + "\n"
    )


async def stream_pipeline(
    *,
    prepared: PreparedTextTurn,
    stt_ms: int,
    request_start: float,
    schedule_consolidation: ConsolidationScheduler,
) -> AsyncIterator[str]:
    """Stream STT->LLM->TTS as NDJSON, synthesizing speech sentence by sentence.

    Transport: NDJSON — chosen over WebSocket/SSE because it is trivially
    producible from a plain async generator via StreamingResponse, and
    consumable on the robot with httpx's ``client.stream()`` + ``aiter_lines()``
    (no extra dependency; a natural stepping stone to a future LiveKit
    transport).

    Event order: text_heard -> emotion -> audio (one per sentence, as each
    closes) -> done. On an LLM failure mid-stream, the fallback phrase is
    spoken as one more audio event rather than aborting — sentences already
    streamed to the client cannot be un-spoken.

    Args:
        prepared: Shared prompt inputs and internal scope for one voice request.
        stt_ms: STT elapsed time, measured by the caller.
        request_start: ``time.perf_counter()`` reading from request start.
        schedule_consolidation: Channel-owned background scheduling callback.

    Yields:
        NDJSON lines (each ending in ``\\n``), see schemas_streaming.py.
    """
    yield StreamTextHeardEvent(value=prepared.message).model_dump_json() + "\n"

    state = _StreamState()
    llm_failed = False
    try:
        async for line in _consume_llm_stream(prepared, state):
            yield line
    except (LLMError, ValueError) as exc:
        logger.error("Streaming LLM failed — speaking fallback phrase: %s", exc, exc_info=True)
        async for line in _emit_fallback(state):
            yield line
        llm_failed = True

    if not llm_failed and state.recordable and state.response_parts:
        record_text_turn(
            prepared.message,
            prepared.conversation_id,
            " ".join(state.response_parts),
            state.emotion or llm.FALLBACK_EMOTION,
            active_person=prepared.active_person,
            history_scope=prepared.history_scope,
            schedule_consolidation=schedule_consolidation,
        )

    total_ms = _elapsed_ms(request_start)
    llm_ms = max(0, total_ms - stt_ms - state.tts_ms_total)
    _log_pipeline_timing(stt_ms, llm_ms, state.tts_ms_total, total_ms)
    yield (
        StreamDoneEvent(
            stt_ms=stt_ms, llm_ms=llm_ms, tts_ms=state.tts_ms_total, total_ms=total_ms
        ).model_dump_json()
        + "\n"
    )
