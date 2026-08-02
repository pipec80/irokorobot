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


StreamEvent = TextHeardEvent | EmotionEvent | AudioEvent | DoneEvent


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
            )
        case event_type:
            raise ValueError(f"Unknown stream event type: {event_type!r}")
