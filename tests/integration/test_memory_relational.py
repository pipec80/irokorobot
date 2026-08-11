"""Integration tests for relational memory retrieval (F4-D1).

The acceptance test of the project's core vision: after the robot has
learned the family, questions that name a RELATION instead of a person
("¿cómo se llaman mis hijos?") must resolve to the right entities —
even across a simulated restart (fresh working memory, DB only).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch
from uuid import UUID

if TYPE_CHECKING:
    from pathlib import Path

import pytest
from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    HouseholdRole,
    IdentityEvidence,
    IdentityEvidenceSource,
)
from server.cognition.models import Confidence, ConfidenceBasis
from server.memory.consolidation import consolidate_turn
from server.memory.context import build_context
from server.memory.declarative import assert_fact, list_entity_names, upsert_entity
from server.memory.meta import set_flag
from server.memory.relations import (
    entities_for_relations,
    find_facts_by_predicate,
    load_entity_by_id,
)
from server.schemas import ExtractedEntity, ExtractedFact, TurnExtraction
from server.settings import settings

from server import db


def _identified_person() -> ActivePersonContext:
    """Create explicit manual evidence for the relational persistence path."""
    observed_at = datetime(2026, 8, 10, tzinfo=UTC)
    confidence = Confidence(
        score=1.0,
        basis=ConfidenceBasis.ASSERTED,
        calibrated=True,
        reason="Explicit local selection",
    )
    return ActivePersonContext(
        person_id=1,
        display_name="Felipe",
        status=ActivePersonStatus.IDENTIFIED,
        confidence=confidence,
        role=HouseholdRole.UNKNOWN,
        evidence=(
            IdentityEvidence(
                evidence_id=UUID("66666666-6666-6666-6666-666666666666"),
                source=IdentityEvidenceSource.MANUAL,
                candidate_person_id=1,
                confidence=confidence,
                observed_at=observed_at,
                expires_at=None,
                reference="trusted-local-adapter",
            ),
        ),
        resolved_at=observed_at,
    )


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
    maxi = await upsert_entity(name="Máximo", type="person")
    luna = await upsert_entity(name="Luna", type="other")
    await assert_fact(entity_id=vale, predicate="hijo_de", object_value="Pipec")
    await assert_fact(entity_id=maxi, predicate="hijo_de", object_value="Pipec")
    await assert_fact(entity_id=luna, predicate="mascota_de", object_value="Pipec")
    await assert_fact(entity_id=luna, predicate="especie", object_value="perra")

    yield db_path
    await db.close_db()
    db._conn = None


@pytest.mark.integration
async def test_find_facts_by_predicate_returns_all_children(family_db: Path) -> None:
    rows = await find_facts_by_predicate("hijo_de")

    names = {name for _id, name, _obj in rows}
    assert names == {"Valentina", "Máximo"}


@pytest.mark.integration
async def test_find_facts_by_predicate_filters_by_object(family_db: Path) -> None:
    assert await find_facts_by_predicate("hijo_de", object_value="Pipec") != []
    assert await find_facts_by_predicate("hijo_de", object_value="Otra") == []


@pytest.mark.integration
async def test_list_entity_names_returns_known_names(family_db: Path) -> None:
    """Dynamic hotwords source: every learned name must be available."""
    names = await list_entity_names()

    assert set(names) == {"Pipec", "Valentina", "Máximo", "Luna"}


@pytest.mark.integration
async def test_list_entity_names_respects_limit(family_db: Path) -> None:
    assert len(await list_entity_names(limit=2)) == 2


@pytest.mark.integration
async def test_find_facts_excludes_superseded(family_db: Path) -> None:
    """A corrected relation must disappear from reverse lookups."""
    rows = await find_facts_by_predicate("especie")
    (luna_id, _, _) = rows[0]
    await assert_fact(entity_id=luna_id, predicate="especie", object_value="gata")

    values = {obj for _id, _name, obj in await find_facts_by_predicate("especie")}
    assert values == {"gata"}


@pytest.mark.integration
async def test_load_entity_by_id_missing_returns_none(family_db: Path) -> None:
    assert await load_entity_by_id(99_999) is None


@pytest.mark.integration
async def test_entities_for_relations_no_trigger_no_query(family_db: Path) -> None:
    assert await entities_for_relations("hola cómo estás") == []


@pytest.mark.integration
async def test_vision_como_se_llaman_mis_hijos(family_db: Path) -> None:
    """THE core vision question: no child is named, yet both must appear."""
    with patch(
        "server.memory.context.search_memories",
        new_callable=AsyncMock,
        return_value=[],
    ):
        ctx = await build_context("¿cómo se llaman mis hijos?")

    names = {e.name for e in ctx.entities}
    assert {"Valentina", "Máximo"} <= names


@pytest.mark.integration
async def test_vision_como_se_llama_mi_mascota(family_db: Path) -> None:
    """The pet question must surface Luna WITH her facts (species included)."""
    with patch(
        "server.memory.context.search_memories",
        new_callable=AsyncMock,
        return_value=[],
    ):
        ctx = await build_context("¿cómo se llama mi mascota?")

    luna = next((e for e in ctx.entities if e.name == "Luna"), None)
    assert luna is not None
    predicates = {f.predicate for f in luna.facts}
    assert {"mascota_de", "especie"} <= predicates


@pytest.mark.integration
async def test_dirty_extraction_repaired_end_to_end(family_db: Path) -> None:
    """The exact 2026-07-06 failure, repaired: dirty qwen output → clean facts.

    consolidate_turn receives the inverted/invented extraction observed live
    and, after guardrails, the relational question must find the child.
    """
    await set_flag("owner_name", "Felipe")
    dirty = TurnExtraction(
        entities=[ExtractedEntity(name="dominga", type="person")],
        facts=[
            ExtractedFact(subject="usuario", predicate="tiene_hijo_de", object="dominga"),
            ExtractedFact(subject="Felipe", predicate="trabaja_en", object=""),
        ],
        episodic_summary=None,
        importance=0.6,
    )
    with (
        patch(
            "server.memory.consolidation._extract",
            new_callable=AsyncMock,
            return_value=dirty,
        ),
        patch(
            "server.memory.consolidation.store_memory",
            new_callable=AsyncMock,
            return_value=1,
        ),
    ):
        await consolidate_turn(
            "tengo una hija dominga", "¡Qué lindo!", active_person=_identified_person()
        )

    children = {name for _id, name, _obj in await find_facts_by_predicate("hijo_de")}
    assert "Dominga" in children  # title-cased, direction repaired
    # The empty-object fact must not exist
    assert await find_facts_by_predicate("trabaja_en") == []


@pytest.mark.integration
async def test_relational_and_forward_lookup_dedupe(family_db: Path) -> None:
    """Naming a child AND the relation must not duplicate the entity."""
    with patch(
        "server.memory.context.search_memories",
        new_callable=AsyncMock,
        return_value=[],
    ):
        ctx = await build_context("¿Valentina es mi hija?")

    ids = [e.id for e in ctx.entities]
    assert len(ids) == len(set(ids))
    assert "Valentina" in {e.name for e in ctx.entities}
