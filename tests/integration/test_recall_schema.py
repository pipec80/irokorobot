"""Migration 014: the recall units, their FTS5 and ``vec0`` indexes, and the cascade.

Plan 0078, ADR 0028 decision 1. Canary rows only.
"""

from __future__ import annotations

import sqlite3
import struct
from typing import TYPE_CHECKING

import pytest
from server.memory.declarative import upsert_entity
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_T = "2026-11-03T10:00:00.000000+00:00"
_LATER = "2027-11-03T10:00:00.000000+00:00"
_DIMENSIONS = 768


@pytest.fixture
async def v14_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "v14.db")
    # The schema as migration 014 left it; migration 015 has its own test (Plan 0083).
    monkeypatch.setattr(db, "_MIGRATIONS", tuple(m for m in db._MIGRATIONS if m[0] <= 14))
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        yield await upsert_entity(name="Canary Owner", type="person")
    finally:
        await db.close_db()
        db._conn = None


def _vector(axis: int) -> bytes:
    """A unit vector along *axis*, packed as ``float32`` for ``vec0``."""
    values = [0.0] * _DIMENSIONS
    values[axis] = 1.0
    return struct.pack(f"{_DIMENSIONS}f", *values)


async def _scalar(sql: str, *params: object) -> object:
    cursor = await db.get_conn().execute(sql, params)
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    return row[0]


async def _record(owner: int) -> int:
    conn = db.get_conn()
    cursor = await conn.execute(
        "INSERT INTO conversation_records (owner_entity_id, started_at, last_turn_at, closed_at, "
        "expires_at) VALUES (?, ?, ?, ?, ?)",
        (owner, _T, _T, _T, _LATER),
    )
    record_id = int(cursor.lastrowid or 0)
    await cursor.close()
    return record_id


async def _turn_unit(owner: int, record_id: int, body: str, *, sensitivity: str = "normal") -> int:
    conn = db.get_conn()
    cursor = await conn.execute(
        "INSERT INTO recall_units (owner_entity_id, source_record_id, kind, body, said_at, "
        "visibility, sensitivity, correlation_id) VALUES (?, ?, 'turn', ?, ?, 'personal', ?, ?)",
        (owner, record_id, body, _T, sensitivity, "00000000-0000-0000-0000-000000000001"),
    )
    unit_id = int(cursor.lastrowid or 0)
    await cursor.close()
    return unit_id


async def _vector_row(owner: int, unit_id: int, axis: int, sensitivity: str = "normal") -> None:
    await db.get_conn().execute(
        "INSERT INTO recall_units_vec (rowid, owner_entity_id, sensitivity, embedding) "
        "VALUES (?, ?, ?, ?)",
        (unit_id, owner, sensitivity, _vector(axis)),
    )


async def _normal_neighbours(owner: int, axis: int) -> list[int]:
    cursor = await db.get_conn().execute(
        "SELECT rowid FROM recall_units_vec WHERE embedding MATCH ? AND k = 5 "
        "AND owner_entity_id = ? AND sensitivity = 'normal'",
        (_vector(axis), owner),
    )
    rows = await cursor.fetchall()
    await cursor.close()
    return [int(row[0]) for row in rows]


async def test_migration_014_sets_user_version_14(v14_db: int) -> None:
    assert await _scalar("PRAGMA user_version") == 14
    assert db.latest_schema_version() == 14


async def test_deleting_a_record_deletes_its_units_fts_rows_and_vectors(v14_db: int) -> None:
    record_id = await _record(v14_db)
    unit_id = await _turn_unit(v14_db, record_id, "fuimos al cerro con Zeta")
    await _vector_row(v14_db, unit_id, 0)

    await db.get_conn().execute("DELETE FROM conversation_records WHERE id = ?", (record_id,))

    assert await _scalar("SELECT COUNT(*) FROM recall_units") == 0
    fts_rows = await _scalar(
        "SELECT COUNT(*) FROM recall_units_fts WHERE recall_units_fts MATCH 'cerro'"
    )
    assert fts_rows == 0
    assert await _scalar("SELECT COUNT(*) FROM recall_units_vec") == 0


