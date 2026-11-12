"""Searching recall units by when a told event happened (Plan 0083 Task 6, D-9).

Canary rows only; the embedding model is a double.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from server.cognition.recall_cues import CueStrength, RecallCue
from server.cognition.spoken_dates import DayWindow
from server.memory import recall_search, recall_store
from server.memory.conversation_types import RecordedTurn, TurnVerdict
from server.memory.declarative import upsert_entity
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_DIMENSIONS = 768
_NOW = datetime(2026, 11, 12, 15, tzinfo=UTC)
_FUTURE = "2027-11-03T10:00:00.000000+00:00"
_SATURDAY = DayWindow(start=date(2026, 11, 7), end=date(2026, 11, 7))
_TODAY = DayWindow(start=date(2026, 11, 12), end=date(2026, 11, 12))


@pytest.fixture
async def owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "recall-occurred.db")
    monkeypatch.setattr(settings, "household_timezone", "America/Santiago")
    monkeypatch.setattr(settings, "recall_max_distance", 0.30)
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "recall_enabled", True)
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        yield await upsert_entity(name="Canary Owner", type="person")
    finally:
        await db.close_db()
        db._conn = None


@pytest.fixture(autouse=True)
def embed(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    values = [0.0] * _DIMENSIONS
    values[0] = 1.0
    double = AsyncMock(return_value=values)
    monkeypatch.setattr(recall_search, "ollama_embed", double)
    return double


async def _saturday_story(owner: int) -> int:
    async with db.transaction() as conn:
        cursor = await conn.execute(
            "INSERT INTO conversation_records (owner_entity_id, started_at, last_turn_at, "
            "closed_at, expires_at) VALUES (?, 't', 't', 't', ?)",
            (owner, _FUTURE),
        )
        record_id = int(cursor.lastrowid or 0)
        await cursor.close()
        turn = RecordedTurn(
            at=_NOW, heard="el sabado fui a la playa", said="ok", voice=TurnVerdict.VERIFIED,
            correlation_id=uuid4(),
        )  # fmt: skip
        return await recall_store.insert_turn_unit(
            conn, record_id=record_id, owner_entity_id=owner, turn=turn, occurred=_SATURDAY
        )


async def _search(owner: int, query: str, window: DayWindow) -> list[int]:
    cue = RecallCue(strength=CueStrength.STRONG, query=query, window=window)
    found = await recall_search.search_recall(owner, cue, client=httpx.AsyncClient(), now=_NOW)
    return [hit.unit.id for hit in found.hits]


@pytest.mark.parametrize("query", ["que", "playa"])
async def test_the_search_passes_the_days(
    owner: int, monkeypatch: pytest.MonkeyPatch, query: str
) -> None:
    unit = await _saturday_story(owner)

    monkeypatch.setattr(settings, "occurred_time_enabled", True)
    assert await _search(owner, query, _SATURDAY) == [unit]
    assert await _search(owner, query, _TODAY) == []

    monkeypatch.setattr(settings, "occurred_time_enabled", False)
    assert await _search(owner, query, _SATURDAY) == []
    assert await _search(owner, query, _TODAY) == [unit]


async def test_the_hits_carry_the_interval_only_with_the_switch(
    owner: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _saturday_story(owner)
    cue = RecallCue(strength=CueStrength.STRONG, query="playa", window=None)

    monkeypatch.setattr(settings, "occurred_time_enabled", True)
    on = await recall_search.search_recall(owner, cue, client=httpx.AsyncClient(), now=_NOW)
    assert [hit.unit.occurred for hit in on.hits] == [_SATURDAY]

    monkeypatch.setattr(settings, "occurred_time_enabled", False)
    off = await recall_search.search_recall(owner, cue, client=httpx.AsyncClient(), now=_NOW)
    assert [hit.unit.occurred for hit in off.hits] == [None]
