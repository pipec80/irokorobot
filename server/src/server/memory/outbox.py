"""Outbox pattern — append-only write log for future sync.

No reader exists in v3; this table is written so that a future sync
agent can replay changes without code refactoring.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from server.db import get_conn

logger = logging.getLogger(__name__)


async def write_outbox(
    aggregate_type: str,
    aggregate_id: int,
    op: str,
    payload: dict[str, Any],
) -> None:
    """Append one record to the outbox table.

    The write commits immediately so it is visible to any future reader
    even if the caller's broader transaction is rolled back or never
    explicitly committed.

    Args:
        aggregate_type: Domain object type (``"entity"``, ``"fact"``,
            ``"memory"``, ``"event"``).
        aggregate_id: Database row id of the changed object.
        op: Operation performed — ``"insert"``, ``"update"``, or ``"delete"``.
        payload: JSON-serializable snapshot of the change.
    """
    conn = get_conn()
    await conn.execute(
        "INSERT INTO outbox (aggregate_type, aggregate_id, op, payload) VALUES (?, ?, ?, ?)",
        (aggregate_type, aggregate_id, op, json.dumps(payload, default=str)),
    )
    await conn.commit()
    logger.debug("Outbox: %s %s id=%d", op, aggregate_type, aggregate_id)
