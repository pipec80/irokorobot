"""Unit tests for server.schemas_streaming — NDJSON wire compat (Plan 0027 Task 1).

The terminal ``StreamDoneEvent`` gains one additive ``authentication_consumed``
boolean. Every other field, every other event, and the wire order are
untouched by this plan.
"""

import pytest
from server.schemas_streaming import StreamDoneEvent, StreamErrorEvent


@pytest.mark.unit
def test_default_is_false() -> None:
    """Omitting the field entirely (existing call sites) must default to False."""
    event = StreamDoneEvent(stt_ms=1, llm_ms=2, tts_ms=3, total_ms=6)

    assert event.authentication_consumed is False
    assert '"authentication_consumed":false' in event.model_dump_json()


@pytest.mark.unit
def test_explicit_true_round_trips() -> None:
    """A consumed owner grant must serialize as true on the wire."""
    event = StreamDoneEvent(stt_ms=1, llm_ms=2, tts_ms=3, total_ms=6, authentication_consumed=True)

    assert event.authentication_consumed is True
    assert '"authentication_consumed":true' in event.model_dump_json()


# --- Plan 0067: the reply hint on `done` --------------------------------


@pytest.mark.unit
def test_done_event_defaults_to_no_short_reply_expected() -> None:
    """Omitting the field (every existing call site) must say no reply is expected."""
    event = StreamDoneEvent(stt_ms=1, llm_ms=2, tts_ms=3, total_ms=6)

    assert event.expects_short_reply is False
    assert '"expects_short_reply":false' in event.model_dump_json()


@pytest.mark.unit
def test_done_event_short_reply_round_trips() -> None:
    """A spoken offer must serialize the hint as true and parse back as true."""
    event = StreamDoneEvent(stt_ms=1, llm_ms=2, tts_ms=3, total_ms=6, expects_short_reply=True)

    wire = event.model_dump_json()

    assert '"expects_short_reply":true' in wire
    assert StreamDoneEvent.model_validate_json(wire).expects_short_reply is True


# --- Plan 0041: the terminal `error` event -----------------------------


@pytest.mark.unit
def test_error_event_has_the_documented_type_discriminator() -> None:
    event = StreamErrorEvent(code="tts_failed", detail="Speech synthesis failed")

    assert event.type == "error"
    assert '"type":"error"' in event.model_dump_json()


@pytest.mark.unit
def test_error_event_retryable_defaults_false() -> None:
    event = StreamErrorEvent(code="internal_error", detail="Internal error")

    assert event.retryable is False
    assert '"retryable":false' in event.model_dump_json()


@pytest.mark.unit
def test_error_event_carries_an_unknown_forward_compatible_code() -> None:
    """The `code` field is a plain string — a new code an old robot has never
    seen must still construct and serialize, never raise."""
    event = StreamErrorEvent(code="something_new_from_a_future_server", detail="...")

    assert event.code == "something_new_from_a_future_server"
