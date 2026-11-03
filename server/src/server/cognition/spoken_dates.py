"""Spoken date windows and labels for recall (ADR 0028 decision 7, Plan 0078).

Pure functions on folded Spanish (``normalize_spanish``): a window is the local calendar days on
which the owner **said** something, never when the story happened. «el verano de 2015» is no
window; it is searched as words. A date the parser does not understand is no window, never a
guess. Timestamps stay UTC; a day is cut at the household's local midnight. It reads no
setting: the cognitive core stays free of configuration (import-graph guard); the caller passes
the zone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
import re
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable
    from zoneinfo import ZoneInfo

__all__ = [
    "DayWindow",
    "date_label",
    "parse_spoken_window",
    "strip_window_words",
    "window_utc_bounds",
]

# Monday first, like ``date.weekday()``; never the process locale.
_WEEKDAYS: Final = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")
_MONTHS: Final = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)
# A spoken weekday label covers the days after «anteayer» and within the last week.
_LAST_WEEKDAY_LABEL_DAYS: Final = 6
_ANTEAYER_DAYS: Final = 2


@dataclass(frozen=True)
class DayWindow:
    """Inclusive local calendar days."""

    start: date
    end: date


def _day(days_back: int) -> Callable[[re.Match[str], date], DayWindow | None]:
    def window(_: re.Match[str], today: date) -> DayWindow | None:
        day = today - timedelta(days=days_back)
        return DayWindow(start=day, end=day)

    return window


def _weekday(match: re.Match[str], today: date) -> DayWindow | None:
    """The most recent past occurrence of the weekday, today excluded."""
    back = (today.weekday() - _WEEKDAYS.index(match.group("weekday"))) % 7 or 7
    day = today - timedelta(days=back)
    return DayWindow(start=day, end=day)


def _last_week(_: re.Match[str], today: date) -> DayWindow | None:
    """The seven days before the current week's Monday."""
    monday = today - timedelta(days=today.weekday())
    return DayWindow(start=monday - timedelta(days=7), end=monday - timedelta(days=1))


def _last_month(_: re.Match[str], today: date) -> DayWindow | None:
    end = today.replace(day=1) - timedelta(days=1)
    return DayWindow(start=end.replace(day=1), end=end)


def _day_of_month(match: re.Match[str], today: date) -> DayWindow | None:
    """The most recent past day with that day and month (today included); ``None`` if invalid."""
    day_number, month = int(match.group("day")), _MONTHS.index(match.group("month")) + 1
    for year in (today.year, today.year - 1):
        try:
            day = date(year, month, day_number)
        except ValueError:
            return None
        if day <= today:
            return DayWindow(start=day, end=day)
    return None


_WEEKDAY_ALTERNATION = "|".join(_WEEKDAYS)
_MONTH_ALTERNATION = "|".join(_MONTHS)
# Checked in this order; the first that matches makes the window.
_PATTERNS: Final[
    tuple[tuple[re.Pattern[str], Callable[[re.Match[str], date], DayWindow | None]], ...]
] = (
    (
        re.compile(r"\b(?:el )?(?P<day>\d{1,2}) de (?P<month>" + _MONTH_ALTERNATION + r")\b"),
        _day_of_month,
    ),
    (re.compile(r"\bla semana pasada\b"), _last_week),
    (re.compile(r"\bel mes pasado\b"), _last_month),
    (re.compile(r"\b(?:anteayer|antes de ayer)\b"), _day(_ANTEAYER_DAYS)),
    (re.compile(r"\bayer\b"), _day(1)),
    # «hoy día» is the Chilean «hoy»: «día» is part of the date, never a topic.
    (re.compile(r"\bhoy(?: dia)?\b"), _day(0)),
    (
        re.compile(r"\b(?:el |este )?(?P<weekday>" + _WEEKDAY_ALTERNATION + r")(?: pasado)?\b"),
        _weekday,
    ),
)


def parse_spoken_window(normalized: str, today: date) -> DayWindow | None:
    """Return the local days a spoken date names, or ``None`` when it names none.

    Args:
        normalized: The message folded by ``normalize_spanish``.
        today: The household's local date.

    Returns:
        The window of «hoy», «ayer», «anteayer», a weekday (its last past occurrence, today
        excluded), «la semana pasada» (Monday to Sunday of the previous week), «el mes pasado»
        or a day with its month (its last past occurrence); ``None`` otherwise.
    """
    for pattern, window in _PATTERNS:
        match = pattern.search(normalized)
        if match is not None:
            return window(match, today)
    return None


def strip_window_words(normalized: str) -> str:
    """Return *normalized* without the words of any spoken date window."""
    for pattern, _ in _PATTERNS:
        normalized = pattern.sub(" ", normalized)
    return " ".join(normalized.split())


def _local_midnight_utc(day: date, tz: ZoneInfo) -> str:
    """The first instant of a local day, as a UTC ISO string with microseconds.

    On a day whose midnight does not exist (the clock jumps from 00:00 to 01:00), ``fold=0``
    takes the offset before the change, which is that day's first real instant.
    """
    moment = datetime.combine(day, time(0), tzinfo=tz)
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


def window_utc_bounds(window: DayWindow, tz: ZoneInfo) -> tuple[str, str]:
    """Return the half-open UTC bounds ``[start 00:00 local, end + 1 day 00:00 local)``.

    Args:
        window: The local days.
        tz: The household time zone.

    Returns:
        The two bounds as UTC ISO 8601 strings with microseconds, comparable as text with the
        stored ``said_at`` values.
    """
    return (
        _local_midnight_utc(window.start, tz),
        _local_midnight_utc(window.end + timedelta(days=1), tz),
    )


def date_label(said_at: datetime, *, today: date, tz: ZoneInfo) -> str:
    """Return how the robot names the local day something was said (Plan 0078 D-7).

    Args:
        said_at: When it was said (timezone-aware).
        today: The household's local date.
        tz: The household time zone.

    Returns:
        «hoy», «ayer», «anteayer», «el jueves» within the last six days, «el 3 de marzo» in the
        same year, or «el 3 de marzo de 2025».
    """
    day = said_at.astimezone(tz).date()
    back = (today - day).days
    match back:
        case 0:
            return "hoy"
        case 1:
            return "ayer"
        case 2:
            return "anteayer"
        case _ if _ANTEAYER_DAYS < back <= _LAST_WEEKDAY_LABEL_DAYS:
            return f"el {_spoken_weekday(day)}"
        case _:
            month = _MONTHS[day.month - 1]
            if day.year == today.year:
                return f"el {day.day} de {month}"
            return f"el {day.day} de {month} de {day.year}"


def _spoken_weekday(day: date) -> str:
    """The weekday with its accents, as it is spoken."""
    return ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")[day.weekday()]
