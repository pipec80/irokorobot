"""Integration tests for the slot-driven onboarding checklist (F4-D2).

The checklist derives the interview state from the DB, so these tests run
against a real temporary SQLite database. The end-to-end scenario replays
the 2026-07-13 live interview that broke the old heuristic: children
mentioned before the owner introduced himself.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


import pytest
from server.memory.declarative import assert_fact, upsert_entity
from server.memory.meta import set_flag
from server.onboarding import next_missing_slot
from server.settings import settings

from server import db

_OWNER = "Felipe Castro"


@pytest.fixture
async def onboarding_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[misc]
    """Provide a clean temporary DB — a robot that just woke up."""
    db_path = tmp_path / "onboarding.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield db_path
    await db.close_db()
    db._conn = None


async def _anchor_owner() -> int:
    """Set the owner flag and entity, returning the owner's entity id."""
    await set_flag("owner_name", _OWNER)
    return await upsert_entity(name=_OWNER, type="person")


@pytest.mark.integration
async def test_empty_db_asks_for_the_name_first(onboarding_db: Path) -> None:
    """Everything anchors on the owner — the name is always the first slot."""
    slot = await next_missing_slot()

    assert slot is not None
    assert slot.key == "nombre"


@pytest.mark.integration
async def test_anchored_owner_moves_to_birth_date(onboarding_db: Path) -> None:
    await _anchor_owner()

    slot = await next_missing_slot()

    assert slot is not None
    assert slot.key == "fecha_nacimiento"


@pytest.mark.integration
async def test_mandatory_slots_come_before_optionals(onboarding_db: Path) -> None:
    """With only relations missing plus one mandatory, the mandatory wins."""
    owner_id = await _anchor_owner()
    for predicate, value in [
        ("fecha_nacimiento", "12 de marzo de 1980"),
        ("vive_en", "Santiago de Chile"),
        ("trabaja_en", "informática"),
    ]:
        await assert_fact(entity_id=owner_id, predicate=predicate, object_value=value)

    slot = await next_missing_slot()

    assert slot is not None
    assert slot.key == "le_gusta"  # mandatory — beats the pending optionals


@pytest.mark.integration
async def test_relation_covered_by_entity_pointing_at_owner(onboarding_db: Path) -> None:
    """A child fact (child hijo_de owner) covers the hijo_de slot."""
    owner_id = await _anchor_owner()
    for predicate, value in [
        ("fecha_nacimiento", "12 de marzo de 1980"),
        ("vive_en", "Santiago de Chile"),
        ("trabaja_en", "informática"),
        ("le_gusta", "andar en bicicleta"),
    ]:
        await assert_fact(entity_id=owner_id, predicate=predicate, object_value=value)
    child_id = await upsert_entity(name="Martina", type="person")
    await assert_fact(entity_id=child_id, predicate="hijo_de", object_value=_OWNER)

    slot = await next_missing_slot()

    assert slot is not None
    assert slot.key == "pareja_de"  # hijo_de covered — first pending optional


@pytest.mark.integration
async def test_declined_relation_counts_as_covered(onboarding_db: Path) -> None:
    """'no tengo pareja' (fact object 'ninguno' on the owner) covers the slot
    so the robot never insists — the detail that separates charming from
    annoying."""
    owner_id = await _anchor_owner()
    await assert_fact(entity_id=owner_id, predicate="pareja_de", object_value="ninguno")

    keys = set()
    slot = await next_missing_slot()
    while slot is not None and slot.key not in keys:
        keys.add(slot.key)
        await assert_fact(entity_id=owner_id, predicate=slot.key, object_value="dato")
        slot = await next_missing_slot()

    assert "pareja_de" not in keys


@pytest.mark.integration
async def test_all_covered_returns_none(onboarding_db: Path) -> None:
    """Checklist exhausted → None; main.py then persists onboarding_complete."""
    owner_id = await _anchor_owner()
    for predicate in [
        "fecha_nacimiento",
        "vive_en",
        "trabaja_en",
        "le_gusta",
        "pareja_de",
        "hijo_de",
        "mascota_de",
    ]:
        await assert_fact(entity_id=owner_id, predicate=predicate, object_value="dato")

    assert await next_missing_slot() is None
