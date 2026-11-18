"""The owner's consent to store conversation text (ADR 0027 decision 7, Plan 0076).

The only SQL on ``conversation_consent_grants``. One active grant per person, carrying the version
of the notice that was read. Revoking the grant stops the record and deletes every stored segment
and, by cascade, every episode, in the same transaction (Plan 0076 D-3): consent and conversation
text share one lifecycle, like a face or a voice and its prints.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Final

from server import db
from server.memory.conversation_record import delete_all_records
from server.timestamps import instant_text

if TYPE_CHECKING:
    from datetime import datetime

    import aiosqlite

logger = logging.getLogger(__name__)

__all__ = [
    "CONVERSATION_NOTICE_PATH",
    "CONVERSATION_NOTICE_VERSION",
    "grant_conversation_consent",
    "has_active_conversation_consent",
    "load_conversation_notice",
    "withdraw_in",
]

_PURPOSE: Final = "conversation_storage"

#: The notice read before the consent; its version is stored with the grant.
CONVERSATION_NOTICE_VERSION: Final = "v1"
CONVERSATION_NOTICE_PATH: Final = (
    Path(__file__).resolve().parents[4] / "docs" / "legal" / "conversation-notice-v1.md"
)


def load_conversation_notice() -> str:
    """Return the tracked conversation notice.

    Returns:
        The notice's Markdown text.

    Raises:
        ValueError: If the notice file is missing or unreadable (its message is safe to print).
    """
    try:
        return CONVERSATION_NOTICE_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(
            f"the conversation notice is missing at {CONVERSATION_NOTICE_PATH}"
        ) from exc


async def grant_conversation_consent(
    person_entity_id: int, *, notice_version: str, now: datetime
) -> int:
    """Record an active consent to store conversation text; idempotent.

    Args:
        person_entity_id: The owner granting the consent.
        notice_version: The version of the notice that was read.
        now: When the consent was given (timezone-aware).

    Returns:
        The active grant's id (the existing one if a grant was already active).

    Raises:
        BrainMemoryError: If the DB is unavailable.
    """
    async with db.transaction() as conn:
        cursor = await conn.execute(
            "SELECT id FROM conversation_consent_grants "
            "WHERE person_entity_id = ? AND revoked_at IS NULL",
            (person_entity_id,),
        )
        existing = await cursor.fetchone()
        await cursor.close()
        if existing is not None:
            return int(existing[0])
        cursor = await conn.execute(
            "INSERT INTO conversation_consent_grants "
            "(person_entity_id, purpose, notice_version, granted_at) VALUES (?, ?, ?, ?)",
            (person_entity_id, _PURPOSE, notice_version, instant_text(now)),
        )
        grant_id = cursor.lastrowid
        await cursor.close()
    logger.info("Conversation consent granted: person=%s", person_entity_id)
    return int(grant_id) if grant_id is not None else 0


async def withdraw_in(conn: aiosqlite.Connection, person_entity_id: int, *, at: str) -> int:
    """Revoke the consent and delete every record and episode, inside the caller's transaction.

    Only ``deletion_register`` calls it, under the deletion protocol (Plan 0086 D-12):
    ``deletion_register.withdraw_conversation_consent`` is the public way to withdraw it.

    Args:
        conn: The connection of an open ``db.transaction()``.
        person_entity_id: The owner withdrawing the consent.
        at: When it was withdrawn (32-character UTC).

    Returns:
        How many record segments were deleted.
    """
    await conn.execute(
        "UPDATE conversation_consent_grants SET revoked_at = ? "
        "WHERE person_entity_id = ? AND revoked_at IS NULL",
        (at, person_entity_id),
    )
    return await delete_all_records(conn)


async def has_active_conversation_consent(person_entity_id: int) -> bool:
    """Return whether this person has an active (unrevoked) consent.

    Raises:
        BrainMemoryError: If the DB is unavailable.
    """
    cursor = await db.get_conn().execute(
        "SELECT 1 FROM conversation_consent_grants "
        "WHERE person_entity_id = ? AND revoked_at IS NULL",
        (person_entity_id,),
    )
    row = await cursor.fetchone()
    await cursor.close()
    return row is not None
