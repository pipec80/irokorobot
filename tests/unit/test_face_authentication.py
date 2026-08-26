"""Unit tests for the pure face verdict, request resolver, and PIN composition."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
import logging
from unittest.mock import AsyncMock
from uuid import UUID

import numpy as np
import pytest
from server.cognition.authorization import ConsentStatus
from server.cognition.face_authentication import (
    FaceAuthenticationVerdict,
    FaceRequestResolver,
    compose_face_then_pin_resolver,
    evaluate_face_authentication,
)
from server.cognition.identity import (
    ActivePersonStatus,
    HouseholdRole,
    PersonRecord,
)
from server.cognition.identity_sessions import IdentitySessionRegistry
from server.cognition.models import CognitiveEvent
from server.cognition.owner_authentication import OwnerRequestResolver
from server.cognition.response_plan import TextTurnPayload
from server.exceptions import VisionError
from server.vision.faces import DetectedFace, FaceMatch

_NOW = datetime(2026, 8, 25, 10, 0, tzinfo=UTC)
_MATCHED_ENTITY_ID = 7
_FRAME = b"fake-jpeg-bytes"


def _unit_vector(seed: int) -> np.ndarray:
    """Build a deterministic opaque embedding — no real face math involved."""
    vector = np.zeros(512, dtype=np.float32)
    vector[seed % 512] = 1.0
    return vector


def _event(message: str = "Hola") -> CognitiveEvent[TextTurnPayload]:
    return CognitiveEvent(
        event_id=UUID("33333333-3333-3333-3333-333333333333"),
        schema_version=1,
        event_type="text.turn",
        occurred_at=_NOW,
        recorded_at=_NOW,
        source="web.chat",
        correlation_id=UUID("44444444-4444-4444-4444-444444444444"),
        causation_id=None,
        subject_id=None,
        payload=TextTurnPayload(message=message, conversation_id="acceptance-face"),
    )


def _face(seed: int = 1) -> DetectedFace:
    return DetectedFace(embedding=_unit_vector(seed), score=0.9, width=200.0)


def _match(distance: float) -> FaceMatch:
    return FaceMatch(entity_id=_MATCHED_ENTITY_ID, name="Pipec", distance=distance)


# ---------------------------------------------------------------------------
# evaluate_face_authentication — pure decision table, no I/O
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_zero_faces_is_unknown() -> None:
    """No detected face gives no evidence to authenticate anyone."""
    verdict = evaluate_face_authentication(
        detected_face_count=0, match=None, consent_active=True, role=HouseholdRole.OWNER
    )
    assert verdict is FaceAuthenticationVerdict.UNKNOWN


@pytest.mark.unit
def test_two_or_more_faces_is_ambiguous() -> None:
    """Multiple faces in frame must never resolve to a single identity."""
    verdict = evaluate_face_authentication(
        detected_face_count=2, match=_match(0.1), consent_active=True, role=HouseholdRole.OWNER
    )
    assert verdict is FaceAuthenticationVerdict.AMBIGUOUS


@pytest.mark.unit
def test_one_face_no_match_is_unknown() -> None:
    """A single face that matched nobody must resolve to unknown."""
    verdict = evaluate_face_authentication(
        detected_face_count=1, match=None, consent_active=True, role=HouseholdRole.OWNER
    )
    assert verdict is FaceAuthenticationVerdict.UNKNOWN


@pytest.mark.unit
def test_one_face_match_but_consent_inactive_is_unknown() -> None:
    """A matched face without active biometric consent must not authenticate."""
    verdict = evaluate_face_authentication(
        detected_face_count=1, match=_match(0.1), consent_active=False, role=HouseholdRole.OWNER
    )
    assert verdict is FaceAuthenticationVerdict.UNKNOWN


@pytest.mark.unit
def test_one_face_match_consent_but_non_owner_role_is_unknown() -> None:
    """A consenting, matched non-owner must never be treated as the owner."""
    verdict = evaluate_face_authentication(
        detected_face_count=1, match=_match(0.1), consent_active=True, role=HouseholdRole.ADULT
    )
    assert verdict is FaceAuthenticationVerdict.UNKNOWN


@pytest.mark.unit
def test_one_face_match_consent_owner_role_is_identified() -> None:
    """The only row that authenticates: single face, match, consent, owner role."""
    verdict = evaluate_face_authentication(
        detected_face_count=1, match=_match(0.1), consent_active=True, role=HouseholdRole.OWNER
    )
    assert verdict is FaceAuthenticationVerdict.IDENTIFIED


# ---------------------------------------------------------------------------
# FaceRequestResolver — injected fake boundaries only, no real vision calls
# ---------------------------------------------------------------------------


def _owner_person() -> PersonRecord:
    return PersonRecord(person_id=_MATCHED_ENTITY_ID, display_name="Pipec", entity_type="person")


def _resolver(
    *,
    frame: bytes | None,
    detect_faces: Callable[[bytes], Awaitable[list[DetectedFace]]] | None = None,
    match_face: Callable[[np.ndarray], Awaitable[FaceMatch | None]] | None = None,
    read_consent: Callable[[int], Awaitable[bool]] | None = None,
    read_role: Callable[[int], Awaitable[HouseholdRole]] | None = None,
    read_person: Callable[[int], Awaitable[PersonRecord | None]] | None = None,
    clock: Callable[[], datetime] = lambda: _NOW,
) -> FaceRequestResolver:
    async def _default_detect(_frame: bytes) -> list[DetectedFace]:
        return []

    async def _default_match(_embedding: np.ndarray) -> FaceMatch | None:
        return None

    async def _default_consent(_person_id: int) -> bool:
        return True

    async def _default_role(_person_id: int) -> HouseholdRole:
        return HouseholdRole.OWNER

    async def _default_person(person_id: int) -> PersonRecord | None:
        return _owner_person() if person_id == _MATCHED_ENTITY_ID else None

    return FaceRequestResolver(
        frame=frame,
        clock=clock,
        read_role=AsyncMock(side_effect=read_role or _default_role),
        read_person=AsyncMock(side_effect=read_person or _default_person),
        detect_faces=AsyncMock(side_effect=detect_faces or _default_detect),
        match_face=AsyncMock(side_effect=match_face or _default_match),
        read_consent=AsyncMock(side_effect=read_consent or _default_consent),
    )


@pytest.mark.unit
async def test_no_frame_resolves_unknown_without_decoding() -> None:
    """A missing frame must short-circuit before any detection is attempted."""
    resolver = _resolver(frame=None)

    actor = await resolver.resolve_actor(_event())

    assert actor.status is ActivePersonStatus.UNKNOWN
    assert actor.person_id is None
    resolver._detect_faces.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.unit
async def test_zero_detected_faces_resolves_unknown_without_matching() -> None:
    """No faces in frame must not attempt a match at all."""
    resolver = _resolver(frame=_FRAME)

    actor = await resolver.resolve_actor(_event())

    assert actor.status is ActivePersonStatus.UNKNOWN
    resolver._match_face.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.unit
async def test_two_detected_faces_resolves_ambiguous_without_matching() -> None:
    """Two faces must resolve ambiguous and skip matching entirely."""

    async def detect_two(_frame: bytes) -> list[DetectedFace]:
        return [_face(1), _face(2)]

    resolver = _resolver(frame=_FRAME, detect_faces=detect_two)

    actor = await resolver.resolve_actor(_event())

    assert actor.status is ActivePersonStatus.AMBIGUOUS
    assert actor.person_id is None
    resolver._match_face.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.unit
async def test_match_beyond_strict_threshold_resolves_unknown() -> None:
    """A distance that would pass the generic 0.4 threshold must still fail here."""

    async def detect_one(_frame: bytes) -> list[DetectedFace]:
        return [_face(1)]

    async def match_far(_embedding: np.ndarray) -> FaceMatch | None:
        return _match(0.39)

    resolver = _resolver(frame=_FRAME, detect_faces=detect_one, match_face=match_far)

    actor = await resolver.resolve_actor(_event())

    assert actor.status is ActivePersonStatus.UNKNOWN
    assert actor.person_id is None


@pytest.mark.unit
async def test_match_within_threshold_but_consent_inactive_resolves_unknown() -> None:
    """A close match without active consent must not authenticate."""

    async def detect_one(_frame: bytes) -> list[DetectedFace]:
        return [_face(1)]

    async def match_close(_embedding: np.ndarray) -> FaceMatch | None:
        return _match(0.1)

    async def consent_false(_person_id: int) -> bool:
        return False

    resolver = _resolver(
        frame=_FRAME, detect_faces=detect_one, match_face=match_close, read_consent=consent_false
    )

    actor = await resolver.resolve_actor(_event())

    assert actor.status is ActivePersonStatus.UNKNOWN
    assert actor.person_id is None


@pytest.mark.unit
async def test_match_within_threshold_consent_but_non_owner_role_resolves_unknown() -> None:
    """A close, consenting match that is not the owner must not authenticate."""

    async def detect_one(_frame: bytes) -> list[DetectedFace]:
        return [_face(1)]

    async def match_close(_embedding: np.ndarray) -> FaceMatch | None:
        return _match(0.1)

    async def role_adult(_person_id: int) -> HouseholdRole:
        return HouseholdRole.ADULT

    resolver = _resolver(
        frame=_FRAME, detect_faces=detect_one, match_face=match_close, read_role=role_adult
    )

    actor = await resolver.resolve_actor(_event())

    assert actor.status is ActivePersonStatus.UNKNOWN
    assert actor.person_id is None


@pytest.mark.unit
async def test_match_within_threshold_consent_owner_role_identifies_owner() -> None:
    """The full identified path returns the correct person_id and display_name."""

    async def detect_one(_frame: bytes) -> list[DetectedFace]:
        return [_face(1)]

    async def match_close(_embedding: np.ndarray) -> FaceMatch | None:
        return _match(0.1)

    resolver = _resolver(frame=_FRAME, detect_faces=detect_one, match_face=match_close)

    actor = await resolver.resolve_actor(_event())

    assert actor.status is ActivePersonStatus.IDENTIFIED
    assert actor.person_id == _MATCHED_ENTITY_ID
    assert actor.display_name == "Pipec"
    assert actor.role is HouseholdRole.OWNER
    assert resolver.consumed is True


@pytest.mark.unit
async def test_resolve_actor_caches_across_two_calls_in_the_same_turn() -> None:
    """Detection and matching must run exactly once no matter how many calls."""

    async def detect_one(_frame: bytes) -> list[DetectedFace]:
        return [_face(1)]

    async def match_close(_embedding: np.ndarray) -> FaceMatch | None:
        return _match(0.1)

    resolver = _resolver(frame=_FRAME, detect_faces=detect_one, match_face=match_close)
    event = _event()

    first = await resolver.resolve_actor(event)
    second = await resolver.resolve_actor(event)

    assert first == second
    resolver._detect_faces.assert_awaited_once()  # type: ignore[attr-defined]
    resolver._match_face.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.unit
async def test_vision_error_degrades_to_unknown_without_raising() -> None:
    """A face-pipeline failure must never crash the turn — degrade safely."""

    async def failing_detect(_frame: bytes) -> list[DetectedFace]:
        raise VisionError("model unavailable")

    resolver = _resolver(frame=_FRAME, detect_faces=failing_detect)

    actor = await resolver.resolve_actor(_event())

    assert actor.status is ActivePersonStatus.UNKNOWN
    assert actor.person_id is None


@pytest.mark.unit
async def test_no_frame_embedding_or_token_appears_in_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Sensitive material must never reach any log record across all paths."""

    async def detect_one(_frame: bytes) -> list[DetectedFace]:
        return [_face(1)]

    async def match_close(_embedding: np.ndarray) -> FaceMatch | None:
        return _match(0.1)

    async def failing_detect(_frame: bytes) -> list[DetectedFace]:
        raise VisionError("model unavailable")

    with caplog.at_level(logging.DEBUG):
        identified = _resolver(frame=_FRAME, detect_faces=detect_one, match_face=match_close)
        await identified.resolve_actor(_event())

        failing = _resolver(frame=_FRAME, detect_faces=failing_detect)
        await failing.resolve_actor(_event())

    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert _FRAME.decode("latin-1") not in joined
    assert str(_unit_vector(1).tolist()) not in joined


