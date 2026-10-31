"""The owner's consent to store conversation text (ADR 0027 decision 7, Plan 0076).

The only SQL on ``conversation_consent_grants``. One active grant per person, carrying the version
of the notice that was read. Revoking the grant stops the record and deletes every stored segment
and, by cascade, every episode, in the same transaction (Plan 0076 D-3): consent and conversation
text share one lifecycle, like a face or a voice and its prints.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from pathlib import Path
from typing import Final

from server import db
from server.memory.conversation_record import delete_all_records

logger = logging.getLogger(__name__)

__all__ = [
    "CONVERSATION_NOTICE_PATH",
    "CONVERSATION_NOTICE_VERSION",
    "grant_conversation_consent",
    "has_active_conversation_consent",
    "load_conversation_notice",
    "revoke_conversation_consent",
]

_PURPOSE: Final = "conversation_storage"

#: The notice read before the consent; its version is stored with the grant.
CONVERSATION_NOTICE_VERSION: Final = "v1"
CONVERSATION_NOTICE_PATH: Final = (
    Path(__file__).resolve().parents[4] / "docs" / "legal" / "conversation-notice-v1.md"
)


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


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
            (person_entity_id, _PURPOSE, notice_version, _iso(now)),
        )
        grant_id = cursor.lastrowid
        await cursor.close()
    logger.info("Conversation consent granted: person=%s", person_entity_id)
    return int(grant_id) if grant_id is not None else 0


async def revoke_conversation_consent(person_entity_id: int, *, now: datetime) -> int:
    """Revoke the consent and delete every record and episode in one transaction.

    Idempotent: with no active grant it still deletes whatever record exists and succeeds.

    Args:
        person_entity_id: The owner revoking the consent.
        now: When the consent was revoked (timezone-aware).

    Returns:
        How many record segments were deleted.

    Raises:
        BrainMemoryError: If the DB is unavailable.
    """
    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE conversation_consent_grants SET revoked_at = ? "
            "WHERE person_entity_id = ? AND revoked_at IS NULL",
            (_iso(now), person_entity_id),
        )
        deleted = await delete_all_records(conn)
    # secure_delete is on: the checkpoint folds the overwritten pages out of the write-ahead log.
    await db.checkpoint_wal()
    logger.info(
        "Conversation consent revoked: person=%s, %d segment(s) deleted", person_entity_id, deleted
    )
    return deleted


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
