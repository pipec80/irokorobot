"""The capture writes when a told event happened, on a real database (Plan 0083, review gap).

A verified capture with the switch on stores the occurred days, and the search finds the unit by
them; a reader error keeps the turn in the record without days. Face and voice are doubles; the
record, the units and the search are real. Canaries only.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, Mock
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
from server.cognition.recall_cues import CueStrength, RecallCue
from server.cognition.response_plan import TextTurnPayload
from server.cognition.spoken_dates import DayWindow
from server.memory import conversation_capture, recall_search
from server.memory.conversation_capture import CaptureOutcome, capture_turn
from server.memory.declarative import upsert_entity
from server.settings import settings
import yaml

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

pytestmark = pytest.mark.integration

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "occurred_times.yaml"
_STORIES = cast("list[dict[str, object]]", yaml.safe_load(_FIXTURE.read_text(encoding="utf-8")))
_SATURDAY_STORY = str(_STORIES[0]["heard"])  # «El sábado fui a la playa con mi hermana.»
# Thursday 2026-11-12, noon in Santiago.
_AT = datetime(2026, 11, 12, 15, tzinfo=UTC)
_SATURDAY = DayWindow(start=date(2026, 11, 7), end=date(2026, 11, 7))


@pytest.fixture
async def owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "capture-occurred.db")
    monkeypatch.setattr(settings, "household_timezone", "America/Santiago")
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "conversation_record_enabled", True)
    monkeypatch.setattr(settings, "recall_enabled", True)
    monkeypatch.setattr(settings, "occurred_time_enabled", True)
    monkeypatch.setattr(
        recall_search, "ollama_embed", AsyncMock(side_effect=httpx.ConnectError("offline"))
    )
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
        correlation_id=UUID(int=83),
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


async def test_a_verified_capture_stores_the_days_and_the_search_finds_them(owner: int) -> None:
    assert await _capture(owner, _SATURDAY_STORY) is CaptureOutcome.RECORDED
    assert await _rows("SELECT occurred_start, occurred_end FROM recall_units") == [
        ("2026-11-07", "2026-11-07")
    ]
    cue = RecallCue(strength=CueStrength.STRONG, query="que", window=_SATURDAY)
    found = await recall_search.search_recall(
        owner, cue, client=httpx.AsyncClient(), now=_AT + timedelta(hours=1)
    )
    assert [hit.unit.occurred for hit in found.hits] == [_SATURDAY]


async def test_a_reader_error_keeps_the_turn_in_the_record(
    owner: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        conversation_capture, "occurred_window", Mock(side_effect=RuntimeError("zzboomzz"))
    )
    assert await _capture(owner, _SATURDAY_STORY) is CaptureOutcome.RECORDED
    assert len(await _rows("SELECT id FROM conversation_records")) == 1
    assert await _rows("SELECT occurred_start FROM recall_units") == [(None,)]