@pytest.mark.unit
async def test_resolve_consent_granted_only_after_identified_resolution() -> None:
    """Consent must only be GRANTED after this resolver identified the owner."""

    async def detect_one(_frame: bytes) -> list[DetectedFace]:
        return [_face(1)]

    async def match_close(_embedding: np.ndarray) -> FaceMatch | None:
        return _match(0.1)

    identified_resolver = _resolver(frame=_FRAME, detect_faces=detect_one, match_face=match_close)
    event = _event()
    actor = await identified_resolver.resolve_actor(event)
    consent = await identified_resolver.resolve_consent(event, actor)
    assert consent is ConsentStatus.GRANTED

    unknown_resolver = _resolver(frame=None)
    unknown_actor = await unknown_resolver.resolve_actor(event)
    unknown_consent = await unknown_resolver.resolve_consent(event, unknown_actor)
    assert unknown_consent is not ConsentStatus.GRANTED


# ---------------------------------------------------------------------------
# compose_face_then_pin_resolver
# ---------------------------------------------------------------------------


def _pin_resolver() -> OwnerRequestResolver:
    registry = IdentitySessionRegistry(
        lookup_person=lambda _pid: None, clock=lambda: _NOW, ttl=timedelta(seconds=60)
    )
    return OwnerRequestResolver(
        token=None,
        registry=registry,
        read_role=AsyncMock(side_effect=lambda _pid: HouseholdRole.OWNER),
        read_person=AsyncMock(side_effect=lambda _pid: None),
        clock=lambda: _NOW,
    )


