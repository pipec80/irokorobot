"""Unit tests for identifying the speaker of a generic turn (ADR 0020 §1).

Face first, then a presented default-scope token that is only observed; never the voice, never a
spent grant, and never a failed turn.
"""

from datetime import UTC, datetime, timedelta
import logging
from unittest.mock import AsyncMock
from uuid import UUID

import aiosqlite
import numpy as np
import pytest
from server.cognition.face_authentication import FaceRequestResolver
from server.cognition.generic_identity import GenericIdentification, identify_generic_speaker
from server.cognition.identity import (
    ActivePersonStatus,
    HouseholdRole,
    IdentityAssurance,
    IdentityEvidenceSource,
    PersonRecord,
)
from server.cognition.identity_fusion import FusedIdentityResolver
from server.cognition.identity_sessions import IdentitySessionRegistry
from server.cognition.models import CognitiveEvent
from server.cognition.owner_authentication import OwnerRequestResolver, OwnerUnlockScope
from server.cognition.response_plan import TextTurnPayload
from server.exceptions import BrainMemoryError, VisionError
from server.memory.continuity import SuspendCause
from server.settings import settings
from server.vision.faces import DetectedFace, FaceMatch

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 10, 13, 10, 0, tzinfo=UTC)
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


@pytest.fixture(autouse=True)
def _memory_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Identification is on only with memory on; do not depend on the ambient `MEMORY_ENABLED`."""
    monkeypatch.setattr(settings, "memory_enabled", True)


class _World:
    """One request's doubles: a face resolver, a token registry and what the builder saw."""

    def __init__(
        self,
        *,
        faces: int = 1,
        role: HouseholdRole = HouseholdRole.OWNER,
        detect_error: Exception | None = None,
        match_error: Exception | None = None,
        person_error: Exception | None = None,
        with_token: bool = False,
    ) -> None:
        self.builder_calls: list[dict[str, object]] = []
        self.registry = IdentitySessionRegistry(
            lookup_person=lambda _pid: None, clock=lambda: _NOW, ttl=timedelta(seconds=60)
        )
        self.token = (
            self.registry.issue_for_person(
                _OWNER,
                source=IdentityEvidenceSource.LOCAL_UNLOCK,
                scope=OwnerUnlockScope.PERSONAL_PROTECTED_READ.value,
            )
            if with_token
            else None
        )

        async def detect(_frame: bytes) -> list[DetectedFace]:
            if detect_error is not None:
                raise detect_error
            return [
                DetectedFace(embedding=np.zeros(512, dtype=np.float32), score=0.9, width=200.0)
            ] * faces

        async def match(_embedding: np.ndarray) -> FaceMatch | None:
            if match_error is not None:
                raise match_error
            return FaceMatch(entity_id=_OWNER_ID, name="Canary", distance=0.1)

        async def read_person(person_id: int) -> PersonRecord | None:
            if person_error is not None:
                raise person_error
            return _OWNER if person_id == _OWNER_ID else None

        self._face = FaceRequestResolver(
            frame=_FRAME,
            clock=lambda: _NOW,
            read_role=AsyncMock(return_value=role),
            read_person=AsyncMock(side_effect=read_person),
            detect_faces=AsyncMock(side_effect=detect),
            match_face=AsyncMock(side_effect=match),
            read_consent=AsyncMock(return_value=True),
        )
        self._pin_person_error = person_error

    def for_request(self, token: str | None) -> OwnerRequestResolver:
        async def read_person(_pid: int) -> PersonRecord | None:
            if self._pin_person_error is not None:
                raise self._pin_person_error
            return _OWNER

        return OwnerRequestResolver(
            token=token,
            registry=self.registry,
            read_role=AsyncMock(return_value=HouseholdRole.OWNER),
            read_person=AsyncMock(side_effect=read_person),
            clock=lambda: _NOW,
        )

    def build(
        self, pin: OwnerRequestResolver, *, frame: bytes | None, wav_bytes: bytes | None
    ) -> FusedIdentityResolver:
        self.builder_calls.append({"frame": frame, "wav_bytes": wav_bytes})
        return FusedIdentityResolver(
            pin=pin,
            face=self._face if frame is not None else None,
            speaker_factory=None,
            clock=lambda: _NOW,
        )

    def token_is_unspent(self) -> bool:
        assert self.token is not None
        return self.registry.evidence_for(self.token) is not None


