"""Decisions of ``streaming_render`` that need no TTS (Plan 0058)."""

import pytest
from server.streaming_protocol import StreamProtocolError
from server.streaming_render import (
    StreamFallbackReason,
    StreamState,
    _consume_body,
    classify_stream_end,
    llm_elapsed_ms,
)


def _state(*, pending: str | None = "joy", emotion: str | None = None) -> StreamState:
    state = StreamState(request_start=0.0)
    state.pending_emotion = pending
    state.emotion = emotion
    return state


@pytest.mark.unit
def test_a_sentence_that_carries_a_tag_is_never_released() -> None:
    state = _state()

    with pytest.raises(StreamProtocolError):
        _consume_body("Hola. Luego EMOTION:anger. Adiós.", state)

    assert state.emotion is None  # a rejected batch must not promote the emotion event


@pytest.mark.unit
def test_plain_sentences_are_released_and_promote_the_emotion() -> None:
    state = _state()

    buffer, sentences = _consume_body("Hola. ¿Qué tal? Y", state)

    assert sentences == ["Hola.", "¿Qué tal?"]
    assert buffer == "Y"
    assert state.emotion == "joy"


@pytest.mark.unit
@pytest.mark.parametrize(
    "buffer, pending, emotion, expected",
    [
        ("", None, None, StreamFallbackReason.EMPTY_STREAM),
        ("  \n", None, None, StreamFallbackReason.EMPTY_STREAM),
        ("EMOTION:joy", None, None, StreamFallbackReason.INVALID_PROTOCOL),
        ("", "joy", None, StreamFallbackReason.INVALID_PROTOCOL),
        ("   ", "joy", None, StreamFallbackReason.INVALID_PROTOCOL),
        ("{", "joy", None, StreamFallbackReason.INVALID_PROTOCOL),
        ("Adiós EMOTION:joy", "joy", "joy", StreamFallbackReason.INVALID_PROTOCOL),
        ("Hola", "joy", None, None),
        ("E", "joy", None, None),
        ("Adiós", "joy", "joy", None),
        ("", "joy", "joy", None),
    ],
)
def test_the_end_of_the_stream_is_judged_in_one_place(
    buffer: str, pending: str | None, emotion: str | None, expected: StreamFallbackReason | None
) -> None:
    assert classify_stream_end(buffer, _state(pending=pending, emotion=emotion)) is expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "total_ms, stt_ms, tts_ms, expected", [(100, 30, 20, 50), (100, 0, 0, 100), (10, 30, 20, 0)]
)
def test_the_llm_time_is_what_is_left_after_stt_and_tts_and_never_negative(
    total_ms: int, stt_ms: int, tts_ms: int, expected: int
) -> None:
    assert llm_elapsed_ms(total_ms, stt_ms, tts_ms) == expected
