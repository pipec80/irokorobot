"""The capture keeps an unnamed pending topic from a verified announcement (Plan 0084 Task 4).

D-2, D-3, D-7 and D-15. The words come from ``tests/fixtures/pending_announcements.yaml`` or are
canaries; the record's append is a fake that runs the hook, the store's insert a double.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import logging
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, Mock
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
from server.cognition.pending_topics import AnnouncementOutcome
from server.cognition.response_plan import TextTurnPayload
from server.memory import conversation_capture, pending_capture
from server.memory.conversation_capture import CaptureOutcome, capture_turn
from server.memory.pending_capture import KeptTopic, PendingCapture, PendingCaptureOutcome
from server.settings import settings
import yaml

if TYPE_CHECKING:
    from server.memory.conversation_types import RecordedTurn

pytestmark = pytest.mark.unit

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "pending_announcements.yaml"
_CASES = cast("list[dict[str, object]]", yaml.safe_load(_FIXTURE.read_text(encoding="utf-8")))
_BANK = str(_CASES[0]["heard"])  # «Mañana voy al banco a pagar una cuenta.»
_DOCTOR = "El jueves tengo hora con el médico."
_GATE = "Mañana tengo que cambiar la llave del portón."
_QUESTION = next(str(case["heard"]) for case in _CASES if case["outcome"] == "question")
# Thursday 2026-11-12, noon in Santiago.
_NOW = datetime(2026, 11, 12, 15, tzinfo=UTC)
_OWNER = 7
_CORRELATION = UUID(int=84)
_WORDS = ("banco", "cuenta", "medico", "médico", "llave")
_PENDING_KEYS = frozenset({"event", "outcome", "correlation_id", "error_type", "request_id"})


def _event() -> CognitiveEvent[TextTurnPayload]:
    return CognitiveEvent(
        event_id=UUID(int=1),
        schema_version=1,
        event_type="text.turn",
        occurred_at=_NOW,
        recorded_at=_NOW,
        source="audio.transcribe",
        correlation_id=_CORRELATION,
        causation_id=None,
        subject_id=None,
        payload=TextTurnPayload(message="canary", conversation_id="canary-scope"),
    )


def _face() -> ActivePersonContext:
    person = PersonRecord(person_id=_OWNER, display_name="Canary", entity_type="person")
    evidence = IdentityEvidence(
        evidence_id=uuid4(),
        source=IdentityEvidenceSource.FACE,
        candidate_person_id=_OWNER,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False),
        observed_at=_NOW - timedelta(seconds=1),
        reference="canary",
    )
    return resolve_active_person(
        evidence=(evidence,),
        lookup_person=lambda pid: person if pid == _OWNER else None,
        lookup_role=lambda _pid: HouseholdRole.OWNER,
        clock=lambda: _NOW,
    )


@pytest.fixture(autouse=True)
def _switches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "conversation_record_enabled", True)
    monkeypatch.setattr(settings, "recall_enabled", False)
    monkeypatch.setattr(settings, "household_timezone", "America/Santiago")
    monkeypatch.setattr(settings, "pending_topics_enabled", True)


@pytest.fixture
def inserted(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """The topic writer, reached through a fake append that runs the record's hook."""
    insert = AsyncMock(return_value=11)
    monkeypatch.setattr(pending_capture, "insert_unnamed", insert)

    async def append(turn: RecordedTurn, *, index: object = None, **_: object) -> int:
        if index is not None:
            await index(None, 1, turn)  # type: ignore[operator]  # the hook seam
        return 1

    monkeypatch.setattr(conversation_capture, "append_turn", append)
    return insert


async def _capture(heard: str, *, at: datetime = _NOW, verified: bool = True) -> CaptureOutcome:
    face = _face()
    return await capture_turn(
        heard,
        "zzrobotzz",
        face,
        wav_bytes=b"RIFF-canary",
        event=_event(),
        at=at,
        verify=AsyncMock(return_value=face if verified else None),
        owner=AsyncMock(return_value=_OWNER),
        consented=AsyncMock(return_value=True),
        clock=lambda: _NOW,
    )


def _pending_lines(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if str(getattr(r, "event", "")).startswith("pending.")]


def _outcomes(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [str(getattr(r, "outcome", "")) for r in _pending_lines(caplog)]


def _assert_no_text(caplog: pytest.LogCaptureFixture) -> None:
    logged = " ".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records).casefold()
    for word in _WORDS:
        assert word not in logged
    # A pending line carries closed fields only: never a day, a topic or the words.
    standard = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime", "taskName"}
    for record in _pending_lines(caplog):
        assert set(record.__dict__) - standard <= _PENDING_KEYS


