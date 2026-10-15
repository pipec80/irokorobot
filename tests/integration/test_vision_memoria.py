"""Acceptance exam of the retrieval half of the project vision (F4-D4, docs/audit/04 §5).

Two scenarios against a real temporary SQLite DB:

1. Recall after a process restart (empty working memory) via ``build_context``: the question
   "¿cómo se llaman mis hijos?" / "¿cómo se llama mi mascota?" is answered from the DB alone.
2. A manual identity does not revive the legacy onboarding interview.

The family is seeded straight through the legacy repositories. The scenarios that used to seed
it through ``consolidate_turn`` (extract, normalise, persist) and its correction scenario went
away with that function (ADR 0021 decision 11, Plan 0062); the supersede rule they pinned has its
own tests in ``test_memory_integration.py``, and the normaliser keeps its unit tests.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch
from uuid import UUID

if TYPE_CHECKING:
    from pathlib import Path

    import httpx

import pytest
from server.characters import build_system_prompt, get_character
from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    HouseholdRole,
    IdentityEvidence,
    IdentityEvidenceSource,
)
from server.cognition.models import Confidence, ConfidenceBasis
from server.memory.context import build_context
from server.memory.declarative import assert_fact, upsert_entity
from server.memory.meta import get_flag
from server.settings import settings

from server import db


def _manual_active_person() -> ActivePersonContext:
    """Create explicit manual identity evidence for memory acceptance tests."""
    resolved_at = datetime(2026, 8, 10, tzinfo=UTC)
    confidence = Confidence(
        score=1.0,
        basis=ConfidenceBasis.ASSERTED,
        calibrated=True,
        reason="Explicit local selection",
    )
    return ActivePersonContext(
        person_id=7,
        display_name="Pipec",
        status=ActivePersonStatus.IDENTIFIED,
        confidence=confidence,
        role=HouseholdRole.UNKNOWN,
        evidence=(
            IdentityEvidence(
                evidence_id=UUID("11111111-1111-1111-1111-111111111111"),
                source=IdentityEvidenceSource.MANUAL,
                candidate_person_id=7,
                confidence=confidence,
                observed_at=resolved_at,
                reference="trusted-local-adapter",
            ),
        ),
        resolved_at=resolved_at,
    )


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


async def _seed_family() -> None:
    """Persist the family the way the legacy relational retrieval reads it back."""
    await upsert_entity(name="Pipec", type="person")
    for child in ("Valentina", "Joaquín"):
        child_id = await upsert_entity(name=child, type="person")
        await assert_fact(entity_id=child_id, predicate="hijo_de", object_value="Pipec")
    pet_id = await upsert_entity(name="Luna", type="other")
    await assert_fact(entity_id=pet_id, predicate="mascota_de", object_value="Pipec")
    await assert_fact(entity_id=pet_id, predicate="especie", object_value="perro")


@pytest.mark.integration
async def test_recall_after_restart_children_and_pet(
    memory_db: Path, http_client: httpx.AsyncClient
) -> None:
    """Scenario 1 — after a 'restart' (empty working memory) the relational
    retrieval answers "mis hijos" and "mi mascota" from the DB alone."""
    await _seed_family()

    with patch(
        "server.memory.context.search_memories",
        new_callable=AsyncMock,
        return_value=[],
    ):
        children_ctx = await build_context(http_client, "¿cómo se llaman mis hijos?")
        pet_ctx = await build_context(http_client, "¿cómo se llama mi mascota?")

    children = {e.name for e in children_ctx.entities}
    assert {"Valentina", "Joaquín"} <= children
    assert "Luna" in {e.name for e in pet_ctx.entities}


@pytest.mark.integration
async def test_manual_context_does_not_enable_legacy_onboarding(memory_db: Path) -> None:
    """Scenario 2 — manual context must not revive the legacy onboarding owner assertion."""
    await _seed_family()
    assert await get_flag("owner_name") is None

    profile = get_character("iroko")
    prompt = build_system_prompt(
        profile,
        None,
        onboarding=False,
        active_person=_manual_active_person(),
    )
    assert "PRIMER ENCUENTRO" not in prompt
    # Sanity contrast: the sentinel really is what onboarding injects.
    assert "PRIMER ENCUENTRO" in build_system_prompt(profile, None, onboarding=True)
