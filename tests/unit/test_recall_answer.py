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
from server.cognition.recall_cues import WhenKind
from server.exceptions import LLMError
from server.memory import recall_answer
from server.memory.recall_answer import (
    NO_MEMORY,
    build_recall_messages,
    word_recall,
    word_when,
)
from server.memory.recall_search import RecallHit
from server.memory.recall_store import RecallUnit, UnitKind

pytestmark = pytest.mark.unit

_TZ = ZoneInfo("America/Santiago")
_TODAY = date(2026, 11, 4)
_GOLDEN = Path(__file__).resolve().parents[1] / "fixtures" / "recall_prompt_golden.json"
_QUESTION = "¿Qué te conté del cerro?"


def _hit(unit_id: int, body: str, said: datetime, kind: UnitKind = "turn") -> RecallHit:
    unit = RecallUnit(id=unit_id, record_id=unit_id, kind=kind, body=body, said_at=said)
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
async def test_a_model_that_still_says_it_does_not_remember_gets_the_template(
    chat: AsyncMock, said: str
) -> None:
    """Pipec's amendment (2026-11-03): with memories found, the robot always answers from them.

    On hardware the 3B model wrote the fixed phrase 12 of 12 times for a topic question whose
    two memories it had in front of it."""
    chat.return_value = said

    answer = await _word(chat)

    assert answer != NO_MEMORY
    assert answer == "Ayer me contaste esto: Fuimos al cerro con Zeta y llevamos mate."


def test_the_prompt_offers_no_way_out_when_memories_were_found() -> None:
    system = str(build_recall_messages(_QUESTION, _HITS, today=_TODAY, tz=_TZ)[0]["content"])

    assert NO_MEMORY not in system
    assert "me contaste que" in system
    assert "oraciones cortas" in system
    # The 3B model repeated the word «tuteo» of the generic prompt back to Pipec; this prompt
    # asks for tú without naming it.
    assert "tuteo" not in system.lower()


async def test_a_claim_to_have_saved_is_neutralized(chat: AsyncMock) -> None:
    chat.return_value = "Ya lo guardé en mi memoria."

    assert await _word(chat) == REPLACEMENT


@pytest.mark.parametrize(
    "said",
    [
        "Me contaste que fui al cerro con Zeta.",
        "Ayer me contaste que fuiste al cerro con mi amiga Zeta.",
        "Me contaste que yo llevé mate.",
        "Me contaste que fuiste con mis primos al cerro.",
    ],
)
async def test_an_answer_that_speaks_as_the_owner_gets_the_template(
    chat: AsyncMock, said: str
) -> None:
    """Hardware, 2026-11-04: the 3B model kept the owner's first person («fui con mi perrita»).

    A recall answer is Iroko telling the owner what the owner said, so «fui», «yo», «mi» and «mis»
    can only be the owner's words copied as Iroko's; the template quotes them instead."""
    chat.return_value = said

    assert await _word(chat) == "Ayer me contaste esto: Fuimos al cerro con Zeta y llevamos mate."


async def test_a_today_that_no_memory_is_from_gets_the_template(chat: AsyncMock) -> None:
    """The bodies say «hoy» on the day they were said; the answer must use the label instead."""
    chat.return_value = "Me contaste que hoy fuiste al cerro con Zeta."

    assert await _word(chat) == "Ayer me contaste esto: Fuimos al cerro con Zeta y llevamos mate."


async def test_today_is_kept_when_a_memory_is_from_today(chat: AsyncMock) -> None:
    today_hit = _hit(3, "Hoy fuimos al cerro con Zeta.", datetime(2026, 11, 4, 15, tzinfo=UTC))
    chat.return_value = "Hoy me contaste que fuiste al cerro con Zeta."

    assert await _word(chat, (today_hit,)) == "Hoy me contaste que fuiste al cerro con Zeta."


def test_the_prompt_asks_for_the_second_person_and_the_label_day() -> None:
    system = str(build_recall_messages(_QUESTION, _HITS, today=_TODAY, tz=_TZ)[0]["content"])

    assert "«fui» por «fuiste»" in system
    assert "«mi» por «tu»" in system
    assert "entre paréntesis" in system


async def test_the_answer_is_cut_at_two_sentences(chat: AsyncMock) -> None:
    chat.return_value = "Fuiste al cerro. Llevaste mate. Y también fue Zeta."

    assert await _word(chat) == "Fuiste al cerro. Llevaste mate."


_FRIDAY = date(2026, 11, 6)
_BEACH = "Fui a la playa con Zeta y me quemé."
_NOT_RECORDED = "No tengo registrado cuándo fue."
_TUESDAY_HIT = _hit(4, _BEACH, datetime(2026, 11, 3, 15, tzinfo=UTC), "episode")


def _when(kind: WhenKind, hits: tuple[RecallHit, ...], today: date = _TODAY) -> str:
    return word_when(hits, kind, today=today, tz=_TZ)


def test_told_with_a_turn_said_yesterday_says_the_day_it_was_told() -> None:
    assert _when(WhenKind.TOLD, _HITS) == (
        "Ayer me contaste esto: Fuimos al cerro con Zeta y llevamos mate."
    )


def test_happened_with_a_turn_says_the_date_is_not_recorded_first() -> None:
    assert _when(WhenKind.HAPPENED, _HITS) == (
        f"{_NOT_RECORDED} Sí recuerdo que ayer me contaste esto: "
        "Fuimos al cerro con Zeta y llevamos mate."
    )


def test_told_with_an_episode_on_a_weekday() -> None:
    assert _when(WhenKind.TOLD, (_TUESDAY_HIT,), _FRIDAY) == "El martes hablamos de eso."


def test_happened_with_an_episode_on_a_weekday() -> None:
    assert _when(WhenKind.HAPPENED, (_TUESDAY_HIT,), _FRIDAY) == (
        f"{_NOT_RECORDED} Sí recuerdo que el martes hablamos de eso."
    )


def test_a_day_of_the_current_year_is_spoken_as_day_and_month() -> None:
    march = _hit(5, _BEACH, datetime(2026, 3, 3, 15, tzinfo=UTC))

    assert _when(WhenKind.TOLD, (march,)).startswith("El 3 de marzo me contaste esto:")
    assert "el 3 de marzo me contaste esto:" in _when(WhenKind.HAPPENED, (march,))


@pytest.mark.parametrize("kind", list(WhenKind))
def test_only_the_first_hit_is_reported(kind: WhenKind) -> None:
    answer = _when(kind, _HITS)

    assert "Zeta" in answer
    assert "Omega" not in answer
    assert "30 de octubre" not in answer


@pytest.mark.parametrize("kind", list(WhenKind))
@pytest.mark.parametrize("hits", [_HITS, (_TUESDAY_HIT,)])
def test_no_when_answer_turns_the_story_into_the_owner_second_person(
    kind: WhenKind, hits: tuple[RecallHit, ...]
) -> None:
    answer = _when(kind, hits, _FRIDAY)

    assert "fuiste" not in answer
    assert "fue el" not in answer


def test_a_happened_answer_never_states_a_date_as_the_day_of_the_event() -> None:
    answer = _when(WhenKind.HAPPENED, (_TUESDAY_HIT,), _FRIDAY)

    assert answer.startswith(_NOT_RECORDED)
    assert "el martes hablamos" in answer  # the day it was told, not the day of the trip
    assert "fue el" not in answer


def test_word_when_asks_no_model(chat: AsyncMock) -> None:
    _when(WhenKind.TOLD, _HITS)
    _when(WhenKind.HAPPENED, _HITS)

    chat.assert_not_awaited()
