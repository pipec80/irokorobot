"""What the owner says they will do, when it may be asked, and the sentence (Plan 0084 Task 1).

The announcements live in ``tests/fixtures/pending_announcements.yaml``; canaries only.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import NotRequired, TypedDict, cast

import pytest
from server.cognition.pending_topics import (
    ANNOUNCING_VERBS,
    Announcement,
    AnnouncementOutcome,
    follow_up_sentence,
    may_follow_up,
    read_announcement,
)
from server.cognition.spoken_dates import near_day_label
from server.text_keys import normalize_spanish
import yaml

pytestmark = pytest.mark.unit

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "pending_announcements.yaml"
_SAID_DAY = date(2026, 11, 12)
# D-3, confirmed by Pipec on 2026-11-12: the closed list, folded.
_D3_VERBS = frozenset(
    {"voy", "vamos", "tengo", "tenemos", "ire", "iremos", "salgo", "salimos", "viajo"}
    | {"viajamos", "juego", "jugamos", "empiezo", "me toca", "te cuento", "te aviso"}
    | {"le cuento", "le aviso"}
)


class _Case(TypedDict):
    heard: str
    due_day: date | None
    outcome: str
    said_day: NotRequired[date]


def _cases() -> list[_Case]:
    with _FIXTURE.open(encoding="utf-8") as handle:
        return cast("list[_Case]", yaml.safe_load(handle))


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["heard"])
def test_the_announcement_of_a_turn(case: _Case) -> None:
    announcement = read_announcement(case["heard"], said_day=case.get("said_day", _SAID_DAY))
    assert announcement == Announcement(
        due_day=case["due_day"], outcome=AnnouncementOutcome(case["outcome"])
    )


def test_a_day_never_shows_in_a_repr() -> None:
    announcement = read_announcement("Mañana voy al banco.", said_day=_SAID_DAY)
    assert announcement.due_day is not None
    assert "2026" not in repr(announcement)
    assert "datetime" not in repr(announcement)


@pytest.mark.parametrize(
    "due_day, outcome",
    [(None, AnnouncementOutcome.KEPT), (_SAID_DAY, AnnouncementOutcome.NO_VERB)],
)
def test_a_due_day_comes_exactly_with_kept(
    due_day: date | None, outcome: AnnouncementOutcome
) -> None:
    with pytest.raises(ValueError, match="kept"):
        Announcement(due_day=due_day, outcome=outcome)


def test_blank_words_are_no_announcement() -> None:
    assert read_announcement("   ", said_day=_SAID_DAY).outcome is AnnouncementOutcome.NO_PHRASE


def test_the_verb_list_is_closed() -> None:
    assert ANNOUNCING_VERBS == _D3_VERBS
    assert all(normalize_spanish(verb) == verb for verb in ANNOUNCING_VERBS)


@pytest.mark.parametrize(
    "days_after, expected", [(-1, False), (0, False), (1, True), (2, True), (3, False)]
)
def test_may_follow_up(days_after: int, expected: bool) -> None:
    """D-4: from the day after the due day to two days after it, never on the day itself."""
    assert may_follow_up(_SAID_DAY, today=_SAID_DAY + timedelta(days=days_after)) is expected


def test_the_sentence() -> None:
    assert (
        follow_up_sentence("el banco", due_day=_SAID_DAY, today=_SAID_DAY + timedelta(days=1))
        == "¿Cómo te fue ayer con el banco?"
    )
    assert (
        follow_up_sentence("la reunión", due_day=_SAID_DAY, today=_SAID_DAY + timedelta(days=2))
        == "¿Cómo te fue anteayer con la reunión?"
    )


@pytest.mark.parametrize("days_after", [-1, 0, 3, 10])
def test_the_sentence_needs_a_day_in_the_window(days_after: int) -> None:
    with pytest.raises(ValueError, match="window") as raised:
        follow_up_sentence(
            "el banco", due_day=_SAID_DAY, today=_SAID_DAY + timedelta(days=days_after)
        )
    assert "2026" not in str(raised.value)
    assert "banco" not in str(raised.value)


def test_the_near_day_label_is_public() -> None:
    assert [near_day_label(back) for back in range(4)] == ["hoy", "ayer", "anteayer", None]
