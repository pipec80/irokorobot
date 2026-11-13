"""The household's time zone and its local day (ADR 0028 decision 7).

A day the household lives is cut at its local midnight (``HOUSEHOLD_TIMEZONE``); timestamps stay
UTC. One small module, so the capture, the conversation job, the pending topics and the routes
ask the same question without importing the recall search.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from server.settings import settings

if TYPE_CHECKING:
    from datetime import date, datetime

__all__ = ["household_day", "household_zone"]


def household_zone() -> ZoneInfo:
    """Return the household time zone of ``HOUSEHOLD_TIMEZONE`` (ADR 0028 decision 7)."""
    return ZoneInfo(settings.household_timezone)


def household_day(moment: datetime) -> date:
    """Return the household's local day of an aware instant.

    Args:
        moment: A timezone-aware instant.

    Returns:
        The calendar day in ``HOUSEHOLD_TIMEZONE``.
    """
    return moment.astimezone(household_zone()).date()
