"""Integration tests for the brain memory subsystem wiring.

These tests exercise the DB-backed memory modules (declarative, context,
consolidation) with a real temporary SQLite database. External services
(Ollama for embeddings and consolidation) are mocked.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

if TYPE_CHECKING:
    from pathlib import Path

import pytest
from server.memory import working
from server.memory.consolidation import consolidate_turn
from server.memory.context import build_context
from server.memory.declarative import (
    assert_fact,
    find_entities_by_name,
    get_active_facts,
    upsert_entity,
)
from server.memory.meta import get_flag, set_flag
from server.schemas import ExtractedEntity, ExtractedFact, MemoryContext, TurnExtraction
from server.settings import settings

from server import db


@pytest.fixture
async def memory_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[misc]
    """Provide a clean temporary DB for each test."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)

    # Reset the module-level connection so open_db creates a fresh one
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield db_path
    await db.close_db()
    db._conn = None


@pytest.fixture(autouse=True)
def _clean_working_memory() -> None:  # type: ignore[misc]
    """Clear working memory between tests."""
    working._buffers.clear()
    yield  # type: ignore[misc]
    working._buffers.clear()


@pytest.mark.integration
async def test_upsert_entity_returns_positive_id(memory_db: Path) -> None:
    """upsert_entity must return a positive row id."""
    entity_id = await upsert_entity(name="María", type="person")

    assert entity_id > 0


@pytest.mark.integration
async def test_assert_fact_supersedes_old(memory_db: Path) -> None:
    """A new fact with the same predicate supersedes the previous one."""
    eid = await upsert_entity(name="Carlos", type="person")
    await assert_fact(entity_id=eid, predicate="vive_en", object_value="CDMX")
    await assert_fact(entity_id=eid, predicate="vive_en", object_value="Monterrey")

    facts = await get_active_facts(eid)

    assert len(facts) == 1
    assert facts[0].object_value == "Monterrey"


@pytest.mark.integration
async def test_assert_fact_records_superseded_by(memory_db: Path) -> None:
    """Superseded facts must record WHICH fact replaced them (full versioning)."""
    eid = await upsert_entity(name="Luna", type="other")
    old_id = await assert_fact(entity_id=eid, predicate="especie", object_value="perro")
    new_id = await assert_fact(entity_id=eid, predicate="especie", object_value="gata")

    cur = await db.get_conn().execute("SELECT superseded_by FROM facts WHERE id = ?", (old_id,))
    row = await cur.fetchone()
    await cur.close()

    assert row is not None
    assert row[0] == new_id


@pytest.mark.integration
async def test_build_context_empty_db(memory_db: Path) -> None:
    """build_context on an empty DB must return empty MemoryContext."""
    with patch(
        "server.memory.context.search_memories",
        new_callable=AsyncMock,
        return_value=[],
    ):
        ctx = await build_context("hola mundo")

    assert isinstance(ctx, MemoryContext)
    assert ctx.entities == []
    assert ctx.memories == []


@pytest.mark.integration
async def test_build_context_finds_known_entity(memory_db: Path) -> None:
    """build_context must find entities already in the DB."""
    await upsert_entity(name="María", type="person")
    await assert_fact(
        entity_id=1,
        predicate="vive_en",
        object_value="CDMX",
    )

    with patch(
        "server.memory.context.search_memories",
        new_callable=AsyncMock,
        return_value=[],
    ):
        ctx = await build_context("Qué sabes de María")

    assert len(ctx.entities) == 1
    assert ctx.entities[0].name == "María"
    assert ctx.entities[0].facts[0].object_value == "CDMX"


@pytest.mark.integration
async def test_upsert_entity_dedupes_accent_variants(memory_db: Path) -> None:
    """Whisper drops accents ("Máximo"→"Maximo") — variants must merge into
    ONE entity, keeping the incoming spelling as an alias."""
    original_id = await upsert_entity(name="Máximo", type="person")

    variant_id = await upsert_entity(name="Maximo", type="person")

    assert variant_id == original_id
    matches = await find_entities_by_name("Máximo", limit=5)
    assert len(matches) == 1
    assert "Maximo" in matches[0]["aliases"]


