"""Pure speaker verdict and request-scoped speaker evidence (Plan 0053, PC-3B).

`VERIFIED` never means authorized. The resolver below attaches untrusted
`IdentityEvidenceSource.VOICE` evidence, which `resolve_active_person` does not
resolve — fusing voice with face or PIN is PC-4, not this module.

Audio contract for every WAV this module touches: WAV, 16 000 Hz, mono, signed
int16.
"""

from enum import StrEnum

from server.cognition.identity import HouseholdRole
from server.settings import settings


class SpeakerVerdict(StrEnum):
    """Closed outcome of one speaker verification attempt."""

    VERIFIED = "verified"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"


def evaluate_speaker_verification(
    *,
    reference_count: int,
    distance: float | None,
    consent_active: bool,
    role: HouseholdRole,
    backend_available: bool,
) -> SpeakerVerdict:
    """Decide the speaker verdict from pre-computed evidence.

    Pure decision table — no I/O. The caller must already have applied the
    frozen preprocessing and compared against the reference centroid.

    Args:
        reference_count: Stored references for the configured model.
        distance: Cosine distance to the centroid, or `None` when no
            comparison was possible (no reference, unusable audio).
        consent_active: Whether the person has an active voice consent grant.
        role: The person's current household role, re-read this turn.
        backend_available: Whether the embedding backend produced a vector.

    Returns:
        `UNAVAILABLE` when the backend could not run — a degraded sense, not a
        judgement about the speaker. `VERIFIED` only with enough references, a
        distance within `settings.speaker_authentication_match_threshold`,
        active consent and the owner role. `UNKNOWN` for every other case.
    """
    if not backend_available:
        return SpeakerVerdict.UNAVAILABLE
    if reference_count < settings.speaker_min_reference_count:
        return SpeakerVerdict.UNKNOWN
    if distance is None or distance > settings.speaker_authentication_match_threshold:
        return SpeakerVerdict.UNKNOWN
    if not consent_active:
        return SpeakerVerdict.UNKNOWN
    if role is not HouseholdRole.OWNER:
        return SpeakerVerdict.UNKNOWN
    return SpeakerVerdict.VERIFIED
