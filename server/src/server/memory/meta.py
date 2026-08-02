"""Persistent key/value flags — small operational state that survives restarts.

Flags are local runtime state (e.g. ``onboarding_complete``), not domain
data, so they are intentionally NOT written to the outbox.
"""

from __future__ import annotations

import logging

from server.db import get_conn

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


async def set_flag(key: str, value: str) -> None:
    """Insert or update a flag.

    Args:
        key: Flag name.
        value: Value to store.

    Raises:
        BrainMemoryError: If the DB is not open.
    """
    conn = get_conn()
    await conn.execute(
        "INSERT INTO meta (key, value, updated_at) VALUES (?, ?, datetime('now')) "
        "ON CONFLICT (key) DO UPDATE SET value = excluded.value, "
        "updated_at = excluded.updated_at",
        (key, value),
    )
    await conn.commit()
    logger.debug("Meta flag set: %s=%s", key, value)