@pytest.mark.integration
async def test_upsert_entity_dedupes_case_variants(memory_db: Path) -> None:
    """'maría' (Whisper lowercase) and 'María' must be the same entity."""
    a = await upsert_entity(name="María", type="person")
    b = await upsert_entity(name="maría", type="person")

    assert a == b


@pytest.mark.integration
async def test_upsert_entity_same_folded_name_different_type_stays_separate(
    memory_db: Path,
) -> None:
    """Folding dedups within a type only — Luna(person) ≠ Luna(other)."""
    person = await upsert_entity(name="Luna", type="person")
    pet = await upsert_entity(name="Luna", type="other")

    assert person != pet


@pytest.mark.integration
async def test_meta_flag_roundtrip(memory_db: Path) -> None:
    """set_flag/get_flag must persist and update values (migration v2)."""
    assert await get_flag("onboarding_complete") is None

    await set_flag("onboarding_complete", "true")
    assert await get_flag("onboarding_complete") == "true"

    await set_flag("onboarding_complete", "false")
    assert await get_flag("onboarding_complete") == "false"


@pytest.mark.integration
async def test_run_migrations_is_idempotent(memory_db: Path) -> None:
    """Running migrations twice on an up-to-date DB must be a no-op."""
    await db.run_migrations()
    await db.run_migrations()

    cur = await db.get_conn().execute("PRAGMA user_version")
    row = await cur.fetchone()
    await cur.close()
    assert row is not None
    assert int(row[0]) == db._MIGRATIONS[-1][0]


@pytest.mark.integration
async def test_consolidating_self_intro_anchors_owner(memory_db: Path) -> None:
    """'me llamo X' must anchor owner_name — and ONLY anchor it: onboarding
    completion now belongs to the checklist (F4-D2), not to consolidation."""
    fake_extraction = TurnExtraction(
        entities=[ExtractedEntity(name="Pipec", type="person")],
        facts=[],
        episodic_summary="El dueño se presentó.",
        importance=0.9,
    )
    with (
        patch(
            "server.memory.consolidation._extract",
            new_callable=AsyncMock,
            return_value=fake_extraction,
        ),
        patch(
            "server.memory.consolidation.store_memory",
            new_callable=AsyncMock,
            return_value=1,
        ),
    ):
        await consolidate_turn("me llamo Pipec", "¡Un gusto, Pipec!")

    assert await get_flag("owner_name") == "Pipec"
    assert await get_flag("onboarding_complete") is None


@pytest.mark.integration
async def test_implicit_owner_entity_is_person(memory_db: Path) -> None:
    """A fact whose subject is the owner creates a PERSON entity, not a
    concept ("Felipe [concept]" observed in the DB 2026-07-14)."""
    await set_flag("owner_name", "Felipe")
    fake_extraction = TurnExtraction(
        entities=[],
        facts=[
            ExtractedFact(
                subject="usuario", predicate="fecha_nacimiento", object="6 de octubre de 1981"
            )
        ],
        importance=0.8,
    )
    with (
        patch(
            "server.memory.consolidation._extract",
            new_callable=AsyncMock,
            return_value=fake_extraction,
        ),
        patch(
            "server.memory.consolidation.store_memory",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        await consolidate_turn("nací el 6 de octubre de 1981", "¡Qué fecha!")

    matches = await find_entities_by_name("Felipe", limit=1)
    assert matches
    assert matches[0]["type"] == "person"


@pytest.mark.integration
async def test_consolidate_turn_with_mocked_ollama(memory_db: Path) -> None:
    """consolidate_turn must extract and persist entities when Ollama is mocked."""

    fake_extraction = TurnExtraction(
        entities=[ExtractedEntity(name="Luna", type="person")],
        facts=[ExtractedFact(subject="Luna", predicate="es", object="un gato")],
        episodic_summary="El usuario habla de su gato Luna.",
        importance=0.8,
    )

    with (
        patch(
            "server.memory.consolidation._extract_via_ollama",
            new_callable=AsyncMock,
            return_value=fake_extraction,
        ),
        patch(
            "server.memory.consolidation.store_memory",
            new_callable=AsyncMock,
            return_value=1,
        ),
    ):
        await consolidate_turn("Mi gato Luna es muy juguetón", "Qué bonito")

    entities = await find_entities_by_name("Luna")
    assert len(entities) >= 1
    assert entities[0]["name"] == "Luna"
