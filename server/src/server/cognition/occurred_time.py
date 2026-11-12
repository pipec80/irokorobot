"""When a told event happened: the occurred interval of the owner's words (Plan 0083 D-7).

ADR 0037 decision 3 and ADR 0031 decision 5: the occurred time is stored only when the owner says
it, never inferred. Pure and closed: the words must hold exactly one time phrase of the shared
reader (``spoken_dates``), read toward the past against the day they were said; a phrase that
names no direction («el sábado», «hoy», «en marzo») also needs a first-person or narrative past
verb of a closed list, so a plan («el sábado salimos a pasear») or a habit is no event.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from server.cognition.spoken_dates import Toward, count_spoken_times, read_spoken_time
from server.text_keys import normalize_spanish

if TYPE_CHECKING:
    from datetime import date

    from server.cognition.spoken_dates import DayWindow

__all__ = ["TOLD_PAST_VERBS", "occurred_window"]

# Folded past verbs that tell a done event. Not ``recall_cues._WHEN_VERBS``: a statement must
# leave out every form that is also a present («salimos», «viajamos», «vivimos», «paso»), a
# subjunctive («compre», «hable», «llegue», «trabaje», «estudie», «visite») or a noun («viaje»,
# «pase»), since «el sábado» says no direction by itself.
TOLD_PAST_VERBS: Final[frozenset[str]] = frozenset(
    {
        "fui", "fuimos", "fue", "fueron", "estuve", "estuvimos", "estuvo", "hice", "hicimos",
        "hizo", "tuve", "tuvimos", "vi", "vimos", "comi", "comimos", "conoci", "conocimos",
        "volvi", "volvimos", "sali", "naci", "nacio", "vivi", "jugue", "fallecio", "murio", "hubo",
    }
)  # fmt: skip


def occurred_window(heard: str, *, said_day: date) -> DayWindow | None:
    """Return when the event the owner told happened, or ``None`` when the words do not say it.

    Args:
        heard: The owner's words of one turn, as transcribed.
        said_day: The household's local day the words were said (the turn's own time, not the
            clock of the job that indexes it).

    Returns:
        The interval of the one time phrase, read toward the past; ``None`` for no phrase, two or
        more, a phrase toward the future, or a phrase that names no direction without a verb of
        ``TOLD_PAST_VERBS``.
    """
    normalized = normalize_spanish(heard)
    if count_spoken_times(normalized) != 1:
        return None
    spoken = read_spoken_time(normalized, said_day, toward=Toward.PAST)
    if spoken is None:
        return None
    if spoken.ambiguous and TOLD_PAST_VERBS.isdisjoint(normalized.split()):
        return None
    return spoken.window
