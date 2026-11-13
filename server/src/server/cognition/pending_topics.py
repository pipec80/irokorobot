"""What the owner says they will do on one day, and the greeting that picks it up (Plan 0084).

ADR 0037 decision 2. Pure and closed: an announcement holds exactly one time phrase of the shared
reader (``spoken_dates``), read toward the future to a single day, and one first-person verb or
phrase of ``ANNOUNCING_VERBS``; a question is never one. The local model only names the topic
later (``memory/pending_naming``); this module decides the due day, the window in which it may be
asked and the fixed sentence. It reads no setting and logs nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from server.cognition.spoken_dates import (
    Toward,
    count_spoken_times,
    near_day_label,
    read_spoken_time,
)
from server.text_keys import normalize_spanish

if TYPE_CHECKING:
    from datetime import date

__all__ = [
    "ANNOUNCING_VERBS",
    "Announcement",
    "AnnouncementOutcome",
    "follow_up_due_days",
    "follow_up_sentence",
    "may_follow_up",
    "read_announcement",
]

# Folded first-person verbs and phrases (D-3): the present used as future, the plain future, and
# «te cuento» / «le cuento» (usted). A multi-word entry matches as a whole phrase. Third person
# («mañana viene mi hija») is not the owner's plan.
ANNOUNCING_VERBS: Final[frozenset[str]] = frozenset(
    {
        "voy", "vamos", "tengo", "tenemos", "ire", "iremos", "salgo", "salimos", "viajo",
        "viajamos", "juego", "jugamos", "empiezo", "me toca", "te cuento", "te aviso",
        "le cuento", "le aviso",
    }
)  # fmt: skip

# D-4: a topic may be asked from the day after its due day to two days after it.
_FIRST_DAY_AFTER: Final = 1
_LAST_DAY_AFTER: Final = 2
_QUESTION_MARKS: Final = ("?", "¿")
# A verb right after one of these is not a plan: «mañana no voy al banco» (Task 8 review).
_NEGATIONS: Final = frozenset({"no", "nunca", "tampoco"})


class AnnouncementOutcome(StrEnum):
    """What the grammar made of one turn's words, in closed terms (D-15)."""

    KEPT = "kept"
    NO_PHRASE = "no_phrase"
    NOT_SINGLE_DAY = "not_single_day"
    NO_VERB = "no_verb"
    QUESTION = "question"


@dataclass(frozen=True)
class Announcement:
    """The grammar's verdict on one turn.

    Attributes:
        due_day: The local day the plan names; ``None`` unless the outcome is ``KEPT``.
        outcome: Why the words are, or are not, an announcement.
    """

    # A day is never shown in a repr (D-15).
    due_day: date | None = field(repr=False)
    outcome: AnnouncementOutcome

    def __post_init__(self) -> None:
        """Refuse a due day without ``KEPT``, or ``KEPT`` without one."""
        if (self.outcome is AnnouncementOutcome.KEPT) != (self.due_day is not None):
            raise ValueError("a due day comes exactly with a kept announcement")


def _no(outcome: AnnouncementOutcome) -> Announcement:
    return Announcement(due_day=None, outcome=outcome)


def _has_announcing_verb(normalized: str) -> bool:
    """Whether a verb of ``ANNOUNCING_VERBS`` appears, not right after a negation."""
    words = normalized.split()
    for verb in ANNOUNCING_VERBS:
        size = len(verb.split())
        for start in range(len(words) - size + 1):
            if " ".join(words[start : start + size]) == verb and (
                start == 0 or words[start - 1] not in _NEGATIONS
            ):
                return True
    return False


def read_announcement(heard: str, *, said_day: date) -> Announcement:
    """Return whether the owner's words announce a plan for one day, and which day.

    Args:
        heard: The owner's words of one turn, as transcribed.
        said_day: The household's local day the words were said.

    Returns:
        ``KEPT`` with the due day; else ``QUESTION`` for a question mark, ``NO_PHRASE`` when the
        words do not hold exactly one time phrase toward the future, ``NOT_SINGLE_DAY`` for a
        week, a month, a season or a year, and ``NO_VERB`` without a verb of
        ``ANNOUNCING_VERBS`` (one right after «no», «nunca» or
        «tampoco» does not count).
    """
    if any(mark in heard for mark in _QUESTION_MARKS):
        return _no(AnnouncementOutcome.QUESTION)
    normalized = normalize_spanish(heard)
    if count_spoken_times(normalized) != 1:
        return _no(AnnouncementOutcome.NO_PHRASE)
    spoken = read_spoken_time(normalized, said_day, toward=Toward.FUTURE)
    if spoken is None:
        return _no(AnnouncementOutcome.NO_PHRASE)
    if spoken.window.start != spoken.window.end:
        return _no(AnnouncementOutcome.NOT_SINGLE_DAY)
    if not _has_announcing_verb(normalized):
        return _no(AnnouncementOutcome.NO_VERB)
    return Announcement(due_day=spoken.window.start, outcome=AnnouncementOutcome.KEPT)


def follow_up_due_days(today: date) -> tuple[date, date]:
    """Return the oldest and the newest due day a greeting of *today* may ask about (D-4).

    Args:
        today: The household's local day of the greeting.

    Returns:
        Two days before today and the day before today, inclusive.
    """
    return today - timedelta(days=_LAST_DAY_AFTER), today - timedelta(days=_FIRST_DAY_AFTER)


def may_follow_up(due_day: date, *, today: date) -> bool:
    """Return whether a topic due on *due_day* may be asked about today (D-4).

    Args:
        due_day: The day the plan named.
        today: The household's local day of the greeting.

    Returns:
        ``True`` from the day after the due day to two days after it; never on the due day,
        which would ask before it happened.
    """
    oldest, newest = follow_up_due_days(today)
    return oldest <= due_day <= newest


def follow_up_sentence(topic: str, *, due_day: date, today: date) -> str:
    """Return the fixed greeting that picks a topic up (D-10).

    Args:
        topic: The topic as named, article included («el banco»).
        due_day: The day the plan named.
        today: The household's local day of the greeting.

    Returns:
        «¿Cómo te fue ayer con el banco?», or «anteayer» two days after.

    Raises:
        ValueError: If the due day is outside the window of ``may_follow_up``; the message holds
            neither the day nor the topic.
    """
    label = near_day_label((today - due_day).days) if may_follow_up(due_day, today=today) else None
    if label is None:
        raise ValueError("the due day is outside the follow-up window")
    return f"¿Cómo te fue {label} con {topic}?"
