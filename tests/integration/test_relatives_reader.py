"""Reading the relatives loaded at the alta (Plan 0078 Task 10, ADR 0028 decision 9).

The tool, the gated reader, the policy and the audit are real; the speaker is a face-identified
owner. Canary names only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from server.cognition.authorization import ConsentStatus
from server.cognition.household_tools import (
    HouseholdKnowledgeTools,
    HouseholdToolName,
    HouseholdToolResult,
)
from server.cognition.identity import (
    ActivePersonContext,
    HouseholdRole,
    IdentityEvidence,
    IdentityEvidenceSource,
    PersonRecord,
    resolve_active_person,
)
from server.cognition.models import Confidence, ConfidenceBasis, KnowledgeStatus
from server.memory.declarative import upsert_entity
from server.memory.policy_gated_v4_reader import PolicyGatedV4Reader
from server.memory.predicate_registry import resolve_predicate
from server.memory.relational_v4 import assert_entity_relation
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from server.schemas import EntityType

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 11, 4, 15, tzinfo=UTC)


@pytest.fixture
async def owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "relatives.db")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        yield await upsert_entity(name="Canary", type="person")
    finally:
        await db.close_db()
        db._conn = None


def _face(person_id: int, role: HouseholdRole = HouseholdRole.OWNER) -> ActivePersonContext:
    person = PersonRecord(person_id=person_id, display_name="Canary", entity_type="person")
    evidence = IdentityEvidence(
        evidence_id=uuid4(),
        source=IdentityEvidenceSource.FACE,
        candidate_person_id=person_id,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False),
        observed_at=_NOW - timedelta(seconds=1),
        reference="canary",
    )
    return resolve_active_person(
        evidence=(evidence,),
        lookup_person=lambda pid: person if pid == person_id else None,
        lookup_role=lambda _pid: role,
        clock=lambda: _NOW,
    )


async def _relate(source: int, predicate: str, target: int) -> None:
    definition = resolve_predicate(predicate)
    assert definition is not None
    await assert_entity_relation(
        source_entity_id=source, target_entity_id=target, definition=definition
    )


async def _relative(
    owner: int, predicate: str, name: str, entity_type: EntityType = "person"
) -> int:
    entity = await upsert_entity(name=name, type=entity_type)
    if predicate in {"pet_of", "partner_of"}:
        await _relate(entity, predicate, owner)
    else:
        await _relate(owner, predicate, entity)
    return entity


async def _read(
    owner: int, predicate: str, actor: ActivePersonContext | None = None
) -> HouseholdToolResult:
    tools = HouseholdKnowledgeTools(reader=PolicyGatedV4Reader())
    return await tools.get_relatives(
        owner_entity_id=owner,
        predicate=predicate,
        actor=actor or _face(owner),
        consent=ConsentStatus.NOT_REQUIRED,
        correlation_id=uuid4(),
        requested_at=_NOW,
    )


async def test_parents_are_read_together(owner: int) -> None:
    await _relative(owner, "has_parent", "Zeta")
    await _relative(owner, "has_parent", "Omega")

    result = await _read(owner, "has_parent")

    assert result.tool_name is HouseholdToolName.GET_RELATIVES
    assert result.status is KnowledgeStatus.KNOWN
    assert result.value == ("Omega", "Zeta")


async def test_a_pet_and_a_partner_are_read(owner: int) -> None:
    await _relative(owner, "pet_of", "Canela Canary", entity_type="other")
    await _relative(owner, "partner_of", "Zeta")

    pets = await _read(owner, "pet_of")
    partner = await _read(owner, "partner_of")

    assert pets.value == ("Canela Canary",)
    assert partner.value == ("Zeta",)


async def test_a_partner_written_from_the_owners_end_is_read(owner: int) -> None:
    partner = await upsert_entity(name="Omega", type="person")
    await _relate(owner, "partner_of", partner)

    result = await _read(owner, "partner_of")

    assert result.value == ("Omega",)


async def test_nothing_stored_is_unknown(owner: int) -> None:
    result = await _read(owner, "has_sibling")

    assert result.status is KnowledgeStatus.UNKNOWN
    assert result.value is None


async def test_a_revoked_relation_is_not_read(owner: int) -> None:
    await _relative(owner, "has_grandchild", "Zeta")
    async with db.transaction() as conn:
        await conn.execute("UPDATE entity_relations_v4 SET lifecycle = 'revoked'")

    result = await _read(owner, "has_grandchild")

    assert result.status is KnowledgeStatus.UNKNOWN


async def test_another_person_is_not_authorized(owner: int) -> None:
    await _relative(owner, "has_parent", "Zeta")
    other = await upsert_entity(name="Omega Visit", type="person")

    result = await _read(owner, "has_parent", _face(other, HouseholdRole.ADULT))

    assert result.status is KnowledgeStatus.UNAUTHORIZED
    assert result.value is None


async def test_an_unknown_predicate_is_refused(owner: int) -> None:
    with pytest.raises(ValueError, match="relatives"):
        await _read(owner, "child_of")
