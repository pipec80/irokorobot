"""Recall questions with the occurred time on (Plan 0083 Task 5, D-13).

The messages live in ``tests/fixtures/recall_cues_occurred.yaml``; its ``without_flag`` values were recorded
from ``main``, so the switch-off path is pinned. Canaries only.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict, cast

import pytest
from server.cognition.recall_cues import RecallCue, classify_recall_cue
import yaml

if TYPE_CHECKING:
    from server.cognition.spoken_dates import DayWindow

pytestmark = pytest.mark.unit

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "recall_cues_occurred.yaml"
_TODAY = date(2026, 11, 12)


class _Cue(TypedDict):
    strength: str
    when: str | None
    query: str
    start: date | None
    end: date | None


class _Case(TypedDict):
    message: str
    with_flag: _Cue | None
    without_flag: _Cue | None


def _cases() -> list[_Case]:
    with _FIXTURE.open(encoding="utf-8") as handle:
        return cast("list[_Case]", yaml.safe_load(handle))


def _shape(cue: RecallCue | None) -> _Cue | None:
    if cue is None:
        return None
    window: DayWindow | None = cue.window
    return {
        "strength": cue.strength.value,
        "when": None if cue.when is None else cue.when.value,
        "query": cue.query,
        "start": None if window is None else window.start,
        "end": None if window is None else window.end,
    }


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["message"])
def test_with_the_flag_on(case: _Case) -> None:
    assert (
        _shape(classify_recall_cue(case["message"], today=_TODAY, occurred=True))
        == case["with_flag"]
    )


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["message"])
def test_with_the_flag_off_cues_are_unchanged(case: _Case) -> None:
    assert _shape(classify_recall_cue(case["message"], today=_TODAY)) == case["without_flag"]
    assert (
        _shape(classify_recall_cue(case["message"], today=_TODAY, occurred=False))
        == case["without_flag"]
    )
