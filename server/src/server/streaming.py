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
import json
import logging
import time

import httpx

from server import llm, llm_streaming, tts
from server.cognition.response_plan import ResponsePlan
from server.conversation_log import log_spoken
from server.exceptions import LLMError, TTSError
from server.memory.candidate_dialogue import OfferPreparer
from server.pipeline import _elapsed_ms, _log_pipeline_timing
from server.schemas import IdentitySource
from server.schemas_streaming import (
    StreamAudioEvent,
    StreamDoneEvent,
    StreamEmotionEvent,
    StreamTextHeardEvent,
)
from server.streaming_protocol import StreamProtocolError
from server.streaming_render import (
    StreamErrorCode,
    StreamFallbackReason,
    StreamOutcome,
    StreamState,
    _consume_body,
    _done_event,
    _finalize_model_output,
    _log_stream_metrics,
    emit_fallback,
    error_event,
    llm_elapsed_ms,
    synthesize_model_sentence,
)
from server.text_turn import (
    PreparedTextTurn,
    ProposalScheduler,
    drop_offer,
    finish_offer,
    record_text_turn,
    start_offer,
)
from server.user_emotion import classify_user_emotion

logger = logging.getLogger(__name__)


async def _text_deltas(client: httpx.AsyncClient, inputs: PreparedTextTurn) -> AsyncIterator[str]:
    """Yield plain-text deltas from local Ollama, token by token."""
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
    """Consume LLM deltas, emit emotion once the reply validates, synthesize sentences.

    The reply is plain text. The turn's emotion is the user's, decided from their message
    before the model answers (``classify_user_emotion``, ADR 0018), buffered in
    ``state.pending_emotion`` and only promoted once the reply passes the body guards (see
    ``streaming_render._consume_body``). A protocol violation mid-stream converts into the
    same audible fallback as a provider failure.
    """
    state.pending_emotion = classify_user_emotion(inputs.message)
    buffer = ""
    async for delta in _text_deltas(client, inputs):
        buffer += delta
        emotion_before = state.emotion
        try:
            buffer, sentences = _consume_body(buffer, state)
        except StreamProtocolError:
            state.outcome = StreamOutcome.PROTOCOL_FALLBACK
            async for line in emit_fallback(state, reason=StreamFallbackReason.INVALID_PROTOCOL):
                yield line
            return
        if state.emotion is not None and emotion_before is None:
            yield StreamEmotionEvent(value=state.emotion).model_dump_json() + "\n"
        for sentence in sentences:
            if (audio := await synthesize_model_sentence(sentence, state)) is not None:
                yield audio

    async for line in _finalize_model_output(buffer, state):
        yield line


def _succeeded(state: StreamState) -> bool:
    """Whether the whole reply was spoken from valid model output (no fallback)."""
    return state.outcome is StreamOutcome.OK and state.recordable and bool(state.response_parts)


def _record_success(
    prepared: PreparedTextTurn,
    state: StreamState,
    scheduler: ProposalScheduler,
) -> None:
    """Persist a turn — only ever called for a fully successful stream."""
    if not _succeeded(state):
        return
    record_text_turn(
        prepared.message,
        " ".join(state.response_parts),
        active_person=prepared.active_person,
        continuity_turn=prepared.continuity,
        schedule_proposal=scheduler,
    )


def _note_offer_overhead(state: StreamState, started: float) -> None:
    """Record how long the offer step took beyond its own synthesis (kept out of llm_ms)."""
    spent = round((time.perf_counter() - started) * 1000)
    state.offer_overhead_ms = max(0, spent - state.offer_tts_ms)


