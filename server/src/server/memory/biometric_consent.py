"""Local repository for biometric (face) consent grants.

Grants an explicit, revocable consent to use a person's face as owner
authentication evidence (Plan 0029, PC-2). Revoking a grant also purges
every stored face embedding for that person — consent and biometric data
share one lifecycle by design.
"""

from __future__ import annotations

import logging

from server.db import get_conn

logger = logging.getLogger(__name__)

__all__ = [
    "grant_face_consent",
    "has_active_face_consent",
    "revoke_face_consent",
]

_PURPOSE = "owner_authentication"


async def grant_face_consent(person_entity_id: int) -> int:
    """Record an active biometric consent grant for owner authentication.

    Args:
        person_entity_id: Existing person entity granting consent.

    Returns:
        The new ``face_consent_grants`` row id.

    Raises:
        BrainMemoryError: If the DB is unavailable.
        aiosqlite.IntegrityError: If an active grant already exists for
            this person — the partial unique index rejects the insert.
    """
    conn = get_conn()
    cursor = await conn.execute(
        "INSERT INTO face_consent_grants (person_entity_id, purpose) VALUES (?, ?)",
        (person_entity_id, _PURPOSE),
    )
    grant_id = cursor.lastrowid
    await cursor.close()
    await conn.commit()
    logger.info("Face consent granted: person=%s", person_entity_id)
    return int(grant_id) if grant_id is not None else 0


async def revoke_face_consent(person_entity_id: int) -> None:
    """Revoke consent and purge all stored face embeddings for this person.

    Sets ``revoked_at`` on the active grant AND deletes every
    ``face_profiles`` row for *person_entity_id*, along with the matching
    ``vec_faces`` rows (by ``rowid == face_profiles.id``), all inside one
    transaction. Idempotent — calling this when there is no active grant,
    or when there are no ``face_profiles`` rows, does not raise.

    Args:
        person_entity_id: Person whose consent and face data are purged.

    Raises:
        BrainMemoryError: If the DB is unavailable.
    """
    conn = get_conn()
    await conn.execute("BEGIN IMMEDIATE")
    try:
        await conn.execute(
            "DELETE FROM vec_faces WHERE rowid IN "
            "(SELECT id FROM face_profiles WHERE entity_id = ?)",
            (person_entity_id,),
        )
        await conn.execute("DELETE FROM face_profiles WHERE entity_id = ?", (person_entity_id,))
        await conn.execute(
            "UPDATE face_consent_grants SET revoked_at = datetime('now') "
            "WHERE person_entity_id = ? AND revoked_at IS NULL",
            (person_entity_id,),
        )
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise
    logger.info("Face consent revoked and face data purged: person=%s", person_entity_id)


async def has_active_face_consent(person_entity_id: int) -> bool:
    """Return whether this person currently has an active (unrevoked) grant.

    Args:
        person_entity_id: Person to check.

    Returns:
        True if an active grant exists, False otherwise.

    Raises:
        BrainMemoryError: If the DB is unavailable.
    """
    cursor = await get_conn().execute(
        "SELECT 1 FROM face_consent_grants WHERE person_entity_id = ? AND revoked_at IS NULL",
        (person_entity_id,),
    )
    row = await cursor.fetchone()
    await cursor.close()
    return row is not None
