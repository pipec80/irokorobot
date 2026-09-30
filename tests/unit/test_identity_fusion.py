"""Unit tests for the request-scoped fusion of face, voice and optional PIN (Plan 0054)."""

from datetime import UTC, datetime, timedelta
import logging
from typing import TYPE_CHECKING, NamedTuple, cast
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import numpy as np
import pytest
from server.cognition.authorization import ConsentStatus
from server.cognition.face_authentication import FaceRequestResolver
from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    HouseholdRole,
    IdentityAssurance,
    IdentityEvidence,
    IdentityEvidenceSource,
    PersonRecord,
)
from server.cognition.identity_fusion import FusedIdentityResolver, FusionReason
from server.cognition.identity_sessions import IdentitySessionRegistry
from server.cognition.models import CognitiveEvent, Confidence, ConfidenceBasis
from server.cognition.owner_authentication import OwnerRequestResolver
from server.cognition.response_plan import TextTurnPayload
from server.cognition.speaker_authentication import SpeakerVerdict
from server.vision.faces import DetectedFace, FaceMatch

if TYPE_CHECKING:
    from collections.abc import Callable

    from server.cognition.speaker_authentication import SpeakerRequestResolver

_NOW = datetime(2026, 9, 30, 10, 0, tzinfo=UTC)
_OWNER_ID = 7
_OWNER = PersonRecord(person_id=_OWNER_ID, display_name="Canary", entity_type="person")
_FRAME = b"fake-jpeg-bytes"


def _event() -> CognitiveEvent[TextTurnPayload]:
    return CognitiveEvent(
        event_id=UUID("33333333-3333-3333-3333-333333333333"),
        schema_version=1,
        event_type="text.turn",
        occurred_at=_NOW,
        recorded_at=_NOW,
        source="audio.transcribe",
        correlation_id=UUID("44444444-4444-4444-4444-444444444444"),
        causation_id=None,
        subject_id=None,
        payload=TextTurnPayload(message="canary", conversation_id="canary-scope"),
    )


def _face_resolver(
    *, faces: int = 1, role: HouseholdRole = HouseholdRole.OWNER, matches: bool = True
) -> FaceRequestResolver:
    """A real FaceRequestResolver over doubles: `faces` detected, a close match or none."""

    async def detect(_frame: bytes) -> list[DetectedFace]:
        return [
            DetectedFace(embedding=np.zeros(512, dtype=np.float32), score=0.9, width=200.0)
        ] * faces

    async def match(_embedding: np.ndarray) -> FaceMatch | None:
        if not matches:
            return None
        return FaceMatch(entity_id=_OWNER_ID, name="Canary", distance=0.1)

    async def read_role(_person_id: int) -> HouseholdRole:
        return role

    async def read_person(person_id: int) -> PersonRecord | None:
        return _OWNER if person_id == _OWNER_ID else None

    async def read_consent(_person_id: int) -> bool:
        return True

    return FaceRequestResolver(
        frame=_FRAME,
        clock=lambda: _NOW,
        read_role=AsyncMock(side_effect=read_role),
        read_person=AsyncMock(side_effect=read_person),
        detect_faces=AsyncMock(side_effect=detect),
        match_face=AsyncMock(side_effect=match),
        read_consent=AsyncMock(side_effect=read_consent),
    )


def _voice_evidence(person_id: int = _OWNER_ID, *, expired: bool = False) -> IdentityEvidence:
    return IdentityEvidence(
        evidence_id=uuid4(),
        source=IdentityEvidenceSource.VOICE,
        candidate_person_id=person_id,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False),
        observed_at=_NOW - timedelta(minutes=2),
        expires_at=_NOW - timedelta(minutes=1) if expired else None,
        reference="in-turn-speaker-evidence",
    )


class _FakeSpeaker:
    """Stands in for SpeakerRequestResolver: a verdict plus the evidence it attached."""

    def __init__(self, verdict: SpeakerVerdict, evidence: tuple[IdentityEvidence, ...]) -> None:
        self.last_verdict = verdict
        self.calls = 0
        self._evidence = evidence

    async def resolve_actor(self, _event: object) -> ActivePersonContext:
        self.calls += 1
        return ActivePersonContext(
            person_id=None,
            display_name=None,
            status=ActivePersonStatus.UNKNOWN,
            confidence=Confidence(
                score=0.0, basis=ConfidenceBasis.NOT_APPLICABLE, calibrated=False
            ),
            role=HouseholdRole.UNKNOWN,
            evidence=self._evidence,
            resolved_at=_NOW,
        )


