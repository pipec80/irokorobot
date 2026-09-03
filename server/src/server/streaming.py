"""Sentence-streaming orchestration for POST /transcribe/stream (R3).

Kept out of routers/transcribe.py and pipeline.py (200-line file limit);
the classic /transcribe pipeline stays untouched. Emits NDJSON so the robot
can play the first sentence's audio while the LLM still generates the rest.

P0-C6: state/render mechanics (StreamState, synthesis, fallback, protocol
validation) live in streaming_render.py; this module owns the consume loop
and re-raises a mid-stream TTS failure after logging the same metrics
``done`` would have. ``done`` itself is only reached after at least one
audio chunk already spoke — see ``streaming_render._done_event``.

Vision-intent turns (V0.5) are not handled here — that stub-turn branch
stays exclusive to classic /transcribe (see app.py's robot_streaming flag).
"""

from collections.abc import AsyncIterator
import logging
from typing import Literal

import httpx

from server import llm, llm_streaming, tts
from server.cognition.response_plan import ResponsePlan
from server.exceptions import LLMError, TTSError
from server.pipeline import _elapsed_ms, _log_pipeline_timing
from server.schemas_streaming import (
    StreamAudioEvent,
    StreamDoneEvent,
    StreamEmotionEvent,
    StreamTextHeardEvent,
)
from server.streaming_render import (
    StreamFallbackReason,
    StreamOutcome,
    StreamState,
    _consume_body,
    _consume_preamble,
    _done_event,
    _finalize_model_output,
    _log_stream_metrics,
    emit_fallback,
    synthesize_sentence,
)
from server.text_turn import (
    ConsolidationScheduler,
    PreparedTextTurn,
    record_text_turn,
)

logger = logging.getLogger(__name__)


async def _text_deltas(client: httpx.AsyncClient, inputs: PreparedTextTurn) -> AsyncIterator[str]:
    """Yield "EMOTION:xxx\\n"-tagged text deltas from local Ollama, token by token."""
    async for delta in llm_streaming.generate_response_stream(
        client,
        inputs.message,
        context=inputs.context,
        history=inputs.history,
        onboarding=inputs.onboarding,
        onboarding_slot=inputs.onboarding_slot,
        user_emotion=inputs.user_emotion,
        active_person=inputs.active_person,
    ):
        yield delta


async def _consume_llm_stream(
    client: httpx.AsyncClient, inputs: PreparedTextTurn, state: StreamState
) -> AsyncIterator[str]:
    """Consume LLM deltas, emit emotion once its body validates, synthesize sentences.

    Emotion is buffered in ``state.pending_emotion`` and only promoted once
    body content passes ``validate_streaming_body_start`` (see
    ``streaming_render._consume_body``). A protocol violation mid-stream
    converts into the same audible fallback as a provider failure.
    """
    buffer = ""
    async for delta in _text_deltas(client, inputs):
        buffer += delta
        if state.pending_emotion is None and state.emotion is None:
            buffer, consumed = _consume_preamble(buffer, state)
            if not consumed:
                continue
        emotion_before = state.emotion
        try:
            buffer, sentences = _consume_body(buffer, state)
        except LLMError:
            state.outcome = StreamOutcome.PROTOCOL_FALLBACK
            async for line in emit_fallback(state, reason=StreamFallbackReason.INVALID_PROTOCOL):
                yield line
            return
        if state.emotion is not None and emotion_before is None:
            yield StreamEmotionEvent(value=state.emotion).model_dump_json() + "\n"
        for sentence in sentences:
            yield await synthesize_sentence(sentence, state)

    async for line in _finalize_model_output(buffer, state):
        yield line


def _record_success(
    prepared: PreparedTextTurn,
    state: StreamState,
    scheduler: ConsolidationScheduler,
) -> None:
    """Persist a turn — only ever called for a fully successful stream."""
    if state.outcome is not StreamOutcome.OK or not state.recordable or not state.response_parts:
        return
    record_text_turn(
        prepared.message,
        prepared.conversation_id,
        " ".join(state.response_parts),
        state.emotion or llm.FALLBACK_EMOTION,
        active_person=prepared.active_person,
        history_scope=prepared.history_scope,
        schedule_consolidation=scheduler,
    )