async def _identify(
    world: _World, *, frame: bytes | None = _FRAME, token: str | None = None
) -> GenericIdentification:
    return await identify_generic_speaker(
        world.for_request,
        token=token if token is not None else world.token,
        frame=frame,
        event=_event(),
        build_resolver=world.build,
    )


async def test_the_face_of_the_owner_identifies_at_basic_without_voice() -> None:
    world = _World()

    result = await _identify(world)

    assert result.cause is None
    assert result.actor is not None
    assert result.actor.status is ActivePersonStatus.IDENTIFIED
    assert result.actor.person_id == _OWNER_ID
    assert result.actor.assurance is IdentityAssurance.BASIC
    assert world.builder_calls == [{"frame": _FRAME, "wav_bytes": None}]


async def test_without_frame_or_token_the_speaker_is_unknown_for_lack_of_evidence() -> None:
    world = _World()

    result = await _identify(world, frame=None)

    assert result.actor is not None
    assert result.actor.status is ActivePersonStatus.UNKNOWN
    assert result.cause is SuspendCause.NO_EVIDENCE


async def test_a_presented_token_names_the_owner_and_is_never_spent() -> None:
    world = _World(with_token=True)

    result = await _identify(world, frame=None)

    assert result.actor is not None
    assert result.actor.status is ActivePersonStatus.IDENTIFIED
    assert result.actor.person_id == _OWNER_ID
    assert world.token_is_unspent()


async def test_an_identified_face_leaves_a_presented_token_untouched() -> None:
    world = _World(with_token=True)

    result = await _identify(world)

    assert result.actor is not None
    assert result.actor.assurance is IdentityAssurance.BASIC
    assert world.token_is_unspent()


async def test_another_enrolled_person_suspends_and_keeps_the_token() -> None:
    world = _World(role=HouseholdRole.ADULT, with_token=True)

    result = await _identify(world)

    assert result.actor is not None
    assert result.actor.status is ActivePersonStatus.AMBIGUOUS
    assert result.cause is SuspendCause.VETO_OTHER_PERSON
    assert world.token_is_unspent()


async def test_two_faces_suspend() -> None:
    world = _World(faces=2, with_token=True)

    result = await _identify(world)

    assert result.cause is SuspendCause.VETO_MULTIPLE_FACES
    assert world.token_is_unspent()


async def test_a_failed_detector_is_reported_as_an_unavailable_backend() -> None:
    world = _World(detect_error=VisionError("model unavailable"))

    result = await _identify(world)

    assert result.actor is not None
    assert result.actor.status is ActivePersonStatus.UNKNOWN
    assert result.cause is SuspendCause.BACKEND_UNAVAILABLE


@pytest.mark.parametrize(
    "error", [BrainMemoryError("db"), aiosqlite.Error("db")], ids=lambda error: type(error).__name__
)
async def test_a_store_error_in_the_face_path_never_fails_the_turn(error: Exception) -> None:
    world = _World(match_error=error)

    result = await _identify(world)

    assert result.actor is not None
    assert result.actor.status is ActivePersonStatus.UNKNOWN
    assert result.cause is SuspendCause.ERROR


async def test_a_store_error_in_the_token_path_never_fails_the_turn() -> None:
    world = _World(person_error=BrainMemoryError("db"), with_token=True)

    result = await _identify(world, frame=None)

    assert result.actor is None
    assert result.cause is SuspendCause.ERROR


async def test_identification_is_skipped_when_memory_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "memory_enabled", False)
    world = _World(with_token=True)

    result = await _identify(world)

    assert result == GenericIdentification(actor=None, cause=None)
    assert world.builder_calls == []
    assert world.token_is_unspent()


async def test_the_outcome_and_the_elapsed_time_are_logged_without_personal_data(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """ADR 0020 §10 d: the cost of the face check is measured from the log."""
    world = _World()

    with caplog.at_level(logging.INFO, logger="server.cognition.generic_identity"):
        await _identify(world)

    records = [r for r in caplog.records if getattr(r, "event", None) == "identity.generic"]
    assert len(records) == 1
    assert getattr(records[0], "outcome", None) == "identified"
    elapsed = getattr(records[0], "elapsed_ms", None)
    assert isinstance(elapsed, int)
    assert elapsed >= 0
    assert "Canary" not in caplog.text