class _SpeakerFactory:
    """Records how often the speaker resolver is built and for whom."""

    def __init__(self, speaker: _FakeSpeaker) -> None:
        self.speaker = speaker
        self.owner_ids: list[int] = []

    def __call__(self, owner_person_id: int) -> _FakeSpeaker:
        self.owner_ids.append(owner_person_id)
        return self.speaker


def _verified() -> _SpeakerFactory:
    return _SpeakerFactory(_FakeSpeaker(SpeakerVerdict.VERIFIED, (_voice_evidence(),)))


class _Pin(NamedTuple):
    """A PIN resolver with the registry and token behind it, to prove token state."""

    resolver: OwnerRequestResolver
    registry: IdentitySessionRegistry
    token: str | None


def _pin(*, with_token: bool = False) -> _Pin:
    registry = IdentitySessionRegistry(
        lookup_person=lambda _pid: None, clock=lambda: _NOW, ttl=timedelta(seconds=60)
    )
    token = (
        registry.issue_for_person(_OWNER, source=IdentityEvidenceSource.LOCAL_UNLOCK)
        if with_token
        else None
    )
    resolver = OwnerRequestResolver(
        token=token,
        registry=registry,
        read_role=AsyncMock(return_value=HouseholdRole.OWNER),
        read_person=AsyncMock(return_value=_OWNER),
        clock=lambda: _NOW,
    )
    return _Pin(resolver, registry, token)


def _token_is_still_spendable(pin: _Pin) -> bool:
    """Whether the presented token is still in the registry, unconsumed."""
    assert pin.token is not None
    return pin.registry.evidence_for(pin.token) is not None


def _fused(
    *,
    face: FaceRequestResolver | None,
    speaker_factory: _SpeakerFactory | None = None,
    pin: OwnerRequestResolver | None = None,
) -> FusedIdentityResolver:
    return FusedIdentityResolver(
        pin=pin if pin is not None else _pin().resolver,
        face=face,
        # The fake stands in for SpeakerRequestResolver, which needs a real database and
        # embedding model; the fusion only uses `last_verdict` and `resolve_actor`.
        speaker_factory=cast("Callable[[int], SpeakerRequestResolver] | None", speaker_factory),
        clock=lambda: _NOW,
    )


async def test_face_and_verified_voice_identify_with_strong_assurance() -> None:
    factory = _verified()
    fused = _fused(face=_face_resolver(), speaker_factory=factory)
    event = _event()

    actor = await fused.resolve_actor(event)

    assert actor.status is ActivePersonStatus.IDENTIFIED
    assert actor.assurance is IdentityAssurance.STRONG
    assert fused.last_reason is FusionReason.FACE_AND_VOICE
    assert fused.source == "face_voice"
    assert factory.owner_ids == [_OWNER_ID]
    assert await fused.resolve_consent(event, actor) is ConsentStatus.GRANTED


async def test_face_without_a_verified_voice_stays_at_basic() -> None:
    """Review Focus 3: an unverified voice degrades to the default path."""
    factory = _SpeakerFactory(_FakeSpeaker(SpeakerVerdict.UNKNOWN, ()))
    fused = _fused(face=_face_resolver(), speaker_factory=factory)

    actor = await fused.resolve_actor(_event())

    assert actor.status is ActivePersonStatus.IDENTIFIED
    assert actor.assurance is IdentityAssurance.BASIC
    assert fused.last_reason is FusionReason.FACE_ONLY
    assert fused.source == "face"


async def test_an_unavailable_voice_backend_still_answers_at_basic() -> None:
    factory = _SpeakerFactory(_FakeSpeaker(SpeakerVerdict.UNAVAILABLE, ()))
    fused = _fused(face=_face_resolver(), speaker_factory=factory)

    actor = await fused.resolve_actor(_event())

    assert actor.assurance is IdentityAssurance.BASIC
    assert fused.last_reason is FusionReason.BACKEND_UNAVAILABLE


async def test_without_a_speaker_factory_the_face_is_basic_and_nothing_is_built() -> None:
    fused = _fused(face=_face_resolver(), speaker_factory=None)

    actor = await fused.resolve_actor(_event())

    assert actor.assurance is IdentityAssurance.BASIC
    assert fused.last_reason is FusionReason.FACE_ONLY


async def test_voice_evidence_for_another_person_is_ignored() -> None:
    """Review Focus 1: a foreign candidate can neither upgrade nor identify."""
    factory = _SpeakerFactory(
        _FakeSpeaker(SpeakerVerdict.VERIFIED, (_voice_evidence(person_id=99),))
    )
    fused = _fused(face=_face_resolver(), speaker_factory=factory)

    actor = await fused.resolve_actor(_event())

    assert actor.person_id == _OWNER_ID
    assert actor.assurance is IdentityAssurance.BASIC
    assert fused.last_reason is FusionReason.FACE_ONLY


