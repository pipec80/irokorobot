"""The one reader of spoken time, past and future (ADR 0028 decision 7, ADR 0037 decision 4).

Pure functions on folded Spanish (``normalize_spanish``). One ordered table holds every phrase;
each entry carries its direction and which walk reads it. The **legacy** walk is what Plan 0078
reads for recall windows (``parse_spoken_window``, ``strip_window_words``), kept exactly; the
**full** walk (``read_spoken_time``, ``strip_time_words``, ``count_spoken_times``) adds the
future, the years and the seasons (Plan 0083). A phrase the table does not know is no time, never
a guess. Timestamps stay UTC; a day is cut at the household's local midnight. It reads no
setting: the cognitive core stays free of configuration (import-graph guard); the caller passes
the zone.

The module is longer than the 200-line guideline on purpose: it has one responsibility, spoken
time, and ADR 0037 decision 4 forbids a second date parser.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
import re
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable
    from zoneinfo import ZoneInfo

__all__ = [
    "DayWindow",
    "SpokenTime",
    "Toward",
    "count_spoken_times",
    "date_label",
    "day_month_label",
    "near_day_label",
    "occurred_label",
    "parse_spoken_window",
    "read_spoken_time",
    "strip_time_words",
    "strip_window_words",
    "window_utc_bounds",
]

# Monday first, like ``date.weekday()``; never the process locale.
_WEEKDAYS: Final = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")
_SPOKEN_WEEKDAYS: Final = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
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
# The household's seasons (Chile, southern hemisphere), by whole months (Plan 0083 D-5): the month
# each starts and ends in. The summer of year Y starts in December of Y - 1.
_SEASON_MONTHS: Final[dict[str, tuple[int, int]]] = {
    "verano": (12, 2),
    "otono": (3, 5),
    "invierno": (6, 8),
    "primavera": (9, 11),
}
# How each season is said, with its article: «primavera» is feminine.
_SPOKEN_SEASONS: Final = {
    "verano": "el verano",
    "otono": "el otoño",
    "invierno": "el invierno",
    "primavera": "la primavera",
}
# A spoken weekday label covers the days after «anteayer» and within the last week.
_LAST_WEEKDAY_LABEL_DAYS: Final = 6
_ANTEAYER_DAYS: Final = 2
_DAYS_IN_WEEK: Final = 7
_MONTHS_IN_YEAR: Final = 12
# Spoken years outside these bounds are no time (Plan 0083 D-4).
_FIRST_YEAR: Final = 1900
_YEARS_AHEAD: Final = 5
# How many years around today a season is looked for.
_SEASON_YEARS_AROUND: Final = 2


@dataclass(frozen=True)
class DayWindow:
    """Inclusive local calendar days, ``start <= end`` (every producer builds it so)."""

    start: date
    end: date


class Toward(StrEnum):
    """Which way a phrase that names no direction («el sábado») is read."""

    PAST = "past"
    FUTURE = "future"


@dataclass(frozen=True)
class SpokenTime:
    """A resolved time phrase.

    Attributes:
        window: The local days it names.
        ambiguous: Whether the phrase itself names no direction (Plan 0083 D-4): «el sábado»,
            «hoy», «en marzo», or a dated window that holds today.
    """

    window: DayWindow
    ambiguous: bool


class _Direction(StrEnum):
    # PAST and FUTURE mirror ``Toward``: a phrase of one direction is skipped toward the other.
    PAST = "past"
    FUTURE = "future"
    EITHER = "either"
    DATED = "dated"


class _Walk(StrEnum):
    LEGACY = "legacy"
    FULL = "full"
    BOTH = "both"


type _Resolver = Callable[[re.Match[str], date, Toward], DayWindow | None]


@dataclass(frozen=True)
class _Entry:
    pattern: re.Pattern[str]
    resolve: _Resolver
    direction: _Direction
    walk: _Walk


def _one_day(day: date) -> DayWindow:
    return DayWindow(start=day, end=day)


def _month_window(year: int, month: int) -> DayWindow:
    return DayWindow(start=date(year, month, 1), end=date(year, month, monthrange(year, month)[1]))


def _year_window(year: int) -> DayWindow:
    return DayWindow(start=date(year, 1, 1), end=date(year, 12, 31))


def _season_window(season: str, year: int) -> DayWindow:
    """The season of *year*; the summer of *year* starts in December of the year before."""
    first, last = _SEASON_MONTHS[season]
    start_year = year - 1 if first > last else year
    return DayWindow(
        start=date(start_year, first, 1), end=date(year, last, monthrange(year, last)[1])
    )


def _seasons_around(season: str, today: date) -> list[DayWindow]:
    """The windows of *season* from two years back to two years ahead, oldest first."""
    years = range(today.year - _SEASON_YEARS_AROUND, today.year + _SEASON_YEARS_AROUND + 1)
    return [_season_window(season, year) for year in years]


def _word_of(match: re.Match[str], words: tuple[str, ...] | dict[str, tuple[int, int]]) -> str:
    """The one word of *words* a match holds (a weekday or a season)."""
    return next(word for word in match.group(0).split() if word in words)


def _days(offset: int) -> _Resolver:
    def window(_: re.Match[str], today: date, __: Toward) -> DayWindow | None:
        return _one_day(today + timedelta(days=offset))

    return window


def _weekday(match: re.Match[str], today: date, toward: Toward) -> DayWindow | None:
    """The last occurrence before today, or the next after today; today is excluded both ways."""
    named = _WEEKDAYS.index(_word_of(match, _WEEKDAYS))
    if toward is Toward.PAST:
        back = (today.weekday() - named) % _DAYS_IN_WEEK or _DAYS_IN_WEEK
        return _one_day(today - timedelta(days=back))
    ahead = (named - today.weekday()) % _DAYS_IN_WEEK or _DAYS_IN_WEEK
    return _one_day(today + timedelta(days=ahead))


def _week(offset: int) -> _Resolver:
    def window(_: re.Match[str], today: date, __: Toward) -> DayWindow | None:
        monday = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
        return DayWindow(start=monday, end=monday + timedelta(days=_DAYS_IN_WEEK - 1))

    return window


def _shifted_month(today: date, offset: int) -> DayWindow:
    """The month *offset* months from today's month."""
    year, index = divmod(today.year * _MONTHS_IN_YEAR + today.month - 1 + offset, 12)
    return _month_window(year, index + 1)


