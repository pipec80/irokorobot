"""Migrations 017 to 020 (Plan 0085, Part B): what each one leaves behind and what it refuses.

Every test starts from a database built by the real migrations up to the version before the one
under test, so the migration is exercised on the schema it will meet. Canary rows only.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
import sqlite3
from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from server.exceptions import BrainMemoryError
from server.memory import conversation_record as record
from server.memory.conversation_types import RecordedTurn, TurnVerdict, make_turn
from server.memory.declarative import upsert_entity
from server.settings import settings
from server.timestamps import instant_text

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

# --- 017: the dead tables out --------------------------------------------------------------------

_DEAD_TABLES = (
    "outbox",
    "sensor_current",
    "sensor_readings",
    "sensor_aggregates_hourly",
    "facts",
    "legacy_fact_migration_v4",
    "embeddings_cache",
    "events",
)

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
    await _insert_turn(a_record, heard="x" * 2000, said="y" * 4000)

    assert await _scalar("SELECT count(*) FROM conversation_turns") == 1


@pytest.mark.parametrize(
    "said_at",
    [
        "2026-11-16T10:00:00+00:00",  # no fraction
        "2026-11-16T10:00:00.000000Z",  # not the +00:00 suffix
        "2026-11-16T10:00:00.000000+01:00",  # 32 characters, another offset
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
    [{"verdict": "maybe"}, {"heard": "x" * 2001}, {"said": "y" * 4001}],
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