async def test_expired_voice_evidence_leaves_the_face_at_basic() -> None:
    factory = _SpeakerFactory(
        _FakeSpeaker(SpeakerVerdict.VERIFIED, (_voice_evidence(expired=True),))
    )
    fused = _fused(face=_face_resolver(), speaker_factory=factory)

    actor = await fused.resolve_actor(_event())

    assert actor.assurance is IdentityAssurance.BASIC


async def test_the_speaker_is_built_and_consulted_once_per_request() -> None:
    factory = _verified()
    fused = _fused(face=_face_resolver(), speaker_factory=factory)

    for _ in range(3):
        await fused.resolve_actor(_event())

    assert factory.owner_ids == [_OWNER_ID]
    assert factory.speaker.calls == 1


async def test_a_face_that_is_not_the_owner_never_consults_voice_or_pin() -> None:
    """Face unknown: voice is not consulted (nothing to corroborate)."""
    factory = _verified()
    fused = _fused(face=_face_resolver(matches=False), speaker_factory=factory)

    actor = await fused.resolve_actor(_event())

    assert actor.status is ActivePersonStatus.UNKNOWN
    assert factory.owner_ids == []
    assert fused.last_reason is FusionReason.NO_EVIDENCE


async def test_another_enrolled_person_vetoes_even_with_a_valid_token() -> None:
    """Review Focus 2: the veto does not consume the PIN token."""
    pin = _pin(with_token=True)
    factory = _verified()
    fused = _fused(
        face=_face_resolver(role=HouseholdRole.ADULT), speaker_factory=factory, pin=pin.resolver
    )
    event = _event()

    actor = await fused.resolve_actor(event)

    assert actor.status is ActivePersonStatus.AMBIGUOUS
    assert fused.last_reason is FusionReason.VETO_OTHER_PERSON
    assert pin.resolver.consumed is False
    assert _token_is_still_spendable(pin)
    assert factory.owner_ids == []
    assert await fused.resolve_consent(event, actor) is ConsentStatus.NOT_REQUIRED


async def test_two_faces_veto_even_with_a_valid_token_and_keep_the_token() -> None:
    pin = _pin(with_token=True)
    fused = _fused(face=_face_resolver(faces=2), speaker_factory=_verified(), pin=pin.resolver)
    event = _event()

    actor = await fused.resolve_actor(event)

    assert actor.status is ActivePersonStatus.AMBIGUOUS
    assert fused.last_reason is FusionReason.VETO_MULTIPLE_FACES
    assert pin.resolver.consumed is False
    assert _token_is_still_spendable(pin)
    assert await fused.resolve_consent(event, actor) is ConsentStatus.NOT_REQUIRED


async def test_an_unknown_face_falls_through_to_a_valid_pin_token() -> None:
    pin = _pin(with_token=True)
    fused = _fused(face=_face_resolver(matches=False), speaker_factory=None, pin=pin.resolver)
    event = _event()

    actor = await fused.resolve_actor(event)

    assert actor.status is ActivePersonStatus.IDENTIFIED
    assert actor.assurance is IdentityAssurance.STRONG
    assert fused.last_reason is FusionReason.PIN
    assert fused.source == "local_unlock"
    assert fused.consumed is True
    assert await fused.resolve_consent(event, actor) is ConsentStatus.GRANTED


async def test_a_face_identified_owner_never_consumes_the_pin_token() -> None:
    pin = _pin(with_token=True)
    fused = _fused(face=_face_resolver(), speaker_factory=None, pin=pin.resolver)

    await fused.resolve_actor(_event())

    assert pin.resolver.consumed is False
    assert _token_is_still_spendable(pin)


async def test_no_face_and_no_token_is_unknown_with_no_evidence() -> None:
    fused = _fused(face=None, speaker_factory=_verified())
    event = _event()

    actor = await fused.resolve_actor(event)

    assert actor.status is ActivePersonStatus.UNKNOWN
    assert fused.last_reason is FusionReason.NO_EVIDENCE
    assert fused.source is None
    assert await fused.resolve_consent(event, actor) is ConsentStatus.NOT_REQUIRED


async def test_the_log_carries_the_reason_and_no_personal_data(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fused = _fused(face=_face_resolver(), speaker_factory=_verified())

    with caplog.at_level(logging.INFO):
        await fused.resolve_actor(_event())

    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert "face_and_voice" in joined
    assert "Canary" not in joined
