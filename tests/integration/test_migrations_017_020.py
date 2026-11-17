"""Migrations 017 to 020 (Plan 0085, Part B): what each one leaves behind and what it refuses.

Every test starts from a database built by the real migrations up to the version before the one
under test, so the migration is exercised on the schema it will meet. Canary rows only.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
import logging
import re
import sqlite3
from typing import TYPE_CHECKING
from uuid import UUID

import numpy as np
import pytest
from server.exceptions import BrainMemoryError
from server.memory import conversation_record as record
from server.memory.biometric_consent import grant_face_consent, revoke_face_consent
from server.memory.conversation_types import (
    HEARD_MAX_CHARS,
    SAID_MAX_CHARS,
    RecordedTurn,
    TurnVerdict,
    make_turn,
)
from server.memory.db_health import time_columns
from server.memory.declarative import upsert_entity
from server.memory.voice_consent import grant_voice_consent, revoke_voice_consent
from server.settings import settings
from server.timestamps import INSTANT_LENGTH, instant_text
from server.vision.faces import enroll_face
from server.voice.voiceprints import enroll_voiceprint

from server import db
from tests.unit.test_schema_guards import _DEAD_TABLES

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

# --- 017: the dead tables out (the list is in the schema guards) ---------------------------------

# One valid canary row per dead table. Foreign keys are off while it is inserted, so each table
# holds a row on its own (a `legacy_fact_migration_v4` row needs no `facts` row beside it).
_CANARY_ROWS = {
    "outbox": "INSERT INTO outbox (aggregate_type, aggregate_id, op, payload) "
    "VALUES ('entity', 1, 'insert', '{}')",
    "sensor_current": "INSERT INTO sensor_current (sensor_id, sensor_type, value, unit) "
    "VALUES ('canary-sensor', 'temperature', 20.0, 'celsius')",
    "sensor_readings": "INSERT INTO sensor_readings (sensor_id, sensor_type, value, unit) "
    "VALUES ('canary-sensor', 'temperature', 20.0, 'celsius')",
    "sensor_aggregates_hourly": "INSERT INTO sensor_aggregates_hourly "
    "(sensor_id, hour_bucket, avg_value, min_value, max_value, count) "
    "VALUES ('canary-sensor', '2026-11-16 10:00:00', 20.0, 19.0, 21.0, 3)",
    "facts": "INSERT INTO facts (entity_id, predicate, object_value) "
    "VALUES (1, 'canary-predicate', 'canary-value')",
    "legacy_fact_migration_v4": "INSERT INTO legacy_fact_migration_v4 "
    "(legacy_fact_id, outcome, reason) VALUES (1, 'deferred', 'canary-reason')",
    "embeddings_cache": "INSERT INTO embeddings_cache (text_hash, model, vector) "
    "VALUES ('canary-hash', 'canary-model', x'00')",
    "events": "INSERT INTO events (event_type, severity) VALUES ('canary-event', 'info')",
}


@asynccontextmanager
async def _built_at(
    version: int, path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[db.Migration, ...]]:
    """A database built by the real migrations up to *version*; yields the full migration list."""
    monkeypatch.setattr(settings, "brain_db_path", path)
    db._conn = None
    try:
        await db.open_db()
        every_migration = db._MIGRATIONS
        monkeypatch.setattr(db, "_MIGRATIONS", tuple(m for m in every_migration if m[0] <= version))
        await db.run_migrations()
        yield every_migration
    finally:
        await db.close_db()
        db._conn = None


@pytest.fixture
async def v16_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[db.Migration, ...]]:
    """A database at version 16; yields the full migration list."""
    async with _built_at(16, tmp_path / "migrations-017.db", monkeypatch) as every_migration:
        yield every_migration


@pytest.fixture
async def v17_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[db.Migration, ...]]:
    """A database at version 17; yields the full migration list."""
    async with _built_at(17, tmp_path / "migrations-018.db", monkeypatch) as every_migration:
        yield every_migration


async def _scalar(sql: str) -> object:
    cursor = await db.get_conn().execute(sql)
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    return row[0]


async def _tables() -> set[str]:
    cursor = await db.get_conn().execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    names = {row[0] for row in await cursor.fetchall()}
    await cursor.close()
    return names


async def _insert_canary(table: str) -> None:
    conn = db.get_conn()
    await conn.execute("PRAGMA foreign_keys = OFF")
    await conn.execute(_CANARY_ROWS[table])
    await conn.commit()
    await conn.execute("PRAGMA foreign_keys = ON")


async def test_017_drops_the_eight_dead_tables_and_keeps_memories(
    v16_db: tuple[db.Migration, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert set(_DEAD_TABLES) <= await _tables()

    monkeypatch.setattr(db, "_MIGRATIONS", v16_db)
    await db.run_migrations()

    tables = await _tables()
    assert db.latest_schema_version() >= 17
    assert await _scalar("PRAGMA user_version") == db.latest_schema_version()
    assert not set(_DEAD_TABLES) & tables
    assert "memories" in tables
    assert await _scalar("PRAGMA integrity_check") == "ok"
    assert await _scalar("SELECT count(*) FROM pragma_foreign_key_check") == 0


async def test_017_takes_every_dead_index_with_its_table(
    v16_db: tuple[db.Migration, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(db, "_MIGRATIONS", v16_db)
    await db.run_migrations()

    marks = ", ".join("?" for _ in _DEAD_TABLES)
    cursor = await db.get_conn().execute(
        f"SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name IN ({marks})",  # noqa: S608
        _DEAD_TABLES,
    )
    leftover = await cursor.fetchall()
    await cursor.close()
    assert leftover == []


async def test_017_keeps_the_trigger_that_locks_memories(
    v16_db: tuple[db.Migration, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(db, "_MIGRATIONS", v16_db)
    await db.run_migrations()

    assert await _scalar("SELECT name FROM sqlite_master WHERE name = 'memories_retired'") == (
        "memories_retired"
    )


@pytest.mark.parametrize("table", _DEAD_TABLES)
async def test_a_canary_row_in_any_dead_table_aborts_017(
    v16_db: tuple[db.Migration, ...], monkeypatch: pytest.MonkeyPatch, table: str
) -> None:
    await _insert_canary(table)
    monkeypatch.setattr(db, "_MIGRATIONS", v16_db)

    with pytest.raises(BrainMemoryError, match="Migration 17"):
        await db.run_migrations()

    assert await _scalar("PRAGMA user_version") == 16
    assert set(_DEAD_TABLES) <= await _tables()
    assert await _scalar(f"SELECT count(*) FROM {table}") == 1  # noqa: S608


# --- 018: the turns as rows ----------------------------------------------------------------------

_T0 = datetime(2026, 11, 16, 10, 0, tzinfo=UTC)
_TURN_COLUMNS = "record_id, correlation_id, said_at, verdict, heard, said"
_DROPPED_COLUMNS = {"turns", "turn_count", "byte_count"}


def _turn(index: int, seconds: float, heard: str, voice: TurnVerdict) -> RecordedTurn:
    return make_turn(
        heard,
        f"Respuesta {index}: ¿qué tal? 🙂",
        voice=voice,
        correlation_id=UUID(int=index),
        at=_T0 + timedelta(seconds=seconds),
    )


# Stored out of time order on purpose, with two equal instants (3 and 4) and all four verdicts.
_SEVERAL = [
    _turn(1, 5, "hola", TurnVerdict.VERIFIED),
    _turn(2, 1, "ñandú 🙂 canario", TurnVerdict.NOT_VERIFIED),
    _turn(3, 3, "uno", TurnVerdict.NOT_OWNER),
    _turn(4, 3, "dos", TurnVerdict.NOT_CHECKED),
]
_LAST = [_turn(5, 9, "última", TurnVerdict.VERIFIED)]


async def _v17_record_from_json(turns_json: str, owner: int, *, closed: bool) -> int:
    """Write a record the way version 17 stored it: its turns as one JSON array."""
    stamp = instant_text(_T0)
    cursor = await db.get_conn().execute(
        "INSERT INTO conversation_records (owner_entity_id, started_at, last_turn_at, closed_at, "
        "expires_at, turns, turn_count, byte_count) VALUES (?, ?, ?, ?, ?, json(?), 1, 1)",
        (owner, stamp, stamp, stamp if closed else None, stamp if closed else None, turns_json),
    )
    record_id = int(cursor.lastrowid or 0)
    await cursor.close()
    await db.get_conn().commit()
    return record_id


async def _v17_record(owner: int, turns: list[RecordedTurn], *, closed: bool) -> int:
    return await _v17_record_from_json(
        "[" + ",".join(turn.to_json() for turn in turns) + "]", owner, closed=closed
    )


async def _rows(sql: str) -> list[tuple[object, ...]]:
    cursor = await db.get_conn().execute(sql)
    rows = [tuple(row) for row in await cursor.fetchall()]
    await cursor.close()
    return rows


async def _columns_of_records() -> set[object]:
    rows = await _rows("SELECT name FROM pragma_table_info('conversation_records')")
    return {row[0] for row in rows}


async def _read(record_id: int) -> record.RecordView:
    view = await record.read_record(record_id)
    assert view is not None
    return view


async def test_018_turns_the_json_into_rows_in_order_with_the_same_fields(
    v17_db: tuple[db.Migration, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await upsert_entity(name="Canary Owner", type="person")
    several = await _v17_record(owner, _SEVERAL, closed=True)
    await _v17_record(owner, [], closed=True)
    last = await _v17_record(owner, _LAST, closed=False)

    monkeypatch.setattr(db, "_MIGRATIONS", v17_db)
    await db.run_migrations()

    assert await _rows(f"SELECT {_TURN_COLUMNS} FROM conversation_turns ORDER BY id") == [  # noqa: S608
        (
            several if turn in _SEVERAL else last,
            str(turn.correlation_id),
            instant_text(turn.at),
            turn.voice.value,
            turn.heard,
            turn.said,
        )
        for turn in [*_SEVERAL, *_LAST]
    ]


async def test_018_drops_the_three_columns_and_leaves_a_sound_database(
    v17_db: tuple[db.Migration, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await upsert_entity(name="Canary Owner", type="person")
    await _v17_record(owner, _SEVERAL, closed=True)
    monkeypatch.setattr(db, "_MIGRATIONS", v17_db)

    await db.run_migrations()

    assert not _DROPPED_COLUMNS & await _columns_of_records()
    assert await _scalar("PRAGMA user_version") == db.latest_schema_version()
    assert db.latest_schema_version() >= 18
    assert await _scalar("PRAGMA integrity_check") == "ok"
    assert await _scalar("SELECT count(*) FROM pragma_foreign_key_check") == 0


async def test_a_record_reads_back_the_same_turns_after_018(
    v17_db: tuple[db.Migration, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review focus 2: same turns, same order, same verdicts; 0 turns; two equal instants."""
    owner = await upsert_entity(name="Canary Owner", type="person")
    several = await _v17_record(owner, _SEVERAL, closed=True)
    empty = await _v17_record(owner, [], closed=True)
    last = await _v17_record(owner, _LAST, closed=False)
    monkeypatch.setattr(db, "_MIGRATIONS", v17_db)

    await db.run_migrations()

    # What version 17 returned: the record's turns sorted by time, equal instants in stored order.
    assert (await _read(several)).turns == tuple(sorted(_SEVERAL, key=lambda turn: turn.at))
    assert (await _read(empty)).turns == ()
    assert (await _read(last)).turns == tuple(_LAST)
    summary = (await _read(several)).summary
    assert summary.turn_count == len(_SEVERAL)
    assert summary.byte_count == sum(
        len(turn.heard.encode()) + len(turn.said.encode()) for turn in _SEVERAL
    )


