"""Unit tests for robot.app_streaming — streaming FSM states, all I/O mocked."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from robot.exceptions import AudioPlaybackError, CameraError, ServerError
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

    with caplog.at_level("DEBUG", logger="robot.app_streaming"):
        state = await app_streaming.on_speaking_stream(ctx)

    assert state is RobotState.IDLE
    play_wav.assert_awaited_once()
    messages = [record.message for record in caplog.records]
    assert any("Hola." in message for message in messages)
    assert any("First chunk received" in message for message in messages)
    assert any("First playback start" in message for message in messages)
    assert any("chunks=1" in message for message in messages)


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

    async def _fake_transcribe_stream(
        _audio: bytes, *, identity_token: str | None = None, frame: bytes | None = None
    ) -> AsyncIterator[StreamEvent]:
        del identity_token, frame
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
    async def _broken_transcribe_stream(
        _audio: bytes, *, identity_token: str | None = None, frame: bytes | None = None
    ) -> AsyncIterator[StreamEvent]:
        del identity_token, frame
        raise ServerError("down")
        yield  # pragma: no cover - unreachable, keeps this an async generator

    monkeypatch.setattr(app_streaming, "transcribe_stream", _broken_transcribe_stream)
    ctx = LoopContext(audio=b"x")

    assert await app_streaming.on_thinking_stream(ctx) is RobotState.ERROR


@pytest.mark.unit
async def test_thinking_stream_passes_the_held_identity_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Plan 0027: THINKING must forward ctx.identity_token to transcribe_stream."""
    seen: dict[str, object] = {}

    async def _fake_transcribe_stream(
        audio: bytes, *, identity_token: str | None = None, frame: bytes | None = None
    ) -> AsyncIterator[StreamEvent]:
        seen["audio"] = audio
        seen["identity_token"] = identity_token
        seen["frame"] = frame
        yield TextHeardEvent(value="hola")

    monkeypatch.setattr(app_streaming, "transcribe_stream", _fake_transcribe_stream)
    ctx = LoopContext(audio=b"x", identity_token="opaque-token")  # noqa: S106

    state = await app_streaming.on_thinking_stream(ctx)

    assert state is RobotState.SPEAKING
    assert seen["identity_token"] == "opaque-token"  # noqa: S105 — fixture value


@pytest.mark.unit
async def test_speaking_stream_clears_token_when_done_reports_consumed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A consumed grant must be cleared so it is never sent on the next turn."""
    monkeypatch.setattr(audio_playback, "play_wav", AsyncMock())
    ctx = LoopContext(identity_token="opaque-token")  # noqa: S106
    ctx.stream_events = _events(
        EmotionEvent("joy"),
        _audio_event("Hola."),
        DoneEvent(stt_ms=1, llm_ms=1, tts_ms=1, total_ms=3, authentication_consumed=True),
    )

    state = await app_streaming.on_speaking_stream(ctx)

    assert state is RobotState.IDLE
    assert ctx.identity_token is None


@pytest.mark.unit
async def test_speaking_stream_retains_token_when_done_reports_not_consumed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A generic turn's done (authentication_consumed=false) must not drop the token."""
    monkeypatch.setattr(audio_playback, "play_wav", AsyncMock())
    ctx = LoopContext(identity_token="opaque-token")  # noqa: S106
    ctx.stream_events = _events(EmotionEvent("joy"), _audio_event("Hola."), _DONE)

    state = await app_streaming.on_speaking_stream(ctx)

    assert state is RobotState.IDLE
    assert ctx.identity_token == "opaque-token"  # noqa: S105 — fixture value


