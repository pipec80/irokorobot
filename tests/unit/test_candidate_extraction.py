"""Unit tests for the candidate extractor (ADR 0021 decision 4): user text only, no retry."""

import json
import logging
from typing import get_args
from unittest.mock import AsyncMock

import httpx
import pytest
from server.exceptions import LLMError
from server.memory import candidate_extraction
from server.memory.candidate_extraction import _Triple, extract_candidates
from server.memory.candidate_types import RawCandidate
from server.memory.lexicon import CANDIDATE_TOPICS
from server.settings import settings

pytestmark = pytest.mark.unit

_TEXT = "me gusta el mate y odio el cilantro"


def _answer(*triples: dict[str, str]) -> str:
    return json.dumps({"candidates": list(triples)})


def _chat(monkeypatch: pytest.MonkeyPatch, reply: str | Exception) -> AsyncMock:
    mock = (
        AsyncMock(side_effect=reply)
        if isinstance(reply, Exception)
        else AsyncMock(return_value=reply)
    )
    monkeypatch.setattr(candidate_extraction, "ollama_chat", mock)
    return mock


async def test_the_model_sees_only_the_users_words(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat = _chat(monkeypatch, _answer())

    await extract_candidates(http_client, _TEXT)

    messages = chat.call_args.args[1]
    assert [message["role"] for message in messages] == ["system", "user"]
    assert _TEXT in messages[1]["content"]
    assert "[assistant]" not in messages[1]["content"]
    assert chat.call_args.kwargs["options"] == {"temperature": 0.1}
    assert chat.call_args.kwargs["timeout"] == settings.ollama_timeout_s
    assert "format_schema" in chat.call_args.kwargs


async def test_the_answer_is_returned_as_untrusted_triples(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _chat(
        monkeypatch,
        _answer(
            {"predicate": "likes", "object": "el mate", "topic": "drink"},
            {"predicate": "dislikes", "object": "el cilantro", "topic": "food"},
        ),
    )

    result = await extract_candidates(http_client, _TEXT)

    assert result == (
        RawCandidate(predicate="likes", object="el mate", topic="drink"),
        RawCandidate(predicate="dislikes", object="el cilantro", topic="food"),
    )


async def test_at_most_three_triples_are_kept(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    triple = {"predicate": "likes", "object": "el mate", "topic": "drink"}
    _chat(monkeypatch, _answer(triple, triple, triple, triple, triple))

    assert len(await extract_candidates(http_client, _TEXT)) == 3


async def test_a_fenced_answer_is_accepted(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fence = "`" * 3  # built, not written: this file also lives inside a Markdown code fence
    _chat(monkeypatch, f"{fence}json\n" + _answer() + f"\n{fence}")

    assert await extract_candidates(http_client, _TEXT) == ()


@pytest.mark.parametrize(
    "reply",
    [
        "not json",
        _answer({"predicate": "lives_in", "object": "la costa", "topic": "food"}),
        _answer({"predicate": "likes", "object": "el mate", "topic": "health"}),
        '{"candidates": "el mate"}',
    ],
)
async def test_an_invalid_answer_raises_without_echoing_it_and_is_not_retried(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    reply: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    chat = _chat(monkeypatch, reply)

    with caplog.at_level(logging.DEBUG), pytest.raises(LLMError) as excinfo:
        await extract_candidates(http_client, _TEXT)

    assert chat.await_count == 1
    assert str(excinfo.value) == "Candidate extraction returned invalid JSON"
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__
    for fragment in ("mate", "lives_in", "health"):
        assert fragment not in str(excinfo.value)
        assert fragment not in caplog.text


async def test_a_transport_failure_propagates_once(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat = _chat(monkeypatch, httpx.ConnectError("down"))

    with pytest.raises(httpx.ConnectError):
        await extract_candidates(http_client, _TEXT)

    assert chat.await_count == 1


def test_the_schema_topics_are_the_closed_set_of_the_lexicon() -> None:
    topics = set(get_args(_Triple.model_fields["topic"].annotation))

    assert topics == CANDIDATE_TOPICS