async def test_a_verified_announcement_keeps_one_unnamed_topic(
    inserted: AsyncMock, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)

    assert await _capture(_BANK) is CaptureOutcome.RECORDED

    inserted.assert_awaited_once()
    assert inserted.await_args is not None
    kwargs = inserted.await_args.kwargs
    assert kwargs["owner_entity_id"] == _OWNER
    assert kwargs["record_id"] == 1
    assert kwargs["correlation_id"] == _CORRELATION
    assert kwargs["said_day"] == date(2026, 11, 12)
    assert kwargs["due_day"] == date(2026, 11, 13)
    assert kwargs["heard"] == _BANK
    assert kwargs["sensitivity"] == "normal"
    assert _outcomes(caplog) == ["kept"]
    _assert_no_text(caplog)


async def test_a_health_announcement_is_kept_as_medical(inserted: AsyncMock) -> None:
    assert await _capture(_DOCTOR) is CaptureOutcome.RECORDED
    assert inserted.await_args is not None
    assert inserted.await_args.kwargs["sensitivity"] == "medical"
    assert inserted.await_args.kwargs["due_day"] == date(2026, 11, 19)


@pytest.mark.parametrize(
    "heard, verified, outcome",
    [
        (_BANK, False, "not_verified"),
        (_QUESTION, True, "question"),
        (_GATE, True, "sensitive"),
        ("Mañana viene mi hija.", True, "no_verb"),
        ("La próxima semana voy al sur.", True, "not_single_day"),
        ("Hoy estoy cansado.", True, "no_verb"),
        ("Me gusta el mate.", True, "no_phrase"),
    ],
)
async def test_a_turn_that_is_not_an_announcement_keeps_none(
    inserted: AsyncMock,
    caplog: pytest.LogCaptureFixture,
    heard: str,
    verified: bool,
    outcome: str,
) -> None:
    caplog.set_level(logging.INFO)

    assert await _capture(heard, verified=verified) is CaptureOutcome.RECORDED

    inserted.assert_not_awaited()
    assert _outcomes(caplog) == [outcome]
    _assert_no_text(caplog)


async def test_a_turn_that_tells_nothing_keeps_none(
    inserted: AsyncMock, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(pending_capture, "tells_something", Mock(return_value=False))

    assert await _capture(_BANK) is CaptureOutcome.RECORDED

    inserted.assert_not_awaited()
    assert _outcomes(caplog) == ["question"]


async def test_the_household_day_not_utc(inserted: AsyncMock) -> None:
    # 02:30Z on the 13th is 23:30 of the 12th in Santiago: «mañana» is the 13th.
    assert await _capture(_BANK, at=datetime(2026, 11, 13, 2, 30, tzinfo=UTC)) is (
        CaptureOutcome.RECORDED
    )
    assert inserted.await_args is not None
    assert inserted.await_args.kwargs["said_day"] == date(2026, 11, 12)
    assert inserted.await_args.kwargs["due_day"] == date(2026, 11, 13)


async def test_a_reader_error_keeps_the_turn(
    inserted: AsyncMock, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(
        pending_capture, "read_announcement", Mock(side_effect=RuntimeError("zzboomzz banco"))
    )

    assert await _capture(_BANK) is CaptureOutcome.RECORDED

    inserted.assert_not_awaited()
    errors = [r for r in _pending_lines(caplog) if r.event == "pending.capture_error"]  # type: ignore[attr-defined]
    assert [getattr(r, "error_type", None) for r in errors] == ["RuntimeError"]
    assert "zzboomzz" not in caplog.text
    _assert_no_text(caplog)


@pytest.mark.parametrize("switch", ["pending_topics_enabled", "conversation_record_enabled"])
async def test_switch_off_keeps_none_and_logs_todays_lines(
    inserted: AsyncMock,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    switch: str,
) -> None:
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(settings, switch, False)

    await _capture(_BANK)

    inserted.assert_not_awaited()
    assert _pending_lines(caplog) == []


async def test_the_capture_line_is_todays_with_the_switch_on(
    inserted: AsyncMock, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    caplog.set_level(logging.INFO)
    await _capture(_BANK)
    on = [
        r.__dict__.get("outcome")
        for r in caplog.records
        if r.__dict__.get("event") == "conversation.capture"
    ]
    caplog.clear()
    monkeypatch.setattr(settings, "pending_topics_enabled", False)
    await _capture(_BANK)
    off = [
        r.__dict__.get("outcome")
        for r in caplog.records
        if r.__dict__.get("event") == "conversation.capture"
    ]
    assert on == off == [CaptureOutcome.RECORDED]


def test_every_grammar_outcome_is_a_capture_outcome() -> None:
    assert {item.value for item in AnnouncementOutcome} <= {
        item.value for item in PendingCaptureOutcome
    }


def test_a_kept_decision_hides_its_days_and_comes_with_them() -> None:
    kept = KeptTopic(said_day=date(2026, 11, 12), due_day=date(2026, 11, 13), sensitivity="normal")
    assert "2026" not in repr(PendingCapture(PendingCaptureOutcome.KEPT, kept))
    with pytest.raises(ValueError, match="kept"):
        PendingCapture(PendingCaptureOutcome.KEPT)
    with pytest.raises(ValueError, match="kept"):
        PendingCapture(PendingCaptureOutcome.SENSITIVE, kept)