@pytest.mark.unit
async def test_face_identified_short_circuits_pin_resolver() -> None:
    """A face-identified owner must never trigger the PIN resolver."""

    async def detect_one(_frame: bytes) -> list[DetectedFace]:
        return [_face(1)]

    async def match_close(_embedding: np.ndarray) -> FaceMatch | None:
        return _match(0.1)

    face = _resolver(frame=_FRAME, detect_faces=detect_one, match_face=match_close)
    pin = _pin_resolver()
    pin.resolve_actor = AsyncMock(wraps=pin.resolve_actor)  # type: ignore[method-assign]
    resolve_actor, _ = compose_face_then_pin_resolver(face, pin)

    actor = await resolve_actor(_event())

    assert actor.status is ActivePersonStatus.IDENTIFIED
    pin.resolve_actor.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.unit
async def test_face_ambiguous_short_circuits_pin_resolver_and_denies() -> None:
    """A stranger sharing the frame must deny without ever consulting the PIN."""

    async def detect_two(_frame: bytes) -> list[DetectedFace]:
        return [_face(1), _face(2)]

    face = _resolver(frame=_FRAME, detect_faces=detect_two)
    pin = _pin_resolver()
    pin.resolve_actor = AsyncMock(wraps=pin.resolve_actor)  # type: ignore[method-assign]
    resolve_actor, _ = compose_face_then_pin_resolver(face, pin)

    actor = await resolve_actor(_event())

    assert actor.status is ActivePersonStatus.AMBIGUOUS
    assert actor.person_id is None
    assert actor.display_name is None
    pin.resolve_actor.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.unit
