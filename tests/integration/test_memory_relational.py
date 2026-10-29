"""Integration tests for relational memory retrieval (F4-D1).

The acceptance test of the project's core vision: after the robot has
learned the family, questions that name a RELATION instead of a person
("¿cómo se llaman mis hijos?") must resolve to the right entities —
even across a simulated restart (fresh working memory, DB only).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


import pytest
from server.memory.declarative import assert_fact, list_entity_names, upsert_entity
from server.settings import settings

from server import db


@pytest.fixture
async def family_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[misc]
    """Temporary DB seeded with the vision scenario: owner, two kids, one pet."""
    db_path = tmp_path / "family.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)
    db._conn = None
    await db.open_db()
    await db.run_migrations()

    await upsert_entity(name="Pipec", type="person")
    vale = await upsert_entity(name="Valentina", type="person")
    maxi = await upsert_entity(name="Joaquín", type="person")
    luna = await upsert_entity(name="Luna", type="other")
    await assert_fact(entity_id=vale, predicate="hijo_de", object_value="Pipec")
    await assert_fact(entity_id=maxi, predicate="hijo_de", object_value="Pipec")
    await assert_fact(entity_id=luna, predicate="mascota_de", object_value="Pipec")
    await assert_fact(entity_id=luna, predicate="especie", object_value="perra")

    yield db_path
    await db.close_db()
    db._conn = None


@pytest.mark.integration
async def test_list_entity_names_returns_known_names(family_db: Path) -> None:
    """Dynamic hotwords source: every learned name must be available."""
    names = await list_entity_names()

    assert set(names) == {"Pipec", "Valentina", "Joaquín", "Luna"}


@pytest.mark.integration
async def test_list_entity_names_respects_limit(family_db: Path) -> None:
    assert len(await list_entity_names(limit=2)) == 2
