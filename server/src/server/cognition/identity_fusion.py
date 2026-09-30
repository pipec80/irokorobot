"""Request-scoped fusion of face, voice and optional PIN evidence (Plan 0054, ADR 0016).

One resolver per HTTP request. The order is fixed: face first; voice only when the face
matched the owner (the only case in which it can corroborate); the PIN only when a token
was presented and nothing resolved or vetoed. Positive evidence of another person (another
enrolled face, or two or more faces) vetoes and never consumes the PIN token. The final
status and assurance come from `resolve_active_person`, the single place that fuses
evidence. Voice is a corroborating source: it can raise a face to `strong`, never identify.

Audio contract for every WAV the speaker resolver touches: WAV, 16 000 Hz, mono, signed
int16.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from functools import partial
import logging
from typing import Literal

from server.cognition.authorization import ConsentStatus
from server.cognition.face_authentication import (
    FaceAuthenticationVerdict,
    FaceRequestResolver,
    build_default_face_request_resolver,
)
from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    IdentityAssurance,
    PersonRecord,
    resolve_active_person,
)
from server.cognition.models import CognitiveEvent
from server.cognition.owner_authentication import OwnerRequestResolver
from server.cognition.response_plan import TextTurnPayload
from server.cognition.speaker_authentication import (
    SpeakerRequestResolver,
    SpeakerVerdict,
    build_default_speaker_resolver,
)
from server.settings import settings

logger = logging.getLogger(__name__)

__all__ = ["FusedIdentityResolver", "FusionReason", "build_fused_identity_resolver"]

type Clock = Callable[[], datetime]
type SpeakerFactory = Callable[[int], SpeakerRequestResolver]
type IdentitySource = Literal["face", "face_voice", "local_unlock"]


class FusionReason(StrEnum):
    """Closed reason for one turn's identity outcome — the only thing logged (ADR 0016 §8)."""

    PIN = "pin"
    FACE_AND_VOICE = "face_and_voice"
    FACE_ONLY = "face_only"
    VETO_OTHER_PERSON = "veto_other_person"
    VETO_MULTIPLE_FACES = "veto_multiple_faces"
    BACKEND_UNAVAILABLE = "backend_unavailable"
    NO_EVIDENCE = "no_evidence"


