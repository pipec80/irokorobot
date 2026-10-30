"""Unit tests for the diary summary: only the owner's part reaches the model (Plan 0076)."""

from datetime import UTC, datetime, timedelta
import itertools
import json
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest
from server.exceptions import LLMError
from server.memory import conversation_summary
from server.memory.conversation_summary import summarize_owner_part, summary_input
from server.memory.conversation_types import RecordedTurn, TurnVerdict, make_turn
from server.settings import settings

pytestmark = pytest.mark.unit

_T0 = datetime(2026, 10, 29, 10, 0, tzinfo=UTC)


def _turn(index: int, voice: TurnVerdict) -> RecordedTurn:
    return make_turn(
        f"frase-{index}-{voice.value}",
        f"respuesta-{index}-{voice.value}",
        voice=voice,
        correlation_id=UUID(int=index + 1),
        at=_T0 + timedelta(seconds=index),
    )


_MIXES = [mix for size in range(1, 5) for mix in itertools.product(tuple(TurnVerdict), repeat=size)]


@pytest.mark.parametrize("mix", _MIXES, ids=lambda mix: "-".join(v.value for v in mix))
def test_summary_input_never_carries_a_turn_that_is_not_verified(
    mix: tuple[TurnVerdict, ...],
) -> None:
    """Review focus 1: the grid of every verdict mix in up to four turns."""
    turns = [_turn(index, voice) for index, voice in enumerate(mix)]

    text = summary_input(turns)

    for turn in turns:
        present = turn.heard in text and turn.said in text
        assert present is (turn.voice is TurnVerdict.VERIFIED)


def test_summary_input_is_oldest_first_persona_then_robot() -> None:
    late = _turn(5, TurnVerdict.VERIFIED)
    early = _turn(1, TurnVerdict.VERIFIED)

    assert summary_input([late, early]).splitlines() == [
        f"Persona: {early.heard}",
        f"Robot: {early.said}",
        f"Persona: {late.heard}",
        f"Robot: {late.said}",
    ]


def _model(monkeypatch: pytest.MonkeyPatch, answer: str) -> AsyncMock:
    chat = AsyncMock(return_value=answer)
    monkeypatch.setattr(conversation_summary, "ollama_chat", chat)
    return chat


async def test_summarize_validates_cleans_and_cuts_the_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "conversation_episode_max_chars", 20)
    chat = _model(
        monkeypatch,
        json.dumps(
            {"summary": "La persona\n contó   que le gusta el mate.", "sensitivity": "normal"}
        ),
    )
    turns = [_turn(0, TurnVerdict.VERIFIED), _turn(1, TurnVerdict.NOT_OWNER)]

    draft = await summarize_owner_part(httpx.AsyncClient(), turns)

    assert draft.summary == "La persona contó que"
    assert draft.sensitivity == "normal"
    sent: list[dict[str, Any]] = chat.await_args_list[-1].args[1]
    assert "frase-1-not_owner" not in sent[1]["content"]


@pytest.mark.parametrize(
    "answer",
    [
        "no es json",
        json.dumps({"summary": "algo", "sensitivity": "secreto"}),
        json.dumps({"summary": "   ", "sensitivity": "normal"}),
    ],
    ids=["not-json", "unknown-sensitivity", "empty"],
)
async def test_an_invalid_answer_is_an_llm_error_without_the_output(
    monkeypatch: pytest.MonkeyPatch, answer: str
) -> None:
    _model(monkeypatch, answer)

    with pytest.raises(LLMError) as raised:
        await summarize_owner_part(httpx.AsyncClient(), [_turn(0, TurnVerdict.VERIFIED)])

    assert "algo" not in str(raised.value)
    assert raised.value.__cause__ is None
