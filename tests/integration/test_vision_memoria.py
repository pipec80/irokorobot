"""Final acceptance exam of the project vision (F4-D4, docs/audit/04 §5).

Four scenarios prove the core idea end-to-end with a real temporary SQLite
DB and a mocked extractor returning REALISTIC 3B outputs (subject
"usuario", inverted relations) so the deterministic guardrails are
exercised too:

1. Onboarding — name, birth date, two children in one phrase, pet.
2. Recall after a process restart (empty working memory) via build_context.
3. Correction — "Luna en realidad es gata" supersedes especie=perro.
4. Completed onboarding never repeats — no slot left, no PRIMER ENCUENTRO.

The same script measured against real Ollama lives in the R8 eval
(``just eval-memory``); these tests pin the wiring, the eval pins the model.
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
from server.memory import working
from server.memory.consolidation import consolidate_turn
from server.memory.context import build_context
from server.memory.declarative import find_entities_by_name, get_active_facts
from server.memory.meta import get_flag
from server.schemas import ExtractedEntity, ExtractedFact, TurnExtraction
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


@pytest.fixture(autouse=True)
def _clean_working_memory() -> None:  # type: ignore[misc]
    """Clear working memory between tests (a restart empties it too)."""
    working._buffers.clear()
    yield  # type: ignore[misc]
    working._buffers.clear()


async def _consolidate(
    client: httpx.AsyncClient,
    user_text: str,
    extraction: TurnExtraction,
    *,
    active_person: ActivePersonContext,
) -> None:
    """Run consolidate_turn with the extractor mocked to *extraction*."""
    with (
        patch(
            "server.memory.consolidation._extract",
            new_callable=AsyncMock,
            return_value=extraction,
        ),
        # None (not a fake id): facts with a source_memory_id pointing at a
        # row that the mock never inserted would fail the FK constraint.
        patch(
            "server.memory.consolidation.store_memory",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        await consolidate_turn(
            client,
            user_text,
            "¡Qué bien! Cuéntame más.",
            active_person=active_person,
        )


# Realistic RAW extractor outputs for the vision's onboarding script —
# "usuario" subjects and owner-side relations on purpose: that is what
# qwen2.5:3b emits live, and normalize must repair it before persistence.
_ONBOARDING_TURNS: list[tuple[str, TurnExtraction]] = [
    (
        "me llamo Pipec",
        TurnExtraction(
            entities=[ExtractedEntity(name="Pipec", type="person")],
            facts=[ExtractedFact(subject="usuario", predicate="nombre", object="Pipec")],
            episodic_summary="El dueño se presentó como Pipec.",
            importance=0.9,
        ),
    ),
    (
        "nací el 12 de marzo de 1980",
        TurnExtraction(
            facts=[
                ExtractedFact(
                    subject="usuario",
                    predicate="fecha_nacimiento",
                    object="12 de marzo de 1980",
                )
            ],
            importance=0.8,
        ),
    ),
    (
        "tengo dos hijos, Valentina y Máximo",
        TurnExtraction(
            entities=[
                ExtractedEntity(name="Valentina", type="person"),
                ExtractedEntity(name="Máximo", type="person"),
            ],
            facts=[
                # Inverted on purpose — normalize must flip them.
                ExtractedFact(subject="usuario", predicate="hijo_de", object="Valentina"),
                ExtractedFact(subject="usuario", predicate="hijo_de", object="Máximo"),
            ],
            importance=0.9,
        ),
    ),
    (
        "mi perra se llama Luna",
        TurnExtraction(
            entities=[ExtractedEntity(name="Luna", type="other")],
            facts=[
                ExtractedFact(subject="Luna", predicate="especie", object="perro"),
                ExtractedFact(subject="Luna", predicate="mascota_de", object="usuario"),
            ],
            importance=0.8,
        ),
    ),
]


async def _seed_onboarding(client: httpx.AsyncClient) -> None:
    """Consolidate the vision's four onboarding turns."""
    active_person = _manual_active_person()
    for user_text, extraction in _ONBOARDING_TURNS:
        await _consolidate(client, user_text, extraction, active_person=active_person)


async def _active_predicates(name: str) -> dict[str, str]:
    """Return predicate → object for the active facts of entity *name*."""
    matches = await find_entities_by_name(name, limit=1)
    assert matches, f"entity {name!r} not found"
    facts = await get_active_facts(int(matches[0]["id"]))
    return {f.predicate: f.object_value for f in facts}


@pytest.mark.integration
async def test_onboarding_persists_owner_family_and_pet(
    memory_db: Path, http_client: httpx.AsyncClient
) -> None:
    """Scenario 1 — the interview leaves owner, children and pet in the DB."""
    await _seed_onboarding(http_client)

    assert await get_flag("owner_name") is None
    owner_facts = await _active_predicates("Pipec")
    assert owner_facts["nombre"] == "Pipec"
    assert owner_facts["fecha_nacimiento"] == "12 de marzo de 1980"

    for child in ("Valentina", "Máximo"):
        child_facts = await _active_predicates(child)
        assert child_facts["hijo_de"] == "Pipec"

    pet_facts = await _active_predicates("Luna")
    assert pet_facts["mascota_de"] == "Pipec"
    assert pet_facts["especie"] == "perro"


@pytest.mark.integration
async def test_recall_after_restart_children_and_pet(
    memory_db: Path, http_client: httpx.AsyncClient
) -> None:
    """Scenario 2 — after a 'restart' (empty working memory) the relational
    retrieval answers "mis hijos" and "mi mascota" from the DB alone."""
    await _seed_onboarding(http_client)

    with patch(
        "server.memory.context.search_memories",
        new_callable=AsyncMock,
        return_value=[],
    ):
        children_ctx = await build_context(http_client, "¿cómo se llaman mis hijos?")
        pet_ctx = await build_context(http_client, "¿cómo se llama mi mascota?")

    children = {e.name for e in children_ctx.entities}
    assert {"Valentina", "Máximo"} <= children
    assert "Luna" in {e.name for e in pet_ctx.entities}


@pytest.mark.integration
async def test_correction_supersedes_species(
    memory_db: Path, http_client: httpx.AsyncClient
) -> None:
    """Scenario 3 — 'Luna en realidad es gata' supersedes especie=perro."""
    await _seed_onboarding(http_client)

    await _consolidate(
        http_client,
        "Luna en realidad es gata",
        TurnExtraction(
            facts=[ExtractedFact(subject="Luna", predicate="especie", object="gata")],
            importance=0.7,
        ),
        active_person=_manual_active_person(),
    )

    pet_facts = await _active_predicates("Luna")
    assert pet_facts["especie"] == "gata"

    cur = await db.get_conn().execute(
        "SELECT count(*) FROM facts WHERE predicate = 'especie'"
        " AND object_value = 'perro' AND superseded_at IS NOT NULL"
    )
    row = await cur.fetchone()
    await cur.close()
    assert row is not None
    assert row[0] == 1


@pytest.mark.integration
async def test_manual_context_does_not_enable_legacy_onboarding(
    memory_db: Path, http_client: httpx.AsyncClient
) -> None:
    """Manual context must not revive the legacy onboarding owner assertion."""
    await _seed_onboarding(http_client)
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