_AN_OLD_INSTANT_TURN = (
    '[{"at": "2026-11-16T10:00:00+00:00", "heard": "h", "said": "s", "voice": "verified", '
    '"cid": "00000000-0000-0000-0000-000000000001"}]'
)
_TWO_TURNS_ONE_CID = (
    '[{"at": "2026-11-16T10:00:00.000000+00:00", "heard": "h", "said": "s", "voice": "verified", '
    '"cid": "00000000-0000-0000-0000-000000000001"}, '
    '{"at": "2026-11-16T10:00:01.000000+00:00", "heard": "h", "said": "s", "voice": "verified", '
    '"cid": "00000000-0000-0000-0000-000000000001"}]'
)


@pytest.mark.parametrize("turns_json", [_AN_OLD_INSTANT_TURN, _TWO_TURNS_ONE_CID])
async def test_018_refuses_a_turn_that_breaks_a_rule_and_leaves_version_17(
    v17_db: tuple[db.Migration, ...], monkeypatch: pytest.MonkeyPatch, turns_json: str
) -> None:
    owner = await upsert_entity(name="Canary Owner", type="person")
    await _v17_record_from_json(turns_json, owner, closed=True)
    monkeypatch.setattr(db, "_MIGRATIONS", v17_db)

    with pytest.raises(BrainMemoryError, match="Migration 18"):
        await db.run_migrations()

    assert await _scalar("PRAGMA user_version") == 17
    assert "conversation_turns" not in await _tables()
    assert await _columns_of_records() >= _DROPPED_COLUMNS


