"""Unit tests for the speaker wrapper around the actor resolver (Plan 0053, D-6).

`_speaker_augmented_actor_resolver` decides WHEN the speaker resolver is
consulted: only when face/PIN did not already identify the actor, at most once
per request, and it may only ATTACH untrusted evidence — never upgrade the
context. These tests drive it directly with doubles, so a wrapper that never
consulted the resolver could not pass them.
"""

from datetime import UTC, datetime
from uuid import uuid4

import aiosqlite
import pytest
from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    HouseholdRole,
    IdentityEvidence,
    IdentityEvidenceSource,
)
from server.cognition.models import CognitiveEvent, Confidence, ConfidenceBasis
from server.cognition.response_plan import TextTurnPayload
from server.exceptions import BrainMemoryError
from server.routers import transcribe as transcribe_module

_NOW = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
_OWNER_ID = 7


def _event() -> CognitiveEvent[TextTurnPayload]:
    return CognitiveEvent(
        event_id=uuid4(),
        schema_version=1,
        event_type="text.turn",
        occurred_at=_NOW,
        recorded_at=_NOW,
        source="audio.transcribe",
        correlation_id=uuid4(),
        causation_id=None,
        subject_id=None,
        payload=TextTurnPayload(message="canary", conversation_id="canary-scope"),
    )


def _confidence() -> Confidence:
    return Confidence(score=0.0, basis=ConfidenceBasis.NOT_APPLICABLE, calibrated=False)


def _context(
    status: ActivePersonStatus, *, evidence: tuple[IdentityEvidence, ...] = ()
) -> ActivePersonContext:
    identified = status is ActivePersonStatus.IDENTIFIED
    return ActivePersonContext(
        person_id=_OWNER_ID if identified else None,
        display_name="canary" if identified else None,
        status=status,
        confidence=_confidence(),
        role=HouseholdRole.OWNER if identified else HouseholdRole.UNKNOWN,
        evidence=evidence,
        resolved_at=_NOW,
    )


def _voice_evidence() -> IdentityEvidence:
    return IdentityEvidence(
        evidence_id=uuid4(),
        source=IdentityEvidenceSource.VOICE,
        candidate_person_id=_OWNER_ID,
        confidence=_confidence(),
        observed_at=_NOW,
        reference="in-turn-speaker-evidence",
    )


class _FakeSpeaker:
    """Stands in for SpeakerRequestResolver; counts how often it is consulted."""

    def __init__(self, evidence: tuple[IdentityEvidence, ...]) -> None:
        self.calls = 0
        self._evidence = evidence

    async def resolve_actor(self, _event: object) -> ActivePersonContext:
        self.calls += 1
        return _context(ActivePersonStatus.UNKNOWN, evidence=self._evidence)


class _Harness:
    """Patches the wrapper's two collaborators and records how they are used."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.builds = 0
        self.credential_reads = 0
        self.credential: object | None = type("Credential", (), {"person_entity_id": _OWNER_ID})()
        self.credential_error: Exception | None = None
        self.speaker = _FakeSpeaker((_voice_evidence(),))
        monkeypatch.setattr(transcribe_module, "get_active_owner_pin_credential", self._read)
        monkeypatch.setattr(transcribe_module, "build_default_speaker_resolver", self._build)

    async def _read(self) -> object | None:
        self.credential_reads += 1
        if self.credential_error is not None:
            raise self.credential_error
        return self.credential

    def _build(self, _wav: bytes, _owner_id: int) -> _FakeSpeaker:
        self.builds += 1
        return self.speaker


def _base(context: ActivePersonContext):
    async def resolve(_event: object) -> ActivePersonContext:
        return context

    return resolve


async def test_an_identified_actor_never_consults_the_speaker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _Harness(monkeypatch)
    identified = _context(ActivePersonStatus.IDENTIFIED)
    resolve = transcribe_module._speaker_augmented_actor_resolver(_base(identified), b"wav")

    assert await resolve(_event()) is identified
    assert harness.builds == 0
    assert harness.credential_reads == 0
    assert harness.speaker.calls == 0


async def test_an_unidentified_actor_gains_voice_evidence_but_no_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _Harness(monkeypatch)
    unknown = _context(ActivePersonStatus.UNKNOWN)
    resolve = transcribe_module._speaker_augmented_actor_resolver(_base(unknown), b"wav")

    result = await resolve(_event())

    assert [item.source for item in result.evidence] == [IdentityEvidenceSource.VOICE]
    assert result.status is ActivePersonStatus.UNKNOWN
    assert result.person_id is None
    assert result.role is HouseholdRole.UNKNOWN
    assert harness.speaker.calls == 1


async def test_the_speaker_is_built_and_consulted_once_per_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The controller calls the actor resolver up to three times per decision."""
    harness = _Harness(monkeypatch)
    resolve = transcribe_module._speaker_augmented_actor_resolver(
        _base(_context(ActivePersonStatus.UNKNOWN)), b"wav"
    )

    for _ in range(3):
        await resolve(_event())

    assert harness.builds == 1
    assert harness.credential_reads == 1


async def test_evidence_from_the_base_resolver_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _Harness(monkeypatch)
    prior = IdentityEvidence(
        evidence_id=uuid4(),
        source=IdentityEvidenceSource.SESSION,
        candidate_person_id=None,
        confidence=_confidence(),
        observed_at=_NOW,
        reference="canary",
    )
    base = _base(_context(ActivePersonStatus.UNKNOWN, evidence=(prior,)))
    resolve = transcribe_module._speaker_augmented_actor_resolver(base, b"wav")

    result = await resolve(_event())

    assert [item.source for item in result.evidence] == [
        IdentityEvidenceSource.SESSION,
        IdentityEvidenceSource.VOICE,
    ]


async def test_no_owner_credential_skips_the_speaker_and_reads_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _Harness(monkeypatch)
    harness.credential = None
    unknown = _context(ActivePersonStatus.UNKNOWN)
    resolve = transcribe_module._speaker_augmented_actor_resolver(_base(unknown), b"wav")

    first = await resolve(_event())
    second = await resolve(_event())

    assert first is unknown
    assert second is unknown
    assert harness.builds == 0
    assert harness.credential_reads == 1  # review I-2: not re-read on every call


@pytest.mark.parametrize(
    "error", [BrainMemoryError("db unavailable"), aiosqlite.OperationalError("database is locked")]
)
async def test_a_credential_read_failure_degrades_instead_of_raising(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    """Review I-2: a turn with no token used to touch no DB; it must not 500 now."""
    harness = _Harness(monkeypatch)
    harness.credential_error = error
    unknown = _context(ActivePersonStatus.UNKNOWN)
    resolve = transcribe_module._speaker_augmented_actor_resolver(_base(unknown), b"wav")

    assert await resolve(_event()) is unknown
    assert await resolve(_event()) is unknown
    assert harness.builds == 0
    assert harness.credential_reads == 1