async def _shadow_blobs() -> list[bytes]:
    """Every blob and text cell of the recall indexes' shadow tables."""
    conn = db.get_conn()
    cursor = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'recall_units_%'"
    )
    names = [str(row[0]) for row in await cursor.fetchall()]
    await cursor.close()
    cells: list[bytes] = []
    for name in names:
        cursor = await conn.execute(f'SELECT * FROM "{name}"')  # noqa: S608 - names from the schema
        for row in await cursor.fetchall():
            cells.extend(
                value if isinstance(value, bytes) else str(value).encode()
                for value in row
                if value is not None
            )
        await cursor.close()
    return cells


async def test_a_deleted_unit_leaves_no_word_and_no_vector_in_the_indexes(v14_db: int) -> None:
    """Forgetting reaches the indexes' storage, not only their answers (secure-delete)."""
    record_id = await _record(v14_db)
    gone = await _turn_unit(v14_db, record_id, "zzcanaryzz fue al cerro")
    # A dense vector of one odd value: a sparse one would match a slice of its neighbour.
    marker = struct.pack(f"{_DIMENSIONS}f", *([0.0361] * _DIMENSIONS))
    await db.get_conn().execute(
        "INSERT INTO recall_units_vec (rowid, owner_entity_id, sensitivity, embedding) "
        "VALUES (?, ?, 'normal', ?)",
        (gone, v14_db, marker),
    )
    kept = await _turn_unit(v14_db, record_id, "otra palabra cualquiera")
    await _vector_row(v14_db, kept, 5)

    await db.get_conn().execute("DELETE FROM recall_units WHERE id = ?", (gone,))
    await db.get_conn().commit()

    cells = await _shadow_blobs()
    assert not any(b"zzcanaryzz" in cell for cell in cells)
    assert not any(marker[:64] in cell for cell in cells)


async def test_raising_sensitivity_moves_the_vector_out_of_a_normal_search(v14_db: int) -> None:
    record_id = await _record(v14_db)
    unit_id = await _turn_unit(v14_db, record_id, "me duele la rodilla")
    await _vector_row(v14_db, unit_id, 1)
    assert await _normal_neighbours(v14_db, 1) == [unit_id]

    await db.get_conn().execute(
        "UPDATE recall_units SET sensitivity = 'medical' WHERE id = ?", (unit_id,)
    )

    assert await _normal_neighbours(v14_db, 1) == []


async def test_fts_finds_a_word_without_its_accent(v14_db: int) -> None:
    record_id = await _record(v14_db)
    unit_id = await _turn_unit(v14_db, record_id, "mi papá tomaba mate")

    cursor = await db.get_conn().execute(
        "SELECT rowid FROM recall_units_fts WHERE recall_units_fts MATCH 'papa'"
    )
    rows = await cursor.fetchall()
    await cursor.close()

    assert [int(row[0]) for row in rows] == [unit_id]


async def test_vector_distance_is_cosine(v14_db: int) -> None:
    record_id = await _record(v14_db)
    unit_id = await _turn_unit(v14_db, record_id, "canario")
    await _vector_row(v14_db, unit_id, 2)

    distance = await _scalar(
        "SELECT distance FROM recall_units_vec WHERE embedding MATCH ? AND k = 1 "
        "AND owner_entity_id = ?",
        _vector(3),
        v14_db,
    )

    assert float(str(distance)) == pytest.approx(1.0, abs=0.001)


async def test_a_turn_unit_needs_a_correlation_id_and_no_episode(v14_db: int) -> None:
    record_id = await _record(v14_db)

    with pytest.raises(sqlite3.IntegrityError):
        await db.get_conn().execute(
            "INSERT INTO recall_units (owner_entity_id, source_record_id, kind, body, said_at, "
            "visibility, sensitivity) VALUES (?, ?, 'turn', 'canario', ?, 'personal', 'normal')",
            (v14_db, record_id, _T),
        )


async def test_an_episode_unit_needs_an_episode_and_no_correlation_id(v14_db: int) -> None:
    record_id = await _record(v14_db)

    with pytest.raises(sqlite3.IntegrityError):
        await db.get_conn().execute(
            "INSERT INTO recall_units (owner_entity_id, source_record_id, kind, body, said_at, "
            "visibility, sensitivity, correlation_id) "
            "VALUES (?, ?, 'episode', 'canario', ?, 'personal', 'normal', 'cid')",
            (v14_db, record_id, _T),
        )


async def test_close_db_runs_optimize_before_closing(v14_db: int) -> None:
    statements: list[str] = []
    await db.get_conn().set_trace_callback(statements.append)

    await db.close_db()

    assert "PRAGMA optimize" in statements
    assert not db.is_open()
