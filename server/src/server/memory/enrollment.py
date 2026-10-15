"""Whether a person is enrolled for the strong (face and voice) path (ADR 0021 decision 3).

The composite did not exist as one reader: the face keeps its consent in `face_consent_grants`
and the voice in `voice_consent_grants`, each revoked (and purged) on its own. A candidate is
written only while **both** are active, so this reader names the composite and is read again
right before the store, after a model call that can take tens of seconds.
"""

from __future__ import annotations

from server.memory.biometric_consent import has_active_face_consent
from server.memory.voice_consent import has_active_voice_consent

__all__ = ["is_enrolled_for_strong"]


async def is_enrolled_for_strong(person_entity_id: int) -> bool:
    """Return whether the person has an active face consent and an active voice consent.

    Args:
        person_entity_id: The person to check.

    Returns:
        ``True`` only when both grants are active (revoking either one purges its data).

    Raises:
        BrainMemoryError: If the database is unavailable.
    """
    return await has_active_face_consent(person_entity_id) and await has_active_voice_consent(
        person_entity_id
    )