def _month(offset: int) -> _Resolver:
    def window(_: re.Match[str], today: date, __: Toward) -> DayWindow | None:
        return _shifted_month(today, offset)

    return window


def _count(match: re.Match[str]) -> int:
    word = match.group("count")
    return int(word) if word.isdigit() else _COUNT_WORDS[word]


def _ago(match: re.Match[str], today: date, _: Toward) -> DayWindow | None:
    """«hace N días» is that day, «semanas» that week, «meses» that month, «años» that year."""
    count = _count(match)
    match match.group("unit"):
        case "dia" | "dias":
            return _one_day(today - timedelta(days=count))
        case "semana" | "semanas":
            day = today - timedelta(weeks=count)
            monday = day - timedelta(days=day.weekday())
            return DayWindow(start=monday, end=monday + timedelta(days=_DAYS_IN_WEEK - 1))
        case "mes" | "meses":
            return _shifted_month(today, -count)
        case _:
            return _year_window(today.year - count)


def _in_days(match: re.Match[str], today: date, _: Toward) -> DayWindow | None:
    """«en N días (más)», «dentro de N días»: that day ahead."""
    return _one_day(today + timedelta(days=_count(match)))


def _last_year_day(match: re.Match[str], today: date, _: Toward) -> DayWindow | None:
    return _day_of_year(match, today.year - 1)


def _last_year_month(match: re.Match[str], today: date, _: Toward) -> DayWindow | None:
    return _month_of_year(match, today.year - 1)


def _last_year_season(match: re.Match[str], today: date, _: Toward) -> DayWindow | None:
    return _season_of_year(match, today.year - 1)


def _relative_year(offset: int) -> _Resolver:
    def window(_: re.Match[str], today: date, __: Toward) -> DayWindow | None:
        return _year_window(today.year + offset)

    return window


def _day_of_month(match: re.Match[str], today: date, toward: Toward) -> DayWindow | None:
    """The last such day on or before today, or the first on or after it; ``None`` if invalid."""
    day_number, month = int(match.group("day")), _MONTHS.index(match.group("month")) + 1
    past = toward is Toward.PAST
    for year in (today.year, today.year - 1 if past else today.year + 1):
        try:
            day = date(year, month, day_number)
        except ValueError:
            return None
        if (day <= today) if past else (day >= today):
            return _one_day(day)
    return None


def _named_month(match: re.Match[str], today: date, toward: Toward) -> DayWindow | None:
    """The last such month that started on or before today, or the next that ends on or after."""
    month = _MONTHS.index(match.group("month")) + 1
    if toward is Toward.PAST:
        return _month_window(today.year if month <= today.month else today.year - 1, month)
    return _month_window(today.year if month >= today.month else today.year + 1, month)