# The table's own checks, on a database with every migration applied.


@pytest.fixture
async def a_record(v17_db: tuple[db.Migration, ...], monkeypatch: pytest.MonkeyPatch) -> int:
    """A migrated database with one open record; yields the record's id."""
    monkeypatch.setattr(db, "_MIGRATIONS", v17_db)
    await db.run_migrations()
    owner = await upsert_entity(name="Canary Owner", type="person")
    stamp = instant_text(_T0)
    cursor = await db.get_conn().execute(
        "INSERT INTO conversation_records (owner_entity_id, started_at, last_turn_at) "
        "VALUES (?, ?, ?)",
        (owner, stamp, stamp),
    )
    record_id = int(cursor.lastrowid or 0)
    await cursor.close()
    await db.get_conn().commit()
    return record_id


async def _insert_turn(
    record_id: int,
    *,
    cid: str = "00000000-0000-0000-0000-000000000001",
    said_at: str = "2026-11-16T10:00:00.000000+00:00",
    verdict: str = "verified",
    heard: str = "hola",
    said: str = "hola",
) -> None:
    await db.get_conn().execute(
        "INSERT INTO conversation_turns (record_id, correlation_id, said_at, verdict, heard, said) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (record_id, cid, said_at, verdict, heard, said),
    )
    await db.get_conn().commit()


async def test_a_well_formed_turn_is_accepted_at_the_text_limits(a_record: int) -> None:
    await _insert_turn(a_record, heard="x" * HEARD_MAX_CHARS, said="y" * SAID_MAX_CHARS)

    assert await _scalar("SELECT count(*) FROM conversation_turns") == 1


@pytest.mark.parametrize(
    "said_at",
    [
        "2026-11-16T10:00:00+00:00",  # no fraction
        "2026-11-16T10:00:00.000000Z",  # not the +00:00 suffix
        "2026-11-16T10:00:00.000000+01:00",  # the right length, another offset
        "2026-11-16 10:00:00.000000+00:00",  # a space for the T
        "2026-11-16T10:00:00.00000a+00:00",  # a letter for a digit
        "2026-02-30T10:00:00.000000+00:00",  # no such day
        "2026-13-01T10:00:00.000000+00:00",  # no such month
        "2026-11-16T25:00:00.000000+00:00",  # no such hour
        "2026-11-16T10:61:00.000000+00:00",  # no such minute
    ],
)
async def test_a_turn_must_carry_an_exact_instant(a_record: int, said_at: str) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        await _insert_turn(a_record, said_at=said_at)


@pytest.mark.parametrize(
    "overrides",
    [
        {"verdict": "maybe"},
        {"heard": "x" * (HEARD_MAX_CHARS + 1)},
        {"said": "y" * (SAID_MAX_CHARS + 1)},
    ],
)
async def test_a_turn_with_a_bad_verdict_or_text_is_refused(
    a_record: int, overrides: dict[str, str]
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        await _insert_turn(a_record, **overrides)


async def test_a_correlation_id_belongs_to_one_turn(a_record: int) -> None:
    await _insert_turn(a_record)

    with pytest.raises(sqlite3.IntegrityError):
        await _insert_turn(a_record, said_at="2026-11-16T10:00:01.000000+00:00")


async def test_a_turn_needs_its_record_and_goes_with_it(a_record: int) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        await _insert_turn(a_record + 99)
    await _insert_turn(a_record)

    await db.get_conn().execute("DELETE FROM conversation_records WHERE id = ?", (a_record,))
    await db.get_conn().commit()

    assert await _scalar("SELECT count(*) FROM conversation_turns") == 0


# --- 019: the turn linked to what is derived from it -----------------------------------------------


@pytest.fixture
async def v18_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[db.Migration, ...]]:
    """A database at version 18; yields the full migration list."""
    async with _built_at(18, tmp_path / "migrations-019.db", monkeypatch) as every_migration:
        yield every_migration


async def _exec(sql: str, *params: object) -> int:
    """Run one write on the open connection and commit it; return the new row id."""
    cursor = await db.get_conn().execute(sql, params)
    row_id = int(cursor.lastrowid or 0)
    await cursor.close()
    await db.get_conn().commit()
    return row_id


async def _v18_unit(owner: int, record_id: int, cid: str) -> int:
    return await _exec(
        "INSERT INTO recall_units (owner_entity_id, source_record_id, kind, body, said_at, "
        "visibility, sensitivity, correlation_id) VALUES (?, ?, 'turn', 'palabra canario', ?, "
        "'personal', 'normal', ?)",
        owner,
        record_id,
        instant_text(_T0),
        cid,
    )


async def _v18_candidate(owner: int, cid: str, key: str) -> int:
    return await _exec(
        "INSERT INTO memory_candidates (subject_person_id, asserted_by_person_id, predicate, "
        "value_text, value_key, status, channel, source_correlation_id, proposed_at, expires_at) "
        "VALUES (?, ?, 'likes', ?, ?, 'proposed', 'voice_classic', ?, ?, ?)",
        owner,
        owner,
        key,
        key,
        cid,
        instant_text(_T0),
        instant_text(_T0 + timedelta(days=1)),
    )


async def _v18_topic(owner: int, record_id: int, cid: str) -> int:
    return await _exec(
        "INSERT INTO pending_topics (owner_entity_id, source_record_id, correlation_id, said_day, "
        "due_day, heard, state, sensitivity, created_at) "
        "VALUES (?, ?, ?, '2026-11-16', '2026-11-17', 'voy al banco', 'unnamed', 'normal', ?)",
        owner,
        record_id,
        cid,
        instant_text(_T0),
    )


