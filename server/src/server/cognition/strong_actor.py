"""The face-and-voice actor the memory writer demands (ADR 0021 decision 3).

Pipec's rule: nothing private is written on the strength of a face alone. In CM-3a a
candidate, a spoken value, an answer and a promotion all need the face **and** the voice of
the same person, verified on that turn's own clip, and never a PIN token.

A generic turn is identified by its face (ADR 0020 §1) before anything is generated. This
module takes that face-identified actor and, in the background, runs only the voice half of the
fused resolution for the person the face named: the face is not computed a second time.

Audio contract: every clip is WAV, 16 000 Hz, mono, signed int16.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import logging
from typing import TYPE_CHECKING, Protocol

from server.cognition.clock import utc_now
from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    IdentityAssurance,
    IdentityEvidenceSource,
)
from server.cognition.identity_fusion import fuse_face_and_voice
from server.cognition.speaker_authentication import (
    SpeakerRequestResolver,
    SpeakerVerdict,
    build_default_speaker_resolver,
)
from server.settings import settings

if TYPE_CHECKING:
    from datetime import datetime

    from server.cognition.models import CognitiveEvent
    from server.cognition.response_plan import TextTurnPayload

logger = logging.getLogger(__name__)

__all__ = [
    "VoiceVerifier",
    "is_face_actor",
    "is_face_and_voice_actor",
    "verify_face_and_voice",
]

type SpeakerBuilder = Callable[[bytes, int], SpeakerRequestResolver]
type Clock = Callable[[], datetime]


class VoiceVerifier(Protocol):
    """The voice-check seam: ``verify_face_and_voice`` or a test double (same keywords)."""

    def __call__(
        self,
        actor: ActivePersonContext,
        *,
        wav_bytes: bytes | None,
        event: CognitiveEvent[TextTurnPayload],
    ) -> Awaitable[ActivePersonContext | None]:
        """Return the actor fused at ``strong``, or ``None`` when the voice was not verified."""
        ...


def _sources_of(actor: ActivePersonContext) -> set[IdentityEvidenceSource]:
    """Return the evidence sources that name the actor's own person id."""
    return {item.source for item in actor.evidence if item.candidate_person_id == actor.person_id}


def _identified_without_a_token(actor: ActivePersonContext) -> bool:
    """Return whether the actor is an identified person and no token took part in it."""
    return (
        actor.status is ActivePersonStatus.IDENTIFIED
        and actor.person_id is not None
        and IdentityEvidenceSource.LOCAL_UNLOCK not in {item.source for item in actor.evidence}
    )


def is_face_actor(actor: ActivePersonContext) -> bool:
    """Return whether *actor* was identified by its face and carries no token.

    Args:
        actor: A resolved actor.

    Returns:
        ``True`` for an identified person whose evidence includes their face and no
        ``LOCAL_UNLOCK`` item. A token-identified actor, a manual one and an unknown one are
        ``False``: a PIN grant proves the PIN, not the speaker (ADR 0008, ADR 0015).
    """
    return _identified_without_a_token(actor) and IdentityEvidenceSource.FACE in _sources_of(actor)


def is_face_and_voice_actor(actor: ActivePersonContext) -> bool:
    """Return whether *actor* is the composite the memory writer needs.

    Args:
        actor: A resolved actor.

    Returns:
        ``True`` only for an identified person at assurance ``strong`` whose evidence names
        them by face **and** voice and carries no ``LOCAL_UNLOCK`` item (a token also reaches
        ``strong``, so assurance alone does not say how it was reached).
    """
    return (
        _identified_without_a_token(actor)
        and actor.assurance is IdentityAssurance.STRONG
        and {IdentityEvidenceSource.FACE, IdentityEvidenceSource.VOICE} <= _sources_of(actor)
    )


async def verify_face_and_voice(
    actor: ActivePersonContext,
    *,
    wav_bytes: bytes | None,
    event: CognitiveEvent[TextTurnPayload],
    build_speaker: SpeakerBuilder = build_default_speaker_resolver,
    clock: Clock = utc_now,
) -> ActivePersonContext | None:
    """Check the voice of the turn's own clip against the person the face named.

    Args:
        actor: The face-identified actor of the turn (never a token actor).
        wav_bytes: The turn's own audio — WAV, 16 000 Hz, mono, int16 — or ``None``.
        event: The turn's event; the speaker resolver stamps its evidence from it.
        build_speaker: Composition seam for the speaker resolver; tests inject doubles.
        clock: Source of the fusion timestamp.

    Returns:
        The actor fused at ``strong`` from face and voice, or ``None`` when speaker evidence is
        off, there is no clip, the actor is not a face actor, or the voice was not verified
        (not enrolled, no consent, a clip below the floor, another voice, a backend failure).
    """
    if not settings.speaker_authentication_enabled or not wav_bytes:
        return None
    if not is_face_actor(actor) or actor.person_id is None:
        return None
    speaker = build_speaker(wav_bytes, actor.person_id)
    voice_context = await speaker.resolve_actor(event)
    if speaker.last_verdict is not SpeakerVerdict.VERIFIED:
        return None
    fused = fuse_face_and_voice(actor, voice_context, clock=clock)
    if fused is None or not is_face_and_voice_actor(fused):
        return None
    return fused
