"""Opt-in conversation text log (Plan 0052): console only, never the file.

Household content is never logged by default (Plans 0031/0032, guarded by
`test_sensitive_logging.py`). `LOG_CONVERSATION_TEXT=true` is the one deliberate
exception, for an operator debugging their own machine. These tests pin its two
safety properties — off by default, and never reaching the log file — and that
every place a turn is heard or spoken is wired to it.
"""

from collections.abc import Generator
import logging
from pathlib import Path
import time
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
import pytest
from server.cognition.models import KnowledgeStatus
from server.cognition.response_plan import InformationNeed, ResponsePlan, ResponseSource
from server.conversation_log import (
    CONVERSATION_LOGGER_NAME,
    log_heard,
    log_spoken,
    set_enabled,
)
from server.logging_setup import configure_logging
from server.settings import Settings, settings

from server import llm, llm_streaming, streaming, stt, tts

# Distinctive enough that a substring match cannot be a coincidence.
_SENTINEL = "SENTINELHEARDZQX"
_REPLY = "SENTINELSPOKENZQX"


class _Collector(logging.Handler):
    """Keep every record's formatted message for the assertions below."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


@pytest.fixture
def _restore_logging() -> Generator[None, None, None]:
    """Re-apply the process's normal logging configuration after `configure_logging`.

    `dictConfig` shuts down every existing handler and forgets it. Putting the old
    handler objects back would resurrect a closed file handler that logging no
    longer tracks: its file is reopened on the next record and never closed, which
    surfaces as an unraisable `ResourceWarning` in whichever unrelated test runs
    when it is garbage collected. Configuring again from the same settings the app
    uses registers fresh handlers properly.
    """
    yield
    configure_logging(settings)


@pytest.fixture
def collected() -> Generator[_Collector, None, None]:
    """Enable the conversation logger and collect what it emits."""
    conversation = logging.getLogger(CONVERSATION_LOGGER_NAME)
    collector = _Collector()
    conversation.addHandler(collector)
    was_disabled = conversation.disabled
    set_enabled(True)
    yield collector
    conversation.removeHandler(collector)
    conversation.disabled = was_disabled


@pytest.mark.unit
def test_the_setting_is_off_by_default() -> None:
    """A fresh install must not print household content anywhere."""
    assert Settings.model_fields["log_conversation_text"].default is False


@pytest.mark.unit
def test_the_logger_is_disabled_until_the_operator_opts_in() -> None:
    """Disabled drops the record before any handler, including a test's capture."""
    assert logging.getLogger(CONVERSATION_LOGGER_NAME).disabled is True


@pytest.mark.unit
def test_the_conversation_logger_never_reaches_the_root_handlers() -> None:
    """`propagate=False` is what keeps the text out of the JSON Lines file."""
    assert logging.getLogger(CONVERSATION_LOGGER_NAME).propagate is False


@pytest.mark.integration
@pytest.mark.usefixtures("_restore_logging")
def test_off_prints_nothing_to_the_console_or_the_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without the opt-in the two helpers write nowhere."""
    configure_logging(Settings(log_dir=tmp_path, log_to_file=True, log_conversation_text=False))

    log_heard(_SENTINEL)
    log_spoken(_SENTINEL)

    assert _SENTINEL not in capsys.readouterr().err
    assert _SENTINEL not in (tmp_path / "server.log").read_text(encoding="utf-8")


@pytest.mark.integration
@pytest.mark.usefixtures("_restore_logging")
def test_on_prints_to_the_console_and_never_to_the_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """With the opt-in the text is on the console and absent from the file."""
    configure_logging(Settings(log_dir=tmp_path, log_to_file=True, log_conversation_text=True))

    log_heard(_SENTINEL)
    log_spoken(_REPLY)

    console = capsys.readouterr().err
    assert f"Heard: {_SENTINEL}" in console
    assert f"Spoken: {_REPLY}" in console
    file_text = (tmp_path / "server.log").read_text(encoding="utf-8")
    assert _SENTINEL not in file_text
    assert _REPLY not in file_text
    assert "LOG_CONVERSATION_TEXT is on" in file_text, "turning it on must leave a visible trace"


@pytest.mark.integration
def test_a_classic_turn_logs_what_was_heard_and_spoken(
    client: TestClient,
    silence_wav_bytes: bytes,
    collected: _Collector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`/transcribe` reaches both helpers, and neither leaks into the root logger.

    A collector on the root logger sees only what propagates there — the path to
    the log file — so it stands in for the file handler.
    """
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value=_SENTINEL))
    monkeypatch.setattr(llm, "generate_response", AsyncMock(return_value=(_REPLY, "joy")))
    monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("QQ==", 42)))
    root_seen = _Collector()
    logging.getLogger().addHandler(root_seen)

    try:
        response = client.post(
            "/transcribe", files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")}
        )
    finally:
        logging.getLogger().removeHandler(root_seen)

    assert response.status_code == 200
    assert f"Heard: {_SENTINEL}" in collected.messages
    assert f"Spoken: {_REPLY}" in collected.messages
    assert not any(_SENTINEL in message or _REPLY in message for message in root_seen.messages)


@pytest.mark.integration
def test_a_streamed_turn_logs_what_was_heard_and_spoken(
    client: TestClient,
    silence_wav_bytes: bytes,
    collected: _Collector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`/transcribe/stream` reaches both helpers through the sentence synthesizer."""
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value=_SENTINEL))
    monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("QQ==", 42)))

    async def sentinel_stream(*_args: object, **_kwargs: object) -> object:
        yield f"EMOTION:joy\n{_REPLY}."

    monkeypatch.setattr(llm_streaming, "generate_response_stream", sentinel_stream)

    response = client.post(
        "/transcribe/stream", files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")}
    )

    assert response.status_code == 200
    assert f"Heard: {_SENTINEL}" in collected.messages
    assert any(_REPLY in message for message in collected.messages if message.startswith("Spoken"))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_deterministic_plan_logs_what_is_spoken(
    collected: _Collector, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An authorized answer (own children, who am I) never touches the model.

    It is exactly the reply an operator most wants to read, and it has its own
    synthesis site in `stream_response_plan`.
    """
    monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("QQ==", 42)))
    plan = ResponsePlan(
        need=InformationNeed.CURRENT_DATE,
        status=KnowledgeStatus.KNOWN,
        source=ResponseSource.DETERMINISTIC,
        response=_REPLY,
    )

    _ = [
        line
        async for line in streaming.stream_response_plan(
            text_heard=_SENTINEL, plan=plan, stt_ms=1, request_start=time.perf_counter()
        )
    ]

    assert f"Spoken: {_REPLY}" in collected.messages
