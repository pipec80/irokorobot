"""Integration coverage for conservative legacy-fact migration into v4."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from server.exceptions import BrainMemoryError
from server.memory.declarative import assert_fact, upsert_entity
from server.memory.legacy_v4_migration import migrate_active_legacy_facts
from server.memory.predicate_registry import resolve_predicate
from server.memory.relational_v4 import (
    AssertionLifecycle,
    EntityRelationV4,
    LiteralFactV4,
    get_active_entity_relations,
    get_active_literal_facts,
)
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
async def legacy_v4_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[misc]
    """Create a v3-style legacy fixture with deterministic and deferred records."""
    db_path = tmp_path / "legacy-v4.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)
    db._conn = None
    await db.open_db()
    await db.run_migrations()

    felipe_id = await upsert_entity(name="Felipe", type="person")
    maximo_id = await upsert_entity(name="Joaquin", type="person")
    nina_id = await upsert_entity(name="Nina", type="person")
    await upsert_entity(name="Alex", type="person")
    await db.get_conn().execute(
        "INSERT INTO entities (name, type, attributes, aliases) VALUES (?, ?, ?, ?)",
        ("alex", "person", "{}", "[]"),
    )
    await db.get_conn().commit()
    santiago_id = await upsert_entity(name="Santiago", type="place")

    await assert_fact(
        entity_id=maximo_id,
        predicate="hijo_de",
        object_value="Felipe",
        supersede_existing=False,
    )
    await assert_fact(entity_id=felipe_id, predicate="fecha_nacimiento", object_value="2016-10-14")
    prose_birth_date_id = await assert_fact(
        entity_id=felipe_id,
        predicate="fecha_nacimiento",
        object_value="14 de octubre de 2016",
        supersede_existing=False,
    )
    await assert_fact(
        entity_id=felipe_id,
        predicate="le_gusta",
        object_value="cafe",
        supersede_existing=False,
    )
    await assert_fact(
        entity_id=felipe_id,
        predicate="le_gusta",
        object_value="robotica",
        supersede_existing=False,
    )
    edad_id = await assert_fact(entity_id=maximo_id, predicate="edad", object_value="8")
    none_target_id = await assert_fact(
        entity_id=maximo_id,
        predicate="hijo_de",
        object_value="ninguno",
        supersede_existing=False,
    )
    unsupported_id = await assert_fact(entity_id=felipe_id, predicate="color", object_value="azul")
    await assert_fact(entity_id=felipe_id, predicate="vive_en", object_value="Santiago")
    ambiguous_target_id = await assert_fact(
        entity_id=nina_id,
        predicate="hijo_de",
        object_value="alex",
        supersede_existing=False,
    )
    missing_target_id = await assert_fact(
        entity_id=nina_id,
        predicate="hijo_de",
        object_value="No existe",
        supersede_existing=False,
    )
    olivia_id = await upsert_entity(name="Olivia", type="person")
    superseded_id = await assert_fact(
        entity_id=olivia_id,
        predicate="hijo_de",
        object_value="Felipe",
    )
    await assert_fact(entity_id=olivia_id, predicate="hijo_de", object_value="Joaquin")

    yield {
        "felipe_id": felipe_id,
        "maximo_id": maximo_id,
        "santiago_id": santiago_id,
        "prose_birth_date_id": prose_birth_date_id,
        "edad_id": edad_id,
        "none_target_id": none_target_id,
        "unsupported_id": unsupported_id,
        "ambiguous_target_id": ambiguous_target_id,
        "missing_target_id": missing_target_id,
        "superseded_id": superseded_id,
    }
    await db.close_db()
    db._conn = None


async def _legacy_snapshot() -> list[tuple[object, ...]]:
    """Return immutable evidence that migration never rewrites legacy facts."""
    cursor = await db.get_conn().execute(
        "SELECT id, entity_id, predicate, object_value, confidence, source_memory_id, "
        "asserted_at, superseded_at, superseded_by FROM facts ORDER BY id"
    )
    rows = [tuple(row) for row in await cursor.fetchall()]
    await cursor.close()
    return rows


async def _ledger_outcome(legacy_fact_id: int) -> tuple[str, str] | None:
    """Return the stable migration outcome and reason for one legacy fact."""
    cursor = await db.get_conn().execute(
        "SELECT outcome, reason FROM legacy_fact_migration_v4 WHERE legacy_fact_id = ?",
        (legacy_fact_id,),
    )
    row = await cursor.fetchone()
    await cursor.close()
    return (str(row[0]), str(row[1])) if row is not None else None


@pytest.mark.integration
async def test_legacy_migration_is_dry_run_first_and_idempotent(
    legacy_v4_db: dict[str, int],
) -> None:
    """Only deterministic active facts migrate, with all other outcomes ledgered."""
    before = await _legacy_snapshot()

    dry_run = await migrate_active_legacy_facts(apply=False)
    assert dry_run.ledger_rows_written == 0
    assert await _legacy_snapshot() == before
    cursor = await db.get_conn().execute("SELECT COUNT(*) FROM literal_facts_v4")
    literal_count_row = await cursor.fetchone()
    await cursor.close()
    assert literal_count_row is not None
    assert int(literal_count_row[0]) == 0

    first_apply = await migrate_active_legacy_facts(apply=True)
    second_apply = await migrate_active_legacy_facts(apply=True)
    assert first_apply == second_apply
    assert await _legacy_snapshot() == before

    assert await _ledger_outcome(legacy_v4_db["prose_birth_date_id"]) == (
        "deferred",
        "invalid_literal",
    )
    assert await _ledger_outcome(legacy_v4_db["edad_id"]) == ("rejected", "derived_predicate")
    assert await _ledger_outcome(legacy_v4_db["none_target_id"]) == (
        "rejected",
        "empty_target_value",
    )
    assert await _ledger_outcome(legacy_v4_db["unsupported_id"]) == (
        "rejected",
        "unsupported_predicate",
    )
    assert await _ledger_outcome(legacy_v4_db["ambiguous_target_id"]) == (
        "deferred",
        "ambiguous_target_entity",
    )
    assert await _ledger_outcome(legacy_v4_db["missing_target_id"]) == (
        "deferred",
        "missing_target_entity",
    )
    assert await _ledger_outcome(legacy_v4_db["superseded_id"]) is None

    literals_cursor = await db.get_conn().execute(
        "SELECT predicate, value_text FROM literal_facts_v4 WHERE lifecycle = 'active' ORDER BY value_text"
    )
    literals = {tuple(row) for row in await literals_cursor.fetchall()}
    await literals_cursor.close()
    assert ("likes", "cafe") in literals
    assert ("likes", "robotica") in literals
    assert ("birth_date", "2016-10-14") in literals

    relation_cursor = await db.get_conn().execute(
        "SELECT source_entity_id, predicate, target_entity_id FROM entity_relations_v4 "
        "WHERE lifecycle = 'active'"
    )
    relations = {tuple(row) for row in await relation_cursor.fetchall()}
    await relation_cursor.close()
    assert (legacy_v4_db["maximo_id"], "child_of", legacy_v4_db["felipe_id"]) in relations
    assert (legacy_v4_db["felipe_id"], "lives_in", legacy_v4_db["santiago_id"]) in relations


# --- Plan 0065: migration 010 upgrades a version-9 database in place ---------------------------


@pytest.fixture
async def v9_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[misc]
    """A database migrated only to version 9; yields the full migration list for the upgrade."""
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "upgrade-v9.db")
    db._conn = None
    try:
        await db.open_db()
        full_list = db._MIGRATIONS
        monkeypatch.setattr(db, "_MIGRATIONS", tuple(m for m in full_list if m[0] <= 9))
        await db.run_migrations()
        yield full_list
    finally:
        await db.close_db()
        db._conn = None


@pytest.mark.integration
async def test_migration_ten_upgrades_a_version_nine_database_without_losing_rows(
    v9_db: tuple[tuple[int, str], ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    subject_id = await upsert_entity(name="Canary Child", type="person")
    target_id = await upsert_entity(name="Canary Owner", type="person")
    conn = db.get_conn()
    await conn.execute(
        "INSERT INTO literal_facts_v4 (subject_entity_id, predicate, value_text) "
        "VALUES (?, 'likes', 'el tren')",
        (subject_id,),
    )
    await conn.execute(
        "INSERT INTO entity_relations_v4 (source_entity_id, predicate, target_entity_id) "
        "VALUES (?, 'child_of', ?)",
        (subject_id, target_id),
    )
    await conn.commit()
    cursor = await conn.execute("PRAGMA table_info(literal_facts_v4)")
    assert "asserted_by_entity_id" not in {str(row[1]) for row in await cursor.fetchall()}
    await cursor.close()

    monkeypatch.setattr(db, "_MIGRATIONS", v9_db)
    await db.run_migrations()

    cursor = await conn.execute("PRAGMA user_version")
    assert await cursor.fetchone() == (v9_db[-1][0],)
    await cursor.close()
    for table in ("literal_facts_v4", "entity_relations_v4"):
        cursor = await conn.execute(
            f"SELECT COUNT(*), COUNT(asserted_by_entity_id), COUNT(channel) FROM {table}"  # noqa: S608
        )
        assert await cursor.fetchone() == (1, 0, 0)
        await cursor.close()
    # The repository reads the rows written before the migration through its new column lists.
    likes = resolve_predicate("likes")
    child_of = resolve_predicate("child_of")
    assert likes is not None
    assert child_of is not None
    (old_fact,) = await get_active_literal_facts(subject_entity_id=subject_id, definition=likes)
    (old_relation,) = await get_active_entity_relations(definition=child_of)
    for old_row in (old_fact, old_relation):
        assert (old_row.asserted_by_entity_id, old_row.channel) == (None, None)
    assert (old_fact.value_text, old_relation.source_entity_id) == ("el tren", subject_id)


@pytest.mark.integration
async def test_a_migration_that_fails_halfway_leaves_the_database_at_version_nine(
    v9_db: tuple[tuple[int, str], ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Migration 010 is four ALTER TABLEs: all of them or none, and the version stays 9."""
    conn = db.get_conn()
    # Poison its last statement: the column it adds to the relations table already exists.
    await conn.execute("ALTER TABLE entity_relations_v4 ADD COLUMN channel TEXT")
    await conn.commit()
    monkeypatch.setattr(db, "_MIGRATIONS", v9_db)

    with pytest.raises(BrainMemoryError):
        await db.run_migrations()

    cursor = await conn.execute("PRAGMA user_version")
    assert await cursor.fetchone() == (9,)
    await cursor.close()
    for table in ("literal_facts_v4", "entity_relations_v4"):
        cursor = await conn.execute(f"PRAGMA table_info({table})")
        columns = {str(row[1]) for row in await cursor.fetchall()}
        await cursor.close()
        assert "asserted_by_entity_id" not in columns


def test_the_v4_models_expose_the_asserter_and_channel_with_none_defaults() -> None:
    literal = LiteralFactV4(
        id=1,
        subject_entity_id=2,
        predicate="likes",
        value_text="cafe",
        confidence=0.9,
        source_memory_id=None,
        asserted_at="2026-10-22T10:00:00.000000+00:00",
        valid_from=None,
        valid_to=None,
        lifecycle=AssertionLifecycle.ACTIVE,
        visibility="household",
        sensitivity="normal",
        superseded_at=None,
        superseded_by=None,
    )
    relation = EntityRelationV4(
        id=1,
        source_entity_id=2,
        predicate="child_of",
        target_entity_id=3,
        confidence=0.9,
        source_memory_id=None,
        asserted_at="2026-10-22T10:00:00.000000+00:00",
        valid_from=None,
        valid_to=None,
        lifecycle=AssertionLifecycle.ACTIVE,
        visibility="household",
        sensitivity="child_data",
        superseded_at=None,
        superseded_by=None,
    )

    for model in (literal, relation):
        assert (model.asserted_by_entity_id, model.channel) == (None, None)
