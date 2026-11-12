"""The «¿cuándo fui…?» answer with the occurred time (Plan 0083 Task 6, D-10 to D-12).

The cases live in ``tests/fixtures/when_answers.yaml``; canaries only.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
import logging
from pathlib import Path
from typing import NotRequired, TypedDict, cast
from zoneinfo import ZoneInfo

import pytest
from server.cognition.recall_cues import WhenKind
from server.cognition.spoken_dates import DayWindow
from server.memory.recall_answer import build_recall_messages, word_when
from server.memory.recall_search import RecallHit
from server.memory.recall_store import RecallUnit
import yaml

pytestmark = pytest.mark.unit

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "when_answers.yaml"
_TZ = ZoneInfo("America/Santiago")
_TODAY = date(2026, 11, 12)
_QUESTIONS = cast(
    "list[dict[str, object]]",
    yaml.safe_load((_FIXTURE.parent / "recall_cues_occurred.yaml").read_text(encoding="utf-8")),
)


class _Window(TypedDict):
    start: date
    end: date


class _Case(TypedDict):
    body: str
    said: datetime
    occurred: _Window | None
    answer: str
    kind: NotRequired[str]


def _cases() -> list[_Case]:
    with _FIXTURE.open(encoding="utf-8") as handle:
        return cast("list[_Case]", yaml.safe_load(handle))


def _hit(case: _Case, kind: str = "turn") -> RecallHit:
    occurred = case["occurred"]
    unit = RecallUnit(
        id=1,
        record_id=1,
        kind="episode" if kind == "episode" else "turn",
        body=case["body"],
        said_at=case["said"],
        occurred=None
        if occurred is None
        else DayWindow(start=occurred["start"], end=occurred["end"]),
    )
    return RecallHit(unit=unit, distance=None)


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["answer"])
def test_when_it_happened_is_said(case: _Case) -> None:
    kind = WhenKind(case.get("kind", "happened"))
    assert word_when((_hit(case),), kind, today=_TODAY, tz=_TZ) == case["answer"]


def test_an_episode_hit_keeps_the_told_day() -> None:
    case = _cases()[0]
    episode = _hit({**case, "occurred": None}, kind="episode")
    told_day = word_when((episode,), WhenKind.HAPPENED, today=_TODAY, tz=_TZ)
    assert not told_day.startswith("Fue ")


def test_a_bad_window_falls_back_without_a_date(caplog: pytest.LogCaptureFixture) -> None:
    bad = _cases()[5]
    with caplog.at_level(logging.DEBUG):
        word_when((_hit(bad),), WhenKind.HAPPENED, today=_TODAY, tz=_TZ)
    assert caplog.records
    for record in caplog.records:
        message = record.getMessage()
        assert "2026" not in message
        assert bad["body"] not in message


def test_the_recall_prompt_is_unchanged() -> None:
    with_interval = tuple(_hit(case) for case in _cases()[:3])
    without = tuple(_hit({**case, "occurred": None}) for case in _cases()[:3])
    question = str(_QUESTIONS[3]["message"])  # «¿Qué hice ayer?»
    assert build_recall_messages(
        question, with_interval, today=_TODAY, tz=_TZ
    ) == build_recall_messages(question, without, today=_TODAY, tz=_TZ)


def test_the_said_day_is_the_household_day() -> None:
    late = _cases()[3]
    # 02:30 UTC on the 12th is 23:30 of the 11th in Santiago: still «el mismo día».
    moved: _Case = {**late, "said": datetime(2026, 11, 12, 2, 30, tzinfo=UTC)}
    assert word_when((_hit(moved),), WhenKind.HAPPENED, today=_TODAY, tz=_TZ) == late["answer"]
