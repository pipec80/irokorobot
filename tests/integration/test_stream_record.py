"""The streaming pipeline hands every spoken reply to the record (Plan 0076 Task 7).

Once with what was actually spoken — the reply, or the fallback phrase — and never when the
synthesis failed. The recorder is a double; the model and the TTS are scripted.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock

import pytest
from server.exceptions import LLMError, TTSError
from server.settings import settings
from server.text_turn import PreparedTextTurn

from server import llm_streaming, streaming, tts

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import httpx

pytestmark = pytest.mark.integration


def _prepared() -> PreparedTextTurn:
    return PreparedTextTurn("hola robot", "interaction:record", None, None, None)


async def _drain(client: httpx.AsyncClient, record_turn: Mock) -> None:
    async for _line in streaming.stream_pipeline(
        client=client,
        prepared=_prepared(),
        stt_ms=0,
        request_start=time.perf_counter(),
        schedule_proposal=lambda _message, _actor: None,
        record_turn=record_turn,
    ):
        pass


@pytest.fixture(autouse=True)
def _scripted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("AAAA", 42)))
    monkeypatch.setattr(streaming, "record_text_turn", Mock())


async def test_the_spoken_reply_is_recorded_once(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def reply(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        yield "Hola. ¿Cómo estás?"

    monkeypatch.setattr(llm_streaming, "generate_response_stream", reply)
    record_turn = Mock()

    await _drain(http_client, record_turn)

    record_turn.assert_called_once()
    heard, said, actor = record_turn.call_args.args
    assert (heard, said, actor) == ("hola robot", "Hola. ¿Cómo estás?", None)


async def test_the_fallback_phrase_is_recorded(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def broken(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        raise LLMError("down")
        yield ""  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(llm_streaming, "generate_response_stream", broken)
    record_turn = Mock()

    await _drain(http_client, record_turn)

    record_turn.assert_called_once()
    assert record_turn.call_args.args[1] == settings.llm_fallback_phrase


async def test_nothing_is_recorded_when_the_synthesis_fails(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def reply(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        yield "Hola."

    monkeypatch.setattr(llm_streaming, "generate_response_stream", reply)
    monkeypatch.setattr(tts, "synthesize", AsyncMock(side_effect=TTSError("piper down")))
    record_turn = Mock()

    with pytest.raises(TTSError):
        await _drain(http_client, record_turn)

    record_turn.assert_not_called()
