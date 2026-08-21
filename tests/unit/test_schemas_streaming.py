"""Unit tests for server.schemas_streaming — NDJSON wire compat (Plan 0027 Task 1).

The terminal ``StreamDoneEvent`` gains one additive ``authentication_consumed``
boolean. Every other field, every other event, and the wire order are
untouched by this plan.
"""

import pytest
from server.schemas_streaming import StreamDoneEvent


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
