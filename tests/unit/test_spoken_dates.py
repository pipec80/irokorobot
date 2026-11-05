"""Spoken date windows and labels for recall (Plan 0078 Task 2, ADR 0028 decision 7)."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import ValidationError
import pytest
from server.cognition.spoken_dates import (
    DayWindow,
    date_label,
    day_month_label,
    parse_spoken_window,
    strip_window_words,
    window_utc_bounds,
)
from server.memory.recall_search import household_zone
from server.settings import Settings, settings
from server.text_keys import normalize_spanish

pytestmark = pytest.mark.unit

_SANTIAGO = ZoneInfo("America/Santiago")
# A Wednesday.
_WEDNESDAY = date(2026, 11, 4)


def _window(text: str, today: date = _WEDNESDAY) -> DayWindow | None:
    return parse_spoken_window(normalize_spanish(text), today)


def _local_day_hours(year: int) -> Counter[date]:
    """How many UTC hours fall on each local day of *year*, counted hour by hour from zoneinfo."""
    hours: Counter[date] = Counter()
    moment, end = datetime(year, 1, 2, tzinfo=UTC), datetime(year, 12, 30, tzinfo=UTC)
    while moment < end:
        hours[moment.astimezone(_SANTIAGO).date()] += 1
        moment += timedelta(hours=1)
    return hours


def _clock_change_days(year: int) -> list[tuple[date, int]]:
    """The local days that are not 24 hours long, with their length in hours."""
    hours = _local_day_hours(year)
    first, last = min(hours), max(hours)
    return sorted(
        (day, count) for day, count in hours.items() if count != 24 and day not in (first, last)
    )


def test_ayer_at_half_past_midnight_is_the_previous_local_day() -> None:
    # At 00:30 on 4 November «ayer» is the whole local 3 November, not the 24 hours before now.
    now = datetime(2026, 11, 4, 0, 30, tzinfo=_SANTIAGO)
    today = now.astimezone(_SANTIAGO).date()

    window = _window("¿qué te conté ayer?", today)

    assert window == DayWindow(start=date(2026, 11, 3), end=date(2026, 11, 3))
    assert window is not None
    since, until = window_utc_bounds(window, _SANTIAGO)
    assert datetime.fromisoformat(since).astimezone(_SANTIAGO) == datetime(
        2026, 11, 3, tzinfo=_SANTIAGO
    )
    assert datetime.fromisoformat(until).astimezone(_SANTIAGO) == datetime(
        2026, 11, 4, tzinfo=_SANTIAGO
    )


@pytest.mark.parametrize("day, length", _clock_change_days(2026))
def test_the_window_on_the_day_chile_changes_its_clock_spans_the_whole_local_day(
    day: date, length: int
) -> None:
    since, until = window_utc_bounds(DayWindow(start=day, end=day), _SANTIAGO)
    start = datetime.fromisoformat(since)
    end = datetime.fromisoformat(until)
    tick = timedelta(microseconds=1)

    assert start.astimezone(_SANTIAGO).date() == day
    assert (start - tick).astimezone(_SANTIAGO).date() == day - timedelta(days=1)
    assert end.astimezone(_SANTIAGO).date() == day + timedelta(days=1)
    assert (end - tick).astimezone(_SANTIAGO).date() == day
    assert end - start == timedelta(hours=length)


def test_chile_changes_its_clock_twice_in_2026() -> None:
    assert len(_clock_change_days(2026)) == 2


def test_bounds_are_utc_iso_with_microseconds() -> None:
    since, until = window_utc_bounds(DayWindow(start=_WEDNESDAY, end=_WEDNESDAY), _SANTIAGO)

    for bound in (since, until):
        parsed = datetime.fromisoformat(bound)
        assert parsed.utcoffset() == timedelta(0)
        assert "." in bound


@pytest.mark.parametrize(
    "text, start, end",
    [
        ("hoy", date(2026, 11, 4), date(2026, 11, 4)),
        ("ayer", date(2026, 11, 3), date(2026, 11, 3)),
        ("anteayer", date(2026, 11, 2), date(2026, 11, 2)),
        ("el lunes", date(2026, 11, 2), date(2026, 11, 2)),
        ("el sábado", date(2026, 10, 31), date(2026, 10, 31)),
        ("el mes pasado", date(2026, 10, 1), date(2026, 10, 31)),
        ("el 3 de marzo", date(2026, 3, 3), date(2026, 3, 3)),
    ],
)
def test_each_spoken_form_gives_its_window(text: str, start: date, end: date) -> None:
    assert _window(f"¿qué te conté {text}?") == DayWindow(start=start, end=end)


def test_hoy_dia_is_today_and_leaves_no_topic_word() -> None:
    """Chilean «hoy día» (found on Pipec's hardware run, 2026-11-03): «día» is not a topic."""
    assert _window("¿Qué hice hoy día?") == DayWindow(start=_WEDNESDAY, end=_WEDNESDAY)
    assert strip_window_words(normalize_spanish("qué hice hoy día")) == "que hice"


def test_el_martes_on_a_tuesday_is_last_week() -> None:
    tuesday = date(2026, 11, 3)

    assert _window("¿qué te dije el martes?", tuesday) == DayWindow(
        start=date(2026, 10, 27), end=date(2026, 10, 27)
    )


def test_la_semana_pasada_is_monday_to_sunday() -> None:
    window = _window("¿qué te conté la semana pasada?")

    assert window == DayWindow(start=date(2026, 10, 26), end=date(2026, 11, 1))
    assert window is not None
    assert window.start.weekday() == 0
    assert window.end.weekday() == 6


def test_el_3_de_marzo_in_january_is_last_year() -> None:
    assert _window("¿qué te conté el 3 de marzo?", date(2027, 1, 15)) == DayWindow(
        start=date(2026, 3, 3), end=date(2026, 3, 3)
    )


def test_el_mes_pasado_in_january_is_last_december() -> None:
    assert _window("¿qué te conté el mes pasado?", date(2027, 1, 15)) == DayWindow(
        start=date(2026, 12, 1), end=date(2026, 12, 31)
    )


def test_an_unknown_date_is_no_window() -> None:
    assert _window("¿qué te conté el día del cumple de la Zeta?") is None


def test_an_impossible_date_is_no_window() -> None:
    assert _window("¿qué te conté el 31 de febrero?") is None


def test_el_verano_de_2015_is_no_window() -> None:
    assert _window("¿te acuerdas qué hice el verano de 2015?") is None


def test_strip_window_words_drops_only_the_window() -> None:
    assert strip_window_words(normalize_spanish("qué hice el sábado con Zeta")) == (
        "que hice con zeta"
    )
    assert strip_window_words(normalize_spanish("qué te conté ayer del viaje")) == (
        "que te conte del viaje"
    )
    assert strip_window_words(normalize_spanish("el 3 de marzo fuimos al cerro")) == (
        "fuimos al cerro"
    )


@pytest.mark.parametrize(
    "said, label",
    [
        (datetime(2026, 11, 4, 15, tzinfo=UTC), "hoy"),
        (datetime(2026, 11, 3, 15, tzinfo=UTC), "ayer"),
        (datetime(2026, 11, 2, 15, tzinfo=UTC), "anteayer"),
        (datetime(2026, 10, 29, 15, tzinfo=UTC), "el jueves"),
        (datetime(2026, 3, 3, 15, tzinfo=UTC), "el 3 de marzo"),
        (datetime(2025, 3, 3, 15, tzinfo=UTC), "el 3 de marzo de 2025"),
    ],
)
def test_labels(said: datetime, label: str) -> None:
    assert date_label(said, today=_WEDNESDAY, tz=_SANTIAGO) == label


@pytest.mark.parametrize(
    "day, label",
    [
        (date(2015, 3, 3), "el 3 de marzo"),
        (date(1990, 9, 21), "el 21 de septiembre"),
        (date(2024, 2, 29), "el 29 de febrero"),
        (date(2026, 1, 1), "el 1 de enero"),
    ],
)
def test_day_month_label_ignores_the_year(day: date, label: str) -> None:
    assert day_month_label(day) == label


def test_a_label_uses_the_local_day_not_the_utc_day() -> None:
    # 02:00 UTC on 4 November is 23:00 on 3 November in Santiago.
    said = datetime(2026, 11, 4, 2, tzinfo=UTC)

    assert date_label(said, today=_WEDNESDAY, tz=_SANTIAGO) == "ayer"


def test_the_timezone_setting_rejects_an_unknown_zone() -> None:
    with pytest.raises(ValidationError):
        Settings(household_timezone="America/Atlantida")  # pyright: ignore[reportCallIssue]


def test_the_household_zone_comes_from_the_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "household_timezone", "Europe/Madrid")

    assert household_zone() == ZoneInfo("Europe/Madrid")


def test_the_default_embedding_model_is_granite() -> None:
    assert Settings.model_fields["embedding_model"].default == "granite-embedding:278m"
    assert Settings.model_fields["household_timezone"].default == "America/Santiago"
