"""The legacy migration defers a fact whose entity type the predicate does not allow (Plan 0065).

Plan 0065 registered `species` with the Spanish alias `especie`. A legacy `especie` fact on an
entity the extractor typed as a person used to be rejected as an unsupported predicate; it would
now be classified as migrated, and the write would raise and stop the whole `--apply` run. The
classification must see the entity type, so the dry-run and the apply agree and the run goes on.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from server.memory.declarative import assert_fact, upsert_entity
from server.memory.legacy_v4_migration import migrate_active_legacy_facts
from server.memory.predicate_registry import resolve_predicate
from server.memory.relational_v4 import get_active_literal_facts
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration


@pytest.fixture
async def legacy_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "legacy-subject-types.db")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        yield
    finally:
        await db.close_db()
        db._conn = None


async def _ledger_reasons() -> list[str]:
    cursor = await db.get_conn().execute(
        "SELECT outcome || ':' || reason FROM legacy_fact_migration_v4 ORDER BY legacy_fact_id"
    )
    rows = await cursor.fetchall()
    await cursor.close()
    return [str(row[0]) for row in rows]


async def test_a_species_fact_on_a_pet_is_migrated(legacy_db: None) -> None:
    pet = await upsert_entity(name="Canary Pet", type="other")
    await assert_fact(entity_id=pet, predicate="especie", object_value="gato")

    counts = await migrate_active_legacy_facts(apply=True)

    assert (counts.migrated, counts.deferred) == (1, 0)
    species = resolve_predicate("species")
    assert species is not None
    stored = await get_active_literal_facts(subject_entity_id=pet, definition=species)
    assert [fact.value_text for fact in stored] == ["gato"]


async def test_a_species_fact_on_a_person_is_deferred_and_the_run_goes_on(legacy_db: None) -> None:
    """The extractor once typed pets as persons: the dry-run and the apply must agree."""
    mistyped_pet = await upsert_entity(name="Canary Mistyped Pet", type="person")
    owner = await upsert_entity(name="Canary Owner", type="person")
    await assert_fact(entity_id=mistyped_pet, predicate="especie", object_value="perro")
    await assert_fact(entity_id=owner, predicate="fecha_nacimiento", object_value="1980-02-03")

    dry = await migrate_active_legacy_facts(apply=False)
    applied = await migrate_active_legacy_facts(apply=True)

    assert (dry.migrated, dry.deferred) == (1, 1)
    assert (applied.migrated, applied.deferred) == (1, 1)
    assert "deferred:subject_type_mismatch" in await _ledger_reasons()


async def test_a_birth_date_on_a_pet_is_deferred_too(legacy_db: None) -> None:
    """The same hazard existed before for any predicate with a narrower subject type."""
    pet = await upsert_entity(name="Canary Pet", type="other")
    await assert_fact(entity_id=pet, predicate="fecha_nacimiento", object_value="2019-05-06")

    counts = await migrate_active_legacy_facts(apply=True)

    assert (counts.migrated, counts.deferred) == (0, 1)
    assert await _ledger_reasons() == ["deferred:subject_type_mismatch"]


async def test_a_legacy_access_code_is_deferred_and_never_stored(legacy_db: None) -> None:
    """`access_code` is its own alias: a legacy fact so named must not stop the run (ADR 0022)."""
    owner = await upsert_entity(name="Canary Owner", type="person")
    await assert_fact(entity_id=owner, predicate="access_code", object_value="canary-code-9")

    dry = await migrate_active_legacy_facts(apply=False)
    applied = await migrate_active_legacy_facts(apply=True)

    assert (dry.migrated, dry.deferred) == (0, 1)
    assert (applied.migrated, applied.deferred) == (0, 1)
    assert await _ledger_reasons() == ["deferred:security_storage_undecided"]
    cursor = await db.get_conn().execute("SELECT COUNT(*) FROM literal_facts_v4")
    assert await cursor.fetchone() == (0,)
    await cursor.close()
