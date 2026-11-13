"""Migration 016 and the pending-topics store on a real database (Plan 0084 Task 3, D-14).

Canary rows only; the clock is passed in, never read.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import itertools
import sqlite3
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from server.memory import pending_store
from server.memory.declarative import upsert_entity
from server.memory.pending_store import PendingTopic
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_T = "2026-11-03T10:00:00.000000+00:00"
_LATER = "2027-11-03T10:00:00.000000+00:00"
_TODAY = date(2026, 11, 12)
# Noon in Santiago on _TODAY.
_NOON = datetime(2026, 11, 12, 15, tzinfo=UTC)


async def _open(monkeypatch: pytest.MonkeyPatch, path: Path, *, up_to: int | None = None) -> None:
    monkeypatch.setattr(settings, "brain_db_path", path)
    if up_to is not None:
        monkeypatch.setattr(db, "_MIGRATIONS", tuple(m for m in db._MIGRATIONS if m[0] <= up_to))
    db._conn = None
    await db.open_db()
    await db.run_migrations()


@pytest.fixture
async def owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    monkeypatch.setattr(settings, "household_timezone", "America/Santiago")
    try:
        await _open(monkeypatch, tmp_path / "v16.db")
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


async def _unnamed(
    owner_id: int,
    *,
    due_day: date,
    said_day: date | None = None,
    record_id: int | None = None,
    heard: str = "zzheardzz",
) -> int:
    record = record_id if record_id is not None else await _record(owner_id)
    async with db.transaction() as conn:
        return await pending_store.insert_unnamed(
            conn,
            owner_entity_id=owner_id,
            record_id=record,
            correlation_id=uuid4(),
            said_day=said_day or due_day - timedelta(days=1),
            due_day=due_day,
            heard=heard,
            sensitivity="normal",
            now=_NOON,
        )


async def _open_topic(owner_id: int, *, due_day: date, topic: str = "el banco") -> int:
    topic_id = await _unnamed(owner_id, due_day=due_day)
    assert await pending_store.set_topic(topic_id, topic)
    return topic_id


async def test_migration_016_adds_an_empty_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "upgrade-v15.db"
    try:
        await _open(monkeypatch, path, up_to=15)
        assert await _scalar("PRAGMA user_version") == 15
        await db.close_db()
        monkeypatch.undo()
        await _open(monkeypatch, path)

        assert await _scalar("PRAGMA user_version") == 16
        assert db.latest_schema_version() == 16
        assert await _scalar("SELECT count(*) FROM pending_topics") == 0
        for index in ("pending_topics_owner_state_due_idx", "pending_topics_record_idx"):
            assert await _scalar("SELECT count(*) FROM sqlite_master WHERE name = ?", index) == 1
    finally:
        await db.close_db()
        db._conn = None


@pytest.mark.parametrize(
    "said_day, due_day, topic, heard, state, asked_at",
    [
        ("2026-13-01", "2026-13-02", None, "zz", "unnamed", None),  # not a day
        ("2026-11-12", "2026-11-11", None, "zz", "unnamed", None),  # due before said
        ("2026-11-12", "2026-11-13", "el banco", "zz", "open", None),  # named keeps words
        ("2026-11-12", "2026-11-13", "el banco", None, "unnamed", None),  # unnamed with a topic
        ("2026-11-12", "2026-11-13", None, None, "unnamed", None),  # no words, no topic
        ("2026-11-12", "2026-11-13", "x" * 41, None, "open", None),  # topic too long
        ("2026-11-12", "2026-11-13", "el banco", None, "asked", None),  # asked without a time
        ("2026-11-12", "2026-11-13", "el banco", None, "open", _T),  # a time without asked
        ("2026-11-12", "2026-11-13", None, "zz", "expired", None),  # no such state
    ],
)
async def test_the_checks_refuse_a_bad_row(
    owner: int,
    said_day: str,
    due_day: str,
    topic: str | None,
    heard: str | None,
    state: str,
    asked_at: str | None,
) -> None:
    record_id = await _record(owner)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        await db.get_conn().execute(
            "INSERT INTO pending_topics (owner_entity_id, source_record_id, correlation_id, "
            "said_day, due_day, topic, heard, state, sensitivity, created_at, asked_at) "
            "VALUES (?, ?, 'cid', ?, ?, ?, ?, ?, 'normal', ?, ?)",
            (owner, record_id, said_day, due_day, topic, heard, state, _T, asked_at),
        )


async def test_the_sensitivity_is_normal_or_medical(owner: int) -> None:
    record_id = await _record(owner)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        await db.get_conn().execute(
            "INSERT INTO pending_topics (owner_entity_id, source_record_id, correlation_id, "
            "said_day, due_day, heard, state, sensitivity, created_at) "
            "VALUES (?, ?, 'cid', '2026-11-12', '2026-11-13', 'zz', 'unnamed', 'security', ?)",
            (owner, record_id, _T),
        )


async def test_one_topic_per_turn(owner: int) -> None:
    record_id = await _record(owner)
    correlation = UUID(int=84)
    async with db.transaction() as conn:
        await pending_store.insert_unnamed(
            conn,
            owner_entity_id=owner,
            record_id=record_id,
            correlation_id=correlation,
            said_day=_TODAY,
            due_day=_TODAY,
            heard="zz",
            sensitivity="normal",
            now=_NOON,
        )
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        async with db.transaction() as conn:
            await pending_store.insert_unnamed(
                conn,
                owner_entity_id=owner,
                record_id=record_id,
                correlation_id=correlation,
                said_day=_TODAY,
                due_day=_TODAY,
                heard="zz",
                sensitivity="normal",
                now=_NOON,
            )


async def test_a_deleted_record_takes_its_topic_along(owner: int) -> None:
    record_id = await _record(owner)
    await _unnamed(owner, due_day=_TODAY, record_id=record_id)
    await db.get_conn().execute("DELETE FROM conversation_records WHERE id = ?", (record_id,))
    assert await _scalar("SELECT count(*) FROM pending_topics") == 0


async def test_naming_clears_the_words_once(owner: int) -> None:
    topic_id = await _unnamed(owner, due_day=_TODAY, heard="Mañana voy al banco.")
    assert await pending_store.next_unnamed() == (topic_id, "Mañana voy al banco.")

    assert await pending_store.set_topic(topic_id, "el banco")
    assert not await pending_store.set_topic(topic_id, "el cine")
    assert await pending_store.next_unnamed() is None
    assert await _scalar("SELECT heard FROM pending_topics WHERE id = ?", topic_id) is None
    assert await _scalar("SELECT topic FROM pending_topics WHERE id = ?", topic_id) == "el banco"


async def test_next_unnamed_is_the_oldest_and_drop_deletes(owner: int) -> None:
    first = await _unnamed(owner, due_day=_TODAY)
    second = await _unnamed(owner, due_day=_TODAY)
    assert (await pending_store.next_unnamed() or (0,))[0] == first

    await pending_store.drop(first)

    assert (await pending_store.next_unnamed() or (0,))[0] == second


async def test_due_topic_picks_the_oldest_in_the_window(owner: int) -> None:
    await _open_topic(owner, due_day=_TODAY, topic="hoy")
    await _open_topic(owner, due_day=_TODAY - timedelta(days=3), topic="tres")
    yesterday = await _open_topic(owner, due_day=_TODAY - timedelta(days=1), topic="ayer")
    anteayer = await _open_topic(owner, due_day=_TODAY - timedelta(days=2), topic="anteayer")
    await _unnamed(owner, due_day=_TODAY - timedelta(days=2))

    picked = await pending_store.due_topic(owner, today=_TODAY)

    assert picked == PendingTopic(
        id=anteayer, topic="anteayer", due_day=_TODAY - timedelta(days=2), sensitivity="normal"
    )
    assert "anteayer" not in repr(picked)
    assert "2026" not in repr(picked)
    assert await pending_store.mark_asked(anteayer, now=_NOON)
    picked = await pending_store.due_topic(owner, today=_TODAY)
    assert picked is not None
    assert picked.id == yesterday


async def test_a_topic_due_today_or_three_days_ago_is_never_due(owner: int) -> None:
    await _open_topic(owner, due_day=_TODAY)
    await _open_topic(owner, due_day=_TODAY - timedelta(days=3))
    assert await pending_store.due_topic(owner, today=_TODAY) is None


async def test_another_owners_topic_is_never_returned(owner: int) -> None:
    other = await upsert_entity(name="Canary Other", type="person")
    topic_id = await _open_topic(other, due_day=_TODAY - timedelta(days=1))
    assert await pending_store.due_topic(owner, today=_TODAY) is None
    assert await pending_store.mark_asked(topic_id, now=_NOON)
    assert not await pending_store.asked_today(owner, today=_TODAY)


async def test_mark_asked_once_only(owner: int) -> None:
    topic_id = await _open_topic(owner, due_day=_TODAY - timedelta(days=1))
    assert await pending_store.mark_asked(topic_id, now=_NOON)
    assert not await pending_store.mark_asked(topic_id, now=_NOON)
    unnamed = await _unnamed(owner, due_day=_TODAY - timedelta(days=1))
    assert not await pending_store.mark_asked(unnamed, now=_NOON)


async def test_asked_today_is_the_household_day(owner: int) -> None:
    topic_id = await _open_topic(owner, due_day=_TODAY - timedelta(days=1))
    assert not await pending_store.asked_today(owner, today=_TODAY)
    # 01:30 UTC on the 13th is still the 12th in Santiago (UTC-3).
    assert await pending_store.mark_asked(topic_id, now=datetime(2026, 11, 13, 1, 30, tzinfo=UTC))

    assert await pending_store.asked_today(owner, today=_TODAY)
    assert not await pending_store.asked_today(owner, today=_TODAY + timedelta(days=1))


async def test_delete_expired_counts(owner: int) -> None:
    await _open_topic(owner, due_day=_TODAY - timedelta(days=3))
    asked = await _open_topic(owner, due_day=_TODAY - timedelta(days=4))
    assert await pending_store.mark_asked(asked, now=_NOON)
    await _unnamed(owner, due_day=_TODAY - timedelta(days=5))
    kept = await _open_topic(owner, due_day=_TODAY - timedelta(days=2))

    assert await pending_store.delete_expired(today=_TODAY) == 3
    assert await _scalar("SELECT id FROM pending_topics") == kept
    assert await pending_store.delete_expired(today=_TODAY) == 0


@pytest.mark.parametrize(
    "memory, record, pending", list(itertools.product([True, False], repeat=3))
)
def test_pending_topics_on_needs_all_three_switches(
    monkeypatch: pytest.MonkeyPatch, memory: bool, record: bool, pending: bool
) -> None:
    monkeypatch.setattr(settings, "memory_enabled", memory)
    monkeypatch.setattr(settings, "conversation_record_enabled", record)
    monkeypatch.setattr(settings, "pending_topics_enabled", pending)
    assert pending_store.pending_topics_on() is (memory and record and pending)
