"""The legacy migration never writes a fact whose predicate belongs to the data pool (Plan 0070).

Plan 0070 registered the predicates of the commissioning data pool with Spanish aliases such as
`direccion`, `movilidad` or `piso`. A legacy fact so named used to be rejected as an unsupported
predicate; it would now resolve and be written as a household fact. The pool is loaded through
the canonical writer only, so the migration defers such a fact under a closed ledger reason.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from server.memory.declarative import assert_fact, upsert_entity
from server.memory.legacy_v4_migration import migrate_active_legacy_facts
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_LEGACY_POOL_FACTS = (
    ("direccion", "Calle Inventada 1"),
    ("movilidad", "solo"),
    ("piso", "3"),
    ("quien_conoce_el_secreto", "la vecina"),
    ("tiene_hermano_o_hermana", "Canary Sibling"),
)


@pytest.fixture
async def legacy_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "legacy-pool-predicates.db")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        yield
    finally:
        await db.close_db()
        db._conn = None


async def _scalar(sql: str) -> int:
    cursor = await db.get_conn().execute(sql)
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    return int(row[0])


async def test_a_legacy_fact_of_a_pool_predicate_is_deferred_and_never_written(
    legacy_db: None,
) -> None:
    owner = await upsert_entity(name="Canary Owner", type="person")
    await upsert_entity(name="Canary Sibling", type="person")
    for predicate, value in _LEGACY_POOL_FACTS:
        await assert_fact(entity_id=owner, predicate=predicate, object_value=value)

    dry = await migrate_active_legacy_facts(apply=False)
    applied = await migrate_active_legacy_facts(apply=True)

    expected = len(_LEGACY_POOL_FACTS)
    assert (dry.migrated, dry.deferred) == (0, expected)
    assert (applied.migrated, applied.deferred) == (0, expected)
    assert await _scalar("SELECT COUNT(*) FROM literal_facts_v4") == 0
    assert await _scalar("SELECT COUNT(*) FROM entity_relations_v4") == 0
    assert (
        await _scalar(
            "SELECT COUNT(*) FROM legacy_fact_migration_v4 "
            "WHERE outcome = 'deferred' AND reason = 'pool_predicate_not_migrated'"
        )
        == expected
    )
