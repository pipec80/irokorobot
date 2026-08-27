"""Unit tests for the robot FSM (robot.app) — all I/O mocked."""

import base64
from dataclasses import replace
from datetime import UTC, datetime
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from robot.app import LoopContext, RobotState
from robot.exceptions import AudioCaptureError, CameraError, NoSpeechError, ServerError
from robot.server_client import TranscribeResult

from robot import app, app_streaming, server_client

_FAKE_RESULT = TranscribeResult(
    text_heard="hola robot",
    llm_response="hola humano",
    audio_base64=base64.b64encode(b"fake-wav").decode("ascii"),
    duration_ms=42,
    emotion="joy",
)

# Round-1 vision cue: the server asked for a camera frame.
_VISION_CUE_RESULT = replace(
    _FAKE_RESULT, text_heard="¿qué ves?", llm_response="A ver...", vision_requested=True
)


@pytest.fixture(autouse=True)
def _classic_mode_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate this file's classic-FSM tests from a developer's local .env.

    ``Settings()`` reads a real, untracked ``.env`` at import time, so a
    developer machine with ``ROBOT_STREAMING=true`` would otherwise leak
    into every test here and silently route THINKING through the streaming
    module instead of the classic path under test. Tests that specifically
    exercise streaming (e.g. the F-08 guard) override this via their own
    ``monkeypatch.setattr`` call.
    """
    monkeypatch.setattr(app.settings, "robot_streaming", False)


@pytest.mark.unit
async def test_idle_resets_context_and_goes_to_listening() -> None:
    ctx = LoopContext(audio=b"stale", result=_FAKE_RESULT)

    next_state = await app.tick(RobotState.IDLE, ctx)

    assert next_state == RobotState.LISTENING
    assert ctx.audio == b""
    assert ctx.result is None


@pytest.mark.unit
async def test_idle_resets_stream_request_start() -> None:
    """IDLE must clear the streaming request timestamp for the next turn."""
    ctx = LoopContext(stream_request_start=123.0)

    await app.tick(RobotState.IDLE, ctx)

    assert ctx.stream_request_start is None


@pytest.mark.unit
async def test_listening_with_speech_goes_to_thinking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app, "capture_utterance", AsyncMock(return_value=b"wav-bytes"))
    ctx = LoopContext()

    assert await app.tick(RobotState.LISTENING, ctx) == RobotState.THINKING
    assert ctx.audio == b"wav-bytes"


@pytest.mark.unit
async def test_listening_timeout_returns_to_idle(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty capture (onset timeout) must cycle back to IDLE, not call the server."""
    monkeypatch.setattr(app, "capture_utterance", AsyncMock(return_value=b""))

    assert await app.tick(RobotState.LISTENING, LoopContext()) == RobotState.IDLE


@pytest.mark.unit
async def test_listening_capture_error_goes_to_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        app, "capture_utterance", AsyncMock(side_effect=AudioCaptureError("mic gone"))
    )

    assert await app.tick(RobotState.LISTENING, LoopContext()) == RobotState.ERROR


@pytest.mark.unit
async def test_thinking_server_error_goes_to_error_not_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ServerError must route to ERROR — the loop survives (P0-3)."""
    monkeypatch.setattr(app, "transcribe", AsyncMock(side_effect=ServerError("server down")))

    assert await app.tick(RobotState.THINKING, LoopContext(audio=b"x")) == RobotState.ERROR


@pytest.mark.unit
async def test_thinking_no_speech_returns_to_idle_not_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ambient noise (server 422) must cycle back to IDLE without the ERROR wait."""
    monkeypatch.setattr(app, "transcribe", AsyncMock(side_effect=NoSpeechError("silence")))

    assert await app.tick(RobotState.THINKING, LoopContext(audio=b"x")) == RobotState.IDLE


@pytest.mark.unit
async def test_thinking_success_goes_to_speaking(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app, "transcribe", AsyncMock(return_value=_FAKE_RESULT))
    ctx = LoopContext(audio=b"x")

    assert await app.tick(RobotState.THINKING, ctx) == RobotState.SPEAKING
    assert ctx.result == _FAKE_RESULT


