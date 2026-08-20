"""Render helpers guaranteeing audible success or safe fallback (P0-C6).

``streaming.py`` owns the orchestration loop; this module owns per-request
state, sentence synthesis, and the fallback path that lets ``done`` only
ever follow at least one contract-valid audio chunk. Output failing
``streaming_protocol.py``'s wire-format checks — hybrid JSON, a truncated
tag, an empty stream, a tag-only body, or plain text without a tag — is
discarded and replaced with one spoken fallback sentence, never silence.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import StrEnum
import logging

from server import llm, tts
from server.exceptions import LLMError
from server.pipeline import _elapsed_ms
from server.schemas_streaming import StreamAudioEvent, StreamDoneEvent, StreamEmotionEvent
from server.sentences import split_first_sentence
from server.settings import settings
from server.streaming_protocol import parse_streaming_emotion, validate_streaming_body_start

logger = logging.getLogger(__name__)


class StreamOutcome(StrEnum):
    """How one streamed turn ended — drives the final `done` log line."""

    OK = "ok"
    PROTOCOL_FALLBACK = "protocol_fallback"
    LLM_FALLBACK = "llm_fallback"
    PARTIAL_FALLBACK = "partial_fallback"
    TTS_ERROR = "tts_error"


class StreamFallbackReason(StrEnum):
    """Bounded, content-free reason logged alongside a fallback."""

    INVALID_PROTOCOL = "invalid_protocol"
    EMPTY_STREAM = "empty_stream"
    LLM_ERROR = "llm_error"


@dataclass
class StreamState:
    """Mutable accumulator threaded through one streamed turn."""

    request_start: float
    pending_emotion: str | None = None
    emotion: str | None = None
    response_parts: list[str] = field(default_factory=list)
    tts_ms_total: int = 0
    audio_chunks: int = 0
    first_audio_ms: int | None = None
    recordable: bool = True
    outcome: StreamOutcome = StreamOutcome.OK


async def synthesize_sentence(sentence: str, state: StreamState) -> str:
    """Synthesize one contract-valid sentence, updating chunk/timing state.

    Returns:
        One NDJSON ``audio`` line — WAV 16kHz mono int16 audio, base64.
    """
    audio_base64, duration_ms = await tts.synthesize(sentence)
    state.response_parts.append(sentence)
    state.tts_ms_total += duration_ms
    state.audio_chunks += 1
    if state.first_audio_ms is None:
        state.first_audio_ms = _elapsed_ms(state.request_start)
    logger.info(
        "Stream sentence synthesized: %r (duration_ms=%d chunk=%d)",
        sentence,
        duration_ms,
        state.audio_chunks,
    )
    event = StreamAudioEvent(text=sentence, audio_base64=audio_base64, duration_ms=duration_ms)
    return event.model_dump_json() + "\n"


async def emit_fallback(state: StreamState, *, reason: StreamFallbackReason) -> AsyncIterator[str]:
    """Speak a safe fallback — the sole path that closes a stream with no valid content.

    Emits ``neutral`` only when no emotion has been spoken yet; after
    partial audio it preserves the already-emitted emotion and adds only
    the fallback audio event. ``reason`` is bounded and content-free —
    never the raw candidate model output.
    """
    state.recordable = False
    logger.warning("Stream fallback: reason=%s", reason.value)
    if state.emotion is None:
        state.emotion = llm.FALLBACK_EMOTION
        yield StreamEmotionEvent(value=state.emotion).model_dump_json() + "\n"
    yield await synthesize_sentence(settings.llm_fallback_phrase, state)


def _consume_preamble(buffer: str, state: StreamState) -> tuple[str, bool]:
    """Consume the EMOTION preamble line once it is fully buffered.

    Returns:
        ``(remaining_buffer, True)`` once the preamble line was consumed
        (stored in ``state.pending_emotion``), or ``(buffer, False)`` while
        more input may still complete it.
    """
    parsed = parse_streaming_emotion(buffer)
    if parsed is None:
        return buffer, False
    state.pending_emotion, remainder = parsed
    return remainder, True


def _consume_body(buffer: str, state: StreamState) -> tuple[str, list[str]]:
    """Split complete sentences off the body, promoting emotion once valid.

    Promotes ``pending_emotion`` to emitted ``emotion`` the first time
    non-whitespace content passes ``validate_streaming_body_start``; hybrid
    JSON or a repeated tag never promotes and raises instead.

    Raises:
        LLMError: If the body content is structurally invalid.
    """
    if state.emotion is None:
        stripped = buffer.lstrip()
        if stripped:
            validate_streaming_body_start(stripped)
            state.emotion = state.pending_emotion
    sentences: list[str] = []
    while (split := split_first_sentence(buffer)) is not None:
        sentence, buffer = split
        sentences.append(sentence)
    return buffer, sentences


async def _finalize_model_output(buffer: str, state: StreamState) -> AsyncIterator[str]:
    """Validate stream EOF; emit the final sentence or a safe fallback."""
    if state.pending_emotion is None and state.emotion is None:
        try:
            parsed = parse_streaming_emotion(buffer, final=True)
        except LLMError:
            tail = buffer.strip()
            reason = (
                StreamFallbackReason.EMPTY_STREAM
                if not tail
                else StreamFallbackReason.INVALID_PROTOCOL
            )
            state.outcome = StreamOutcome.PROTOCOL_FALLBACK
            async for line in emit_fallback(state, reason=reason):
                yield line
            return
        if parsed is None:
            raise RuntimeError("Final parse returned no result instead of raising")
        state.pending_emotion, buffer = parsed
    tail = buffer.strip()
    if state.emotion is None:
        valid_body = bool(tail)
        if valid_body:
            try:
                validate_streaming_body_start(tail)
            except LLMError:
                valid_body = False
        if not valid_body:
            state.outcome = StreamOutcome.PROTOCOL_FALLBACK
            async for line in emit_fallback(state, reason=StreamFallbackReason.INVALID_PROTOCOL):
                yield line
            return
        if state.pending_emotion is None:
            raise RuntimeError("pending_emotion must be set before promoting to emotion")
        state.emotion = state.pending_emotion
        yield StreamEmotionEvent(value=state.emotion).model_dump_json() + "\n"
    if tail:
        yield await synthesize_sentence(tail, state)


def _done_event(stt_ms: int, request_start: float, state: StreamState) -> str:
    """Serialize the final timing event — requires at least one audio chunk.

    Correct orchestration never reaches ``audio_chunks == 0`` here (every
    fallback path speaks first); a violation is an orchestration bug, so
    this fails loudly instead of emitting a false ``done``.

    Raises:
        RuntimeError: If called before any audio chunk was emitted.
    """
    if state.audio_chunks < 1:
        raise RuntimeError("Refusing to emit done before any audio chunk was spoken")
    total_ms = _elapsed_ms(request_start)
    llm_ms = max(0, total_ms - stt_ms - state.tts_ms_total)
    logger.info(
        "Stream done: outcome=%s chunks=%d first_audio_ms=%s tts_ms=%dms total_ms=%dms",
        state.outcome.value,
        state.audio_chunks,
        state.first_audio_ms,
        state.tts_ms_total,
        total_ms,
    )
    done = StreamDoneEvent(
        stt_ms=stt_ms, llm_ms=llm_ms, tts_ms=state.tts_ms_total, total_ms=total_ms
    )
    return done.model_dump_json() + "\n"
