"""When a told event happened (Plan 0083 Task 2, D-7; ADR 0037 decision 3).

The statements live in ``tests/fixtures/occurred_times.yaml``; canaries only.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import NotRequired, TypedDict, cast

import pytest
from server.cognition.occurred_time import TOLD_PAST_VERBS, occurred_window
from server.cognition.spoken_dates import DayWindow
import yaml

pytestmark = pytest.mark.unit

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "occurred_times.yaml"
_SAID_DAY = date(2026, 11, 12)
# Folded forms that are also a present, a subjunctive or a noun (D-7): never in the list.
_EXCLUDED = frozenset(
    {"salimos", "viajamos", "vivimos", "paso", "compre", "hable", "llegue", "trabaje", "estudie"}
    | {"visite", "viaje", "pase"}
)


class _Case(TypedDict):
    heard: str
    start: date | None
    end: date | None
    said_day: NotRequired[date]


def _cases() -> list[_Case]:
    with _FIXTURE.open(encoding="utf-8") as handle:
        return cast("list[_Case]", yaml.safe_load(handle))


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["heard"])
def test_the_occurred_interval_of_a_told_turn(case: _Case) -> None:
    window = occurred_window(case["heard"], said_day=case.get("said_day", _SAID_DAY))
    start, end = case["start"], case["end"]
    expected = None if start is None or end is None else DayWindow(start=start, end=end)
    assert window == expected


def test_the_verb_list_is_closed() -> None:
    assert not (TOLD_PAST_VERBS & _EXCLUDED)
    assert all(verb == verb.casefold() and verb.isalpha() for verb in TOLD_PAST_VERBS)


def test_blank_words_have_no_interval() -> None:
    assert occurred_window("   ", said_day=_SAID_DAY) is None
