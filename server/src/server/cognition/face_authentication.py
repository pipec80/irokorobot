"""In-turn face evidence resolver and pure authentication verdict.

Resolves owner identity from an optional webcam frame attached to the same
request as the question — no PIN, no gesture. This mirrors the shape
`OwnerRequestResolver` (`server.cognition.owner_authentication`, Plan
0025/0026) already exposes, so a face-first, PIN-fallback pair can be
composed behind one `(resolve_actor, resolve_consent)` seam. Authentication
here never substitutes for the existing authorization/consent evaluation —
it only supplies fresh, in-memory identity evidence and a narrowly scoped
consent signal for one turn.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from enum import StrEnum
import logging
from uuid import uuid4

import numpy as np

from server.cognition.authorization import ConsentStatus
from server.cognition.controller import ActivePersonResolver, ConsentResolver
from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    HouseholdRole,
    IdentityEvidence,
    IdentityEvidenceSource,
    PersonRecord,
    resolve_active_person,
)
from server.cognition.models import CognitiveEvent, Confidence, ConfidenceBasis
from server.cognition.owner_authentication import OwnerRequestResolver
from server.cognition.response_plan import TextTurnPayload
from server.exceptions import VisionError
from server.memory.biometric_consent import has_active_face_consent
from server.memory.entity_labels import get_person_label
from server.memory.household_authorization import get_active_role
from server.settings import settings
from server.vision.faces import (
    DetectedFace,
    FaceMatch,
    detect_faces as _detect_faces_default,
    match_face as _match_face_default,
)

logger = logging.getLogger(__name__)

__all__ = [
    "FaceAuthenticationVerdict",
    "FaceRequestResolver",
    "build_default_face_request_resolver",
    "compose_face_then_pin_resolver",
    "evaluate_face_authentication",
]

_MIN_AMBIGUOUS_FACES = 2
_REFERENCE = "in-turn-face-evidence"

type Clock = Callable[[], datetime]
type RoleReader = Callable[[int], Awaitable[HouseholdRole]]
type PersonReader = Callable[[int], Awaitable[PersonRecord | None]]
type FaceDetector = Callable[[bytes], Awaitable[list[DetectedFace]]]
type FaceMatcher = Callable[[np.ndarray], Awaitable[FaceMatch | None]]
type ConsentReader = Callable[[int], Awaitable[bool]]


class FaceAuthenticationVerdict(StrEnum):
    """Closed outcome of one in-turn face authentication attempt."""

    IDENTIFIED = "identified"
    UNKNOWN = "unknown"
    AMBIGUOUS = "ambiguous"


def evaluate_face_authentication(
    *,
    detected_face_count: int,
    match: FaceMatch | None,
    consent_active: bool,
    role: HouseholdRole,
) -> FaceAuthenticationVerdict:
    """Decide the face authentication verdict from pre-computed evidence.

    Pure decision table — no I/O. The caller must already have applied
    `settings.face_authentication_match_threshold`: `match` is expected to
    be `None` whenever the closest enrolled face was not within that
    stricter, authentication-only bound, even if it passed the generic
    conversational `settings.face_match_threshold`.

    Args:
        detected_face_count: Number of faces found in the frame.
        match: The already-threshold-filtered closest enrolled face, or
            `None` when nobody matched closely enough.
        consent_active: Whether the matched person has an active biometric
            consent grant for owner authentication (Plan 0029, Task 1).
        role: The matched person's current household role.

    Returns:
        `AMBIGUOUS` when two or more faces are present — matching is not
        even attempted in that case. `IDENTIFIED` only for exactly one
        detected face with a within-threshold match, active consent, and
        the owner role. `UNKNOWN` for every other case.
    """
    if detected_face_count >= _MIN_AMBIGUOUS_FACES:
        return FaceAuthenticationVerdict.AMBIGUOUS
    if match is None:
        return FaceAuthenticationVerdict.UNKNOWN
    if not consent_active:
        return FaceAuthenticationVerdict.UNKNOWN
    if role is not HouseholdRole.OWNER:
        return FaceAuthenticationVerdict.UNKNOWN
    return FaceAuthenticationVerdict.IDENTIFIED


def _unknown_active_person(event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
    """Build the safe public actor without deriving identity from the frame."""
    return ActivePersonContext(
        person_id=None,
        display_name=None,
        status=ActivePersonStatus.UNKNOWN,
        confidence=Confidence(
            score=0.0,
            basis=ConfidenceBasis.NOT_APPLICABLE,
            calibrated=False,
            reason="No trusted active-person evidence",
        ),
        role=HouseholdRole.UNKNOWN,
        evidence=(),
        resolved_at=event.occurred_at,
    )


def _ambiguous_active_person(event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
    """Build the safe, non-disclosing actor for a multi-face-in-frame turn."""
    return ActivePersonContext(
        person_id=None,
        display_name=None,
        status=ActivePersonStatus.AMBIGUOUS,
        confidence=Confidence(
            score=0.0,
            basis=ConfidenceBasis.NOT_APPLICABLE,
            calibrated=False,
            reason="Multiple faces detected in frame",
        ),
        role=HouseholdRole.UNKNOWN,
        evidence=(),
        resolved_at=event.occurred_at,
    )


class FaceRequestResolver:
    """Request-scoped actor/consent resolver bound to one optional frame."""

    def __init__(
        self,
        *,
        frame: bytes | None,
        clock: Clock,
        read_role: RoleReader,
        read_person: PersonReader,
        detect_faces: FaceDetector,
        match_face: FaceMatcher,
        read_consent: ConsentReader,
    ) -> None:
        """Create a resolver for exactly one HTTP request.

        Args:
            frame: Optional webcam frame attached to the current request.
                `None` means no frame was supplied — resolves immediately
                to `UNKNOWN` without decoding anything.
            clock: Source of the resolution timestamp.
            read_role: Boundary that reads a person's active household role.
            read_person: Boundary that reads a person's safe display record.
            detect_faces: Boundary that detects every face in a frame.
            match_face: Boundary that finds the closest enrolled face for
                one embedding, already pre-filtered at the generic
                conversational threshold.
            read_consent: Boundary that reads whether a person currently
                has an active biometric consent grant.
        """
        self._frame = frame
        self._clock = clock
        self._read_role = read_role
        self._read_person = read_person
        self._detect_faces = detect_faces
        self._match_face = match_face
        self._read_consent = read_consent
        self.consumed = False
        self.last_verdict: FaceAuthenticationVerdict | None = None
        self._cached_context: ActivePersonContext | None = None

    async def resolve_actor(self, event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
        """Resolve the in-turn face actor, running detection at most once.

        Args:
            event: The protected event this resolution is scoped to.

        Returns:
            The identified owner context, the safe ambiguous context when
            two or more faces share the frame, or the safe unknown actor
            for every other case (no frame, no face, no match, no consent,
            wrong role, or a degraded vision pipeline).
        """
        if self._cached_context is not None:
            return self._cached_context
        context = await self._resolve(event)
        self._cached_context = context
        return context

    async def _resolve(self, event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
        """Run the one-shot detect → match → decide → identify pipeline.

        Every path — including 0 faces, 2+ faces, and no-match — routes
        through `evaluate_face_authentication` so the 6-row decision table
        lives in exactly one place; this method only branches on its
        returned verdict.
        """
        faces = await self._detected_faces()
        match, role, consent_active = await self._match_when_singular(faces)

        verdict = evaluate_face_authentication(
            detected_face_count=len(faces),
            match=match,
            consent_active=consent_active,
            role=role,
        )
        self.last_verdict = verdict

        if verdict is FaceAuthenticationVerdict.IDENTIFIED and match is not None:
            return await self._identify(event, match, role)
        if verdict is FaceAuthenticationVerdict.AMBIGUOUS:
            return _ambiguous_active_person(event)
        return _unknown_active_person(event)

    async def _detected_faces(self) -> list[DetectedFace]:
        """Detect faces in the bound frame, degrading failures to an empty list.

        Returns:
            Every detected face, largest first. Empty when no frame was
            supplied, no face was found, or the vision pipeline failed.
        """
        if self._frame is None:
            return []
        try:
            return await self._detect_faces(self._frame)
        except VisionError as exc:
            logger.warning("Face detection failed, degrading to unknown: %s", exc)
            return []

    async def _match_when_singular(
        self, faces: list[DetectedFace]
    ) -> tuple[FaceMatch | None, HouseholdRole, bool]:
        """Attempt a match only when exactly one face was detected.

        Matching is meaningless when zero or 2+ faces are present — the
        verdict is already determined by face count alone in those cases —
        so this skips the match/role/consent round-trips entirely rather
        than spending them on an outcome that cannot change.

        Args:
            faces: Every face detected in the bound frame.

        Returns:
            The threshold-filtered match with its role and consent state,
            or `(None, HouseholdRole.UNKNOWN, False)` when matching was
            skipped or found nobody within the authentication threshold.
        """
        if len(faces) != 1:
            return None, HouseholdRole.UNKNOWN, False
        match = await self._strict_match(faces[0])
        if match is None:
            return None, HouseholdRole.UNKNOWN, False
        role = await self._read_role(match.entity_id)
        consent_active = await self._read_consent(match.entity_id)
        return match, role, consent_active

    async def _strict_match(self, face: DetectedFace) -> FaceMatch | None:
        """Apply the stricter authentication-only threshold on top of `match_face`."""
        candidate = await self._match_face(face.embedding)
        if candidate is None:
            return None
        if candidate.distance > settings.face_authentication_match_threshold:
            return None
        return candidate

    async def _identify(
        self,
        event: CognitiveEvent[TextTurnPayload],
        match: FaceMatch,
        role: HouseholdRole,
    ) -> ActivePersonContext:
        """Build in-memory FACE evidence and resolve the final owner context."""
        person = await self._read_person(match.entity_id)
        if person is None:
            self.last_verdict = FaceAuthenticationVerdict.UNKNOWN
            return _unknown_active_person(event)

        evidence = IdentityEvidence(
            evidence_id=uuid4(),
            source=IdentityEvidenceSource.FACE,
            candidate_person_id=person.person_id,
            confidence=Confidence(
                score=1.0,
                basis=ConfidenceBasis.MEASURED,
                calibrated=True,
                reason="In-turn face match within the authentication threshold",
            ),
            observed_at=self._clock(),
            reference=_REFERENCE,
        )

        def _lookup_person(person_id: int) -> PersonRecord | None:
            return person if person_id == person.person_id else None

        context = resolve_active_person(
            evidence=(evidence,),
            lookup_person=_lookup_person,
            lookup_role=lambda _person_id: role,
            clock=self._clock,
        )
        self.consumed = context.person_id is not None
        return context

    async def resolve_consent(
        self,
        event: CognitiveEvent[TextTurnPayload],
        actor: ActivePersonContext,
    ) -> ConsentStatus:
        """Grant scoped consent only after this resolver identified the owner.

        Args:
            event: The protected event being authorized.
            actor: The context produced by :meth:`resolve_actor` for this event.

        Returns:
            `GRANTED` only when this exact resolver produced an identified
            owner actor; otherwise a status that authorizes nothing.
        """
        del event
        if self.consumed and actor.person_id is not None and actor.role is HouseholdRole.OWNER:
            return ConsentStatus.GRANTED
        return ConsentStatus.NOT_REQUIRED


def compose_face_then_pin_resolver(
    face: FaceRequestResolver, pin: OwnerRequestResolver
) -> tuple[ActivePersonResolver, ConsentResolver]:
    """Compose face-first, PIN-fallback actor and consent resolution.

    Args:
        face: Request-scoped in-turn face evidence resolver.
        pin: Request-scoped owner PIN resolver (Plan 0025/0026).

    Returns:
        A `(resolve_actor, resolve_consent)` pair for `CognitiveController`.
        Face evidence is tried first: an identified face actor short-
        circuits and returns immediately without consulting the PIN; an
        ambiguous face verdict (a stranger sharing the frame) also short-
        circuits and denies, without consulting the PIN either; any other
        face outcome falls through unchanged to the PIN resolver, exactly
        preserving the existing Plan 0026/0027 no-frame behavior.
    """

    async def resolve_actor(event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
        actor = await face.resolve_actor(event)
        if actor.status is ActivePersonStatus.IDENTIFIED:
            return actor
        if face.last_verdict is FaceAuthenticationVerdict.AMBIGUOUS:
            return actor
        return await pin.resolve_actor(event)

    async def resolve_consent(
        event: CognitiveEvent[TextTurnPayload], actor: ActivePersonContext
    ) -> ConsentStatus:
        if face.last_verdict is FaceAuthenticationVerdict.AMBIGUOUS:
            return ConsentStatus.NOT_REQUIRED
        if face.consumed:
            return await face.resolve_consent(event, actor)
        return await pin.resolve_consent(event, actor)

    return resolve_actor, resolve_consent


def _utc_now() -> datetime:
    """Return the current aware UTC timestamp for production boundaries."""
    return datetime.now(UTC)


async def _read_person_record(person_entity_id: int) -> PersonRecord | None:
    """Adapt the safe entity-label lookup to the identity `PersonRecord` shape."""
    label = await get_person_label(entity_id=person_entity_id)
    if label is None:
        return None
    return PersonRecord(
        person_id=label.entity_id, display_name=label.display_name, entity_type="person"
    )


def build_default_face_request_resolver(frame: bytes | None) -> FaceRequestResolver:
    """Compose the production face resolver over the real repositories.

    Args:
        frame: Optional webcam frame bytes attached to the current request.

    Returns:
        A resolver wired to the real vision pipeline (`server.vision.faces`),
        the biometric consent repository (Plan 0029, Task 1), and the
        existing household role/person repositories.
    """
    return FaceRequestResolver(
        frame=frame,
        clock=_utc_now,
        read_role=get_active_role,
        read_person=_read_person_record,
        detect_faces=_detect_faces_default,
        match_face=_match_face_default,
        read_consent=has_active_face_consent,
    )
