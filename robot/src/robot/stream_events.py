"""NDJSON event types consumed from POST /transcribe/stream (R3).

Mirrors server/src/server/schemas_streaming.py — kept as a separate module
(not folded into server_client.py) for the same reason that file is split
from schemas.py: one small file per concern, under the 200-line limit.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TextHeardEvent:
    """First stream event — the STT transcript."""

    value: str


@dataclass(frozen=True)
class EmotionEvent:
    """Detected user emotion, emitted before any audio."""

    value: str


@dataclass(frozen=True)
class AudioEvent:
    """One synthesized sentence's audio."""

    text: str
    audio_base64: str
    duration_ms: int


@dataclass(frozen=True)
class DoneEvent:
    """Final event — per-stage latency."""

    stt_ms: int
    llm_ms: int
    tts_ms: int
    total_ms: int
    # Plan 0027: whether this turn consumed a fresh one-use owner unlock
    # grant. Additive — an older server's payload lacks the key and this
    # defaults to False (see parse_stream_event below).
    authentication_consumed: bool = False


@dataclass(frozen=True)
class ErrorEvent:
    """Terminal event for a post-header stream failure (Plan 0041, ADR 0012).

    ``code`` is a plain, forward-compatible string — a code this robot
    build has never seen must still parse safely, never raise. ``detail``
    is fixed, client-safe text chosen by the server, never a raw provider
    exception; safe to log, never meant to be spoken aloud.
    """

    code: str
    detail: str
    retryable: bool = False


StreamEvent = TextHeardEvent | EmotionEvent | AudioEvent | DoneEvent | ErrorEvent


def parse_stream_event(data: dict[str, Any]) -> StreamEvent:  # Any: raw NDJSON, heterogeneous
    """Build a typed StreamEvent from one decoded NDJSON line.

    Args:
        data: Decoded JSON object with a ``"type"`` discriminator field.

    Returns:
        The matching StreamEvent variant, built from known fields only —
        the wire contract allows adding fields without breaking older robots.

    Raises:
        ValueError: If ``"type"`` is missing or not a recognized event type.
    """
    match data.get("type"):
        case "text_heard":
            return TextHeardEvent(value=data["value"])
        case "emotion":
            return EmotionEvent(value=data["value"])
        case "audio":
            return AudioEvent(
                text=data["text"],
                audio_base64=data["audio_base64"],
                duration_ms=data["duration_ms"],
            )
        case "done":
            return DoneEvent(
                stt_ms=data["stt_ms"],
                llm_ms=data["llm_ms"],
                tts_ms=data["tts_ms"],
                total_ms=data["total_ms"],
                authentication_consumed=bool(data.get("authentication_consumed", False)),
            )
        case "error":
            return ErrorEvent(
                code=str(data["code"]),
                detail=str(data["detail"]),
                retryable=bool(data.get("retryable", False)),
            )
        case event_type:
            raise ValueError(f"Unknown stream event type: {event_type!r}")
