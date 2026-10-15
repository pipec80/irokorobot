"""Unit tests for the face-and-voice actor (ADR 0021 decision 3): never a face alone, never a token."""

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest
from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    HouseholdRole,
    IdentityAssurance,
    IdentityEvidence,
    IdentityEvidenceSource,
    PersonRecord,
    resolve_active_person,
)
from server.cognition.models import CognitiveEvent, Confidence, ConfidenceBasis
from server.cognition.response_plan import TextTurnPayload
from server.cognition.speaker_authentication import SpeakerRequestResolver, SpeakerVerdict
from server.cognition.strong_actor import (
    is_face_actor,
    is_face_and_voice_actor,
    verify_face_and_voice,
)
from server.settings import settings

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)
_OWNER_ID = 7
_OTHER_ID = 8
_WAV = b"RIFF-canary-clip"


def _evidence(
    source: IdentityEvidenceSource, person_id: int = _OWNER_ID, *, scope: str | None = None
) -> IdentityEvidence:
    return IdentityEvidence(
        evidence_id=uuid4(),
        source=source,
        candidate_person_id=person_id,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False),
        observed_at=_NOW - timedelta(seconds=1),
        reference="canary",
        grant_scope=scope,
    )


def _resolve(*items: IdentityEvidence) -> ActivePersonContext:
    people = {
        _OWNER_ID: PersonRecord(person_id=_OWNER_ID, display_name="Canary", entity_type="person"),
        _OTHER_ID: PersonRecord(person_id=_OTHER_ID, display_name="Other", entity_type="person"),
    }
    return resolve_active_person(
        evidence=tuple(items),
        lookup_person=people.get,
        lookup_role=lambda _pid: HouseholdRole.OWNER,
        clock=lambda: _NOW,
    )


def _event() -> CognitiveEvent[TextTurnPayload]:
    return CognitiveEvent(
        event_id=uuid4(),
        schema_version=1,
        event_type="text.turn",
        occurred_at=_NOW,
        recorded_at=_NOW,
        source="audio.transcribe",
        correlation_id=UUID(int=9),
        causation_id=None,
        subject_id=None,
        payload=TextTurnPayload(message="canary", conversation_id="canary"),
    )


def _face_actor() -> ActivePersonContext:
    return _resolve(_evidence(IdentityEvidenceSource.FACE))


class _Speaker:
    def __init__(self, verdict: SpeakerVerdict, *items: IdentityEvidence) -> None:
        self.last_verdict = verdict
        self._items = items

    async def resolve_actor(self, event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
        return ActivePersonContext(
            person_id=None,
            display_name=None,
            status=ActivePersonStatus.UNKNOWN,
            confidence=Confidence(
                score=0.0, basis=ConfidenceBasis.NOT_APPLICABLE, calibrated=False
            ),
            role=HouseholdRole.UNKNOWN,
            evidence=self._items,
            resolved_at=event.occurred_at,
        )


class _Builder:
    """Records how the speaker resolver was built and hands back a scripted one."""

    def __init__(self, speaker: _Speaker) -> None:
        self.speaker = speaker
        self.calls: list[tuple[bytes, int]] = []

    def __call__(self, wav_bytes: bytes, owner_person_id: int) -> SpeakerRequestResolver:
        self.calls.append((wav_bytes, owner_person_id))
        return cast("SpeakerRequestResolver", self.speaker)


@pytest.fixture(autouse=True)
def _speaker_evidence_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "speaker_authentication_enabled", True)


def _verified() -> _Builder:
    return _Builder(_Speaker(SpeakerVerdict.VERIFIED, _evidence(IdentityEvidenceSource.VOICE)))


def test_a_face_alone_is_a_face_actor_and_not_a_face_and_voice_actor() -> None:
    actor = _face_actor()

    assert is_face_actor(actor)
    assert not is_face_and_voice_actor(actor)
    assert actor.assurance is IdentityAssurance.BASIC


def test_face_and_voice_of_the_same_person_is_the_composite() -> None:
    actor = _resolve(
        _evidence(IdentityEvidenceSource.FACE), _evidence(IdentityEvidenceSource.VOICE)
    )

    assert actor.assurance is IdentityAssurance.STRONG
    assert is_face_and_voice_actor(actor)