@pytest.mark.unit
async def test_speaking_plays_decoded_audio_and_never_captures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Half-duplex: SPEAKING plays the WAV and must not touch the microphone."""
    play_mock = AsyncMock()
    capture_mock = AsyncMock()
    monkeypatch.setattr(app, "play_wav", play_mock)
    monkeypatch.setattr(app, "capture_utterance", capture_mock)
    ctx = LoopContext(result=_FAKE_RESULT)

    next_state = await app.tick(RobotState.SPEAKING, ctx)

    assert next_state == RobotState.IDLE
    play_mock.assert_awaited_once_with(b"fake-wav")
    capture_mock.assert_not_awaited()


@pytest.mark.unit
async def test_speaking_without_result_goes_to_idle() -> None:
    assert await app.tick(RobotState.SPEAKING, LoopContext()) == RobotState.IDLE


@pytest.mark.unit
async def test_speaking_with_vision_request_goes_to_looking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After speaking the cue phrase, a vision_requested result must LOOK."""
    monkeypatch.setattr(app, "play_wav", AsyncMock())
    ctx = LoopContext(result=_VISION_CUE_RESULT)

    assert await app.tick(RobotState.SPEAKING, ctx) == RobotState.LOOKING


@pytest.mark.unit
async def test_looking_captures_sends_and_speaks(monkeypatch: pytest.MonkeyPatch) -> None:
    """LOOKING captures one frame, asks the server, and speaks the answer.

    Half-duplex holds: the microphone is never touched while looking."""
    capture_mock = MagicMock(return_value=b"jpeg-bytes")
    mic_mock = AsyncMock()
    vision_result = replace(_FAKE_RESULT, llm_response="¡Veo una bola roja!")
    respond_mock = AsyncMock(return_value=vision_result)
    monkeypatch.setattr(app, "capture_frame", capture_mock)
    monkeypatch.setattr(app, "respond_vision", respond_mock)
    monkeypatch.setattr(app, "capture_utterance", mic_mock)
    ctx = LoopContext(result=_VISION_CUE_RESULT)

    next_state = await app.tick(RobotState.LOOKING, ctx)

    assert next_state == RobotState.SPEAKING
    assert ctx.result == vision_result
    respond_mock.assert_awaited_once_with("¿qué ves?", b"jpeg-bytes")
    mic_mock.assert_not_awaited()