async def _offer_event(offer: str, state: StreamState) -> str | None:
    """Synthesize the memory offer as one more audio event with empty text (ADR 0021 decision 9).

    The text stays empty, so the robot prints nothing, and the offer never reaches
    ``log_spoken``: it carries a value. Its synthesis counts as TTS time, so ``llm_ms`` stays
    the model's.

    Audio contract: the event carries one base64 WAV clip — 16 000 Hz, mono, int16.

    Args:
        offer: The spoken offer phrase; it carries a value, so a failure logs only the class.
        state: The turn's stream state; its TTS totals are updated with this synthesis.

    Returns:
        The NDJSON ``audio`` line (ending in ``\\n``), or ``None`` when the synthesis failed.
        Any ``Exception`` is caught here, not only ``TTSError``/``ValueError``: the reply was
        already spoken, so a broken offer is skipped and never costs the turn its ``done``.
    """
    try:
        audio_base64, duration_ms = await tts.synthesize(offer)
    except Exception as exc:  # the reply was spoken: any failure of the offer is skipped
        logger.warning("Memory offer not synthesized (%s)", type(exc).__name__)
        return None
    state.tts_ms_total += duration_ms
    state.offer_tts_ms = duration_ms
    event = StreamAudioEvent(text="", audio_base64=audio_base64, duration_ms=duration_ms)
    return event.model_dump_json() + "\n"


async def stream_response_plan(
    *,
    text_heard: str,
    plan: ResponsePlan,
    stt_ms: int,
    request_start: float,
    authentication_consumed: bool = False,
    identity_source: IdentitySource | None = None,
) -> AsyncIterator[str]:
    """Render an already-authorized plan without LLM or memory work.

    Args:
        authentication_consumed: Whether this request's owner grant resolver
            consumed a fresh one-use token for this plan (Plan 0027).
            Carried only on the terminal ``done`` event.
        identity_source: Which evidence source identified the actor for this
            turn — ``"face"``, ``"face_voice"``, ``"local_unlock"``, or ``None``
            (Plans 0029 and 0054).
            Never a name or other protected value. Carried only on the
            terminal ``done`` event.

    Yields:
        NDJSON text, emotion, one 16kHz mono int16 WAV audio response, and
        final timing events.
    """
    yield StreamTextHeardEvent(value=text_heard).model_dump_json() + "\n"
    yield StreamEmotionEvent(value=plan.emotion).model_dump_json() + "\n"
    audio_base64, duration_ms = await tts.synthesize(plan.response)
    log_spoken(plan.response)
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
    schedule_proposal: ProposalScheduler,
    prepare_offer: OfferPreparer | None = None,
) -> AsyncIterator[str]:
    """Stream STT->LLM->TTS as NDJSON, synthesizing speech sentence by sentence.

    Transport is NDJSON, not WebSocket/SSE: trivially producible from a plain
    async generator via StreamingResponse and consumable on the robot with
    httpx's ``aiter_lines()`` — no extra dependency.

    Event order: text_heard -> emotion -> audio (one per sentence) -> the offer's audio, with
    empty text, when one was prepared -> done.
    An LLM failure or any invalid model output (hybrid JSON, a protocol tag,
    an empty stream, ...) speaks the fallback phrase instead of
    aborting — never a silent success (P0-C6). A TTS failure logs the same
    metrics `done` would have and re-raises without emitting `done`.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039).
        prepared: Shared prompt inputs and internal scope for one voice request.
        stt_ms: STT elapsed time, measured by the caller.
        request_start: ``time.perf_counter()`` reading from request start.
        schedule_proposal: Channel-owned background proposal scheduling callback.
        prepare_offer: Channel-owned memory-offer preparation (ADR 0021 decision 9); it runs while
            the model streams, and a prepared offer is spoken after the reply, before ``done``.

    Yields:
        NDJSON lines (each ending in ``\\n``), see schemas_streaming.py.
    """
    yield StreamTextHeardEvent(value=prepared.message).model_dump_json() + "\n"

    state = StreamState(request_start=request_start)
    offer_task = start_offer(prepare_offer, prepared.active_person)
    try:
        try:
            async for line in _consume_llm_stream(client, prepared, state):
                yield line
        except TTSError:
            state.outcome = StreamOutcome.TTS_ERROR
            _log_stream_metrics(state, _elapsed_ms(request_start))
            # Let the cancelled preparation finish before the error propagates, so no
            # background task outlives the turn.
            await finish_offer(offer_task, reply_failed=True)
            raise
        except (LLMError, ValueError) as exc:
            if llm.is_connectivity_failure(exc):
                logger.warning("Streaming LLM unreachable — speaking fallback phrase: %s", exc)
            else:
                logger.error(
                    "Streaming LLM failed — speaking fallback phrase: %s", exc, exc_info=True
                )
            state.outcome = (
                StreamOutcome.PARTIAL_FALLBACK if state.audio_chunks else StreamOutcome.LLM_FALLBACK
            )
            async for line in emit_fallback(state, reason=StreamFallbackReason.LLM_ERROR):
                yield line

        _record_success(prepared, state, schedule_proposal)
        offer_started = time.perf_counter()
        offer = await finish_offer(offer_task, reply_failed=not _succeeded(state))
        offer_line = await _offer_event(offer, state) if offer is not None else None
        if offer_line is not None:
            state.offer_spoken = True
            yield offer_line
    finally:
        # A client that hangs up mid-stream must not leave the preparation running.
        drop_offer(offer_task)
    _note_offer_overhead(state, offer_started)

    total_ms = _elapsed_ms(request_start)
    llm_ms = llm_elapsed_ms(total_ms, stt_ms, state.tts_ms_total + state.offer_overhead_ms)
    _log_pipeline_timing("stream.legacy_text_turn", stt_ms, llm_ms, state.tts_ms_total, total_ms)
    yield _done_event(stt_ms, request_start, state)