def test_a_token_reaches_strong_but_is_neither_face_actor_nor_composite() -> None:
    token = _resolve(
        _evidence(IdentityEvidenceSource.LOCAL_UNLOCK, scope="personal_protected_read")
    )

    assert token.assurance is IdentityAssurance.STRONG
    assert not is_face_actor(token)
    assert not is_face_and_voice_actor(token)


def test_a_token_next_to_face_and_voice_still_refuses_the_composite() -> None:
    actor = _resolve(
        _evidence(IdentityEvidenceSource.FACE),
        _evidence(IdentityEvidenceSource.VOICE),
        _evidence(IdentityEvidenceSource.LOCAL_UNLOCK, scope="personal_protected_read"),
    )

    assert actor.assurance is IdentityAssurance.STRONG
    assert not is_face_actor(actor)
    assert not is_face_and_voice_actor(actor)


def test_a_manual_session_is_not_a_face_actor() -> None:
    assert not is_face_actor(_resolve(_evidence(IdentityEvidenceSource.MANUAL)))


def test_voice_alone_and_an_unknown_actor_are_not_actors_at_all() -> None:
    voice_only = _resolve(_evidence(IdentityEvidenceSource.VOICE))
    unknown = _resolve()

    assert voice_only.status is ActivePersonStatus.PROBABLE
    for actor in (voice_only, unknown):
        assert not is_face_actor(actor)
        assert not is_face_and_voice_actor(actor)


def test_a_voice_that_names_another_person_is_not_the_composite() -> None:
    actor = _resolve(
        _evidence(IdentityEvidenceSource.FACE, _OWNER_ID),
        _evidence(IdentityEvidenceSource.VOICE, _OTHER_ID),
    )

    assert actor.status is ActivePersonStatus.AMBIGUOUS
    assert not is_face_and_voice_actor(actor)


async def test_a_verified_voice_raises_the_face_actor_to_the_composite() -> None:
    builder = _verified()

    fused = await verify_face_and_voice(
        _face_actor(), wav_bytes=_WAV, event=_event(), build_speaker=builder
    )

    assert fused is not None
    assert is_face_and_voice_actor(fused)
    assert fused.person_id == _OWNER_ID
    assert builder.calls == [(_WAV, _OWNER_ID)]


@pytest.mark.parametrize("verdict", [SpeakerVerdict.UNKNOWN, SpeakerVerdict.UNAVAILABLE])
async def test_a_voice_that_is_not_verified_gives_nothing(verdict: SpeakerVerdict) -> None:
    builder = _Builder(_Speaker(verdict, _evidence(IdentityEvidenceSource.VOICE)))

    assert (
        await verify_face_and_voice(
            _face_actor(), wav_bytes=_WAV, event=_event(), build_speaker=builder
        )
        is None
    )


async def test_verified_evidence_of_another_person_gives_nothing() -> None:
    builder = _Builder(
        _Speaker(SpeakerVerdict.VERIFIED, _evidence(IdentityEvidenceSource.VOICE, _OTHER_ID))
    )

    assert (
        await verify_face_and_voice(
            _face_actor(), wav_bytes=_WAV, event=_event(), build_speaker=builder
        )
        is None
    )


@pytest.mark.parametrize("wav", [None, b""])
async def test_no_clip_means_no_voice_check_at_all(wav: bytes | None) -> None:
    builder = _verified()

    result = await verify_face_and_voice(
        _face_actor(), wav_bytes=wav, event=_event(), build_speaker=builder
    )

    assert result is None
    assert builder.calls == []


async def test_speaker_evidence_off_means_no_voice_check_at_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "speaker_authentication_enabled", False)
    builder = _verified()

    result = await verify_face_and_voice(
        _face_actor(), wav_bytes=_WAV, event=_event(), build_speaker=builder
    )

    assert result is None
    assert builder.calls == []


async def test_a_token_actor_never_reaches_the_voice_check() -> None:
    builder = _verified()
    token = _resolve(
        _evidence(IdentityEvidenceSource.LOCAL_UNLOCK, scope="personal_protected_read")
    )

    result = await verify_face_and_voice(
        token, wav_bytes=_WAV, event=_event(), build_speaker=builder
    )

    assert result is None
    assert builder.calls == []