async def test_face_ambiguous_short_circuits_pin_resolve_consent_too() -> None:
    """An ambiguous face verdict must deny consent without ever consulting the PIN."""

    async def detect_two(_frame: bytes) -> list[DetectedFace]:
        return [_face(1), _face(2)]

    face = _resolver(frame=_FRAME, detect_faces=detect_two)
    pin = _pin_resolver()
    pin.resolve_consent = AsyncMock(wraps=pin.resolve_consent)  # type: ignore[method-assign]
    resolve_actor, resolve_consent = compose_face_then_pin_resolver(face, pin)
    event = _event()

    actor = await resolve_actor(event)
    consent = await resolve_consent(event, actor)

    assert consent is ConsentStatus.NOT_REQUIRED
    pin.resolve_consent.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.unit
async def test_face_unknown_falls_through_to_pin_unchanged() -> None:
    """No frame supplied must preserve the exact existing PIN-only behavior."""
    face = _resolver(frame=None)
    pin = _pin_resolver()
    expected = await pin.resolve_actor(_event())
    pin.resolve_actor = AsyncMock(return_value=expected)  # type: ignore[method-assign]
    resolve_actor, _ = compose_face_then_pin_resolver(face, pin)

    actor = await resolve_actor(_event())

    assert actor == expected
    pin.resolve_actor.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.unit
async def test_resolve_consent_routes_to_face_when_face_identified() -> None:
    """Consent for a face-identified actor must be asked to the face resolver."""

    async def detect_one(_frame: bytes) -> list[DetectedFace]:
        return [_face(1)]

    async def match_close(_embedding: np.ndarray) -> FaceMatch | None:
        return _match(0.1)

    face = _resolver(frame=_FRAME, detect_faces=detect_one, match_face=match_close)
    pin = _pin_resolver()
    pin.resolve_consent = AsyncMock(wraps=pin.resolve_consent)  # type: ignore[method-assign]
    resolve_actor, resolve_consent = compose_face_then_pin_resolver(face, pin)
    event = _event()

    actor = await resolve_actor(event)
    consent = await resolve_consent(event, actor)

    assert consent is ConsentStatus.GRANTED
    pin.resolve_consent.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.unit
async def test_resolve_consent_routes_to_pin_when_face_did_not_identify() -> None:
    """Consent for a PIN-identified actor must be asked to the PIN resolver, not face."""
    face = _resolver(frame=None)
    pin = _pin_resolver()
    pin.resolve_consent = AsyncMock(wraps=pin.resolve_consent)  # type: ignore[method-assign]
    face.resolve_consent = AsyncMock(wraps=face.resolve_consent)  # type: ignore[method-assign]
    resolve_actor, resolve_consent = compose_face_then_pin_resolver(face, pin)
    event = _event()

    actor = await resolve_actor(event)
    await resolve_consent(event, actor)

    pin.resolve_consent.assert_awaited_once()  # type: ignore[attr-defined]
    face.resolve_consent.assert_not_awaited()  # type: ignore[attr-defined]
