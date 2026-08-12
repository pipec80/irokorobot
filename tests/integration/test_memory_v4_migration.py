"""Integration coverage for conservative legacy-fact migration into v4."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from server.memory.declarative import assert_fact, upsert_entity
from server.memory.legacy_v4_migration import migrate_active_legacy_facts
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
    maximo_id = await upsert_entity(name="Maximo", type="person")
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
    await assert_fact(entity_id=felipe_id, predicate="fecha_nacimiento", object_value="2017-12-29")
    prose_birth_date_id = await assert_fact(
        entity_id=felipe_id,
        predicate="fecha_nacimiento",
        object_value="29 de diciembre de 2017",
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
    await assert_fact(entity_id=olivia_id, predicate="hijo_de", object_value="Maximo")

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
    assert ("birth_date", "2017-12-29") in literals

    relation_cursor = await db.get_conn().execute(
        "SELECT source_entity_id, predicate, target_entity_id FROM entity_relations_v4 "
        "WHERE lifecycle = 'active'"
    )
    relations = {tuple(row) for row in await relation_cursor.fetchall()}
    await relation_cursor.close()
    assert (legacy_v4_db["maximo_id"], "child_of", legacy_v4_db["felipe_id"]) in relations
    assert (legacy_v4_db["felipe_id"], "lives_in", legacy_v4_db["santiago_id"]) in relations
