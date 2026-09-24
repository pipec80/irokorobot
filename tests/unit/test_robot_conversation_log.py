"""Robot side of the opt-in conversation text log (Plan 0052).

Same contract as the server's: off and disabled by default, console only when
enabled, never through the root handlers (the log file). Every place the robot
hears or speaks a sentence must be wired to it.
"""

from collections.abc import AsyncIterator, Generator
import logging
from unittest.mock import AsyncMock

import pytest
from robot.conversation_log import (
    CONVERSATION_LOGGER_NAME,
    enable_console,
    log_heard,
    log_spoken,
)
from robot.fsm_types import LoopContext, RobotState
from robot.server_client import TranscribeResult
from robot.settings import Settings
from robot.stream_events import AudioEvent, DoneEvent, EmotionEvent, StreamEvent, TextHeardEvent

from robot import app, app_streaming, audio_playback

# Distinctive enough that a substring match cannot be a coincidence.
_HEARD = "SENTINELHEARDZQX"
_SPOKEN = "SENTINELSPOKENZQX"


class _Collector(logging.Handler):
    """Keep every record's formatted message for the assertions below."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


@pytest.fixture
def _restore_conversation_logger() -> Generator[None, None, None]:
    """Undo `enable_console` so one test cannot switch the log on for the rest."""
    conversation = logging.getLogger(CONVERSATION_LOGGER_NAME)
    saved = (conversation.handlers[:], conversation.level, conversation.disabled)
    yield
    for handler in conversation.handlers[:]:
        if handler not in saved[0]:
            handler.close()
    conversation.handlers[:] = saved[0]
    conversation.setLevel(saved[1])
    conversation.disabled = saved[2]


@pytest.fixture
def collected(_restore_conversation_logger: None) -> _Collector:
    """Enable the conversation logger and collect what it emits.

    The restore fixture it depends on undoes all of this after the test.
    """
    conversation = logging.getLogger(CONVERSATION_LOGGER_NAME)
    collector = _Collector()
    conversation.addHandler(collector)
    conversation.setLevel(logging.INFO)
    conversation.disabled = False
    return collector


@pytest.mark.unit
def test_the_setting_is_off_by_default() -> None:
    """A fresh install must not print household content anywhere."""
    assert Settings.model_fields["log_conversation_text"].default is False


@pytest.mark.unit
def test_the_logger_is_disabled_and_never_reaches_the_root_handlers() -> None:
    """Disabled drops the record early; `propagate=False` keeps it off the file."""
    conversation = logging.getLogger(CONVERSATION_LOGGER_NAME)
    assert conversation.disabled is True
    assert conversation.propagate is False


@pytest.mark.unit
@pytest.mark.usefixtures("_restore_conversation_logger")
def test_disabled_prints_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    """Without the opt-in the helpers write nowhere."""
    log_heard(_HEARD)
    log_spoken(_SPOKEN)

    captured = capsys.readouterr()
    assert _HEARD not in captured.err + captured.out
    assert _SPOKEN not in captured.err + captured.out


@pytest.mark.unit
@pytest.mark.usefixtures("_restore_conversation_logger")
def test_enabled_prints_to_the_console_and_never_to_the_root_handlers(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A collector on the root logger stands in for the log file handler."""
    root_seen = _Collector()
    logging.getLogger().addHandler(root_seen)
    try:
        enable_console(logging.Formatter("%(levelname)s %(message)s"))
        log_heard(_HEARD)
        log_spoken(_SPOKEN)
    finally:
        logging.getLogger().removeHandler(root_seen)

    console = capsys.readouterr().err
    assert f"Heard: {_HEARD}" in console
    assert f"Spoken: {_SPOKEN}" in console
    assert not any(_HEARD in message or _SPOKEN in message for message in root_seen.messages)


async def _stream(*items: StreamEvent) -> AsyncIterator[StreamEvent]:
    for item in items:
        yield item


@pytest.mark.unit
async def test_streaming_thinking_logs_what_was_heard(
    collected: _Collector, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first stream event carries the transcript."""

    async def _fake_transcribe_stream(
        _audio: bytes, *, identity_token: str | None = None, frame: bytes | None = None
    ) -> AsyncIterator[StreamEvent]:
        del identity_token, frame
        yield TextHeardEvent(value=_HEARD)

    monkeypatch.setattr(app_streaming, "transcribe_stream", _fake_transcribe_stream)

    state = await app_streaming.on_thinking_stream(LoopContext(audio=b"x"))

    assert state is RobotState.SPEAKING
    assert f"Heard: {_HEARD}" in collected.messages


@pytest.mark.unit
async def test_streaming_speaking_logs_each_sentence(
    collected: _Collector, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every audio event with text is logged as it is spoken."""
    monkeypatch.setattr(audio_playback, "play_wav", AsyncMock())
    ctx = LoopContext(stream_request_start=100.0)
    ctx.stream_events = _stream(
        EmotionEvent("joy"),
        AudioEvent(text=_SPOKEN, audio_base64="ZmFrZQ==", duration_ms=10),
        DoneEvent(stt_ms=1, llm_ms=1, tts_ms=1, total_ms=3),
    )

    state = await app_streaming.on_speaking_stream(ctx)

    assert state is RobotState.IDLE
    assert f"Spoken: {_SPOKEN}" in collected.messages


@pytest.mark.unit
async def test_classic_thinking_logs_heard_and_spoken(
    collected: _Collector, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The non-streaming turn logs both sides once the server answered."""
    result = TranscribeResult(
        text_heard=_HEARD,
        llm_response=_SPOKEN,
        audio_base64="ZmFrZQ==",
        duration_ms=10,
        emotion="neutral",
    )
    monkeypatch.setattr(app, "transcribe", AsyncMock(return_value=result))
    monkeypatch.setattr(app.settings, "robot_streaming", False)

    state = await app._on_thinking(LoopContext(audio=b"x"))

    assert state is RobotState.SPEAKING
    assert f"Heard: {_HEARD}" in collected.messages
    assert f"Spoken: {_SPOKEN}" in collected.messages