def _named_season(match: re.Match[str], today: date, toward: Toward) -> DayWindow | None:
    """The last such season that started on or before today, or the next that ends on or after."""
    windows = _seasons_around(_word_of(match, _SEASON_MONTHS), today)
    if toward is Toward.PAST:
        return [window for window in windows if window.start <= today][-1]
    return next(window for window in windows if window.end >= today)


def _last_season(match: re.Match[str], today: date, _: Toward) -> DayWindow | None:
    """The last whole season that ended before today."""
    windows = _seasons_around(_word_of(match, _SEASON_MONTHS), today)
    return [window for window in windows if window.end < today][-1]


def _next_season(match: re.Match[str], today: date, _: Toward) -> DayWindow | None:
    """The first season that starts after today."""
    windows = _seasons_around(_word_of(match, _SEASON_MONTHS), today)
    return next(window for window in windows if window.start > today)


def _dated(build: Callable[[re.Match[str], int], DayWindow | None]) -> _Resolver:
    """A resolver for a phrase with its own year; a year out of bounds is no time."""

    def window(match: re.Match[str], today: date, _: Toward) -> DayWindow | None:
        year = int(match.group("year"))
        if not _FIRST_YEAR <= year <= today.year + _YEARS_AHEAD:
            return None
        return build(match, year)

    return window


def _day_of_year(match: re.Match[str], year: int) -> DayWindow | None:
    try:
        day = date(year, _MONTHS.index(match.group("month")) + 1, int(match.group("day")))
    except ValueError:
        return None
    return _one_day(day)


def _month_of_year(match: re.Match[str], year: int) -> DayWindow | None:
    return _month_window(year, _MONTHS.index(match.group("month")) + 1)


def _season_of_year(match: re.Match[str], year: int) -> DayWindow | None:
    return _season_window(_word_of(match, _SEASON_MONTHS), year)


def _whole_year(_: re.Match[str], year: int) -> DayWindow | None:
    return _year_window(year)


_WEEKDAY: Final = "(?:" + "|".join(_WEEKDAYS) + ")"
_MONTH: Final = "(?P<month>" + "|".join(_MONTHS) + ")"
_YEAR: Final = r"(?P<year>\d{4})"
# «hace tres días», «en 3 días más» (Pipec, 2026-11-12, hardware): a count in digits or words.
_COUNT_WORDS: Final[dict[str, int]] = {
    "un": 1,
    "una": 1,
    "uno": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
}
_COUNT: Final = r"(?P<count>\d{1,2}|" + "|".join(_COUNT_WORDS) + ")"
# A season with its article: «el verano», «la primavera».
_SEASON: Final = "(?:el (?:verano|otono|invierno)|la primavera)"
_SEASON_WORD: Final = "(?:verano|otono|invierno|primavera)"
# «en verano», «en el verano», «el verano», «en la primavera», «la primavera». A bare season word
# is no time («este verano», «las vacaciones de verano», D-6); with a year it is («verano de 2015»).
_SEASON_LEAD: Final = "(?:en (?:el |la )?|el |la )"


def _entry(regex: str, resolve: _Resolver, direction: _Direction, walk: _Walk) -> _Entry:
    return _Entry(re.compile(rf"\b(?:{regex})\b"), resolve, direction, walk)


