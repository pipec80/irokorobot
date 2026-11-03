"""Wording a recall answer only from what was found (Plan 0078 Task 8, ADR 0028 decision 8)."""

from __future__ import annotations

from datetime import UTC, date, datetime
import json
from pathlib import Path
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import httpx
import pytest
from server.claim_guard import REPLACEMENT
from server.exceptions import LLMError
from server.memory import recall_answer
from server.memory.recall_answer import NO_MEMORY, build_recall_messages, word_recall
from server.memory.recall_search import RecallHit
from server.memory.recall_store import RecallUnit

pytestmark = pytest.mark.unit

_TZ = ZoneInfo("America/Santiago")
_TODAY = date(2026, 11, 4)
_GOLDEN = Path(__file__).resolve().parents[1] / "fixtures" / "recall_prompt_golden.json"
_QUESTION = "¿Qué te conté del cerro?"


def _hit(unit_id: int, body: str, said: datetime) -> RecallHit:
    unit = RecallUnit(id=unit_id, record_id=unit_id, kind="turn", body=body, said_at=said)
    return RecallHit(unit=unit, distance=None)


_HITS = (
    _hit(1, "Fuimos al cerro con Zeta y llevamos mate.", datetime(2026, 11, 3, 15, tzinfo=UTC)),
    _hit(2, "La persona contó que Omega subió el cerro.", datetime(2026, 10, 30, 15, tzinfo=UTC)),
)


async def _word(chat: AsyncMock, hits: tuple[RecallHit, ...] = _HITS) -> str:
    return await word_recall(httpx.AsyncClient(), _QUESTION, hits, today=_TODAY, tz=_TZ)


@pytest.fixture
def chat(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    double = AsyncMock(return_value="Sí, ayer me contaste que fuiste al cerro con Zeta.")
    monkeypatch.setattr(recall_answer, "ollama_chat", double)
    return double


def test_the_prompt_matches_its_golden() -> None:
    messages = build_recall_messages(_QUESTION, _HITS, today=_TODAY, tz=_TZ)

    assert messages == json.loads(_GOLDEN.read_text(encoding="utf-8"))


def test_the_prompt_carries_only_the_found_units() -> None:
    messages = build_recall_messages(_QUESTION, _HITS[:1], today=_TODAY, tz=_TZ)
    text = json.dumps(messages, ensure_ascii=False)

    assert "Zeta y llevamos mate" in text
    assert "Omega" not in text
    assert len(messages) == 2


def test_the_bodies_are_capped_at_1200_characters() -> None:
    long_hits = tuple(_hit(i, "x" * 700, datetime(2026, 11, 3, tzinfo=UTC)) for i in range(3))

    user = build_recall_messages(_QUESTION, long_hits, today=_TODAY, tz=_TZ)[1]["content"]

    assert user.count("x") == 1200


async def test_the_model_answer_is_returned_and_called_as_the_plan_says(chat: AsyncMock) -> None:
    assert await _word(chat) == "Sí, ayer me contaste que fuiste al cerro con Zeta."
    assert chat.await_args is not None
    assert chat.await_args.kwargs["options"] == {"temperature": 0.1}


@pytest.mark.parametrize("error", [LLMError("x"), httpx.ConnectError("x"), TimeoutError()])
async def test_a_model_failure_uses_the_template(chat: AsyncMock, error: Exception) -> None:
    chat.side_effect = error

    assert await _word(chat) == "Ayer me contaste esto: Fuimos al cerro con Zeta y llevamos mate."


async def test_an_empty_answer_uses_the_template(chat: AsyncMock) -> None:
    chat.return_value = "   "

    assert (await _word(chat)).startswith("Ayer me contaste esto:")


@pytest.mark.parametrize(
    "said", ["No me acuerdo de eso.", "  «No me acuerdo de eso.»  ", "no me acuerdo de eso"]
)
async def test_the_model_saying_it_does_not_remember_gives_the_fixed_phrase(
    chat: AsyncMock, said: str
) -> None:
    chat.return_value = said

    assert await _word(chat) == NO_MEMORY


async def test_a_claim_to_have_saved_is_neutralized(chat: AsyncMock) -> None:
    chat.return_value = "Ya lo guardé en mi memoria."

    assert await _word(chat) == REPLACEMENT


async def test_the_answer_is_cut_at_two_sentences(chat: AsyncMock) -> None:
    chat.return_value = "Fuiste al cerro. Llevaste mate. Y también fue Zeta."

    assert await _word(chat) == "Fuiste al cerro. Llevaste mate."
