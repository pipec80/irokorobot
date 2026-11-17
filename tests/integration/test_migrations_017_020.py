"""Migrations 017 to 020 (Plan 0085, Part B): what each one leaves behind and what it refuses.

Every test starts from a database built by the real migrations up to the version before the one
under test, so the migration is exercised on the schema it will meet. Canary rows only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from server.exceptions import BrainMemoryError
from server.settings import settings

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


@pytest.fixture
async def v16_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[db.Migration, ...]]:
    """A database built by the real migrations up to 16; yields the full migration list."""
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "migrations-017.db")
    db._conn = None
    try:
        await db.open_db()
        every_migration = db._MIGRATIONS
        monkeypatch.setattr(db, "_MIGRATIONS", tuple(m for m in every_migration if m[0] <= 16))
        await db.run_migrations()
        yield every_migration
    finally:
        await db.close_db()
        db._conn = None


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
