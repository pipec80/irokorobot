"""Persistent key/value flags — small operational state that survives restarts.

Flags are local runtime state (e.g. ``onboarding_complete``), not domain
data.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from server import db
from server.cognition.clock import utc_now
from server.db import get_conn
from server.memory.export_model import fetch_count
from server.timestamps import instant_text

if TYPE_CHECKING:
    import aiosqlite

logger = logging.getLogger(__name__)


async def get_flag(key: str) -> str | None:
    """Return the value stored for *key*, or ``None`` if unset.

    Args:
        key: Flag name (e.g. ``"onboarding_complete"``).

    Returns:
        Stored string value, or ``None``.

    Raises:
        BrainMemoryError: If the DB is not open.
    """
    conn = get_conn()
    cur = await conn.execute("SELECT value FROM meta WHERE key = ?", (key,))
    row = await cur.fetchone()
    await cur.close()
    return str(row[0]) if row else None


async def set_flag_in(conn: aiosqlite.Connection, key: str, value: str) -> None:
    """Insert or update a flag inside the caller's open transaction (the deletion register).

    Args:
        conn: The connection of an open ``db.transaction()``.
        key: Flag name.
        value: Value to store.
    """
    await conn.execute(
        "INSERT INTO meta (key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT (key) DO UPDATE SET value = excluded.value, "
        "updated_at = excluded.updated_at",
        (key, value, instant_text(utc_now())),
    )


async def set_flag(key: str, value: str) -> None:
    """Insert or update a flag.

    Args:
        key: Flag name.
        value: Value to store.

    Raises:
        BrainMemoryError: If the DB is not open.
    """
    async with db.transaction() as conn:
        await conn.execute(
            "INSERT INTO meta (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value, "
            "updated_at = excluded.updated_at",
            (key, value, instant_text(utc_now())),
        )
    logger.debug("Meta flag set: %s=%s", key, value)


async def count_flags() -> int:
    """How many system flags, for the «no sale» section of an export (Plan 0087 D-5)."""
    return await fetch_count("SELECT count(*) FROM meta")
