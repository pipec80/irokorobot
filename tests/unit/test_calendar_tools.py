"""Unit tests for deterministic P0.3 calendar tools."""

from datetime import date

from server.cognition.calendar_tools import calculate_age, get_current_date
from server.cognition.models import KnowledgeStatus


def test_get_current_date_returns_the_injected_iso_date() -> None:
    """Reject a date tool that reads the system clock instead of its input."""
    result = get_current_date(date(2026, 8, 12))

    assert result.status is KnowledgeStatus.KNOWN
    assert result.value == "2026-08-12"


def test_calculate_age_counts_completed_years_at_birthday_boundary() -> None:
    """Reject an age calculation that rounds calendar years incorrectly."""
    before_birthday = calculate_age("2017-12-29", date(2026, 12, 28))
    on_birthday = calculate_age("2017-12-29", date(2026, 12, 29))

    assert before_birthday.value == 8
    assert on_birthday.value == 9
    assert before_birthday.status is KnowledgeStatus.KNOWN
    assert on_birthday.status is KnowledgeStatus.KNOWN


def test_calculate_age_uses_february_28_for_leap_day_birthdays_in_common_years() -> None:
    """Define the leap-day anniversary rule rather than leaving it implicit."""
    before_anniversary = calculate_age("2020-02-29", date(2021, 2, 27))
    on_anniversary = calculate_age("2020-02-29", date(2021, 2, 28))

    assert before_anniversary.value == 0
    assert on_anniversary.value == 1


def test_calculate_age_returns_unknown_for_future_or_invalid_birth_date() -> None:
    """Reject a tool that guesses an age for invalid input."""
    future = calculate_age("2027-01-01", date(2026, 8, 12))
    malformed = calculate_age("12/08/2020", date(2026, 8, 12))

    assert future.status is KnowledgeStatus.UNKNOWN
    assert malformed.status is KnowledgeStatus.UNKNOWN
    assert future.value is None
    assert malformed.value is None
