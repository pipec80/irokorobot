"""The topic of a pending plan, named by the local model in the owner's words (Plan 0084 Task 2).

The model is a double; its answers live in ``tests/fixtures/pending_names.yaml``. Canaries only.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TypedDict, cast
from unittest.mock import AsyncMock

import httpx
import pytest
from server.exceptions import LLMError
from server.memory import pending_naming
from server.memory.pending_naming import (
    MAX_TOPIC_CHARS,
    MAX_TOPIC_WORDS,
    is_copied_topic,
    name_topic,
)
from server.settings import settings
import yaml

pytestmark = pytest.mark.unit

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "pending_names.yaml"
_HEARD = "Mañana voy al banco a pagar una cuenta."


class _Case(TypedDict):
    heard: str
    answer: str
    kept: str | None


def _cases() -> list[_Case]:
    with _FIXTURE.open(encoding="utf-8") as handle:
        return cast("list[_Case]", yaml.safe_load(handle))


def _chat(monkeypatch: pytest.MonkeyPatch, reply: str | Exception) -> AsyncMock:
    mock = (
        AsyncMock(side_effect=reply)
        if isinstance(reply, Exception)
        else AsyncMock(return_value=reply)
    )
    monkeypatch.setattr(pending_naming, "ollama_chat", mock)
    return mock


@pytest.mark.parametrize("case", _cases(), ids=lambda case: f"{case['heard']}|{case['answer']}")
async def test_the_topic_kept_from_the_models_answer(
    case: _Case, http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _chat(monkeypatch, case["answer"])

    assert await name_topic(http_client, case["heard"]) == case["kept"]


async def test_the_prompt_sees_only_the_words(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat = _chat(monkeypatch, '{"topic": "el banco"}')

    await name_topic(http_client, _HEARD)

    messages = chat.call_args.args[1]
    assert [message["role"] for message in messages] == ["system", "user"]
    assert messages[1]["content"] == _HEARD
    assert _HEARD not in messages[0]["content"]
    assert chat.call_args.kwargs["options"] == {"temperature": 0.0}
    assert chat.call_args.kwargs["timeout"] == settings.ollama_timeout_s
    assert chat.call_args.kwargs["model"] == settings.consolidation_model
    assert "format_schema" in chat.call_args.kwargs


@pytest.mark.parametrize(
    "error", [httpx.ConnectError("down"), httpx.ReadTimeout("slow"), TimeoutError()]
)
async def test_a_model_failure_propagates_so_the_job_keeps_the_row(
    error: Exception, http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _chat(monkeypatch, error)

    with pytest.raises(type(error)):
        await name_topic(http_client, _HEARD)


@pytest.mark.parametrize("answer", ["zzno-jsonzz", '{"tema": "x"}', '{"topic": 3}'])
async def test_an_answer_that_is_not_the_schema_is_a_model_failure(
    answer: str, http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A model regression keeps the topic for a later try instead of deleting it (Task 8)."""
    _chat(monkeypatch, answer)

    with pytest.raises(LLMError) as raised:
        await name_topic(http_client, _HEARD)
    assert answer not in str(raised.value)
    assert raised.value.__cause__ is None


async def test_an_empty_model_answer_propagates(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _chat(monkeypatch, LLMError("Ollama response carries no text message content"))

    with pytest.raises(LLMError):
        await name_topic(http_client, _HEARD)


async def test_no_text_reaches_a_log_line(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    for answer in ('{"topic": "el teatro"}', '{"topic": ""}', '{"topic": "el banco"}'):
        _chat(monkeypatch, answer)
        await name_topic(http_client, _HEARD)

    logged = " ".join(f"{record.getMessage()} {record.__dict__}" for record in caplog.records)
    for word in ("banco", "teatro", "cuenta", "sé"):
        assert word not in logged


def test_the_limits() -> None:
    assert (MAX_TOPIC_WORDS, MAX_TOPIC_CHARS) == (4, 40)


@pytest.mark.parametrize(
    "topic, expected",
    [
        ("el banco", True),
        ("banco", True),
        ("una cuenta", True),
        ("la cuenta", True),
        ("el teatro", False),
        ("", False),
        ("la", False),
        ("el banco a pagar una", False),
        ("el banco ✓", False),
    ],
)
def test_is_copied_topic(topic: str, expected: bool) -> None:
    assert is_copied_topic(topic, _HEARD) is expected


def test_the_prompt_asks_for_the_short_name() -> None:
    """Found on hardware: «la hora con el médico» is five words and was dropped (2026-11-13)."""
    system = pending_naming._SYSTEM
    assert "una o dos palabras" in system
    assert "«el médico»" in system
    assert "Nunca «la hora»" in system