_E, _P, _F, _D = _Direction.EITHER, _Direction.PAST, _Direction.FUTURE, _Direction.DATED
_LEG, _FULL, _BOTH = _Walk.LEGACY, _Walk.FULL, _Walk.BOTH
# Checked in this order; the first that matches makes the window, and a longer phrase comes before
# the shorter one inside it. The legacy walk reads, in order, the day of a month, «la semana
# pasada», «el mes pasado», «anteayer», «ayer», «hoy» and the weekday, exactly as Plan 0078 did.
_TABLE: Final[tuple[_Entry, ...]] = (
    # «… del año pasado» names the year of a day, a month or a season (Pipec, 2026-11-12).
    _entry(rf"(?:el )?(?P<day>\d{{1,2}}) de {_MONTH} del ano pasado", _last_year_day, _P, _FULL),
    _entry(rf"(?:en )?{_MONTH} del ano pasado", _last_year_month, _P, _FULL),
    _entry(rf"{_SEASON_LEAD}?{_SEASON_WORD} del ano pasado", _last_year_season, _P, _FULL),
    _entry(rf"hace {_COUNT} (?P<unit>dias?|semanas?|mes|meses|anos?)", _ago, _P, _FULL),
    _entry(rf"(?:en|dentro de) {_COUNT} dias?(?: mas)?", _in_days, _F, _FULL),
    _entry(
        rf"(?:el )?(?P<day>\d{{1,2}}) de {_MONTH} del? {_YEAR}", _dated(_day_of_year), _D, _FULL
    ),
    _entry(rf"(?:el )?(?P<day>\d{{1,2}}) de {_MONTH}", _day_of_month, _E, _BOTH),
    _entry(rf"(?:en )?{_MONTH} del? {_YEAR}", _dated(_month_of_year), _D, _FULL),
    _entry(rf"{_SEASON_LEAD}?{_SEASON_WORD} del? {_YEAR}", _dated(_season_of_year), _D, _FULL),
    _entry("la semana pasada", _week(-1), _P, _BOTH),
    _entry("la proxima semana|la semana que viene", _week(1), _F, _FULL),
    _entry("el mes pasado", _month(-1), _P, _BOTH),
    _entry("el proximo mes|el mes que viene", _month(1), _F, _FULL),
    _entry("el ano pasado", _relative_year(-1), _P, _FULL),
    _entry("el proximo ano|el ano que viene", _relative_year(1), _F, _FULL),
    _entry(rf"(?:en el ano|el ano|en el|en|el) {_YEAR}", _dated(_whole_year), _D, _FULL),
    _entry("el (?:verano|otono|invierno) pasado|la primavera pasada", _last_season, _P, _FULL),
    _entry(
        rf"el proximo (?:verano|otono|invierno)|la proxima primavera|{_SEASON} que viene",
        _next_season,
        _F,
        _FULL,
    ),
    _entry("pasado manana", _days(2), _F, _FULL),
    _entry("esta manana|esta tarde|esta noche", _days(0), _E, _FULL),
    # «la mañana», «esta mañana», «por la mañana»: the morning, never tomorrow (Review focus 1).
    _entry(r"(?<!\bla )(?<!\besta )manana", _days(1), _F, _FULL),
    _entry("anteayer|antes de ayer", _days(-_ANTEAYER_DAYS), _P, _BOTH),
    _entry("ayer", _days(-1), _P, _BOTH),
    # «hoy día» is the Chilean «hoy»: «día» is part of the date, never a topic.
    _entry("hoy(?: dia)?", _days(0), _E, _BOTH),
    _entry(rf"(?:el )?{_WEEKDAY} pasado", _weekday, _P, _FULL),
    _entry(rf"el proximo {_WEEKDAY}|(?:el |este ){_WEEKDAY} que viene", _weekday, _F, _FULL),
    _entry(rf"(?:el |este )?{_WEEKDAY}(?: pasado)?", _weekday, _P, _LEG),
    # A plural weekday («los lunes») is a habit, no time (D-6).
    _entry(rf"(?:(?:el|este) )?(?<!\blos ){_WEEKDAY}", _weekday, _E, _FULL),
    _entry(rf"en {_MONTH}", _named_month, _E, _FULL),
    _entry(f"{_SEASON_LEAD}{_SEASON_WORD}", _named_season, _E, _FULL),
)
_LEGACY_WALK: Final = tuple(entry for entry in _TABLE if entry.walk is not _Walk.FULL)
_FULL_WALK: Final = tuple(entry for entry in _TABLE if entry.walk is not _Walk.LEGACY)


def parse_spoken_window(normalized: str, today: date) -> DayWindow | None:
    """Return the local days a spoken date names, or ``None`` when it names none.

    The legacy walk of Plan 0078, read toward the past.

    Args:
        normalized: The message folded by ``normalize_spanish``.
        today: The household's local date.

    Returns:
        The window of «hoy», «ayer», «anteayer», a weekday (its last past occurrence, today
        excluded), «la semana pasada» (Monday to Sunday of the previous week), «el mes pasado»
        or a day with its month (its last past occurrence); ``None`` otherwise.
    """
    for entry in _LEGACY_WALK:
        match = entry.pattern.search(normalized)
        if match is not None:
            return entry.resolve(match, today, Toward.PAST)
    return None


def strip_window_words(normalized: str) -> str:
    """Return *normalized* without the words of any legacy spoken date window."""
    return _strip(normalized, _LEGACY_WALK)


def _strip(normalized: str, walk: tuple[_Entry, ...]) -> str:
    for entry in walk:
        normalized = entry.pattern.sub(" ", normalized)
    return " ".join(normalized.split())


def _accepts(entry: _Entry, window: DayWindow, today: date, toward: Toward) -> SpokenTime | None:
    """Whether a resolved window is a time toward *toward*, and how surely (Plan 0083 D-4)."""
    match entry.direction:
        case _Direction.EITHER:
            return SpokenTime(window=window, ambiguous=True)
        case _Direction.DATED:
            reached = window.start <= today if toward is Toward.PAST else window.end >= today
            if not reached:
                return None
            return SpokenTime(window=window, ambiguous=window.start <= today <= window.end)
        case _:
            return SpokenTime(window=window, ambiguous=False)


