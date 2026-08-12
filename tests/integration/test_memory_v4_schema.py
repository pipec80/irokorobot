"""Integration coverage for additive relational-memory v4 schema."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from server.memory.declarative import assert_fact, upsert_entity
from server.memory.predicate_registry import resolve_predicate
from server.memory.relational_v4 import assert_literal_fact
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
async def v4_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[misc]
    """Open a fresh database with every additive migration applied."""
    db_path = tmp_path / "memory-v4-schema.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield
    await db.close_db()
    db._conn = None


@pytest.mark.integration
async def test_v4_schema_is_additive_and_preserves_legacy_facts(v4_db: None) -> None:
    """Version 4 adds isolated tables without changing legacy fact behavior."""
    conn = db.get_conn()
    version_cursor = await conn.execute("PRAGMA user_version")
    version_row = await version_cursor.fetchone()
    await version_cursor.close()
    assert version_row == (4,)

    tables_cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    tables = {str(row[0]) for row in await tables_cursor.fetchall()}
    await tables_cursor.close()
    assert {"literal_facts_v4", "entity_relations_v4", "legacy_fact_migration_v4"} <= tables

    owner_id = await upsert_entity(name="Felipe", type="person")
    await assert_fact(entity_id=owner_id, predicate="alias", object_value="Pipe")
    before_cursor = await conn.execute("SELECT COUNT(*) FROM facts")
    legacy_count_before_row = await before_cursor.fetchone()
    await before_cursor.close()
    assert legacy_count_before_row is not None
    legacy_count_before = int(legacy_count_before_row[0])

    likes = resolve_predicate("likes")
    assert likes is not None
    await assert_literal_fact(subject_entity_id=owner_id, definition=likes, value="robotica")

    after_cursor = await conn.execute("SELECT COUNT(*) FROM facts")
    legacy_count_after_row = await after_cursor.fetchone()
    await after_cursor.close()
    assert legacy_count_after_row is not None
    legacy_count_after = int(legacy_count_after_row[0])
    assert legacy_count_after == legacy_count_before

    foreign_key_cursor = await conn.execute("PRAGMA foreign_key_check")
    assert await foreign_key_cursor.fetchall() == []
    await foreign_key_cursor.close()
