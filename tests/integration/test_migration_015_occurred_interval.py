"""Migration 015: when a told event happened, on the recall units (Plan 0083 Task 3, D-8).

ADR 0037 decision 3. Two nullable local-day columns and their CHECK; canary rows only.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
import sqlite3
from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from server.cognition.spoken_dates import DayWindow
from server.memory import recall_store
from server.memory.conversation_types import RecordedTurn, TurnVerdict
from server.memory.declarative import upsert_entity
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_T = "2026-11-03T10:00:00.000000+00:00"
_LATER = "2027-11-03T10:00:00.000000+00:00"
_CID = UUID("00000000-0000-0000-0000-0000000000bb")
_LAST_YEAR = DayWindow(start=date(2025, 1, 1), end=date(2025, 12, 31))


async def _open(monkeypatch: pytest.MonkeyPatch, path: Path, *, up_to: int | None = None) -> None:
    monkeypatch.setattr(settings, "brain_db_path", path)
    if up_to is not None:
        monkeypatch.setattr(db, "_MIGRATIONS", tuple(m for m in db._MIGRATIONS if m[0] <= up_to))
    db._conn = None
    await db.open_db()
    await db.run_migrations()


@pytest.fixture
async def owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    try:
        await _open(monkeypatch, tmp_path / "v15.db")
        yield await upsert_entity(name="Canary Owner", type="person")
    finally:
        await db.close_db()
        db._conn = None


async def _scalar(sql: str, *params: object) -> object:
    cursor = await db.get_conn().execute(sql, params)
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    return row[0]


async def _record(owner_id: int) -> int:
    cursor = await db.get_conn().execute(
        "INSERT INTO conversation_records (owner_entity_id, started_at, last_turn_at, closed_at, "
        "expires_at) VALUES (?, ?, ?, ?, ?)",
        (owner_id, _T, _T, _T, _LATER),
    )
    record_id = int(cursor.lastrowid or 0)
    await cursor.close()
    await db.get_conn().commit()
    return record_id


def _turn() -> RecordedTurn:
    return RecordedTurn(
        at=datetime(2026, 11, 3, 10, tzinfo=UTC),
        heard="el año pasado fui a la nieve",
        said="zzrobotzz",
        voice=TurnVerdict.VERIFIED,
        correlation_id=_CID,
    )


async def test_migration_015_adds_two_empty_columns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "upgrade-v14.db"
    try:
        await _open(monkeypatch, path, up_to=14)
        owner_id = await upsert_entity(name="Canary Owner", type="person")
        record_id = await _record(owner_id)
        await db.get_conn().execute(
            "INSERT INTO recall_units (owner_entity_id, source_record_id, kind, body, said_at, "
            "visibility, sensitivity, correlation_id) "
            "VALUES (?, ?, 'turn', 'fuimos al cerro con Zeta', ?, 'personal', 'normal', 'cid')",
            (owner_id, record_id, _T),
        )
        await db.get_conn().commit()
        await db.close_db()
        monkeypatch.undo()
        await _open(monkeypatch, path)

        assert await _scalar("PRAGMA user_version") == 15
        assert db.latest_schema_version() == 15
        assert (
            await _scalar(
                "SELECT count(*) FROM recall_units "
                "WHERE occurred_start IS NULL AND occurred_end IS NULL"
            )
            == 1
        )
        assert (
            await _scalar(
                "SELECT count(*) FROM recall_units_fts WHERE recall_units_fts MATCH 'cerro'"
            )
            == 1
        )
        assert (
            await _scalar(
                "SELECT count(*) FROM sqlite_master WHERE name = 'recall_units_owner_occurred_idx'"
            )
            == 1
        )
    finally:
        await db.close_db()
        db._conn = None


@pytest.mark.parametrize(
    "start,end",
    [("2025-02-01", None), (None, "2025-02-01"), ("2025-02-01", "2025-01-01"),
     ("2025-13-01", "2025-13-02"), ("2025-2-1", "2025-2-2")],
)  # fmt: skip
async def test_the_check_refuses_a_bad_interval(
    owner: int, start: str | None, end: str | None
) -> None:
    record_id = await _record(owner)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        await db.get_conn().execute(
            "INSERT INTO recall_units (owner_entity_id, source_record_id, kind, body, said_at, "
            "visibility, sensitivity, correlation_id, occurred_start, occurred_end) "
            "VALUES (?, ?, 'turn', 'zzbodyzz', ?, 'personal', 'normal', 'cid', ?, ?)",
            (owner, record_id, _T, start, end),
        )


async def test_a_turn_unit_stores_its_interval(owner: int) -> None:
    record_id = await _record(owner)
    async with db.transaction() as conn:
        unit_id = await recall_store.insert_turn_unit(
            conn, record_id=record_id, owner_entity_id=owner, turn=_turn(), occurred=_LAST_YEAR
        )
    row = await db.get_conn().execute(
        "SELECT occurred_start, occurred_end FROM recall_units WHERE id = ?", (unit_id,)
    )
    assert tuple(await row.fetchone() or ()) == ("2025-01-01", "2025-12-31")


async def test_a_turn_unit_without_one_stores_null(owner: int) -> None:
    record_id = await _record(owner)
    async with db.transaction() as conn:
        unit_id = await recall_store.insert_turn_unit(
            conn, record_id=record_id, owner_entity_id=owner, turn=_turn()
        )
    assert await _scalar("SELECT occurred_start FROM recall_units WHERE id = ?", unit_id) is None


async def test_an_episode_unit_never_has_one(owner: int) -> None:
    record_id = await _record(owner)
    cursor = await db.get_conn().execute(
        "INSERT INTO conversation_episodes (owner_entity_id, source_record_id, visibility, "
        "sensitivity, summary, model, created_at, expires_at) "
        "VALUES (?, ?, 'personal', 'normal', 'zzsummaryzz', 'zzmodelzz', ?, ?)",
        (owner, record_id, _T, _LATER),
    )
    episode_id = int(cursor.lastrowid or 0)
    await db.get_conn().commit()
    async with db.transaction() as conn:
        unit_id = await recall_store.insert_episode_unit(
            conn,
            record_id=record_id,
            episode_id=episode_id,
            owner_entity_id=owner,
            summary="zzsummaryzz",
            sensitivity="normal",
            said_at=_T,
        )
    assert await _scalar("SELECT occurred_start FROM recall_units WHERE id = ?", unit_id) is None


async def test_a_deleted_record_takes_its_interval_along(owner: int) -> None:
    record_id = await _record(owner)
    async with db.transaction() as conn:
        await recall_store.insert_turn_unit(
            conn, record_id=record_id, owner_entity_id=owner, turn=_turn(), occurred=_LAST_YEAR
        )
    await db.get_conn().execute("DELETE FROM conversation_records WHERE id = ?", (record_id,))
    assert await _scalar("SELECT count(*) FROM recall_units") == 0


@pytest.mark.parametrize("memory", [True, False])
@pytest.mark.parametrize("recall", [True, False])
@pytest.mark.parametrize("occurred", [True, False])
def test_occurred_time_on_needs_memory_and_recall(
    monkeypatch: pytest.MonkeyPatch, *, memory: bool, recall: bool, occurred: bool
) -> None:
    monkeypatch.setattr(settings, "memory_enabled", memory)
    monkeypatch.setattr(settings, "recall_enabled", recall)
    monkeypatch.setattr(settings, "occurred_time_enabled", occurred)
    assert recall_store.occurred_time_on() is (memory and recall and occurred)
