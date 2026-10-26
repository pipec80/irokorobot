"""Retract what an earlier seed import wrote, while the robot is being commissioned (Plan 0071).

ADR 0024 decision 8: loading again with the replacement flag deletes the rows whose channel is an
import channel, the contacts, the section statuses and the entities the import created that
nothing refers to any more, and then the file is written again with the refuse policy. It is
refused once the robot learned anything by voice (a stored row with a voice channel or a live
memory candidate). Every function joins the caller's transaction; the SQL stays in the
repositories that own each table.
"""

from __future__ import annotations

import logging
import sqlite3

from server.exceptions import ReplaceBlockedError, ReplaceRefusedError
from server.memory.candidates import count_live_candidates
from server.memory.care_contacts import delete_contacts_by_channel, entity_has_contact_rows
from server.memory.commissioning import clear_section_statuses, get_open_commissioning
from server.memory.declarative import delete_orphan_import_entities
from server.memory.relational_v4 import (
    count_rows_by_channel,
    delete_rows_by_channel,
    entity_has_rows,
)
from server.memory.write_types import IMPORT_CHANNELS, VOICE_CHANNELS

__all__ = ["assert_no_voice_memory", "retract_earlier_import"]

logger = logging.getLogger(__name__)


async def assert_no_voice_memory(now: str) -> None:
    """Refuse a replacement once the robot learned something by voice.

    Args:
        now: The run's instant (UTC ISO 8601); a candidate lapsed by then is not live.

    Raises:
        ReplaceRefusedError: If a V4 row has a voice channel or a candidate still holds a value.
    """
    if await count_rows_by_channel(VOICE_CHANNELS) > 0 or await count_live_candidates(now) > 0:
        raise ReplaceRefusedError


async def retract_earlier_import() -> int:
    """Delete what earlier imports wrote, inside the caller's transaction.

    In this order: the V4 rows of the import channels, the contacts of those channels, the
    section statuses of the open record, then the entities an import created that nothing refers
    to. A row of another channel, or with none, is never touched.

    Returns:
        How many rows and entities were deleted (statuses not counted).

    Raises:
        ReplaceBlockedError: If another table (a role, a face, a voice, a consent) refers to an
            imported person the cleanup would delete.
    """
    deleted = await delete_rows_by_channel(IMPORT_CHANNELS, manage_transaction=False)
    deleted += await delete_contacts_by_channel(IMPORT_CHANNELS, manage_transaction=False)
    record = await get_open_commissioning()
    if record is not None:
        await clear_section_statuses(record.id, manage_transaction=False)
    try:
        deleted += await delete_orphan_import_entities(
            has_rows=entity_has_rows,
            has_contacts=entity_has_contact_rows,
            manage_transaction=False,
        )
    except sqlite3.IntegrityError as exc:
        # A role, a face, a voice or a consent restricts the delete: the caller rolls back.
        raise ReplaceBlockedError from exc
    logger.debug(
        "Earlier import retracted: %d",
        deleted,
        extra={"event": "memory.seed_retracted", "count": deleted},
    )
    return deleted
