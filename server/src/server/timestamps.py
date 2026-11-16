"""The one time format of the writers (Plan 0085, decision D-3).

An instant is stored as UTC ISO 8601 with microseconds and an explicit ``+00:00`` offset, always
32 characters, so a text comparison is a time comparison. A calendar day (the validity of a
temporal fact or relation) is ``YYYY-MM-DD``. Standard library only: this module reads no
settings, database or framework.
"""

from datetime import UTC, date, datetime
from typing import Final
from zoneinfo import ZoneInfo

__all__ = ["INSTANT_LENGTH", "day_text", "instant_text", "parse_instant", "validity_day"]

INSTANT_LENGTH: Final = 32


def instant_text(moment: datetime) -> str:
    """Format an aware instant as the 32-character UTC text every writer stores.

    Args:
        moment: A timezone-aware datetime.

    Returns:
        ``YYYY-MM-DDTHH:MM:SS.ffffff+00:00`` in UTC.

    Raises:
        ValueError: If ``moment`` is naive.
    """
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("a naive datetime is not an instant: it must be timezone-aware")
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


def parse_instant(text: str) -> datetime:
    """Parse the text written by :func:`instant_text`; any other format is refused.

    Args:
        text: A 32-character UTC instant.

    Returns:
        The aware UTC datetime.

    Raises:
        ValueError: If ``text`` is not exactly the 32-character UTC format.
    """
    if len(text) != INSTANT_LENGTH or not text.endswith("+00:00"):
        raise ValueError("not a 32-character UTC instant")
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("not a 32-character UTC instant") from exc
    if instant_text(moment) != text:
        raise ValueError("not a 32-character UTC instant")
    return moment


def day_text(day: date) -> str:
    """Format a calendar day as ``YYYY-MM-DD``."""
    return day.isoformat()


def validity_day(moment: datetime, zone: ZoneInfo) -> str:
    """Return the calendar day of an aware instant in a time zone, as ``YYYY-MM-DD``.

    Args:
        moment: A timezone-aware datetime.
        zone: The household time zone.

    Returns:
        The local day of ``moment`` in ``zone``.

    Raises:
        ValueError: If ``moment`` is naive (it would silently read in the operating-system zone).
    """
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("a naive datetime has no validity day: it must be timezone-aware")
    return day_text(moment.astimezone(zone).date())
