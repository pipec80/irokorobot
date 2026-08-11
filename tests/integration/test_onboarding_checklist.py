"""Integration tests for the slot-driven onboarding checklist (F4-D2).

The checklist derives the interview state from the DB, so these tests run
against a real temporary SQLite database. The end-to-end scenario replays
the 2026-07-13 live interview that broke the old heuristic: children
mentioned before the owner introduced himself.
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
from server.memory.declarative import assert_fact, upsert_entity
from server.memory.meta import get_flag, set_flag
from server.onboarding import next_missing_slot
from server.schemas import ExtractedEntity, ExtractedFact, TurnExtraction
from server.settings import settings

from server import db

_OWNER = "Felipe Castro"


def _identified_person() -> ActivePersonContext:
    """Create explicit manual evidence for consolidation compatibility tests."""
    observed_at = datetime(2026, 8, 10, tzinfo=UTC)
    confidence = Confidence(
        score=1.0,
        basis=ConfidenceBasis.ASSERTED,
        calibrated=True,
        reason="Explicit local selection",
    )
    return ActivePersonContext(
        person_id=1,
        display_name=_OWNER,
        status=ActivePersonStatus.IDENTIFIED,
        confidence=confidence,
        role=HouseholdRole.UNKNOWN,
        evidence=(
            IdentityEvidence(
                evidence_id=UUID("55555555-5555-5555-5555-555555555555"),
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
    child_id = await upsert_entity(name="Dominga", type="person")
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


def _turn(entities: list[ExtractedEntity], facts: list[ExtractedFact]) -> TurnExtraction:
    return TurnExtraction(entities=entities, facts=facts, episodic_summary=None, importance=0.8)


@pytest.mark.integration
async def test_self_introduction_does_not_anchor_legacy_owner(
    onboarding_db: Path,
) -> None:
    """No incoming turn may infer or replace the legacy household owner."""
    kids_turn = _turn(
        entities=[
            ExtractedEntity(name="Máximo", type="person"),
            ExtractedEntity(name="Dominga", type="person"),
        ],
        facts=[
            ExtractedFact(subject="Máximo", predicate="hijo_de", object="Usuario"),
            ExtractedFact(subject="Dominga", predicate="hijo_de", object="Usuario"),
        ],
    )
    intro_turn = _turn(
        entities=[ExtractedEntity(name="Felipe Castro", type="person")],
        facts=[ExtractedFact(subject="usuario", predicate="edad", object="40")],
    )
    with (
        patch("server.memory.consolidation._extract", new_callable=AsyncMock) as extract,
        patch(
            "server.memory.consolidation.store_memory",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        extract.return_value = kids_turn
        await consolidate_turn("sí, tengo dos hijos, Máximo y mi hija Dominga", "¡Qué maravilla!")
        assert await get_flag("owner_name") is None

        extract.return_value = intro_turn
        await consolidate_turn(
            "te quería contar de mí, me llamo Felipe Castro",
            "¡Un gusto!",
            active_person=_identified_person(),
        )

    assert await get_flag("owner_name") is None
    slot = await next_missing_slot()
    assert slot is not None
    assert slot.key == "nombre"