class FusedIdentityResolver:
    """Resolve the actor of one request from face, voice and an optional PIN token."""

    def __init__(
        self,
        *,
        pin: OwnerRequestResolver,
        face: FaceRequestResolver | None,
        speaker_factory: SpeakerFactory | None,
        clock: Clock,
    ) -> None:
        """Create a resolver for exactly one HTTP request.

        Args:
            pin: Request-scoped PIN resolver (Plan 0025/0026); consulted last.
            face: Request-scoped face resolver, or `None` when no frame is usable.
            speaker_factory: Builds the speaker resolver for the identified owner's
                id, or `None` when speaker evidence is disabled or there is no audio.
            clock: Source of the resolution timestamp.
        """
        self._pin = pin
        self._face = face
        self._speaker_factory = speaker_factory
        self._clock = clock
        self._cached: ActivePersonContext | None = None
        self.last_reason: FusionReason | None = None
        self.source: IdentitySource | None = None

    @property
    def consumed(self) -> bool:
        """Whether this request consumed a fresh one-use owner PIN grant."""
        return self._pin.consumed

    async def resolve_actor(self, event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
        """Resolve the actor once per request; later calls return the cached result.

        Args:
            event: The protected event this resolution is scoped to.

        Returns:
            The identified owner (`basic` from the face, `strong` with a corroborating
            voice or a PIN grant), the ambiguous actor on a veto, or the unknown actor.
        """
        if self._cached is not None:
            return self._cached
        context = await self._resolve(event)
        self._cached = context
        logger.info(
            "Identity fusion: %s",
            self.last_reason.value if self.last_reason else "none",
            extra={"event": "identity.fusion", "reason": self.last_reason},
        )
        return context

    async def resolve_consent(
        self, event: CognitiveEvent[TextTurnPayload], actor: ActivePersonContext
    ) -> ConsentStatus:
        """Grant scoped consent only through the path that identified the owner.

        Args:
            event: The protected event being authorized.
            actor: The context produced by :meth:`resolve_actor` for this event.

        Returns:
            `GRANTED` only when the face or the consumed PIN grant identified the owner.
        """
        if self.source in {"face", "face_voice"} and self._face is not None:
            return await self._face.resolve_consent(event, actor)
        if self._pin.consumed:
            return await self._pin.resolve_consent(event, actor)
        return ConsentStatus.NOT_REQUIRED

    async def _resolve(self, event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
        """Run face, then voice, then PIN, stopping at the first identification or veto."""
        if self._face is not None:
            face_context = await self._face.resolve_actor(event)
            verdict = self._face.last_verdict
            if verdict is FaceAuthenticationVerdict.AMBIGUOUS:
                self.last_reason = FusionReason.VETO_MULTIPLE_FACES
                return face_context
            if verdict is FaceAuthenticationVerdict.OTHER_PERSON:
                self.last_reason = FusionReason.VETO_OTHER_PERSON
                return face_context
            if face_context.status is ActivePersonStatus.IDENTIFIED:
                return await self._with_voice(event, face_context)
        pin_context = await self._pin.resolve_actor(event)
        if self._pin.consumed:
            self.last_reason = FusionReason.PIN
            self.source = "local_unlock"
        else:
            self.last_reason = FusionReason.NO_EVIDENCE
        return pin_context

    async def _with_voice(
        self, event: CognitiveEvent[TextTurnPayload], face_context: ActivePersonContext
    ) -> ActivePersonContext:
        """Raise an identified face to `strong` when the voice of the same person agrees."""
        self.source = "face"
        self.last_reason = FusionReason.FACE_ONLY
        owner_id = face_context.person_id
        if self._speaker_factory is None or owner_id is None:
            return face_context
        speaker = self._speaker_factory(owner_id)
        voice_context = await speaker.resolve_actor(event)
        if speaker.last_verdict is SpeakerVerdict.UNAVAILABLE:
            self.last_reason = FusionReason.BACKEND_UNAVAILABLE
            return face_context
        voice_evidence = tuple(
            item for item in voice_context.evidence if item.candidate_person_id == owner_id
        )
        if speaker.last_verdict is not SpeakerVerdict.VERIFIED or not voice_evidence:
            return face_context
        person = PersonRecord(
            person_id=owner_id, display_name=face_context.display_name or "", entity_type="person"
        )
        fused = resolve_active_person(
            evidence=face_context.evidence + voice_evidence,
            lookup_person=lambda person_id: person if person_id == owner_id else None,
            lookup_role=lambda _person_id: face_context.role,
            clock=self._clock,
        )
        if fused.assurance is not IdentityAssurance.STRONG:
            return face_context
        self.source = "face_voice"
        self.last_reason = FusionReason.FACE_AND_VOICE
        return fused


def _utc_now() -> datetime:
    """Return the current aware UTC timestamp for production boundaries."""
    return datetime.now(UTC)


def build_fused_identity_resolver(
    pin: OwnerRequestResolver, *, frame: bytes | None, wav_bytes: bytes | None
) -> FusedIdentityResolver:
    """Compose the production resolver for one request.

    Args:
        pin: The request's PIN resolver.
        frame: Validated webcam frame bytes, or `None` (no frame, or
            `settings.face_authentication_enabled` is off).
        wav_bytes: The turn's own audio — WAV, 16 000 Hz, mono, int16 — used only
            when `settings.speaker_authentication_enabled` is on.

    Returns:
        A resolver wired to the real face and speaker resolvers.
    """
    face = (
        build_default_face_request_resolver(frame)
        if settings.face_authentication_enabled and frame is not None
        else None
    )
    speaker_factory: SpeakerFactory | None = (
        partial(build_default_speaker_resolver, wav_bytes)
        if settings.speaker_authentication_enabled and wav_bytes is not None
        else None
    )
    return FusedIdentityResolver(
        pin=pin, face=face, speaker_factory=speaker_factory, clock=_utc_now
    )
