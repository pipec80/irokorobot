"""The capture keeps a pending topic on a real database, and the job names it (Plan 0084 Task 4).

Face, voice and the model are doubles; the record, the topics and the job are real. Canaries only.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import logging
from pathlib import Path
import sqlite3
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
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
from server.memory import conversation_jobs, pending_capture, pending_store
from server.memory.conversation_capture import CaptureOutcome, capture_turn
from server.memory.declarative import upsert_entity
from server.settings import settings
import yaml

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

pytestmark = pytest.mark.integration

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "pending_capture_cases.yaml"
_CASES = cast("list[dict[str, object]]", yaml.safe_load(_FIXTURE.read_text(encoding="utf-8")))
_BANK = str(_CASES[0]["heard"])
_TIRED = next(str(case["heard"]) for case in _CASES if case["outcome"] == "no_verb")
# Thursday 2026-11-12, noon in Santiago.
_AT = datetime(2026, 11, 12, 15, tzinfo=UTC)


@pytest.fixture
async def owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "capture-pending.db")
    monkeypatch.setattr(settings, "household_timezone", "America/Santiago")
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "conversation_record_enabled", True)
    monkeypatch.setattr(settings, "conversation_episodes_enabled", False)
    monkeypatch.setattr(settings, "recall_enabled", False)
    monkeypatch.setattr(settings, "pending_topics_enabled", True)
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        yield await upsert_entity(name="Canary Owner", type="person")
    finally:
        await db.close_db()
        db._conn = None


def _face(owner_id: int) -> ActivePersonContext:
    person = PersonRecord(person_id=owner_id, display_name="Canary", entity_type="person")
    evidence = IdentityEvidence(
        evidence_id=uuid4(),
        source=IdentityEvidenceSource.FACE,
        candidate_person_id=owner_id,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False),
        observed_at=_AT - timedelta(seconds=1),
        reference="canary",
    )
    return resolve_active_person(
        evidence=(evidence,),
        lookup_person=lambda pid: person if pid == owner_id else None,
        lookup_role=lambda _pid: HouseholdRole.OWNER,
        clock=lambda: _AT,
    )


def _event() -> CognitiveEvent[TextTurnPayload]:
    return CognitiveEvent(
        event_id=UUID(int=1),
        schema_version=1,
        event_type="text.turn",
        occurred_at=_AT,
        recorded_at=_AT,
        source="audio.transcribe",
        correlation_id=UUID(int=84),
        causation_id=None,
        subject_id=None,
        payload=TextTurnPayload(message="canary", conversation_id="canary-scope"),
    )


async def _capture(owner_id: int, heard: str) -> CaptureOutcome:
    face = _face(owner_id)
    return await capture_turn(
        heard,
        "zzrobotzz",
        face,
        wav_bytes=b"RIFF-canary",
        event=_event(),
        at=_AT,
        verify=AsyncMock(return_value=face),
        owner=AsyncMock(return_value=owner_id),
        consented=AsyncMock(return_value=True),
        clock=lambda: _AT,
    )


async def _rows(sql: str) -> list[tuple[object, ...]]:
    cursor = await db.get_conn().execute(sql)
    rows = [tuple(row) for row in await cursor.fetchall()]
    await cursor.close()
    return rows


async def test_a_verified_announcement_is_kept_and_named_by_the_job(
    owner: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert await _capture(owner, _BANK) is CaptureOutcome.RECORDED
    assert await _rows(
        "SELECT said_day, due_day, heard, topic, state, sensitivity FROM pending_topics"
    ) == [("2026-11-12", "2026-11-13", _BANK, None, "unnamed", "normal")]

    monkeypatch.setattr(conversation_jobs, "name_topic", AsyncMock(return_value="el banco"))
    # Past the idle time the record closes, and the job may use the model.
    async with httpx.AsyncClient() as client:
        await conversation_jobs.run_once(client, _AT + timedelta(minutes=10))

    assert await _rows("SELECT heard, topic, state FROM pending_topics") == [
        (None, "el banco", "open")
    ]


async def test_the_topic_goes_with_its_record(owner: int) -> None:
    await _capture(owner, _BANK)
    await db.get_conn().execute("DELETE FROM conversation_records")
    assert await _rows("SELECT id FROM pending_topics") == []


async def test_a_turn_that_is_no_announcement_is_recorded_without_a_topic(owner: int) -> None:
    assert await _capture(owner, _TIRED) is CaptureOutcome.RECORDED
    assert len(await _rows("SELECT id FROM conversation_records")) == 1
    assert await _rows("SELECT id FROM pending_topics") == []


async def test_the_job_expires_by_the_household_day_near_midnight(owner: int) -> None:
    """02:30Z on the 13th is still the 12th in Santiago: a topic due on the 10th survives."""
    await _capture(owner, _BANK)
    record = (await _rows("SELECT id FROM conversation_records"))[0][0]
    ids = {}
    for due in (date(2026, 11, 9), date(2026, 11, 10)):
        async with db.transaction() as conn:
            ids[due] = await pending_store.insert_unnamed(
                conn,
                owner_entity_id=owner,
                record_id=int(str(record)),
                correlation_id=uuid4(),
                said_day=due - timedelta(days=1),
                due_day=due,
                heard="zzheardzz",
                sensitivity="normal",
                now=_AT,
            )
        assert await pending_store.set_topic(ids[due], "el banco")
    await db.get_conn().execute("DELETE FROM pending_topics WHERE due_day = '2026-11-13'")
    await db.get_conn().commit()

    async with httpx.AsyncClient() as client:
        await conversation_jobs.run_once(client, datetime(2026, 11, 13, 2, 30, tzinfo=UTC))

    assert await _rows("SELECT due_day FROM pending_topics") == [("2026-11-10",)]


async def test_a_failing_topic_insert_rolls_the_turn_back_and_logs_no_text(
    owner: int, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The topic is written inside the append, like the recall unit: both or neither (pinned)."""
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(
        pending_capture, "insert_unnamed", AsyncMock(side_effect=sqlite3.IntegrityError("zz banco"))
    )

    assert await _capture(owner, _BANK) is CaptureOutcome.FAILED

    assert await _rows("SELECT id FROM conversation_records") == []
    assert "banco" not in caplog.text


async def test_a_turn_longer_than_the_record_cap_keeps_its_topic(owner: int) -> None:
    long_heard = _BANK + " y" * 1500

    assert await _capture(owner, long_heard) is CaptureOutcome.RECORDED

    assert await _rows("SELECT length(heard), state FROM pending_topics") == [(2000, "unnamed")]
