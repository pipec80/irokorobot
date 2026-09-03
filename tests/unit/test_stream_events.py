"""Unit tests for robot.stream_events.parse_stream_event — NDJSON wire compat.

Plan 0027 Task 1: the terminal ``done`` event gains an additive
``authentication_consumed`` boolean. An older server's payload (field absent)
must parse as ``False`` so an updated robot stays compatible; a newer
payload's ``True`` must round-trip. Unknown event types remain rejected —
unaffected by this additive change.
"""

import pytest
from robot.stream_events import (
    AudioEvent,
    DoneEvent,
    EmotionEvent,
    ErrorEvent,
    TextHeardEvent,
    parse_stream_event,
)


@pytest.mark.unit
def test_done_without_field_defaults_to_false() -> None:
    """An older server's `done` payload (no such key) must not crash the robot."""
    event = parse_stream_event(
        {"type": "done", "stt_ms": 1, "llm_ms": 2, "tts_ms": 3, "total_ms": 6}
    )

    assert event == DoneEvent(stt_ms=1, llm_ms=2, tts_ms=3, total_ms=6)
    assert isinstance(event, DoneEvent)
    assert event.authentication_consumed is False


@pytest.mark.unit
def test_done_with_consumed_true_parses_true() -> None:
    """A fresh owner grant consumed this turn must surface as True."""
    event = parse_stream_event(
        {
            "type": "done",
            "stt_ms": 1,
            "llm_ms": 2,
            "tts_ms": 3,
            "total_ms": 6,
            "authentication_consumed": True,
        }
    )

    assert isinstance(event, DoneEvent)
    assert event.authentication_consumed is True


@pytest.mark.unit
def test_done_with_consumed_false_parses_false() -> None:
    """An explicit False (generic turn, non-consuming) must round-trip as False."""
    event = parse_stream_event(
        {
            "type": "done",
            "stt_ms": 1,
            "llm_ms": 2,
            "tts_ms": 3,
            "total_ms": 6,
            "authentication_consumed": False,
        }
    )

    assert isinstance(event, DoneEvent)
    assert event.authentication_consumed is False


@pytest.mark.unit
def test_other_event_types_unaffected() -> None:
    """The additive done field must not disturb the other three event types."""
    assert parse_stream_event({"type": "text_heard", "value": "hola"}) == TextHeardEvent(
        value="hola"
    )
    assert parse_stream_event({"type": "emotion", "value": "joy"}) == EmotionEvent(value="joy")
    assert parse_stream_event(
        {"type": "audio", "text": "hola", "audio_base64": "AAAA", "duration_ms": 5}
    ) == AudioEvent(text="hola", audio_base64="AAAA", duration_ms=5)


@pytest.mark.unit
def test_unknown_event_type_still_rejected() -> None:
    """Unknown discriminators must keep raising — the additive change is scoped to done."""
    with pytest.raises(ValueError, match="Unknown stream event type"):
        parse_stream_event({"type": "bogus"})


# --- Plan 0041: the terminal `error` event -----------------------------


@pytest.mark.unit
def test_error_event_parses_code_detail_and_retryable() -> None:
    event = parse_stream_event(
        {
            "type": "error",
            "code": "tts_failed",
            "detail": "Speech synthesis failed",
            "retryable": True,
        }
    )

    assert event == ErrorEvent(code="tts_failed", detail="Speech synthesis failed", retryable=True)


@pytest.mark.unit
def test_error_event_retryable_defaults_false() -> None:
    event = parse_stream_event(
        {"type": "error", "code": "internal_error", "detail": "Internal error"}
    )

    assert isinstance(event, ErrorEvent)
    assert event.retryable is False


@pytest.mark.unit
def test_error_event_with_an_unknown_code_still_parses_safely() -> None:
    """Forward compatibility: a code this robot has never seen must not raise."""
    event = parse_stream_event(
        {"type": "error", "code": "brand_new_code_from_the_future", "detail": "..."}
    )

    assert isinstance(event, ErrorEvent)
    assert event.code == "brand_new_code_from_the_future"
