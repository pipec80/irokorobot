"""Local repository for voice (speaker) consent grants.

Grants an explicit, revocable consent to use a person's voice as identity
evidence (Plan 0053, PC-3B). Revoking a grant also purges every stored
voiceprint for that person — consent and biometric data share one lifecycle
by design, mirroring ``memory/biometric_consent.py`` for face evidence.
"""

from __future__ import annotations

import logging

from server import db
from server.db import get_conn

logger = logging.getLogger(__name__)

__all__ = [
    "grant_voice_consent",
    "has_active_voice_consent",
    "revoke_voice_consent",
]

_PURPOSE = "speaker_evidence"


async def grant_voice_consent(person_entity_id: int) -> int:
    """Record an active voice consent grant for speaker evidence.

    Idempotent: a person may enroll additional voice references on separate
    occasions without re-granting consent each time — calling this again
    while a grant is already active returns the existing grant id unchanged.

    Args:
        person_entity_id: Existing person entity granting consent.

    Returns:
        The active ``voice_consent_grants`` row id — newly created, or the
        pre-existing one if consent was already active for this person.

    Raises:
        BrainMemoryError: If the DB is unavailable.
    """
    async with db.transaction() as conn:
        cursor = await conn.execute(
            "SELECT id FROM voice_consent_grants WHERE person_entity_id = ? AND revoked_at IS NULL",
            (person_entity_id,),
        )
        existing = await cursor.fetchone()
        await cursor.close()
        if existing is not None:
            return int(existing[0])
        cursor = await conn.execute(
            "INSERT INTO voice_consent_grants (person_entity_id, purpose) VALUES (?, ?)",
            (person_entity_id, _PURPOSE),
        )
        grant_id = cursor.lastrowid
        await cursor.close()
    logger.info("Voice consent granted: person=%s", person_entity_id)
    return int(grant_id) if grant_id is not None else 0


async def revoke_voice_consent(person_entity_id: int) -> None:
    """Revoke consent and purge every stored voiceprint for this person.

    Sets ``revoked_at`` on the active grant AND deletes every
    ``voice_profiles`` row for *person_entity_id*, inside one transaction.
    Idempotent — no active grant and no rows is not an error.

    Args:
        person_entity_id: Person whose consent and voiceprints are purged.

    Raises:
        BrainMemoryError: If the DB is unavailable.
    """
    async with db.transaction() as conn:
        await conn.execute("DELETE FROM voice_profiles WHERE entity_id = ?", (person_entity_id,))
        await conn.execute(
            "UPDATE voice_consent_grants SET revoked_at = datetime('now') "
            "WHERE person_entity_id = ? AND revoked_at IS NULL",
            (person_entity_id,),
        )
    logger.info("Voice consent revoked and voiceprints purged: person=%s", person_entity_id)


async def has_active_voice_consent(person_entity_id: int) -> bool:
    """Return whether this person currently has an active (unrevoked) grant.

    Args:
        person_entity_id: Person to check.

    Returns:
        True if an active grant exists, False otherwise.

    Raises:
        BrainMemoryError: If the DB is unavailable.
    """
    cursor = await get_conn().execute(
        "SELECT 1 FROM voice_consent_grants WHERE person_entity_id = ? AND revoked_at IS NULL",
        (person_entity_id,),
    )
    row = await cursor.fetchone()
    await cursor.close()
    return row is not None
