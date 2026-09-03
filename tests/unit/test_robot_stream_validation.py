"""Unit tests for robot.stream_validation — pure ordering policy, no I/O."""

import pytest
from robot.exceptions import ServerError
from robot.stream_events import AudioEvent, DoneEvent, EmotionEvent, ErrorEvent, TextHeardEvent
from robot.stream_validation import StreamValidationState

_EMOTION = EmotionEvent("joy")
_AUDIO = AudioEvent(text="Hola.", audio_base64="ZmFrZQ==", duration_ms=10)
_DONE = DoneEvent(stt_ms=1, llm_ms=1, tts_ms=1, total_ms=3)
_ERROR = ErrorEvent(code="tts_failed", detail="Speech synthesis failed", retryable=True)


@pytest.mark.unit
def test_valid_stream_finishes() -> None:
    """emotion -> audio -> done, then finish(), must not raise."""
    state = StreamValidationState()

    state.accept(_EMOTION)
    state.accept(_AUDIO)
    state.accept(_DONE)
    state.finish()

    assert state.emotion_seen is True
    assert state.audio_chunks == 1
    assert state.done_seen is True


@pytest.mark.unit
def test_done_before_audio_is_rejected() -> None:
    state = StreamValidationState()
    state.accept(_EMOTION)

    with pytest.raises(ServerError):
        state.accept(_DONE)


@pytest.mark.unit
def test_partial_audio_without_done_is_rejected() -> None:
    """EOF after emotion + audio but no done must fail at finish()."""
    state = StreamValidationState()
    state.accept(_EMOTION)
    state.accept(_AUDIO)

    with pytest.raises(ServerError):
        state.finish()


@pytest.mark.unit
def test_zero_audio_without_done_is_rejected() -> None:
    """EOF with nothing but emotion must fail at finish()."""
    state = StreamValidationState()
    state.accept(_EMOTION)

    with pytest.raises(ServerError):
        state.finish()


@pytest.mark.unit
def test_duplicate_done_is_rejected() -> None:
    state = StreamValidationState()
    state.accept(_EMOTION)
    state.accept(_AUDIO)
    state.accept(_DONE)

    with pytest.raises(ServerError):
        state.accept(_DONE)


@pytest.mark.unit
def test_duplicate_emotion_is_rejected() -> None:
    state = StreamValidationState()
    state.accept(_EMOTION)

    with pytest.raises(ServerError):
        state.accept(_EMOTION)


@pytest.mark.unit
def test_repeated_text_heard_is_rejected() -> None:
    state = StreamValidationState()

    with pytest.raises(ServerError):
        state.accept(TextHeardEvent(value="hola"))


@pytest.mark.unit
def test_audio_before_emotion_is_rejected() -> None:
    state = StreamValidationState()

    with pytest.raises(ServerError):
        state.accept(_AUDIO)


@pytest.mark.unit
def test_event_after_done_is_rejected() -> None:
    state = StreamValidationState()
    state.accept(_EMOTION)
    state.accept(_AUDIO)
    state.accept(_DONE)

    with pytest.raises(ServerError):
        state.accept(AudioEvent(text="mas", audio_base64="ZmFrZQ==", duration_ms=5))


# --- Plan 0041: the terminal `error` event -----------------------------


@pytest.mark.unit
def test_error_after_emotion_and_partial_audio_finishes_cleanly() -> None:
    """A TTS failure mid-stream ends in error — finish() must not demand a done."""
    state = StreamValidationState()
    state.accept(_EMOTION)
    state.accept(_AUDIO)

    state.accept(_ERROR)
    state.finish()  # must not raise

    assert state.error_seen is True
    assert state.done_seen is False


@pytest.mark.unit
def test_error_with_zero_audio_still_finishes_cleanly() -> None:
    """A TTS failure right after emotion (no audio played yet) is still a valid terminal."""
    state = StreamValidationState()
    state.accept(_EMOTION)

    state.accept(_ERROR)
    state.finish()  # must not raise


@pytest.mark.unit
def test_event_after_error_is_rejected() -> None:
    state = StreamValidationState()
    state.accept(_EMOTION)
    state.accept(_ERROR)

    with pytest.raises(ServerError):
        state.accept(_AUDIO)


@pytest.mark.unit
def test_duplicate_error_is_rejected() -> None:
    state = StreamValidationState()
    state.accept(_EMOTION)
    state.accept(_ERROR)

    with pytest.raises(ServerError):
        state.accept(_ERROR)


@pytest.mark.unit
def test_done_after_error_is_rejected() -> None:
    state = StreamValidationState()
    state.accept(_EMOTION)
    state.accept(_AUDIO)
    state.accept(_ERROR)

    with pytest.raises(ServerError):
        state.accept(_DONE)
