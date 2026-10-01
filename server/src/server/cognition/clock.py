"""The one production clock of the cognition layer (Plan 0055)."""

from datetime import UTC, datetime

__all__ = ["utc_now"]


def utc_now() -> datetime:
    """Return the current aware UTC timestamp for production boundaries."""
    return datetime.now(UTC)
