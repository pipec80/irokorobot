"""The one time format of the writers (Plan 0085, decision D-3)."""

from datetime import UTC, date, datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo

import pytest
from server.timestamps import INSTANT_LENGTH, day_text, instant_text, parse_instant, validity_day

_INSTANT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00")


@pytest.mark.unit
def test_an_offset_moment_becomes_its_utc_instant() -> None:
    moment = datetime(2026, 11, 16, 10, 0, 0, 123456, tzinfo=timezone(timedelta(hours=3)))

    text = instant_text(moment)

    assert text == "2026-11-16T07:00:00.123456+00:00"
    assert len(text) == INSTANT_LENGTH == 32


@pytest.mark.unit
def test_a_naive_moment_is_refused() -> None:
    with pytest.raises(ValueError, match="naive"):
        instant_text(datetime(2026, 11, 16, 10, 0, 0))


@pytest.mark.unit
def test_a_moment_without_microseconds_still_has_32_characters() -> None:
    text = instant_text(datetime(2026, 11, 16, 10, 0, 0, tzinfo=UTC))

    assert len(text) == INSTANT_LENGTH
    assert _INSTANT.fullmatch(text)


@pytest.mark.unit
def test_the_text_round_trips() -> None:
    moment = datetime(2026, 11, 16, 7, 0, 0, 5, tzinfo=UTC)

    assert parse_instant(instant_text(moment)) == moment


@pytest.mark.unit
def test_text_order_is_time_order() -> None:
    base = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
    moments = [
        base + timedelta(microseconds=1),
        base,
        base + timedelta(seconds=1),
        base - timedelta(days=400),
        base + timedelta(days=400, microseconds=999999),
        base.replace(microsecond=0) + timedelta(microseconds=10),
    ]

    assert sorted(instant_text(m) for m in moments) == [instant_text(m) for m in sorted(moments)]


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "2026-11-16 07:00:00",
        "2026-11-16T07:00:00+00:00",
        "2026-11-16T07:00:00.123456",
        "2026-11-16T10:00:00.123456+03:00",
        "",
    ],
)
def test_parse_refuses_any_other_format(text: str) -> None:
    with pytest.raises(ValueError, match="instant"):
        parse_instant(text)


@pytest.mark.unit
def test_the_validity_day_is_the_household_day() -> None:
    moment = datetime(2026, 11, 16, 2, 30, tzinfo=UTC)

    assert validity_day(moment, ZoneInfo("America/Santiago")) == "2026-11-15"
    assert validity_day(moment, ZoneInfo("UTC")) == "2026-11-16"


@pytest.mark.unit
def test_a_naive_moment_has_no_validity_day() -> None:
    with pytest.raises(ValueError, match="naive"):
        validity_day(datetime(2026, 11, 16, 10, 0, 0), ZoneInfo("America/Santiago"))


@pytest.mark.unit
def test_day_text() -> None:
    assert day_text(date(2026, 1, 5)) == "2026-01-05"
