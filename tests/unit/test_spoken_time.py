"""The one reader of spoken time, past and future (Plan 0083 Task 1, ADR 0037 decision 4).

Every phrase lives in ``tests/fixtures/spoken_times.yaml``; the ``legacy`` list was recorded from
the code of ``main`` before the reader changed, so the functions Plan 0078 reads are pinned.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import NotRequired, TypedDict, cast

import pytest
from server.cognition.spoken_dates import (
    DayWindow,
    SpokenTime,
    Toward,
    count_spoken_times,
    occurred_label,
    parse_spoken_window,
    read_spoken_time,
    strip_time_words,
    strip_window_words,
)
from server.text_keys import normalize_spanish
import yaml

pytestmark = pytest.mark.unit

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "spoken_times.yaml"
_TODAY = date(2026, 11, 12)


class _Expected(TypedDict):
    start: date
    end: date
    ambiguous: bool


class _TimeCase(TypedDict):
    phrase: str
    past: _Expected | None
    future: _Expected | None
    today: NotRequired[date]


class _LegacyCase(TypedDict):
    text: str
    today: str
    start: str | None
    end: str | None
    stripped: str


def _load() -> dict[str, list[dict[str, object]]]:
    with _FIXTURE.open(encoding="utf-8") as handle:
        loaded: dict[str, list[dict[str, object]]] = yaml.safe_load(handle)
    return loaded


def _times() -> list[_TimeCase]:
    return cast("list[_TimeCase]", _load()["times"])


def _section(name: str) -> list[dict[str, object]]:
    return _load()[name]


def _expected(case: _Expected | None) -> SpokenTime | None:
    if case is None:
        return None
    return SpokenTime(
        window=DayWindow(start=case["start"], end=case["end"]), ambiguous=case["ambiguous"]
    )


def _case_id(case: _TimeCase) -> str:
    return f"{case['phrase']}@{case.get('today', _TODAY)}"


@pytest.mark.parametrize("case", _times(), ids=_case_id)
def test_a_phrase_resolves_toward_each_direction(case: _TimeCase) -> None:
    folded = normalize_spanish(case["phrase"])
    today = case.get("today", _TODAY)
    assert read_spoken_time(folded, today, toward=Toward.PAST) == _expected(case["past"])
    assert read_spoken_time(folded, today, toward=Toward.FUTURE) == _expected(case["future"])


@pytest.mark.parametrize("case", _section("counts"), ids=lambda case: str(case["text"]))
def test_count_spoken_times(case: dict[str, object]) -> None:
    assert count_spoken_times(normalize_spanish(str(case["text"]))) == case["count"]


@pytest.mark.parametrize("case", _section("strips"), ids=lambda case: str(case["text"]))
def test_strip_time_words(case: dict[str, object]) -> None:
    assert strip_time_words(normalize_spanish(str(case["text"]))) == case["stripped"]


@pytest.mark.parametrize("case", _section("labels"), ids=lambda case: str(case["label"]))
def test_occurred_labels(case: dict[str, object]) -> None:
    start, end = case["start"], case["end"]
    assert isinstance(start, date)
    assert isinstance(end, date)
    assert occurred_label(DayWindow(start=start, end=end), today=_TODAY) == case["label"]


def test_a_window_no_span_describes_raises_without_the_date() -> None:
    window = DayWindow(start=date(2026, 11, 3), end=date(2026, 11, 5))
    with pytest.raises(ValueError, match="span") as raised:
        occurred_label(window, today=_TODAY)
    assert "2026" not in str(raised.value)
    assert "11" not in str(raised.value)


@pytest.mark.parametrize(
    "case", cast("list[_LegacyCase]", _section("legacy")), ids=lambda case: case["text"]
)
def test_the_legacy_window_is_unchanged(case: _LegacyCase) -> None:
    folded = normalize_spanish(case["text"])
    window = parse_spoken_window(folded, date.fromisoformat(case["today"]))
    got = None if window is None else (window.start.isoformat(), window.end.isoformat())
    expected = None if case["start"] is None else (case["start"], case["end"])
    assert got == expected
    assert strip_window_words(folded) == case["stripped"]


def test_toward_values() -> None:
    assert Toward.PAST.value == "past"
    assert Toward.FUTURE.value == "future"