async def stream_response_plan(
    *,
    text_heard: str,
    plan: ResponsePlan,
    stt_ms: int,
    request_start: float,
    authentication_consumed: bool = False,
    identity_source: Literal["face", "local_unlock"] | None = None,
) -> AsyncIterator[str]:
    """Render an already-authorized plan without LLM or memory work.

    Args:
        authentication_consumed: Whether this request's owner grant resolver
            consumed a fresh one-use token for this plan (Plan 0027).
            Carried only on the terminal ``done`` event.
        identity_source: Which evidence source identified the actor for this
            turn — ``"face"``, ``"local_unlock"``, or ``None`` (Plan 0029).
            Never a name or other protected value. Carried only on the
            terminal ``done`` event.

    Yields:
        NDJSON text, emotion, one 16kHz mono int16 WAV audio response, and
        final timing events.
    """
    yield StreamTextHeardEvent(value=text_heard).model_dump_json() + "\n"
    yield StreamEmotionEvent(value=plan.emotion).model_dump_json() + "\n"
    audio_base64, duration_ms = await tts.synthesize(plan.response)
    audio_event = StreamAudioEvent(
        text=plan.response, audio_base64=audio_base64, duration_ms=duration_ms
    )
    yield audio_event.model_dump_json() + "\n"
    total_ms = _elapsed_ms(request_start)
    _log_pipeline_timing(
        f"stream.{plan.source.value}", stt_ms, plan.duration_ms, duration_ms, total_ms
    )
    done_event = StreamDoneEvent(
        stt_ms=stt_ms,
        llm_ms=plan.duration_ms,
        tts_ms=duration_ms,
        total_ms=total_ms,
        authentication_consumed=authentication_consumed,
        identity_source=identity_source,
    )
    yield done_event.model_dump_json() + "\n"


async def stream_pipeline(
    *,
    client: httpx.AsyncClient,
    prepared: PreparedTextTurn,
    stt_ms: int,
    request_start: float,
    schedule_consolidation: ConsolidationScheduler,
) -> AsyncIterator[str]:
    """Stream STT->LLM->TTS as NDJSON, synthesizing speech sentence by sentence.

    Transport is NDJSON, not WebSocket/SSE: trivially producible from a plain
    async generator via StreamingResponse and consumable on the robot with
    httpx's ``aiter_lines()`` — no extra dependency.

    Event order: text_heard -> emotion -> audio (one per sentence) -> done.
    An LLM failure or any invalid model output (hybrid JSON, a truncated
    tag, an empty stream, ...) speaks the fallback phrase instead of
    aborting — never a silent success (P0-C6). A TTS failure logs the same
    metrics `done` would have and re-raises without emitting `done`.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039).
        prepared: Shared prompt inputs and internal scope for one voice request.
        stt_ms: STT elapsed time, measured by the caller.
        request_start: ``time.perf_counter()`` reading from request start.
        schedule_consolidation: Channel-owned background scheduling callback.

    Yields:
        NDJSON lines (each ending in ``\\n``), see schemas_streaming.py.
    """
    yield StreamTextHeardEvent(value=prepared.message).model_dump_json() + "\n"

    state = StreamState(request_start=request_start)
    try:
        async for line in _consume_llm_stream(client, prepared, state):
            yield line
    except TTSError:
        state.outcome = StreamOutcome.TTS_ERROR
        _log_stream_metrics(state, _elapsed_ms(request_start))
        raise
    except (LLMError, ValueError) as exc:
        logger.error("Streaming LLM failed — speaking fallback phrase: %s", exc, exc_info=True)
        state.outcome = (
            StreamOutcome.PARTIAL_FALLBACK if state.audio_chunks else StreamOutcome.LLM_FALLBACK
        )
        async for line in emit_fallback(state, reason=StreamFallbackReason.LLM_ERROR):
            yield line

    _record_success(prepared, state, schedule_consolidation)

    total_ms = _elapsed_ms(request_start)
    llm_ms = max(0, total_ms - stt_ms - state.tts_ms_total)
    _log_pipeline_timing("stream.legacy_text_turn", stt_ms, llm_ms, state.tts_ms_total, total_ms)
    yield _done_event(stt_ms, request_start, state)