async def test_019_maps_every_existing_unit_candidate_and_topic_to_its_turn(
    v18_db: tuple[db.Migration, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await upsert_entity(name="Canary Owner", type="person")
    turns = [_turn(index, index, f"palabra {index}", TurnVerdict.VERIFIED) for index in (1, 2, 3)]
    for turn in turns:
        await record.append_turn(turn, owner_entity_id=owner, now=_T0)
    record_id = int(str(await _scalar("SELECT min(record_id) FROM conversation_turns")))
    for turn in turns:
        cid = str(turn.correlation_id)
        await _v18_unit(owner, record_id, cid)
        await _v18_candidate(owner, cid, f"canario {cid[-1]}")
        await _v18_topic(owner, record_id, cid)
    # A turn that was never stored (the record was off, or the turn purged): its rows stay NULL.
    gone = str(UUID(int=99))
    await _v18_unit(owner, record_id, gone)
    await _v18_candidate(owner, gone, "canario 99")
    await _v18_topic(owner, record_id, gone)
    monkeypatch.setattr(db, "_MIGRATIONS", v18_db)

    await db.run_migrations()

    turn_ids = [row[0] for row in await _rows("SELECT id FROM conversation_turns ORDER BY id")]
    assert len(turn_ids) == 3
    for table, column in (
        ("recall_units", "turn_id"),
        ("memory_candidates", "source_turn_id"),
        ("pending_topics", "source_turn_id"),
    ):
        mapped = [row[0] for row in await _rows(f"SELECT {column} FROM {table} ORDER BY id")]  # noqa: S608
        assert mapped == [*turn_ids, None]
    # Every row whose turn exists points at the turn that carries its own correlation id.
    for table, cid_column, turn_column in (
        ("recall_units", "correlation_id", "turn_id"),
        ("memory_candidates", "source_correlation_id", "source_turn_id"),
        ("pending_topics", "correlation_id", "source_turn_id"),
    ):
        assert (
            await _scalar(
                f"SELECT count(*) FROM {table} x JOIN conversation_turns t ON t.id = x.{turn_column} "  # noqa: S608
                f"WHERE t.correlation_id <> x.{cid_column}"
            )
            == 0
        )
    assert await _scalar("PRAGMA integrity_check") == "ok"
    assert await _scalar("SELECT count(*) FROM pragma_foreign_key_check") == 0


@pytest.fixture
async def head_db(v18_db: tuple[db.Migration, ...], monkeypatch: pytest.MonkeyPatch) -> int:
    """A database with every migration applied and one owner; yields the owner's id."""
    monkeypatch.setattr(db, "_MIGRATIONS", v18_db)
    await db.run_migrations()
    return await upsert_entity(name="Canary Owner", type="person")


async def test_019_drops_the_redundant_entity_name_index_and_keeps_the_unique_pair(
    head_db: int,
) -> None:
    indexed = {
        row[0]
        for row in await _rows(
            "SELECT group_concat(i.name, ',') FROM pragma_index_list('entities') l "
            "JOIN pragma_index_info(l.name) i GROUP BY l.name"
        )
    }

    assert await _scalar("SELECT count(*) FROM sqlite_master WHERE name = 'entities_name_idx'") == 0
    assert "name,type" in indexed


async def test_an_update_of_a_units_body_is_refused(head_db: int) -> None:
    record_id = await _exec(
        "INSERT INTO conversation_records (owner_entity_id, started_at, last_turn_at) "
        "VALUES (?, ?, ?)",
        head_db,
        instant_text(_T0),
        instant_text(_T0),
    )
    unit_id = await _v18_unit_at_head(head_db, record_id)

    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        await _exec("UPDATE recall_units SET body = 'otra' WHERE id = ?", unit_id)

    assert await _scalar("SELECT body FROM recall_units") == "palabra canario"
    # Other columns of a unit still change (the sensitivity scrub, the embedding model).
    await _exec("UPDATE recall_units SET sensitivity = 'private' WHERE id = ?", unit_id)
    assert await _scalar("SELECT sensitivity FROM recall_units") == "private"


async def _v18_unit_at_head(owner: int, record_id: int) -> int:
    return await _v18_unit(owner, record_id, str(UUID(int=7)))


async def test_every_foreign_key_a_delete_follows_is_found_by_an_index(head_db: int) -> None:
    """A parent's DELETE checks each child by its foreign-key column: none may scan the table.

    ``EXPLAIN QUERY PLAN`` of the DELETE itself does not list the child checks, so each foreign
    key is probed with the lookup SQLite runs for it, ``SELECT 1 FROM child WHERE fk = ?``.
    """
    keys = await _rows(
        'SELECT m.name, f."from", f."table", f.seq FROM sqlite_master m '
        "JOIN pragma_foreign_key_list(m.name) f WHERE m.type = 'table' ORDER BY 1, 2"
    )
    assert keys
    assert {row[3] for row in keys} == {0}  # no composite key: one column is probed per key
    scans = []
    for child, column, parent, _seq in keys:
        plan = await _rows(f"EXPLAIN QUERY PLAN SELECT 1 FROM {child} WHERE {column} = 1")  # noqa: S608
        details = " ".join(str(row[3]) for row in plan)
        if "USING" not in details or "SCAN" in details:
            scans.append(f"{child}.{column} -> {parent}: {details}")
    assert scans == []
    parents = {row[2] for row in keys}
    assert {"entities", "conversation_turns"} <= parents


# --- 020: the old times and the two biometric tables ---------------------------------------------

_MIGRATION_020 = db._MIGRATIONS_DIR / "migration_020_times_and_profiles.sql"
_UNPARSED_FORMATS = [
    "2026/11/16 10:00",  # a third format
    "2026-11-16T10:00:00-03:00",  # 25 characters, another offset: not a UTC instant
    "2026-11-16",  # a day in an instant column
    "2026-11-16T10:00:00.123+00:00",  # three fraction digits
    "2026-13-01 10:00:00",  # 19 characters, no such month
]


@pytest.fixture
async def v19_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[db.Migration, ...]]:
    """A database at version 19; yields the full migration list."""
    async with _built_at(19, tmp_path / "migrations-020.db", monkeypatch) as every_migration:
        yield every_migration


async def _run_020(
    every_migration: tuple[db.Migration, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(db, "_MIGRATIONS", every_migration)
    await db.run_migrations()


async def test_020_names_every_time_column_the_schema_has(
    v19_db: tuple[db.Migration, ...],
) -> None:
    columns = await time_columns(db.get_conn())
    sql = _MIGRATION_020.read_text(encoding="utf-8")

    assert len(columns) >= 40
    missing = [f"{t}.{c}" for t, c in columns if f"UPDATE {t} SET {c} =" not in sql]  # noqa: S608
    assert missing == []


async def _v19_entity(name: str, created: str, updated: str) -> int:
    return await _exec(
        "INSERT INTO entities (name, type, created_at, updated_at) VALUES (?, 'person', ?, ?)",
        name,
        created,
        updated,
    )


async def test_020_converts_each_19_and_25_character_instant_exactly(
    v19_db: tuple[db.Migration, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    await _v19_entity("Canary A", "2026-11-16 10:00:01", "2026-11-16T10:00:02+00:00")
    await _v19_entity("Canary B", "2026-11-16T23:59:59.123456+00:00", "2026-01-02 03:04:05")
    owner = await _v19_entity("Canary C", "2025-12-31 23:59:59", "2025-12-31T23:59:59+00:00")
    await _exec(
        "INSERT INTO literal_facts_v4 (subject_entity_id, predicate, value_text, asserted_at, "
        "confirmed_at, superseded_at) VALUES (?, 'likes', 'te', '2026-03-04 05:06:07', NULL, "
        "'2026-03-04T05:06:08+00:00')",
        owner,
    )
    await _exec(
        "INSERT INTO meta (key, value, updated_at) VALUES ('canary', 'x', '2026-05-06 07:08:09')"
    )

    await _run_020(v19_db, monkeypatch)

    assert await _rows("SELECT name, created_at, updated_at FROM entities ORDER BY id") == [
        ("Canary A", "2026-11-16T10:00:01.000000+00:00", "2026-11-16T10:00:02.000000+00:00"),
        ("Canary B", "2026-11-16T23:59:59.123456+00:00", "2026-01-02T03:04:05.000000+00:00"),
        ("Canary C", "2025-12-31T23:59:59.000000+00:00", "2025-12-31T23:59:59.000000+00:00"),
    ]
    assert await _rows("SELECT asserted_at, confirmed_at, superseded_at FROM literal_facts_v4") == [
        ("2026-03-04T05:06:07.000000+00:00", None, "2026-03-04T05:06:08.000000+00:00")
    ]
    assert await _scalar("SELECT updated_at FROM meta WHERE key = 'canary'") == (
        "2026-05-06T07:08:09.000000+00:00"
    )
    assert await _scalar("PRAGMA user_version") == 20


@pytest.mark.parametrize("bad", _UNPARSED_FORMATS)
async def test_a_value_in_a_third_time_format_aborts_020_and_leaves_version_19(
    v19_db: tuple[db.Migration, ...], monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    await _v19_entity("Canary A", "2026-11-16 10:00:01", "2026-11-16T10:00:02+00:00")
    await _v19_entity("Canary B", bad, "2026-11-16 10:00:03")
    before = await _rows("SELECT id, name, created_at, updated_at FROM entities ORDER BY id")
    profile_sql = await _scalar("SELECT sql FROM sqlite_master WHERE name = 'face_profiles'")

    with pytest.raises(BrainMemoryError, match="Migration 20"):
        await _run_020(v19_db, monkeypatch)

    assert await _scalar("PRAGMA user_version") == 19
    assert (
        await _rows("SELECT id, name, created_at, updated_at FROM entities ORDER BY id") == before
    )
    assert await _scalar("SELECT sql FROM sqlite_master WHERE name = 'face_profiles'") == (
        profile_sql
    )
    assert await _scalar("PRAGMA foreign_keys") == 1


async def _v19_fact(
    subject: int, predicate: str, valid_from: str | None, valid_to: str | None
) -> None:
    await _exec(
        "INSERT INTO literal_facts_v4 (subject_entity_id, predicate, value_text, asserted_at, "
        "valid_from, valid_to) VALUES (?, ?, 'v', ?, ?, ?)",
        subject,
        predicate,
        instant_text(_T0),
        valid_from,
        valid_to,
    )


async def test_020_turns_an_instant_validity_bound_into_its_day_and_keeps_days_and_months(
    v19_db: tuple[db.Migration, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = await _v19_entity("Canary A", instant_text(_T0), instant_text(_T0))
    other = await _v19_entity("Canary B", instant_text(_T0), instant_text(_T0))
    await _v19_fact(subject, "p19", "2026-11-16 10:00:00", "2026-11-17T23:59:59+00:00")
    await _v19_fact(subject, "p32", "2026-11-18T08:30:00.250000+00:00", None)
    await _v19_fact(subject, "pday", "2026-11-19", "2026-11")
    await _exec(
        "INSERT INTO entity_relations_v4 (source_entity_id, predicate, target_entity_id, "
        "asserted_at, valid_from, valid_to) VALUES (?, 'knows', ?, ?, '2026-02-03 04:05:06', "
        "'2026-02-04')",
        subject,
        other,
        instant_text(_T0),
    )

    await _run_020(v19_db, monkeypatch)

    assert await _rows(
        "SELECT predicate, valid_from, valid_to FROM literal_facts_v4 ORDER BY id"
    ) == [
        ("p19", "2026-11-16", "2026-11-17"),
        ("p32", "2026-11-18", None),
        ("pday", "2026-11-19", "2026-11"),
    ]
    assert await _rows("SELECT valid_from, valid_to FROM entity_relations_v4") == [
        ("2026-02-03", "2026-02-04")
    ]


_FACT_WITH_BOUND = {
    "valid_from": "INSERT INTO literal_facts_v4 (subject_entity_id, predicate, value_text, "
    "asserted_at, valid_from) VALUES (?, 'p', 'v', ?, ?)",
    "valid_to": "INSERT INTO literal_facts_v4 (subject_entity_id, predicate, value_text, "
    "asserted_at, valid_to) VALUES (?, 'p', 'v', ?, ?)",
}


@pytest.mark.parametrize("bad", ["2026/11/16", "2026-11-16T10:00:00-03:00", "11-2026", "mañana"])
@pytest.mark.parametrize("column", ["valid_from", "valid_to"])
async def test_a_validity_bound_in_another_shape_aborts_020(
    v19_db: tuple[db.Migration, ...], monkeypatch: pytest.MonkeyPatch, column: str, bad: str
) -> None:
    subject = await _v19_entity("Canary A", instant_text(_T0), instant_text(_T0))
    await _exec(
        _FACT_WITH_BOUND[column],
        subject,
        instant_text(_T0),
        bad,
    )

    with pytest.raises(BrainMemoryError, match="Migration 20"):
        await _run_020(v19_db, monkeypatch)

    assert await _scalar("PRAGMA user_version") == 19
    assert await _scalar(f"SELECT {column} FROM literal_facts_v4") == bad  # noqa: S608


async def test_converted_and_new_instants_sort_in_time_order(
    v19_db: tuple[db.Migration, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    await _v19_entity("old-1", "2026-11-16 09:59:59", "2026-11-16 09:59:59")
    await _v19_entity("old-2", "2026-11-16T10:00:00+00:00", "2026-11-16T10:00:00+00:00")
    await _run_020(v19_db, monkeypatch)
    for name, moment in (
        ("new-1", _T0 + timedelta(microseconds=1)),
        ("new-2", _T0 + timedelta(seconds=1)),
        ("new-0", _T0 - timedelta(seconds=2)),
    ):
        stamp = instant_text(moment)
        await _exec(
            "INSERT INTO entities (name, type, created_at, updated_at) VALUES (?, 'person', ?, ?)",
            name,
            stamp,
            stamp,
        )

    names = [row[0] for row in await _rows("SELECT name FROM entities ORDER BY created_at, id")]

    assert names == ["new-0", "old-1", "old-2", "new-1", "new-2"]


_FACE_BLOB = np.full(512, 0.5, dtype=np.float32).tobytes()
_VOICE_BLOB = np.full(192, 0.25, dtype=np.float32).tobytes()
_VOICE_MODEL = "canary-model@rev"
_PROFILE_INSERTS = {
    "face_profiles": "INSERT INTO face_profiles (entity_id, label, created_at) VALUES (?, 'otra', ?)",
    "voice_profiles": "INSERT INTO voice_profiles (entity_id, label, created_at, embedding, "
    "model_id) VALUES (?, 'otra', ?, ?, ?)",
}


async def _v19_profiles(person: int) -> None:
    """Three face and three voice profiles with ids 1..3, in version 19's old time formats."""
    for index in (1, 2, 3):
        await _exec(
            "INSERT INTO face_profiles (id, entity_id, label, created_at) VALUES (?, ?, ?, ?)",
            index,
            person,
            f"cara {index}",
            f"2026-11-1{index} 10:00:0{index}",
        )
        await _exec("INSERT INTO vec_faces (rowid, embedding) VALUES (?, ?)", index, _FACE_BLOB)
        await _exec(
            "INSERT INTO voice_profiles (id, entity_id, label, embedding, model_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            index,
            person,
            f"voz {index}",
            _VOICE_BLOB,
            _VOICE_MODEL,
            f"2026-11-1{index}T10:00:0{index}+00:00",
        )


async def test_020_rebuilds_both_profile_tables_keeping_every_row_and_vector(
    v19_db: tuple[db.Migration, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    person = await _v19_entity("Canary A", instant_text(_T0), instant_text(_T0))
    await _v19_profiles(person)

    await _run_020(v19_db, monkeypatch)

    assert await _rows(
        "SELECT id, entity_id, label, created_at FROM face_profiles ORDER BY id"
    ) == [
        (1, person, "cara 1", "2026-11-11T10:00:01.000000+00:00"),
        (2, person, "cara 2", "2026-11-12T10:00:02.000000+00:00"),
        (3, person, "cara 3", "2026-11-13T10:00:03.000000+00:00"),
    ]
    assert await _rows(
        "SELECT id, entity_id, label, model_id, created_at, length(embedding) "
        "FROM voice_profiles ORDER BY id"
    ) == [
        (
            index,
            person,
            f"voz {index}",
            _VOICE_MODEL,
            f"2026-11-1{index}T10:00:0{index}.000000+00:00",
            768,
        )
        for index in (1, 2, 3)
    ]
    assert await _scalar("SELECT embedding FROM voice_profiles WHERE id = 2") == _VOICE_BLOB
    # vec_faces is keyed by rowid = face_profiles.id: every id kept, so it is untouched.
    assert await _rows("SELECT rowid FROM vec_faces ORDER BY rowid") == [(1,), (2,), (3,)]
    assert await _scalar("SELECT count(*) FROM pragma_foreign_key_check") == 0
    for table in ("face_profiles", "voice_profiles"):
        index = f"idx_{table}_entity"
        assert await _scalar(f"SELECT tbl_name FROM sqlite_master WHERE name = '{index}'") == table  # noqa: S608


@pytest.mark.parametrize("table", ["face_profiles", "voice_profiles"])
async def test_020_makes_the_profile_tables_strict_autoincrement_and_restrictive(
    v19_db: tuple[db.Migration, ...], monkeypatch: pytest.MonkeyPatch, table: str
) -> None:
    await _run_020(v19_db, monkeypatch)

    assert await _scalar(f"SELECT strict FROM pragma_table_list('{table}')") == 1  # noqa: S608
    sql = str(await _scalar(f"SELECT sql FROM sqlite_master WHERE name = '{table}'"))  # noqa: S608
    assert "AUTOINCREMENT" in sql
    assert "datetime(" not in sql
    assert await _rows(
        f'SELECT "table", "from", on_delete FROM pragma_foreign_key_list(\'{table}\')'  # noqa: S608
    ) == [("entities", "entity_id", "RESTRICT")]


async def test_020_sets_each_profile_counter_to_the_old_top_id(
    v19_db: tuple[db.Migration, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    person = await _v19_entity("Canary A", instant_text(_T0), instant_text(_T0))
    await _v19_profiles(person)

    await _run_020(v19_db, monkeypatch)

    assert await _rows(
        "SELECT name, seq FROM sqlite_sequence WHERE name IN ('face_profiles', 'voice_profiles') "
        "ORDER BY name"
    ) == [("face_profiles", 3), ("voice_profiles", 3)]


@pytest.mark.parametrize("table", ["face_profiles", "voice_profiles"])
async def test_a_deleted_top_profile_id_is_never_reused_after_020(
    v19_db: tuple[db.Migration, ...], monkeypatch: pytest.MonkeyPatch, table: str
) -> None:
    person = await _v19_entity("Canary A", instant_text(_T0), instant_text(_T0))
    await _v19_profiles(person)
    await _run_020(v19_db, monkeypatch)
    extra = _PROFILE_INSERTS[table]
    tail: tuple[object, ...] = (_VOICE_BLOB, _VOICE_MODEL) if table == "voice_profiles" else ()

    fourth = await _exec(extra, person, instant_text(_T0), *tail)
    await _exec(f"DELETE FROM {table} WHERE id = ?", fourth)  # noqa: S608
    fifth = await _exec(extra, person, instant_text(_T0), *tail)

    assert (fourth, fifth) == (4, 5)


@pytest.mark.parametrize("stamp", [None, "2026-11-16 10:00:00", "2026-11-16T10:00:00+00:00"])
async def test_a_profile_needs_an_exact_instant_from_the_writer(
    head_db: int, stamp: str | None
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        await _exec(
            "INSERT INTO face_profiles (entity_id, label, created_at) VALUES (?, 'cara', ?)",
            head_db,
            stamp,
        )


async def test_deleting_a_person_with_a_face_or_a_voiceprint_is_refused(head_db: int) -> None:
    await _exec(
        "INSERT INTO face_profiles (entity_id, label, created_at) VALUES (?, 'cara', ?)",
        head_db,
        instant_text(_T0),
    )
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        await _exec("DELETE FROM entities WHERE id = ?", head_db)
    await _exec("DELETE FROM face_profiles WHERE entity_id = ?", head_db)
    await _exec(
        "INSERT INTO voice_profiles (entity_id, label, embedding, model_id, created_at) "
        "VALUES (?, 'voz', ?, ?, ?)",
        head_db,
        _VOICE_BLOB,
        _VOICE_MODEL,
        instant_text(_T0),
    )

    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        await _exec("DELETE FROM entities WHERE id = ?", head_db)

    assert await _scalar(f"SELECT count(*) FROM entities WHERE id = {head_db}") == 1  # noqa: S608


async def test_revoking_the_consents_clears_the_profiles_and_then_the_person_can_go(
    head_db: int,
) -> None:
    await grant_face_consent(head_db)
    await enroll_face(head_db, np.eye(512, dtype=np.float32)[0], "cara")
    await grant_voice_consent(head_db)
    await enroll_voiceprint(head_db, np.eye(192, dtype=np.float32)[0], "voz", _VOICE_MODEL)
    stamps = await _rows(
        "SELECT created_at FROM face_profiles UNION ALL SELECT created_at FROM voice_profiles"
    )
    assert [len(str(row[0])) for row in stamps] == [INSTANT_LENGTH, INSTANT_LENGTH]

    await revoke_face_consent(head_db)
    await revoke_voice_consent(head_db)
    # The revoked grants stay as the consent history and also refer to the person: only the
    # profiles are under test here, so the history is cleared by hand.
    await _exec("DELETE FROM face_consent_grants WHERE person_entity_id = ?", head_db)
    await _exec("DELETE FROM voice_consent_grants WHERE person_entity_id = ?", head_db)
    await _exec("DELETE FROM entities WHERE id = ?", head_db)

    assert await _scalar("SELECT count(*) FROM face_profiles") == 0
    assert await _scalar("SELECT count(*) FROM voice_profiles") == 0
    assert await _scalar("SELECT count(*) FROM vec_faces") == 0
    assert await _scalar(f"SELECT count(*) FROM entities WHERE id = {head_db}") == 0  # noqa: S608


# --- review gaps (Plan 0085, B7) ---------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["turn", "episode"])
async def test_019_refuses_two_units_for_one_turn_or_one_episode_and_leaves_version_18(
    v18_db: tuple[db.Migration, ...], monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    owner = await upsert_entity(name="Canary Owner", type="person")
    turn = _turn(1, 1, "palabra", TurnVerdict.VERIFIED)
    await record.append_turn(turn, owner_entity_id=owner, now=_T0)
    record_id = int(str(await _scalar("SELECT min(record_id) FROM conversation_turns")))
    if kind == "turn":
        for _ in range(2):
            await _v18_unit(owner, record_id, str(turn.correlation_id))
        constraint = "recall_units.turn_id"
    else:
        episode_id = await _exec(
            "INSERT INTO conversation_episodes (source_record_id, owner_entity_id, visibility, "
            "sensitivity, summary, model, created_at, expires_at) "
            "VALUES (?, ?, 'personal', 'normal', 'resumen', 'canary', ?, ?)",
            record_id,
            owner,
            instant_text(_T0),
            instant_text(_T0 + timedelta(days=1)),
        )
        for _ in range(2):
            await _exec(
                "INSERT INTO recall_units (owner_entity_id, source_record_id, episode_id, kind, "
                "body, said_at, visibility, sensitivity) "
                "VALUES (?, ?, ?, 'episode', 'resumen', ?, 'personal', 'normal')",
                owner,
                record_id,
                episode_id,
                instant_text(_T0),
            )
        constraint = "recall_units.episode_id"
    monkeypatch.setattr(db, "_MIGRATIONS", v18_db)

    with pytest.raises(BrainMemoryError, match=f"UNIQUE constraint failed: {constraint}"):
        await db.run_migrations()

    assert await _scalar("PRAGMA user_version") == 18
    assert await _scalar("SELECT count(*) FROM recall_units") == 2
    assert (
        await _scalar(
            "SELECT count(*) FROM sqlite_master WHERE name IN ('recall_units_turn_idx', "
            "'recall_units_one_per_episode_idx', 'recall_units_body_locked', "
            "'memory_candidates_source_turn_idx', 'pending_topics_source_turn_idx')"
        )
        == 0
    )
    assert (
        await _scalar(
            "SELECT count(*) FROM pragma_table_info('recall_units') WHERE name = 'turn_id'"
        )
        == 0
    )
    assert await _scalar("PRAGMA foreign_keys") == 1


async def test_a_failed_020_names_the_guard_that_fired_and_no_value(
    v19_db: tuple[db.Migration, ...],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    planted = "canary-third-format"
    await _v19_entity("Canary A", planted, "2026-11-16 10:00:03")

    with (
        caplog.at_level(logging.ERROR, logger="server.db"),
        pytest.raises(BrainMemoryError) as raised,
    ):
        await _run_020(v19_db, monkeypatch)

    for text in (str(raised.value), caplog.text):
        assert "a_time_column_holds_a_value_that_is_not_an_exact_instant" in text
        assert planted not in text
    assert await _scalar("PRAGMA user_version") == 19


async def _unchanged_profile_state() -> dict[str, object]:
    """Both profile tables (SQL and rows), their counters and the face vectors, as they are."""
    return {
        "sql": await _rows(
            "SELECT name, sql FROM sqlite_master "
            "WHERE name IN ('face_profiles', 'voice_profiles') ORDER BY name"
        ),
        "indexes": await _rows(
            "SELECT name, tbl_name FROM sqlite_master WHERE type = 'index' "
            "AND tbl_name IN ('face_profiles', 'voice_profiles') ORDER BY name"
        ),
        "face_rows": await _rows("SELECT * FROM face_profiles ORDER BY id"),
        "voice_rows": await _rows("SELECT * FROM voice_profiles ORDER BY id"),
        "counters": await _rows("SELECT name, seq FROM sqlite_sequence ORDER BY name"),
        "vectors": await _rows("SELECT rowid FROM vec_faces ORDER BY rowid"),
    }


async def test_020_failing_after_the_rebuild_leaves_both_profile_tables_as_they_were(
    v19_db: tuple[db.Migration, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    person = await _v19_entity("Canary A", instant_text(_T0), instant_text(_T0))
    await _v19_profiles(person)
    conn = db.get_conn()
    await conn.execute("PRAGMA foreign_keys = OFF")
    await _exec(
        "INSERT INTO face_profiles (id, entity_id, label, created_at) VALUES (9, 9999, 'sin dueño', ?)",
        "2026-11-19 10:00:09",
    )
    await _exec("INSERT INTO vec_faces (rowid, embedding) VALUES (9, ?)", _FACE_BLOB)
    await conn.execute("PRAGMA foreign_keys = ON")
    before = await _unchanged_profile_state()

    with pytest.raises(BrainMemoryError, match="CHECK constraint failed: violations = 0"):
        await _run_020(v19_db, monkeypatch)

    assert await _scalar("PRAGMA user_version") == 19
    assert await _unchanged_profile_state() == before
    assert await _scalar("PRAGMA foreign_keys") == 1
    assert not conn.in_transaction


_DUMMIES = {"INTEGER": "1", "TEXT": "'x'", "REAL": "0.5", "BLOB": "x'00'"}


async def _plant_row_with_times(table: str, stamps: dict[str, str]) -> None:
    """Insert one row into *table*: its time columns get *stamps*, any other required column a dummy.

    The caller has foreign keys and check constraints off, so a dummy needs only its type.
    """
    info = await _rows(
        'SELECT name, upper(type), "notnull", dflt_value, pk '  # noqa: S608
        f"FROM pragma_table_info('{table}') ORDER BY cid"
    )
    values: dict[str, str] = {}
    single_key = sum(1 for row in info if row[4]) == 1
    for name, kind, notnull, default, pk in info:
        if name in stamps:
            values[str(name)] = "'" + stamps[str(name)] + "'"
        elif pk and single_key and kind == "INTEGER":
            continue  # a rowid alias fills itself
        elif (notnull and default is None) or pk:
            values[str(name)] = _DUMMIES.get(str(kind), "'x'")
    columns = ", ".join(f'"{name}"' for name in values)
    await _exec(f'INSERT INTO "{table}" ({columns}) VALUES ({", ".join(values.values())})')  # noqa: S608


@pytest.mark.parametrize(
    "old_format", ["2026-03-04 05:06:{s:02d}", "2026-03-04T05:06:{s:02d}+00:00"]
)
async def test_020_converts_every_time_column_of_the_schema_exactly(
    v19_db: tuple[db.Migration, ...], monkeypatch: pytest.MonkeyPatch, old_format: str
) -> None:
    columns = await time_columns(db.get_conn())
    by_table: dict[str, list[str]] = {}
    for table, column in columns:
        by_table.setdefault(table, []).append(column)
    stamp_of = {pair: index % 60 for index, pair in enumerate(columns)}
    conn = db.get_conn()
    await conn.execute("PRAGMA foreign_keys = OFF")
    await conn.execute("PRAGMA ignore_check_constraints = ON")
    # The retired legacy table refuses new rows; a database that still holds old ones is the case.
    await conn.execute("DROP TRIGGER memories_retired")
    for table, names in by_table.items():
        await _plant_row_with_times(
            table, {name: old_format.format(s=stamp_of[(table, name)]) for name in names}
        )

    for table, name in columns:
        planted = str(await _scalar(f'SELECT "{name}" FROM "{table}"'))  # noqa: S608
        assert len(planted) == len(old_format.format(s=0)), f"{table}.{name} was not planted"

    await _run_020(v19_db, monkeypatch)

    wrong = []
    for table, name in columns:
        found = await _scalar(f'SELECT "{name}" FROM "{table}"')  # noqa: S608
        expected = f"2026-03-04T05:06:{stamp_of[(table, name)]:02d}.000000+00:00"
        if found != expected:
            wrong.append(f"{table}.{name}: {found!r}")
    assert wrong == []


async def test_020_guard_view_lists_exactly_the_time_columns_of_the_schema(
    v19_db: tuple[db.Migration, ...],
) -> None:
    """A new ``*_at`` column that the guard view forgets would escape the exact-instant check."""
    sql = _MIGRATION_020.read_text(encoding="utf-8")
    view = sql[sql.index("CREATE TEMP VIEW _all_times") :]
    view = view[: view.index(";")]
    in_guard = re.findall(r"SELECT '(\w+)', '(\w+)', \w+ FROM \w+", view)

    assert sorted(in_guard) == sorted(await time_columns(db.get_conn()))
