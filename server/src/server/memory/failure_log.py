"""How a background seam of a turn logs a failure it swallows: class, level and site, no message.

A database error's message can carry a value, so only the exception class and the innermost
frame's ``file:line:function`` are logged. A class a bad moment explains (database, disk, a lost
race) is a warning; any other (a ``TypeError`` from signature drift) is a bug and an error, so it
is found instead of looking like a busy database. Shared by the memory offer (Plan 0063) and the
pending-topic follow-up (Plan 0084).
"""

from __future__ import annotations

import logging
from pathlib import Path
import sqlite3
import traceback

from server.exceptions import BrainMemoryError

__all__ = ["failure_level", "failure_site"]

#: Failures a bad moment explains (database, disk, a lost race); any other class is a bug.
_OPERATIONAL_FAILURES = (
    BrainMemoryError,
    sqlite3.Error,
    OSError,
    TimeoutError,
    RuntimeError,
    ValueError,
)


def failure_site(exc: BaseException) -> str:
    """Return ``file:line:function`` of the innermost frame; it never carries a message.

    Args:
        exc: The swallowed exception.
    """
    frames = traceback.extract_tb(exc.__traceback__)
    if not frames:
        return "unknown"
    frame = frames[-1]
    return f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}"


def failure_level(exc: BaseException) -> int:
    """Return ``WARNING`` for an operational failure and ``ERROR`` for any other class.

    Args:
        exc: The swallowed exception.
    """
    return logging.WARNING if isinstance(exc, _OPERATIONAL_FAILURES) else logging.ERROR
