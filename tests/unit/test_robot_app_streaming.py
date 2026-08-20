"""Unit tests for robot.app_streaming — streaming FSM states, all I/O mocked."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from robot.exceptions import AudioPlaybackError, ServerError
from robot.fsm_types import LoopContext, RobotState
from robot.stream_events import AudioEvent, DoneEvent, EmotionEvent, StreamEvent, TextHeardEvent

from robot import app_streaming, audio_playback


def _audio_event(text: str) -> AudioEvent:
    return AudioEvent(text=text, audio_base64="ZmFrZQ==", duration_ms=10)


_DONE = DoneEvent(stt_ms=1, llm_ms=1, tts_ms=1, total_ms=3)


async def _events(*items: StreamEvent) -> AsyncIterator[StreamEvent]:
    for item in items:
        yield item


@pytest.mark.unit
async def test_valid_stream_speaks_and_returns_idle(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A well-ordered stream must play every chunk and log the pipeline summary."""
    play_wav = AsyncMock()
    monkeypatch.setattr(audio_playback, "play_wav", play_wav)
    ctx = LoopContext(stream_request_start=100.0)
    ctx.stream_events = _events(EmotionEvent("joy"), _audio_event("Hola."), _DONE)

    with caplog.at_level("INFO", logger="robot.app_streaming"):
        state = await app_streaming.on_speaking_stream(ctx)

    assert state is RobotState.IDLE
    play_wav.assert_awaited_once()
    assert any("Hola." in record.message for record in caplog.records)
    assert any("chunk" in record.message.lower() for record in caplog.records)


@pytest.mark.unit
async def test_eof_without_done_is_rejected_after_partial_playback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Critical EOF regression: emotion + one audio + no done must ERROR.

    The audio that already arrived must still have played — the robot does
    not withhold speech it already validated up to that point, it only
    refuses to treat the incomplete stream as a successful turn.
    """
    play_wav = AsyncMock()
    monkeypatch.setattr(audio_playback, "play_wav", play_wav)
    ctx = LoopContext()
    ctx.stream_events = _events(EmotionEvent("joy"), _audio_event("Hola."))

    state = await app_streaming.on_speaking_stream(ctx)

    assert state is RobotState.ERROR
    play_wav.assert_awaited_once()


@pytest.mark.unit
async def test_done_before_audio_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    play_wav = AsyncMock()
    monkeypatch.setattr(audio_playback, "play_wav", play_wav)
    ctx = LoopContext()
    ctx.stream_events = _events(EmotionEvent("joy"), _DONE)

    state = await app_streaming.on_speaking_stream(ctx)

    assert state is RobotState.ERROR
    play_wav.assert_not_awaited()


@pytest.mark.unit
async def test_no_stream_events_returns_idle() -> None:
    ctx = LoopContext()

    assert await app_streaming.on_speaking_stream(ctx) is RobotState.IDLE


@pytest.mark.unit
async def test_playback_failure_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        audio_playback, "play_wav", AsyncMock(side_effect=AudioPlaybackError("device gone"))
    )
    ctx = LoopContext()
    ctx.stream_events = _events(EmotionEvent("joy"), _audio_event("Hola."), _DONE)

    assert await app_streaming.on_speaking_stream(ctx) is RobotState.ERROR


@pytest.mark.unit
async def test_chunk_start_callback_runs_before_play_wav_with_one_based_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The playback-start callback must fire immediately before each play_wav call."""
    calls: list[str] = []

    async def _tracking_play_wav(_wav_bytes: bytes) -> None:
        calls.append("play")

    monkeypatch.setattr(audio_playback, "play_wav", _tracking_play_wav)
    seen_indices: list[int] = []
    original_play_wav_stream = app_streaming.play_wav_stream

    async def _wrapped_play_wav_stream(chunks: AsyncIterator[bytes], **kwargs: object) -> None:
        def _on_chunk_start(index: int) -> None:
            seen_indices.append(index)
            calls.append(f"start-{index}")

        await original_play_wav_stream(chunks, on_chunk_start=_on_chunk_start)

    monkeypatch.setattr(app_streaming, "play_wav_stream", _wrapped_play_wav_stream)
    ctx = LoopContext()
    ctx.stream_events = _events(
        EmotionEvent("joy"), _audio_event("Uno."), _audio_event("Dos."), _DONE
    )

    state = await app_streaming.on_speaking_stream(ctx)

    assert state is RobotState.IDLE
    assert seen_indices == [1, 2]
    assert calls == ["start-1", "play", "start-2", "play"]


@pytest.mark.unit
async def test_thinking_stream_sets_request_start_before_first_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THINKING must timestamp the request before consuming the first event."""

    async def _fake_transcribe_stream(_audio: bytes) -> AsyncIterator[StreamEvent]:
        yield TextHeardEvent(value="hola")

    monkeypatch.setattr(app_streaming, "transcribe_stream", _fake_transcribe_stream)
    ctx = LoopContext(audio=b"x", stream_request_start=None)

    assert ctx.stream_request_start is None
    state = await app_streaming.on_thinking_stream(ctx)

    assert state is RobotState.SPEAKING
    assert ctx.stream_request_start is not None


@pytest.mark.unit
async def test_thinking_stream_server_error_goes_to_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _broken_transcribe_stream(_audio: bytes) -> AsyncIterator[StreamEvent]:
        raise ServerError("down")
        yield  # pragma: no cover - unreachable, keeps this an async generator

    monkeypatch.setattr(app_streaming, "transcribe_stream", _broken_transcribe_stream)
    ctx = LoopContext(audio=b"x")

    assert await app_streaming.on_thinking_stream(ctx) is RobotState.ERROR