@pytest.mark.unit
async def test_looking_camera_error_returns_to_idle(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dead webcam must not kill the loop — log and resume listening."""
    monkeypatch.setattr(app, "capture_frame", MagicMock(side_effect=CameraError("no cam")))
    ctx = LoopContext(result=_VISION_CUE_RESULT)

    assert await app.tick(RobotState.LOOKING, ctx) == RobotState.IDLE


@pytest.mark.unit
async def test_looking_server_error_returns_to_idle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app, "capture_frame", MagicMock(return_value=b"jpeg"))
    monkeypatch.setattr(app, "respond_vision", AsyncMock(side_effect=ServerError("down")))
    ctx = LoopContext(result=_VISION_CUE_RESULT)

    assert await app.tick(RobotState.LOOKING, ctx) == RobotState.IDLE


@pytest.mark.unit
async def test_full_vision_cycle(monkeypatch: pytest.MonkeyPatch) -> None:
    """Vision turn: IDLE → LISTENING → THINKING → SPEAKING → LOOKING →
    SPEAKING → IDLE — the second result carries vision_requested=False."""
    vision_result = replace(_FAKE_RESULT, llm_response="¡Veo una bola roja!")
    monkeypatch.setattr(app, "capture_utterance", AsyncMock(return_value=b"wav"))
    monkeypatch.setattr(app, "transcribe", AsyncMock(return_value=_VISION_CUE_RESULT))
    monkeypatch.setattr(app, "play_wav", AsyncMock())
    monkeypatch.setattr(app, "capture_frame", MagicMock(return_value=b"jpeg"))
    monkeypatch.setattr(app, "respond_vision", AsyncMock(return_value=vision_result))

    ctx = LoopContext()
    visited = [RobotState.IDLE]
    state = RobotState.IDLE
    for _ in range(6):
        state = await app.tick(state, ctx)
        visited.append(state)

    assert visited == [
        RobotState.IDLE,
        RobotState.LISTENING,
        RobotState.THINKING,
        RobotState.SPEAKING,
        RobotState.LOOKING,
        RobotState.SPEAKING,
        RobotState.IDLE,
    ]


@pytest.mark.unit
async def test_error_recovers_to_idle(monkeypatch: pytest.MonkeyPatch) -> None:
    """ERROR must wait and recover — the robot never stays down."""
    sleep_mock = AsyncMock()
    monkeypatch.setattr(app.asyncio, "sleep", sleep_mock)

    assert await app.tick(RobotState.ERROR, LoopContext()) == RobotState.IDLE
    sleep_mock.assert_awaited_once()


@pytest.mark.unit
async def test_streaming_vision_guard_exits_when_both_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ROBOT_STREAMING + server VISION_ENABLED must refuse to start (F-08)."""
    monkeypatch.setattr(app.settings, "robot_streaming", True)
    monkeypatch.setattr(app, "check_vision_enabled", AsyncMock(return_value=True))

    with pytest.raises(SystemExit):
        await app._guard_streaming_vision_compat()


@pytest.mark.unit
async def test_streaming_vision_guard_starts_when_vision_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Streaming alone (server vision off) must start normally."""
    monkeypatch.setattr(app.settings, "robot_streaming", True)
    monkeypatch.setattr(app, "check_vision_enabled", AsyncMock(return_value=False))

    await app._guard_streaming_vision_compat()  # must not raise


@pytest.mark.unit
async def test_streaming_vision_guard_skips_health_call_when_streaming_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-streaming robot must not pay a network round trip at startup."""
    monkeypatch.setattr(app.settings, "robot_streaming", False)
    check_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(app, "check_vision_enabled", check_mock)

    await app._guard_streaming_vision_compat()

    check_mock.assert_not_awaited()


@pytest.mark.unit
async def test_full_happy_cycle(monkeypatch: pytest.MonkeyPatch) -> None:
    """One full interaction: IDLE → LISTENING → THINKING → SPEAKING → IDLE."""
    monkeypatch.setattr(app, "capture_utterance", AsyncMock(return_value=b"wav"))
    monkeypatch.setattr(app, "transcribe", AsyncMock(return_value=_FAKE_RESULT))
    monkeypatch.setattr(app, "play_wav", AsyncMock())

    ctx = LoopContext()
    visited = [RobotState.IDLE]
    state = RobotState.IDLE
    for _ in range(4):
        state = await app.tick(state, ctx)
        visited.append(state)

    assert visited == [
        RobotState.IDLE,
        RobotState.LISTENING,
        RobotState.THINKING,
        RobotState.SPEAKING,
        RobotState.IDLE,
    ]


@pytest.mark.unit
async def test_thinking_passes_the_held_token_to_transcribe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The classic THINKING state must forward ctx.identity_token unchanged."""
    monkeypatch.setattr(app.settings, "robot_face_auth_enabled", False)
    transcribe_mock = AsyncMock(return_value=_FAKE_RESULT)
    monkeypatch.setattr(app, "transcribe", transcribe_mock)
    ctx = LoopContext(audio=b"x", identity_token="opaque-token")  # noqa: S106 — fixture value

    await app.tick(RobotState.THINKING, ctx)

    transcribe_mock.assert_awaited_once_with(
        b"x",
        identity_token="opaque-token",  # noqa: S106
        frame=None,
    )


@pytest.mark.unit
async def test_thinking_clears_the_token_only_when_consumed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A consumed grant must be cleared so it is never replayed."""
    consumed_result = replace(_FAKE_RESULT, authentication_consumed=True)
    monkeypatch.setattr(app, "transcribe", AsyncMock(return_value=consumed_result))
    ctx = LoopContext(audio=b"x", identity_token="opaque-token")  # noqa: S106 — fixture value

    await app.tick(RobotState.THINKING, ctx)

    assert ctx.identity_token is None


@pytest.mark.unit
async def test_thinking_retains_the_token_when_not_consumed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A generic reply that never resolved the actor must not drop the grant."""
    monkeypatch.setattr(app, "transcribe", AsyncMock(return_value=_FAKE_RESULT))
    ctx = LoopContext(audio=b"x", identity_token="opaque-token")  # noqa: S106 — fixture value

    await app.tick(RobotState.THINKING, ctx)

    assert ctx.identity_token == "opaque-token"  # noqa: S105 — fixture value


@pytest.mark.unit
async def test_idle_never_resets_the_identity_token() -> None:
    """The token survives across turns — only consumption or restart clears it."""
    ctx = LoopContext(audio=b"stale", identity_token="opaque-token")  # noqa: S106 — fixture value

    await app.tick(RobotState.IDLE, ctx)

    assert ctx.identity_token == "opaque-token"  # noqa: S105 — fixture value


@pytest.mark.unit
async def test_unlock_prompt_disabled_never_prompts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setting false must never call the secret reader or the unlock client."""
    monkeypatch.setattr(app.settings, "robot_owner_unlock_prompt", False)
    read_secret = AsyncMock()

    token = await app._prompt_owner_unlock(read_secret=read_secret)

    assert token is None
    read_secret.assert_not_awaited()


@pytest.mark.unit
async def test_unlock_prompt_enabled_prompts_once_at_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setting true must prompt exactly once before the FSM starts."""
    monkeypatch.setattr(app.settings, "robot_owner_unlock_prompt", True)
    monkeypatch.setattr(app.settings, "robot_streaming", False)
    read_secret = AsyncMock(return_value="482173")
    unlock_result = server_client.OwnerUnlockResult(
        token="opaque-token",  # noqa: S106 — fixture value
        expires_at=datetime(2026, 8, 21, 10, 1, tzinfo=UTC),
    )
    unlock = AsyncMock(return_value=unlock_result)

    token = await app._prompt_owner_unlock(read_secret=read_secret, unlock=unlock)

    assert token == "opaque-token"  # noqa: S105 — fixture value
    read_secret.assert_awaited_once()
    unlock.assert_awaited_once_with("482173")


@pytest.mark.unit
async def test_unlock_prompt_empty_pin_continues_without_a_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty answer must skip the unlock call and return no token."""
    monkeypatch.setattr(app.settings, "robot_owner_unlock_prompt", True)
    monkeypatch.setattr(app.settings, "robot_streaming", False)
    read_secret = AsyncMock(return_value="")
    unlock = AsyncMock()

    token = await app._prompt_owner_unlock(read_secret=read_secret, unlock=unlock)

    assert token is None
    unlock.assert_not_awaited()


@pytest.mark.unit
async def test_unlock_prompt_server_rejection_continues_without_a_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A rejected PIN must degrade to public conversation, not crash startup."""
    monkeypatch.setattr(app.settings, "robot_owner_unlock_prompt", True)
    monkeypatch.setattr(app.settings, "robot_streaming", False)
    read_secret = AsyncMock(return_value="000000")
    unlock = AsyncMock(side_effect=ServerError("Owner unlock rejected (401)"))

    token = await app._prompt_owner_unlock(read_secret=read_secret, unlock=unlock)

    assert token is None


@pytest.mark.unit
async def test_unlock_prompt_works_when_streaming_is_also_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Plan 0027: the opt-in prompt is no longer classic-only — no SystemExit."""
    monkeypatch.setattr(app.settings, "robot_owner_unlock_prompt", True)
    monkeypatch.setattr(app.settings, "robot_streaming", True)
    read_secret = AsyncMock(return_value="482173")
    unlock_result = server_client.OwnerUnlockResult(
        token="opaque-token",  # noqa: S106 — fixture value
        expires_at=datetime(2026, 8, 21, 10, 1, tzinfo=UTC),
    )
    unlock = AsyncMock(return_value=unlock_result)

    token = await app._prompt_owner_unlock(read_secret=read_secret, unlock=unlock)

    assert token == "opaque-token"  # noqa: S105 — fixture value
    read_secret.assert_awaited_once()


@pytest.mark.unit
async def test_unlock_prompt_never_logs_the_pin_or_token(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Neither the candidate PIN nor the issued token may reach any log record."""
    monkeypatch.setattr(app.settings, "robot_owner_unlock_prompt", True)
    monkeypatch.setattr(app.settings, "robot_streaming", False)
    read_secret = AsyncMock(return_value="482173")
    unlock_result = server_client.OwnerUnlockResult(
        token="opaque-token",  # noqa: S106 — fixture value
        expires_at=datetime(2026, 8, 21, 10, 1, tzinfo=UTC),
    )
    unlock = AsyncMock(return_value=unlock_result)

    with caplog.at_level(logging.DEBUG):
        await app._prompt_owner_unlock(read_secret=read_secret, unlock=unlock)

    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert "482173" not in joined
    assert "opaque-token" not in joined


@pytest.mark.unit
async def test_thinking_face_auth_disabled_never_captures_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default off: capture_frame must never run, and frame=None must reach transcribe()."""
    monkeypatch.setattr(app.settings, "robot_face_auth_enabled", False)
    capture_mock = MagicMock(return_value=b"jpeg-bytes")
    monkeypatch.setattr(app_streaming, "capture_frame", capture_mock)
    transcribe_mock = AsyncMock(return_value=_FAKE_RESULT)
    monkeypatch.setattr(app, "transcribe", transcribe_mock)
    ctx = LoopContext(audio=b"x")

    next_state = await app.tick(RobotState.THINKING, ctx)

    assert next_state == RobotState.SPEAKING
    capture_mock.assert_not_called()
    transcribe_mock.assert_awaited_once_with(b"x", identity_token=None, frame=None)


@pytest.mark.unit
async def test_thinking_face_auth_enabled_captures_and_forwards_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Enabled: capture_frame must run (via asyncio.to_thread) and its bytes forwarded."""
    monkeypatch.setattr(app.settings, "robot_face_auth_enabled", True)
    capture_mock = MagicMock(return_value=b"jpeg-bytes")
    monkeypatch.setattr(app_streaming, "capture_frame", capture_mock)
    transcribe_mock = AsyncMock(return_value=_FAKE_RESULT)
    monkeypatch.setattr(app, "transcribe", transcribe_mock)
    ctx = LoopContext(audio=b"x")

    next_state = await app.tick(RobotState.THINKING, ctx)

    assert next_state == RobotState.SPEAKING
    capture_mock.assert_called_once()
    transcribe_mock.assert_awaited_once_with(b"x", identity_token=None, frame=b"jpeg-bytes")


@pytest.mark.unit
async def test_thinking_face_auth_camera_error_degrades_to_no_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dead webcam must not raise or route to ERROR — the turn proceeds with frame=None."""
    monkeypatch.setattr(app.settings, "robot_face_auth_enabled", True)
    monkeypatch.setattr(
        app_streaming, "capture_frame", MagicMock(side_effect=CameraError("no cam"))
    )
    transcribe_mock = AsyncMock(return_value=_FAKE_RESULT)
    monkeypatch.setattr(app, "transcribe", transcribe_mock)
    ctx = LoopContext(audio=b"x")

    next_state = await app.tick(RobotState.THINKING, ctx)

    assert next_state == RobotState.SPEAKING
    transcribe_mock.assert_awaited_once_with(b"x", identity_token=None, frame=None)


@pytest.mark.unit
async def test_thinking_never_logs_frame_bytes(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Captured frame bytes must never reach any log record."""
    monkeypatch.setattr(app.settings, "robot_face_auth_enabled", True)
    frame_marker = b"fake-jpeg-marker"
    monkeypatch.setattr(app_streaming, "capture_frame", MagicMock(return_value=frame_marker))
    monkeypatch.setattr(app, "transcribe", AsyncMock(return_value=_FAKE_RESULT))
    ctx = LoopContext(audio=b"x")

    with caplog.at_level(logging.DEBUG):
        await app.tick(RobotState.THINKING, ctx)

    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert "fake-jpeg-marker" not in joined
