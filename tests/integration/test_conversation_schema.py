"""Migration 013: the conversation record, the diary, the audit rebuild and the legacy drop.

Plan 0076, ADR 0027. Canary rows only.
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pytest
from server.memory.declarative import upsert_entity
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_T = "2026-10-29T10:00:00.000000+00:00"
_LATER = "2027-10-29T10:00:00.000000+00:00"


@pytest.fixture
async def v13_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "v13.db")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
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


async def _tables() -> set[str]:
    cursor = await db.get_conn().execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    rows = await cursor.fetchall()
    await cursor.close()
    return {str(row[0]) for row in rows}


async def _record(owner: int, *, closed: bool = False, previous: int | None = None) -> int:
    conn = db.get_conn()
    cursor = await conn.execute(
        "INSERT INTO conversation_records (previous_id, owner_entity_id, started_at, last_turn_at, "
        "closed_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
        (previous, owner, _T, _T, _T if closed else None, _LATER if closed else None),
    )
    record_id = int(cursor.lastrowid or 0)
    await cursor.close()
    await conn.commit()
    return record_id


async def test_migration_013_brings_the_schema_to_13(v13_db: int) -> None:
    assert await _scalar("PRAGMA user_version") == 13
    assert db.latest_schema_version() == 13
    assert {
        "conversation_consent_grants",
        "conversation_records",
        "conversation_episodes",
        "admin_audit",
    } <= await _tables()


async def test_the_legacy_vector_index_is_gone_and_memories_takes_no_row(v13_db: int) -> None:
    """`memories` stays only as the parent of four nullable foreign keys; it takes nothing."""
    assert "vec_memories" not in await _tables()

    with pytest.raises(sqlite3.IntegrityError, match="retired"):
        await db.get_conn().execute(
            "INSERT INTO memories (kind, content) VALUES ('episodic', 'canario')"
        )


async def test_deleting_an_entity_still_works_after_the_retirement(v13_db: int) -> None:
    """The child tables keep their foreign key to `memories`; a cascade must not break."""
    child = await upsert_entity(name="Canary Child", type="person")
    await db.get_conn().execute(
        "INSERT INTO facts (entity_id, predicate, object_value) VALUES (?, 'le_gusta', 'mate')",
        (child,),
    )

    await db.get_conn().execute("DELETE FROM entities WHERE id = ?", (child,))

    assert await _scalar("SELECT COUNT(*) FROM facts WHERE entity_id = ?", child) == 0


async def test_a_second_open_segment_is_refused(v13_db: int) -> None:
    await _record(v13_db)

    with pytest.raises(sqlite3.IntegrityError):
        await _record(v13_db)


async def test_turns_must_be_valid_json(v13_db: int) -> None:
    record_id = await _record(v13_db)

    with pytest.raises(sqlite3.IntegrityError):
        await db.get_conn().execute(
            "UPDATE conversation_records SET turns = 'not json' WHERE id = ?", (record_id,)
        )


async def test_closed_and_expiry_go_together(v13_db: int) -> None:
    record_id = await _record(v13_db)

    with pytest.raises(sqlite3.IntegrityError):
        await db.get_conn().execute(
            "UPDATE conversation_records SET closed_at = ? WHERE id = ?", (_T, record_id)
        )


async def test_deleting_a_record_deletes_its_episode_and_unlinks_the_next_segment(
    v13_db: int,
) -> None:
    first = await _record(v13_db, closed=True)
    second = await _record(v13_db, previous=first)
    conn = db.get_conn()
    await conn.execute(
        "INSERT INTO conversation_episodes (source_record_id, owner_entity_id, visibility, "
        "sensitivity, summary, model, created_at, expires_at) "
        "VALUES (?, ?, 'personal', 'normal', 'La persona contó algo.', 'canary', ?, ?)",
        (first, v13_db, _T, _LATER),
    )
    await conn.commit()

    await conn.execute("DELETE FROM conversation_records WHERE id = ?", (first,))
    await conn.commit()

    assert await _scalar("SELECT COUNT(*) FROM conversation_episodes") == 0
    assert (
        await _scalar("SELECT previous_id FROM conversation_records WHERE id = ?", second) is None
    )


@pytest.mark.parametrize(
    "column, value",
    [("visibility", "household"), ("sensitivity", "biometric")],
)
async def test_an_episode_outside_its_closed_lists_is_refused(
    v13_db: int, column: str, value: str
) -> None:
    record_id = await _record(v13_db, closed=True)
    values = {"visibility": "personal", "sensitivity": "normal", column: value}

    with pytest.raises(sqlite3.IntegrityError):
        await db.get_conn().execute(
            "INSERT INTO conversation_episodes (source_record_id, owner_entity_id, visibility, "
            "sensitivity, summary, model, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, 'x', 'canary', ?, ?)",
            (record_id, v13_db, values["visibility"], values["sensitivity"], _T, _LATER),
        )


async def test_one_active_consent_per_person(v13_db: int) -> None:
    sql = (
        "INSERT INTO conversation_consent_grants (person_entity_id, purpose, notice_version, "
        "granted_at) VALUES (?, 'conversation_storage', 'v1', ?)"
    )
    await db.get_conn().execute(sql, (v13_db, _T))

    with pytest.raises(sqlite3.IntegrityError):
        await db.get_conn().execute(sql, (v13_db, _T))


async def test_the_admin_audit_keeps_its_rows_and_accepts_the_new_operations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "upgrade-v12.db")
    db._conn = None
    try:
        await db.open_db()
        full_list = db._MIGRATIONS
        monkeypatch.setattr(db, "_MIGRATIONS", tuple(m for m in full_list if m[0] <= 12))
        await db.run_migrations()
        conn = db.get_conn()
        await conn.execute(
            "INSERT INTO admin_audit (id, recorded_at, actor_label, actor_role, channel, operation, "
            "target_kind, outcome) VALUES (7, ?, 'Canary Admin', 'builder', 'admin_local', 'add', "
            "'pool_literal', 'applied')",
            (_T,),
        )
        await conn.commit()

        monkeypatch.setattr(db, "_MIGRATIONS", full_list)
        await db.run_migrations()

        assert await _scalar("SELECT operation FROM admin_audit WHERE id = 7") == "add"
        await conn.execute(
            "INSERT INTO admin_audit (recorded_at, actor_label, actor_role, channel, operation, "
            "target_kind, outcome) VALUES (?, 'Canary Admin', 'owner', 'admin_local', 'grant', "
            "'conversation_consent', 'applied')",
            (_T,),
        )
        assert await _scalar("SELECT MAX(id) FROM admin_audit") == 8
        with pytest.raises(sqlite3.IntegrityError):
            await conn.execute(
                "INSERT INTO admin_audit (recorded_at, actor_label, actor_role, channel, "
                "operation, target_kind, outcome) VALUES (?, 'Canary Admin', 'owner', "
                "'admin_local', 'wipe', 'conversation_record', 'applied')",
                (_T,),
            )
    finally:
        await db.close_db()
        db._conn = None
