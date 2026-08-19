"""Unit tests for server.streaming_protocol: strict streaming wire format.

Covers the P0-C6 Task 2 defense-in-depth fix: parse_streaming_emotion and
validate_streaming_body_start must positively detect ANY invalid model
output — hybrid JSON, a truncated tag, an empty stream, or a repeated
protocol tag — instead of silently letting it through as speakable text.

Imports server.llm_streaming as a module (not the individual names) so a
missing attribute (validate_streaming_body_start does not exist there yet
pre-implementation) or an unsupported keyword argument (parse_streaming_emotion
does not accept ``final`` yet pre-implementation) fails inside a test
assertion rather than at collection time.
"""

from __future__ import annotations

import pytest
from server.exceptions import LLMError

from server import llm_streaming


@pytest.mark.unit
def test_parse_emotion_waits_for_fragmented_line() -> None:
    """A valid tag arriving token-by-token must not be rejected mid-stream."""
    fragments = ["EMO", "EMOTION", "EMOTION:", "EMOTION:jo", "EMOTION:joy"]
    for fragment in fragments:
        assert llm_streaming.parse_streaming_emotion(fragment, final=False) is None

    assert llm_streaming.parse_streaming_emotion("EMOTION:joy\n", final=False) == ("joy", "")
    assert llm_streaming.parse_streaming_emotion("EMOTION:joy\nhola", final=True) == (
        "joy",
        "hola",
    )

    # Unknown emotion still completes the line, but normalizes to neutral.
    assert llm_streaming.parse_streaming_emotion("EMOTION:cosmic\nhola", final=False) == (
        "neutral",
        "hola",
    )


@pytest.mark.unit
def test_parse_emotion_rejects_incomplete_final_line() -> None:
    """A stream that ends without ever completing a valid line is invalid."""
    incomplete_cases = [
        "",  # empty final stream
        "EMOTION:jo",  # truncated emotion tag, no newline
        "EMOTION:joy",  # missing newline entirely
        "hola sin protocolo",  # never started the protocol
    ]
    for buffer in incomplete_cases:
        with pytest.raises(LLMError) as exc_info:
            llm_streaming.parse_streaming_emotion(buffer, final=True)
        message = str(exc_info.value)
        assert message  # bounded, non-empty
        if buffer:
            assert buffer not in message


@pytest.mark.unit
def test_validate_body_rejects_structured_json() -> None:
    """Hybrid output mixing the JSON contract into the streaming body is invalid."""
    hybrid_bodies = [
        '{"response": "hola", "emotion": "joy"}',
        '{"response":"hola"}',
        '["hola", "chau"]',
        '```json\n{"response": "hola"}\n```',
        '  {"response": "hola"}',  # leading whitespace before the brace
    ]
    for body in hybrid_bodies:
        with pytest.raises(LLMError) as exc_info:
            llm_streaming.validate_streaming_body_start(body)
        assert body not in str(exc_info.value)


@pytest.mark.unit
def test_validate_body_rejects_repeated_protocol() -> None:
    """A second EMOTION: tag inside the body means the model repeated the preamble."""
    repeated_bodies = [
        "EMOTION:joy\nhola de nuevo",
        "emotion:joy\nhola",
        "  EMOTION:sadness\nhola",
    ]
    for body in repeated_bodies:
        with pytest.raises(LLMError) as exc_info:
            llm_streaming.validate_streaming_body_start(body)
        assert body not in str(exc_info.value)

    # A normal plain-text body must pass without raising.
    llm_streaming.validate_streaming_body_start("hola, como estas?")


@pytest.mark.unit
def test_full_hybrid_example_rejected_before_speech() -> None:
    """EMOTION:joy\\n{"response":"hola"} — valid tag, but the body is JSON."""
    result = llm_streaming.parse_streaming_emotion('EMOTION:joy\n{"response":"hola"}', final=True)
    assert result is not None
    emotion, body = result
    assert emotion == "joy"
    with pytest.raises(LLMError):
        llm_streaming.validate_streaming_body_start(body)


@pytest.mark.unit
def test_llm_streaming_reexports_protocol_functions() -> None:
    """llm_streaming.py must still resolve both names for existing call sites."""
    from server import streaming_protocol  # noqa: PLC0415 — keeps collection RED-safe

    assert llm_streaming.parse_streaming_emotion is streaming_protocol.parse_streaming_emotion
    assert (
        llm_streaming.validate_streaming_body_start
        is streaming_protocol.validate_streaming_body_start
    )
