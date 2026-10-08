"""Render helpers guaranteeing audible success or safe fallback (P0-C6).

``streaming.py`` owns the orchestration loop; this module owns per-request
state, sentence synthesis, and the fallback path that lets ``done`` only
ever follow at least one contract-valid audio chunk. Output failing
``streaming_protocol.py``'s wire-format checks is discarded and replaced
with one spoken fallback sentence, never silence.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import StrEnum
import logging

from server import llm, tts
from server.conversation_log import log_spoken
from server.pipeline import _elapsed_ms
from server.schemas_streaming import (
    StreamAudioEvent,
    StreamDoneEvent,
    StreamEmotionEvent,
    StreamErrorEvent,
)
from server.sentences import split_first_sentence
from server.settings import settings
from server.streaming_protocol import (
    StreamProtocolError,
    is_body_start_undecided,
    reject_embedded_tag,
    validate_streaming_body_start,
)

logger = logging.getLogger(__name__)


class StreamOutcome(StrEnum):
    """How one streamed turn ended — drives the final `done` log line."""

    OK = "ok"
    PROTOCOL_FALLBACK = "protocol_fallback"
    LLM_FALLBACK = "llm_fallback"
    PARTIAL_FALLBACK = "partial_fallback"
    TTS_ERROR = "tts_error"


class StreamErrorCode(StrEnum):
    """Stable, bounded terminal-error codes (Plan 0041, ADR 0012).

    Values are wire-visible (the robot's ``ErrorEvent.code`` is a plain
    string, forward-compatible with codes it has never seen) — treat this
    enum as append-only.
    """

    TTS_FAILED = "tts_failed"
    INTERNAL_ERROR = "internal_error"


_ERROR_DETAIL: dict[StreamErrorCode, str] = {
    StreamErrorCode.TTS_FAILED: "Speech synthesis failed",
    StreamErrorCode.INTERNAL_ERROR: "Internal error",
}


def error_event(code: StreamErrorCode, *, retryable: bool = False) -> str:
    """Serialize the terminal `error` NDJSON line for one bounded failure code.

    Args:
        code: A stable ``StreamErrorCode`` — its mapped detail text is
            always fixed and client-safe, never a provider exception or
            raw model output.
        retryable: Whether retrying the turn may succeed.

    Returns:
        One NDJSON line (including the trailing newline).
    """
    event = StreamErrorEvent(code=code.value, detail=_ERROR_DETAIL[code], retryable=retryable)
    return event.model_dump_json() + "\n"


def llm_elapsed_ms(total_ms: int, stt_ms: int, tts_ms: int) -> int:
    """Return the time the LLM took: what is left of the total once STT and TTS are removed.

    Args:
        total_ms: Whole request time.
        stt_ms: Speech-to-text time.
        tts_ms: Summed text-to-speech time of every spoken sentence.

    Returns:
        The remainder in milliseconds, never negative (the parts are measured separately).
    """
    return max(0, total_ms - stt_ms - tts_ms)


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
    """Synthesize one contract-valid sentence into one NDJSON WAV audio line."""
    audio_base64, duration_ms = await tts.synthesize(sentence)
    state.response_parts.append(sentence)
    state.tts_ms_total += duration_ms
    state.audio_chunks += 1
    if state.first_audio_ms is None:
        state.first_audio_ms = _elapsed_ms(state.request_start)
    logger.info(
        "Stream sentence synthesized: %d chars (duration_ms=%d chunk=%d)",
        len(sentence),
        duration_ms,
        state.audio_chunks,
        extra={
            "event": "stream.sentence",
            "chars": len(sentence),
            "duration_ms": duration_ms,
            "chunk": state.audio_chunks,
        },
    )
    log_spoken(sentence)
    event = StreamAudioEvent(text=sentence, audio_base64=audio_base64, duration_ms=duration_ms)
    return event.model_dump_json() + "\n"


async def emit_fallback(state: StreamState, *, reason: StreamFallbackReason) -> AsyncIterator[str]:
    """Speak a safe fallback — the sole path that closes a stream with no valid content.

    Emits ``neutral`` only when no emotion has been spoken yet; after partial
    audio it preserves the emitted emotion and adds only fallback audio.
    ``reason`` is bounded and content-free — never the raw candidate output.
    """
    state.recordable = False
    logger.warning("Stream fallback: reason=%s", reason.value)
    if state.emotion is None:
        state.emotion = llm.FALLBACK_EMOTION
        yield StreamEmotionEvent(value=state.emotion).model_dump_json() + "\n"
    yield await synthesize_sentence(settings.llm_fallback_phrase, state)


def _consume_body(buffer: str, state: StreamState) -> tuple[str, list[str]]:
    """Split complete sentences off the reply, promoting the emotion once it is valid.

    Promotes ``pending_emotion`` (the user's emotion, decided at the start of the turn) to
    the emitted ``emotion`` the first time content passes ``validate_streaming_body_start``
    and every sentence closed in the same call passes ``reject_embedded_tag``. While the
    start is still a prefix of a forbidden one (``E``, a lone backtick) nothing is promoted
    or spoken: the next delta decides it. No sentence that carries a protocol tag is released.
    The promotion happens with the first content, not with the first closed sentence, so if a
    later sentence is rejected the fallback follows an ``emotion`` event that already carries
    the user's emotion; a call rejected on its own first content promotes nothing and the
    fallback sends ``neutral``. Either way exactly one ``emotion`` precedes the first audio,
    which is what the robot requires.

    Returns:
        ``(remaining_buffer, sentences)`` where ``sentences`` are safe to speak.

    Raises:
        StreamProtocolError: If the reply is structurally invalid or mentions a tag.
        RuntimeError: If ``state.pending_emotion`` was never set (a programming error).
    """
    if state.pending_emotion is None:
        raise RuntimeError("pending_emotion must be set before consuming the reply")
    has_content = bool(buffer.strip())
    if state.emotion is None and has_content:
        if is_body_start_undecided(buffer):
            return buffer, []
        validate_streaming_body_start(buffer)
    sentences: list[str] = []
    while (split := split_first_sentence(buffer)) is not None:
        sentence, buffer = split
        reject_embedded_tag(sentence)
        sentences.append(sentence)
    if state.emotion is None and has_content:
        state.emotion = state.pending_emotion
    return buffer, sentences


def classify_stream_end(buffer: str, state: StreamState) -> StreamFallbackReason | None:
    """Decide whether what is left when the stream ends can be spoken.

    The single judgement shared by production and by the evaluator under ``scripts/``.
    A tail that is still a prefix of a forbidden start (``E``) is ordinary text here.

    Args:
        buffer: Text received but not yet spoken.
        state: The turn's state at the end of the stream.

    Returns:
        ``None`` when the end can be spoken, otherwise the reason it cannot.
    """
    tail = buffer.strip()
    if state.emotion is None and not tail:
        return StreamFallbackReason.EMPTY_STREAM
    try:
        if state.emotion is None:
            validate_streaming_body_start(tail)
        reject_embedded_tag(tail)
    except StreamProtocolError:
        return StreamFallbackReason.INVALID_PROTOCOL
    return None


async def _finalize_model_output(buffer: str, state: StreamState) -> AsyncIterator[str]:
    """Validate stream EOF; emit the final sentence or a safe fallback."""
    reason = classify_stream_end(buffer, state)
    if reason is not None:
        state.outcome = StreamOutcome.PROTOCOL_FALLBACK
        async for line in emit_fallback(state, reason=reason):
            yield line
        return
    if state.emotion is None:
        if state.pending_emotion is None:
            raise RuntimeError("pending_emotion must be set before promoting to emotion")
        state.emotion = state.pending_emotion
        yield StreamEmotionEvent(value=state.emotion).model_dump_json() + "\n"
    tail = buffer.strip()
    if tail:
        yield await synthesize_sentence(tail, state)


def _log_stream_metrics(state: StreamState, total_ms: int) -> None:
    """Log the bounded operational metrics line shared by every stream outcome."""
    logger.info(
        "Stream done: outcome=%s chunks=%d first_audio_ms=%s tts_ms=%dms total_ms=%dms",
        state.outcome.value,
        state.audio_chunks,
        state.first_audio_ms,
        state.tts_ms_total,
        total_ms,
    )


def _done_event(
    stt_ms: int,
    request_start: float,
    state: StreamState,
    *,
    authentication_consumed: bool = False,
) -> str:
    """Serialize the final timing event — requires at least one audio chunk.

    Correct orchestration never reaches ``audio_chunks == 0`` here (every
    fallback path speaks first); a violation is an orchestration bug, so
    this fails loudly instead of emitting a false ``done``.

    Args:
        authentication_consumed: Whether this request consumed a fresh
            one-use owner grant (Plan 0027). Generic/legacy streaming never
            resolves an actor, so it always defaults false.

    Raises:
        RuntimeError: If called before any audio chunk was emitted.
    """
    if state.audio_chunks < 1:
        raise RuntimeError("Refusing to emit done before any audio chunk was spoken")
    total_ms = _elapsed_ms(request_start)
    llm_ms = llm_elapsed_ms(total_ms, stt_ms, state.tts_ms_total)
    _log_stream_metrics(state, total_ms)
    done = StreamDoneEvent(
        stt_ms=stt_ms,
        llm_ms=llm_ms,
        tts_ms=state.tts_ms_total,
        total_ms=total_ms,
        authentication_consumed=authentication_consumed,
    )
    return done.model_dump_json() + "\n"
