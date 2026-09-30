"""Unit tests for the pure face verdict and the request-scoped face resolver."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
import logging
from unittest.mock import AsyncMock
from uuid import UUID

import numpy as np
import pytest
from server.cognition.authorization import ConsentStatus
from server.cognition.face_authentication import (
    FaceAuthenticationVerdict,
    FaceRequestResolver,
    evaluate_face_authentication,
)
from server.cognition.identity import (
    ActivePersonStatus,
    HouseholdRole,
    PersonRecord,
)
from server.cognition.models import CognitiveEvent
from server.cognition.response_plan import TextTurnPayload
from server.exceptions import VisionError
from server.settings import settings
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
@pytest.mark.parametrize("consent_active", [True, False])
def test_one_face_match_of_a_non_owner_is_positive_evidence_of_another_person(
    consent_active: bool,
) -> None:
    """ADR 0016 §4: a match with someone who is not the owner vetoes, consent or not."""
    verdict = evaluate_face_authentication(
        detected_face_count=1,
        match=_match(0.1),
        consent_active=consent_active,
        role=HouseholdRole.ADULT,
    )
    assert verdict is FaceAuthenticationVerdict.OTHER_PERSON


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
async def test_match_beyond_strict_threshold_resolves_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A distance beyond the strict auth threshold must fail even if some
    looser, generic threshold would have accepted it.

    Pins `face_authentication_match_threshold` explicitly rather than
    relying on whatever the production default currently is — the point
    under test is the boundary check itself, not any particular value.
    """
    monkeypatch.setattr(settings, "face_authentication_match_threshold", 0.25)

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
async def test_match_within_threshold_of_a_non_owner_resolves_ambiguous() -> None:
    """A close match with another enrolled person denies and never identifies."""

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

    assert actor.status is ActivePersonStatus.AMBIGUOUS
    assert actor.person_id is None
    assert resolver.last_verdict is FaceAuthenticationVerdict.OTHER_PERSON


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