def read_spoken_time(normalized: str, today: date, *, toward: Toward) -> SpokenTime | None:
    """Return the time a message names, read toward the past or the future.

    Args:
        normalized: The message folded by ``normalize_spanish``.
        today: The household's local date.
        toward: How a phrase that names no direction is read; a phrase of the other direction
            («ayer» toward the future) is skipped.

    Returns:
        The first phrase of the table that resolves in that direction, or ``None``: a phrase the
        table does not know, an invalid date and a year out of bounds are no time. A phrase that
        matches and does not resolve takes its words along, so a shorter phrase inside it
        («el sábado» inside «el sábado pasado») is never read instead.
    """
    skipped = _Direction.FUTURE if toward is Toward.PAST else _Direction.PAST
    for entry in _FULL_WALK:
        match = entry.pattern.search(normalized)
        if match is None:
            continue
        if entry.direction is not skipped:
            window = entry.resolve(match, today, toward)
            spoken = None if window is None else _accepts(entry, window, today, toward)
            if spoken is not None:
                return spoken
        normalized = entry.pattern.sub(" ", normalized)
    return None


def strip_time_words(normalized: str) -> str:
    """Return *normalized* without the words of any time phrase of the full table."""
    return _strip(normalized, _FULL_WALK)


def count_spoken_times(normalized: str) -> int:
    """Return how many time phrases *normalized* holds, each counted once.

    A longer phrase wins over a shorter one inside it: «pasado mañana» and «el sábado pasado» are
    one phrase each.
    """
    count = 0
    for entry in _FULL_WALK:
        normalized, found = entry.pattern.subn(" ", normalized)
        count += found
    return count


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
    near = near_day_label(back)
    if near is not None:
        return near
    if _ANTEAYER_DAYS < back <= _LAST_WEEKDAY_LABEL_DAYS:
        return f"el {_SPOKEN_WEEKDAYS[day.weekday()]}"
    return day_month_label(day) + _other_year(day.year, today)


def near_day_label(back: int) -> str | None:
    """Return how a near day is said.

    Args:
        back: How many days before today the day is.

    Returns:
        «hoy», «ayer» or «anteayer» for 0, 1 or 2 days back; ``None`` for any other distance.
    """
    match back:
        case 0:
            return "hoy"
        case 1:
            return "ayer"
        case 2:
            return "anteayer"
        case _:
            return None


def day_month_label(day: date) -> str:
    """Return the day and month as it is spoken, without the year.

    Args:
        day: The calendar day.

    Returns:
        «el 3 de marzo».
    """
    return f"el {day.day} de {_MONTHS[day.month - 1]}"


def _other_year(year: int, today: date) -> str:
    return "" if year == today.year else f" de {year}"


def _day_label(day: date, today: date) -> str:
    near = near_day_label((today - day).days)
    if near is not None:
        return near
    if day.year == today.year:
        return f"el {_SPOKEN_WEEKDAYS[day.weekday()]} {day.day} de {_MONTHS[day.month - 1]}"
    return f"{day_month_label(day)} de {day.year}"


def _season_of(window: DayWindow) -> str | None:
    """The season *window* is exactly, or ``None``."""
    for season in _SEASON_MONTHS:
        if _season_window(season, window.end.year) == window:
            return season
    return None


def occurred_label(window: DayWindow, *, today: date) -> str:
    """Return how the robot names when a told event happened (Plan 0083 D-11).

    Args:
        window: The occurred interval, one of the spans the reader resolves.
        today: The household's local date.

    Returns:
        «ayer», «el sábado 7 de noviembre», «la semana del lunes 2 de noviembre», «en marzo de
        2015», «en el verano de 2015» or «en 2015».

    Raises:
        ValueError: If no spoken span describes the window; the message holds no date.
    """
    start, end = window.start, window.end
    if start == end:
        return _day_label(start, today)
    if start.weekday() == 0 and (end - start).days == _DAYS_IN_WEEK - 1:
        return f"la semana del lunes {start.day} de {_MONTHS[start.month - 1]}" + _other_year(
            start.year, today
        )
    if window == _month_window(start.year, start.month):
        return f"en {_MONTHS[start.month - 1]}" + _other_year(start.year, today)
    season = _season_of(window)
    if season is not None:
        return f"en {_SPOKEN_SEASONS[season]} de {end.year}"
    if window == _year_window(start.year):
        return f"en {start.year}"
    raise ValueError("no spoken span describes this window")