@pytest.mark.unit
async def test_speaking_stream_retains_token_when_eof_before_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EOF before done must leave the token untouched — replay is denied server-side."""
    monkeypatch.setattr(audio_playback, "play_wav", AsyncMock())
    ctx = LoopContext(identity_token="opaque-token")  # noqa: S106
    ctx.stream_events = _events(EmotionEvent("joy"), _audio_event("Hola."))

    state = await app_streaming.on_speaking_stream(ctx)

    assert state is RobotState.ERROR
    assert ctx.identity_token == "opaque-token"  # noqa: S105 — fixture value


@pytest.mark.unit
async def test_thinking_stream_face_auth_disabled_never_captures_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default off: capture_frame must never run, and frame=None must reach transcribe_stream."""
    monkeypatch.setattr(app_streaming.settings, "robot_face_auth_enabled", False)
    capture_mock = MagicMock(return_value=b"jpeg-bytes")
    monkeypatch.setattr(app_streaming, "capture_frame", capture_mock)
    seen: dict[str, object] = {}

    async def _fake_transcribe_stream(
        _audio: bytes, *, identity_token: str | None = None, frame: bytes | None = None
    ) -> AsyncIterator[StreamEvent]:
        del identity_token
        seen["frame"] = frame
        yield TextHeardEvent(value="hola")

    monkeypatch.setattr(app_streaming, "transcribe_stream", _fake_transcribe_stream)
    ctx = LoopContext(audio=b"x")

    state = await app_streaming.on_thinking_stream(ctx)

    assert state is RobotState.SPEAKING
    capture_mock.assert_not_called()
    assert seen["frame"] is None


@pytest.mark.unit
async def test_thinking_stream_face_auth_enabled_captures_and_forwards_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Enabled: capture_frame must run (via asyncio.to_thread) and its bytes forwarded."""
    monkeypatch.setattr(app_streaming.settings, "robot_face_auth_enabled", True)
    capture_mock = MagicMock(return_value=b"jpeg-bytes")
    monkeypatch.setattr(app_streaming, "capture_frame", capture_mock)
    seen: dict[str, object] = {}

    async def _fake_transcribe_stream(
        _audio: bytes, *, identity_token: str | None = None, frame: bytes | None = None
    ) -> AsyncIterator[StreamEvent]:
        del identity_token
        seen["frame"] = frame
        yield TextHeardEvent(value="hola")

    monkeypatch.setattr(app_streaming, "transcribe_stream", _fake_transcribe_stream)
    ctx = LoopContext(audio=b"x")

    state = await app_streaming.on_thinking_stream(ctx)

    assert state is RobotState.SPEAKING
    capture_mock.assert_called_once()
    assert seen["frame"] == b"jpeg-bytes"


@pytest.mark.unit
async def test_thinking_stream_face_auth_camera_error_degrades_to_no_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dead webcam must not raise or route to ERROR — the turn proceeds with frame=None."""
    monkeypatch.setattr(app_streaming.settings, "robot_face_auth_enabled", True)
    monkeypatch.setattr(
        app_streaming, "capture_frame", MagicMock(side_effect=CameraError("no cam"))
    )
    seen: dict[str, object] = {}

    async def _fake_transcribe_stream(
        _audio: bytes, *, identity_token: str | None = None, frame: bytes | None = None
    ) -> AsyncIterator[StreamEvent]:
        del identity_token
        seen["frame"] = frame
        yield TextHeardEvent(value="hola")

    monkeypatch.setattr(app_streaming, "transcribe_stream", _fake_transcribe_stream)
    ctx = LoopContext(audio=b"x")

    state = await app_streaming.on_thinking_stream(ctx)

    assert state is RobotState.SPEAKING
    assert seen["frame"] is None


@pytest.mark.unit
async def test_thinking_stream_never_logs_frame_bytes(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Captured frame bytes must never reach any log record."""
    monkeypatch.setattr(app_streaming.settings, "robot_face_auth_enabled", True)
    frame_marker = b"fake-jpeg-marker"
    monkeypatch.setattr(app_streaming, "capture_frame", MagicMock(return_value=frame_marker))

    async def _fake_transcribe_stream(
        _audio: bytes, *, identity_token: str | None = None, frame: bytes | None = None
    ) -> AsyncIterator[StreamEvent]:
        del identity_token, frame
        yield TextHeardEvent(value="hola")

    monkeypatch.setattr(app_streaming, "transcribe_stream", _fake_transcribe_stream)
    ctx = LoopContext(audio=b"x")

    with caplog.at_level("DEBUG"):
        await app_streaming.on_thinking_stream(ctx)

    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert "fake-jpeg-marker" not in joined
