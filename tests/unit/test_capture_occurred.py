"""The capture writes when a told event happened (Plan 0083 Task 7, D-7 and D-14).

The words come from ``tests/fixtures/occurred_times.yaml``; canaries only.
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
from server.cognition.response_plan import TextTurnPayload
from server.cognition.spoken_dates import DayWindow
from server.memory import conversation_capture
from server.memory.conversation_capture import CaptureOutcome, capture_turn
from server.settings import settings
import yaml

if TYPE_CHECKING:
    from server.memory.conversation_types import RecordedTurn

pytestmark = pytest.mark.unit

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "occurred_times.yaml"
_CASES = cast("list[dict[str, object]]", yaml.safe_load(_FIXTURE.read_text(encoding="utf-8")))
_SATURDAY_STORY = str(_CASES[0]["heard"])  # «El sábado fui a la playa con mi hermana.»
_YESTERDAY_STORY = "Ayer fui al cine."
_QUESTIONS = cast(
    "list[dict[str, object]]",
    yaml.safe_load((_FIXTURE.parent / "recall_cues_occurred.yaml").read_text(encoding="utf-8")),
)
_WHAT_YESTERDAY = str(_QUESTIONS[3]["message"])  # «¿Qué hice ayer?»
_NOW = datetime(2026, 11, 12, 15, tzinfo=UTC)
_OWNER = 7


def _event() -> CognitiveEvent[TextTurnPayload]:
    return CognitiveEvent(
        event_id=UUID(int=1),
        schema_version=1,
        event_type="text.turn",
        occurred_at=_NOW,
        recorded_at=_NOW,
        source="audio.transcribe",
        correlation_id=UUID(int=83),
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
    monkeypatch.setattr(settings, "recall_enabled", True)
    monkeypatch.setattr(settings, "household_timezone", "America/Santiago")
    monkeypatch.setattr(settings, "occurred_time_enabled", False)


@pytest.fixture
def inserted(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """The unit writer, reached through a fake append that runs the indexer."""
    insert = AsyncMock(return_value=5)
    monkeypatch.setattr(conversation_capture, "insert_turn_unit", insert)

    async def append(turn: RecordedTurn, *, index: object = None, **_: object) -> int:
        if index is not None:
            await index(None, 1, turn)  # type: ignore[operator]  # the indexer seam
        return 1

    monkeypatch.setattr(conversation_capture, "append_turn", append)
    return insert


async def _capture(heard: str, *, at: datetime = _NOW) -> CaptureOutcome:
    face = _face()
    return await capture_turn(
        heard,
        "zzrobotzz",
        face,
        wav_bytes=b"RIFF-canary",
        event=_event(),
        at=at,
        verify=AsyncMock(return_value=face),
        owner=AsyncMock(return_value=_OWNER),
        consented=AsyncMock(return_value=True),
        clock=lambda: _NOW,
    )


def _occurred(insert: AsyncMock) -> object:
    assert insert.await_args is not None
    return insert.await_args.kwargs.get("occurred")


async def test_the_capture_writes_the_interval_with_the_switch(
    inserted: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert await _capture(_SATURDAY_STORY) is CaptureOutcome.RECORDED
    assert _occurred(inserted) is None

    monkeypatch.setattr(settings, "occurred_time_enabled", True)
    assert await _capture(_SATURDAY_STORY) is CaptureOutcome.RECORDED
    assert _occurred(inserted) == DayWindow(start=date(2026, 11, 7), end=date(2026, 11, 7))


async def test_the_household_day_not_utc(
    inserted: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review focus 3: 02:30 UTC on the 13th is 23:30 of the 12th in Santiago."""
    monkeypatch.setattr(settings, "occurred_time_enabled", True)
    late = datetime(2026, 11, 13, 2, 30, tzinfo=UTC)
    await _capture(_YESTERDAY_STORY, at=late)
    assert _occurred(inserted) == DayWindow(start=date(2026, 11, 11), end=date(2026, 11, 11))


async def test_an_error_in_the_reader_keeps_the_turn_without_an_interval(
    inserted: AsyncMock, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A reader bug never costs the record its turn (ADR 0027): the unit is kept with no days."""
    monkeypatch.setattr(settings, "occurred_time_enabled", True)
    monkeypatch.setattr(
        conversation_capture, "occurred_window", Mock(side_effect=RuntimeError("zzboomzz"))
    )
    with caplog.at_level(logging.INFO):
        assert await _capture(_SATURDAY_STORY) is CaptureOutcome.RECORDED
    assert _occurred(inserted) is None
    [warning] = [
        r for r in caplog.records if getattr(r, "event", "") == "conversation.occurred_error"
    ]
    assert warning.levelno == logging.WARNING
    assert all(
        "zzboomzz" not in r.getMessage() and "playa" not in r.getMessage() for r in caplog.records
    )


async def test_a_question_turn_reads_no_time(
    inserted: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The interval is read only for a turn that becomes a unit, never for a recall question."""
    monkeypatch.setattr(settings, "occurred_time_enabled", True)
    reader = Mock(return_value=None)
    monkeypatch.setattr(conversation_capture, "occurred_window", reader)
    assert await _capture(_WHAT_YESTERDAY) is CaptureOutcome.RECORDED
    reader.assert_not_called()
    inserted.assert_not_awaited()


@pytest.mark.parametrize("switch", [False, True])
async def test_the_log_line_says_whether_the_unit_got_an_interval(
    inserted: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    *,
    switch: bool,
) -> None:
    del inserted
    monkeypatch.setattr(settings, "occurred_time_enabled", switch)
    with caplog.at_level(logging.INFO):
        await _capture(_SATURDAY_STORY)
    [line] = [r for r in caplog.records if getattr(r, "event", "") == "conversation.capture"]
    assert hasattr(line, "occurred") is switch
    if switch:
        assert line.occurred is True  # type: ignore[attr-defined]  # a log extra
    assert all("2026" not in record.getMessage() for record in caplog.records)
    assert all("playa" not in record.getMessage() for record in caplog.records)
