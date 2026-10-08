"""Decisions of ``streaming_render`` that need no TTS (Plan 0059)."""

import pytest
from server.streaming_protocol import StreamProtocolError
from server.streaming_render import (
    StreamFallbackReason,
    StreamState,
    _consume_body,
    classify_stream_end,
    llm_elapsed_ms,
)

_FENCE = "`" * 3  # built, not written: this file also lives inside a Markdown code fence


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
def test_a_reply_that_starts_with_an_underscore_wrapped_tag_is_never_released() -> None:
    """Audit A-1: the whole reply is refused, whatever the wrapper around the tag."""
    state = _state()

    with pytest.raises(StreamProtocolError):
        _consume_body("_EMOTION:joy_\nHola. Que tal.", state)

    assert state.emotion is None


@pytest.mark.unit
def test_consuming_a_body_without_a_pending_emotion_is_a_programming_error() -> None:
    """Audit A-7: audio must never go out before an emotion event could be sent."""
    state = _state(pending=None)

    with pytest.raises(RuntimeError):
        _consume_body("Hola. Bien", state)


@pytest.mark.unit
def test_a_tag_after_the_emotion_was_promoted_is_still_refused() -> None:
    state = _state(emotion="joy")

    with pytest.raises(StreamProtocolError):
        _consume_body("EMOTION: anger. Adiós.", state)


@pytest.mark.unit
def test_plain_sentences_are_released_and_promote_the_pending_emotion() -> None:
    state = _state()

    buffer, sentences = _consume_body("Hola. ¿Qué tal? Y", state)

    assert sentences == ["Hola.", "¿Qué tal?"]
    assert buffer == "Y"
    assert state.emotion == "joy"


@pytest.mark.unit
def test_content_without_a_closed_sentence_already_promotes_the_emotion() -> None:
    state = _state()

    buffer, sentences = _consume_body("Hola sin punto", state)

    assert (buffer, sentences) == ("Hola sin punto", [])
    assert state.emotion == "joy"


@pytest.mark.unit
@pytest.mark.parametrize("buffer", ["", "  \n", "   "])
def test_a_buffer_with_no_content_promotes_nothing(buffer: str) -> None:
    state = _state()

    _consume_body(buffer, state)

    assert state.emotion is None


@pytest.mark.unit
@pytest.mark.parametrize("buffer", ["E", "EMO", "emotion", "`", "``", "  EMOTION"])
def test_an_undecided_body_start_waits_and_speaks_or_promotes_nothing(buffer: str) -> None:
    state = _state()

    remaining, sentences = _consume_body(buffer, state)

    assert (remaining, sentences) == (buffer, [])
    assert state.emotion is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "buffer", ["{", '{"a": 1}', "[1]", f"{_FENCE}json", "EMOTION:joy\nHola", "emotion: joy Hola"]
)
def test_a_forbidden_body_start_is_refused_without_promoting(buffer: str) -> None:
    state = _state()

    with pytest.raises(StreamProtocolError):
        _consume_body(buffer, state)

    assert state.emotion is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "buffer, pending, emotion, expected",
    [
        ("", "neutral", None, StreamFallbackReason.EMPTY_STREAM),
        ("  \n", "neutral", None, StreamFallbackReason.EMPTY_STREAM),
        ("{", "neutral", None, StreamFallbackReason.INVALID_PROTOCOL),
        (f"{_FENCE}json", "neutral", None, StreamFallbackReason.INVALID_PROTOCOL),
        ("EMOTION:joy", "neutral", None, StreamFallbackReason.INVALID_PROTOCOL),
        ("EMOTION:joy\nHola", "neutral", None, StreamFallbackReason.INVALID_PROTOCOL),
        ("Adiós EMOTION:joy", "neutral", "neutral", StreamFallbackReason.INVALID_PROTOCOL),
        ("Hola", "neutral", None, None),
        ("E", "neutral", None, None),  # an undecided prefix at the end is ordinary text
        ("`", "neutral", None, None),
        ("Adiós", "neutral", "neutral", None),
        ("", "neutral", "neutral", None),
    ],
)
def test_the_end_of_the_stream_is_judged_in_one_place(
    buffer: str, pending: str | None, emotion: str | None, expected: StreamFallbackReason | None
) -> None:
    assert classify_stream_end(buffer, _state(pending=pending, emotion=emotion)) is expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "total_ms, stt_ms, tts_ms, expected",
    [(1000, 200, 300, 500), (100, 200, 300, 0), (500, 0, 0, 500), (0, 0, 0, 0)],
)
def test_the_llm_time_is_what_remains_and_never_negative(
    total_ms: int, stt_ms: int, tts_ms: int, expected: int
) -> None:
    assert llm_elapsed_ms(total_ms, stt_ms, tts_ms) == expected