_TERMINAL_TYPES = frozenset({"done", "error"})


async def guarantee_terminal_event(events: AsyncIterator[str]) -> AsyncIterator[str]:
    """Guarantee every wrapped stream ends in exactly one `done`/`error`, then EOF.

    The single boundary Task 2 (Plan 0041, ADR 0012) applies at the router,
    wrapping every stream producer (``stream_pipeline``, ``stream_response_plan``)
    so a post-header failure — known (``TTSError``) or genuinely unexpected —
    never truncates the ASGI connection. A client disconnect
    (``asyncio.CancelledError``) is never caught here: it is not an
    ``Exception`` subclass, so it always propagates untouched and nothing is
    emitted into a transport that is already gone.

    Once a terminal event has passed through, the guarantee is spent: any
    further producer line is a producer-contract violation and is dropped
    (the generator is still drained so its own cleanup runs), and a
    producer that then raises is logged but never gets a second terminal
    event on the wire.

    Args:
        events: The wrapped generator's own NDJSON lines.

    Yields:
        Every line ``events`` yields up to and including its first
        `done`/`error`, then nothing more. If ``events`` raises or ends
        before ever yielding a terminal line, exactly one terminal `error`
        line is appended.
    """
    saw_terminal = False
    try:
        async for line in events:
            if saw_terminal:
                logger.error(
                    "Stream produced a line after its terminal event — dropping it (producer bug)"
                )
                continue
            yield line
            try:
                event_type = json.loads(line).get("type")
            except (ValueError, TypeError):
                event_type = None
            if event_type in _TERMINAL_TYPES:
                saw_terminal = True
    except TTSError as exc:
        if saw_terminal:
            logger.error("Streaming TTS failed after the terminal event: %s", exc, exc_info=True)
            return
        logger.error("Streaming TTS failed after headers: %s", exc, exc_info=True)
        yield error_event(StreamErrorCode.TTS_FAILED, retryable=True)
        return
    except Exception as exc:
        if saw_terminal:
            logger.error(
                "Unhandled streaming failure after the terminal event: %s", exc, exc_info=True
            )
            return
        logger.error("Unhandled streaming failure after headers: %s", exc, exc_info=True)
        yield error_event(StreamErrorCode.INTERNAL_ERROR)
        return
    if not saw_terminal:
        logger.error("Stream ended without a terminal event — orchestration bug")
        yield error_event(StreamErrorCode.INTERNAL_ERROR)
