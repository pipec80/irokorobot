"""Unit tests for capturing a spoken exchange and its voice verdict (Plan 0076, ADR 0027)."""

from datetime import UTC, datetime, timedelta
import logging
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from server.cognition.identity import (
    ActivePersonContext,
    HouseholdRole,
    IdentityEvidence,
    IdentityEvidenceSource,
    PersonRecord,
    resolve_active_person,
)
from server.cognition.models import CognitiveEvent, Confidence, ConfidenceBasis
from server.cognition.response_plan import TextTurnPayload
from server.memory import conversation_capture
from server.memory.conversation_capture import CaptureOutcome, capture_turn, turn_verdict
from server.memory.conversation_types import RecordedTurn, TurnVerdict
from server.settings import settings

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 10, 29, 10, 0, tzinfo=UTC)
_OWNER = 7
_OTHER = 8
_WAV = b"RIFF-canary"
_CANARY_HEARD = "Zeta me contó un secreto"
_CANARY_SAID = "Qué interesante, Zeta"


def _event() -> CognitiveEvent[TextTurnPayload]:
    return CognitiveEvent(
        event_id=UUID(int=1),
        schema_version=1,
        event_type="text.turn",
        occurred_at=_NOW,
        recorded_at=_NOW,
        source="audio.transcribe",
        correlation_id=UUID(int=76),
        causation_id=None,
        subject_id=None,
        payload=TextTurnPayload(message="canary", conversation_id="canary-scope"),
    )


def _actor(source: IdentityEvidenceSource, person_id: int = _OWNER) -> ActivePersonContext:
    token = source is IdentityEvidenceSource.LOCAL_UNLOCK
    person = PersonRecord(person_id=person_id, display_name="Canary", entity_type="person")
    evidence = IdentityEvidence(
        evidence_id=uuid4(),
        source=source,
        candidate_person_id=person_id,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False),
        observed_at=_NOW - timedelta(seconds=1),
        reference="canary",
        expires_at=_NOW + timedelta(minutes=5) if token else None,
        grant_scope="personal_protected_read" if token else None,
        grant_spent=token,
    )
    return resolve_active_person(
        evidence=(evidence,),
        lookup_person=lambda pid: person if pid == person_id else None,
        lookup_role=lambda _pid: HouseholdRole.OWNER,
        clock=lambda: _NOW,
    )


@pytest.fixture(autouse=True)
def _record_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "conversation_record_enabled", True)


