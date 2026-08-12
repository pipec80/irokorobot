"""Pure deterministic calendar tools for the P0.3 controller."""

from datetime import date

from server.cognition.models import KnowledgeStatus
from server.cognition.response_plan import ToolResult

_FEBRUARY = 2
_LEAP_DAY = 29
_COMMON_YEAR_LEAP_DAY_ANNIVERSARY = 28


def get_current_date(today: date) -> ToolResult:
    """Return an injected current date without reading a system clock.

    Args:
        today: Date supplied by the controller's clock boundary.

    Returns:
        A known deterministic ISO date result.
    """
    return ToolResult(
        tool_name="get_current_date",
        status=KnowledgeStatus.KNOWN,
        value=today.isoformat(),
    )


def calculate_age(birth_date: str, on_date: date) -> ToolResult:
    """Calculate completed years from a strict ISO birth date.

    Args:
        birth_date: Date of birth in exact ``YYYY-MM-DD`` form.
        on_date: Date on which age is evaluated.

    Returns:
        A known integer age or an unknown result with a safe reason.
    """
    born = _parse_iso_date(birth_date)
    if born is None:
        return _unknown_age("birth date must use strict ISO YYYY-MM-DD format")
    if born > on_date:
        return _unknown_age("birth date is in the future")
    anniversary = _anniversary_in_year(born, on_date.year)
    age = on_date.year - born.year
    if on_date < anniversary:
        age -= 1
    return ToolResult(
        tool_name="calculate_age",
        status=KnowledgeStatus.KNOWN,
        value=age,
    )


def _parse_iso_date(value: str) -> date | None:
    """Return an exact ISO date or no value for malformed input."""
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    if parsed.isoformat() != value:
        return None
    return parsed


def _anniversary_in_year(birth_date: date, year: int) -> date:
    """Return the birthday anniversary, using February 28 for leap-day births."""
    if birth_date.month == _FEBRUARY and birth_date.day == _LEAP_DAY:
        try:
            return birth_date.replace(year=year)
        except ValueError:
            return date(year, _FEBRUARY, _COMMON_YEAR_LEAP_DAY_ANNIVERSARY)
    return birth_date.replace(year=year)


def _unknown_age(reason: str) -> ToolResult:
    """Build one safe unknown age result."""
    return ToolResult(
        tool_name="calculate_age",
        status=KnowledgeStatus.UNKNOWN,
        reason=reason,
    )