@pytest.fixture
def appended(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    append = AsyncMock(return_value=1)
    monkeypatch.setattr(conversation_capture, "append_turn", append)
    return append


async def _verdict(actor: ActivePersonContext | None, verify: AsyncMock) -> TurnVerdict:
    return await turn_verdict(actor, owner_id=_OWNER, wav_bytes=_WAV, event=_event(), verify=verify)


async def _capture(
    actor: ActivePersonContext | None,
    *,
    verify: AsyncMock | None = None,
    owner: AsyncMock | None = None,
    consented: AsyncMock | None = None,
) -> CaptureOutcome:
    return await capture_turn(
        _CANARY_HEARD,
        _CANARY_SAID,
        actor,
        wav_bytes=_WAV,
        event=_event(),
        at=_NOW,
        verify=verify or AsyncMock(return_value=None),
        owner=owner or AsyncMock(return_value=_OWNER),
        consented=consented or AsyncMock(return_value=True),
        clock=lambda: _NOW,
    )


async def test_no_actor_is_not_checked_and_the_voice_is_never_computed() -> None:
    verify = AsyncMock()

    assert await _verdict(None, verify) is TurnVerdict.NOT_CHECKED
    verify.assert_not_awaited()


@pytest.mark.parametrize(
    "actor",
    [
        _actor(IdentityEvidenceSource.FACE, _OTHER),
        _actor(IdentityEvidenceSource.LOCAL_UNLOCK),
        resolve_active_person(evidence=(), lookup_person=lambda _pid: None, clock=lambda: _NOW),
    ],
    ids=["another-person", "token", "unknown"],
)
async def test_anyone_but_the_owner_face_is_not_owner_and_the_voice_is_never_computed(
    actor: ActivePersonContext,
) -> None:
    verify = AsyncMock()

    assert await _verdict(actor, verify) is TurnVerdict.NOT_OWNER
    verify.assert_not_awaited()


async def test_the_owner_face_with_a_verified_voice_is_verified() -> None:
    face = _actor(IdentityEvidenceSource.FACE)
    verify = AsyncMock(return_value=face)

    assert await _verdict(face, verify) is TurnVerdict.VERIFIED
    verify.assert_awaited_once()
    assert verify.await_args is not None
    assert verify.await_args.kwargs["wav_bytes"] == _WAV


async def test_the_owner_face_with_an_unverified_voice_is_not_verified() -> None:
    face = _actor(IdentityEvidenceSource.FACE)

    assert await _verdict(face, AsyncMock(return_value=None)) is TurnVerdict.NOT_VERIFIED


async def test_a_capture_appends_the_bounded_exchange_with_its_verdict(appended: AsyncMock) -> None:
    face = _actor(IdentityEvidenceSource.FACE)

    outcome = await _capture(face, verify=AsyncMock(return_value=face))

    assert outcome is CaptureOutcome.RECORDED
    turn: RecordedTurn = appended.await_args.args[0]
    assert (turn.heard, turn.said, turn.voice) == (
        _CANARY_HEARD,
        _CANARY_SAID,
        TurnVerdict.VERIFIED,
    )
    assert turn.correlation_id == UUID(int=76)
    assert appended.await_args.kwargs["owner_entity_id"] == _OWNER


@pytest.mark.parametrize("switch", ["memory_enabled", "conversation_record_enabled"])
async def test_a_switch_off_writes_nothing_and_reads_no_owner(
    monkeypatch: pytest.MonkeyPatch, appended: AsyncMock, switch: str
) -> None:
    monkeypatch.setattr(settings, switch, False)
    owner = AsyncMock(return_value=_OWNER)

    assert await _capture(None, owner=owner) is CaptureOutcome.DISABLED
    owner.assert_not_awaited()
    appended.assert_not_awaited()


async def test_no_consent_writes_nothing(appended: AsyncMock) -> None:
    outcome = await _capture(None, consented=AsyncMock(return_value=False))

    assert outcome is CaptureOutcome.NO_CONSENT
    appended.assert_not_awaited()


async def test_no_owner_writes_nothing(appended: AsyncMock) -> None:
    assert await _capture(None, owner=AsyncMock(return_value=None)) is CaptureOutcome.NO_OWNER
    appended.assert_not_awaited()


async def test_a_failing_append_is_failed_and_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        conversation_capture, "append_turn", AsyncMock(side_effect=RuntimeError(_CANARY_HEARD))
    )

    assert await _capture(None) is CaptureOutcome.FAILED


async def test_a_failing_voice_check_is_failed_and_never_raises(appended: AsyncMock) -> None:
    face = _actor(IdentityEvidenceSource.FACE)

    outcome = await _capture(face, verify=AsyncMock(side_effect=RuntimeError("backend")))

    assert outcome is CaptureOutcome.FAILED
    appended.assert_not_awaited()


async def test_the_log_carries_no_text(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(
        conversation_capture, "append_turn", AsyncMock(side_effect=RuntimeError(_CANARY_HEARD))
    )

    with caplog.at_level(logging.DEBUG):
        await _capture(None)
        monkeypatch.setattr(conversation_capture, "append_turn", AsyncMock(return_value=1))
        await _capture(None)

    assert "Zeta" not in caplog.text
    assert all("Zeta" not in str(record.__dict__) for record in caplog.records)
