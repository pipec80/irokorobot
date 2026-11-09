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
    SidedNames,
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
    from uuid import UUID

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


async def _read_parents(owner: int, actor: ActivePersonContext | None = None) -> SidedNames:
    tools = HouseholdKnowledgeTools(reader=PolicyGatedV4Reader())
    return await tools.get_parents(
        owner_entity_id=owner,
        actor=actor or _face(owner),
        consent=ConsentStatus.NOT_REQUIRED,
        correlation_id=uuid4(),
        requested_at=_NOW,
    )


async def _audit_shapes(correlation_id: UUID) -> set[tuple[str, str, str, str, str]]:
    cursor = await db.get_conn().execute(
        "SELECT action, decision, data_categories, policy_id, reason "
        "FROM authorization_audit_events WHERE correlation_id = ?",
        (str(correlation_id),),
    )
    rows = await cursor.fetchall()
    await cursor.close()
    return {(row[0], row[1], row[2], row[3], row[4]) for row in rows}


async def test_each_parent_is_read_in_its_own_group(owner: int) -> None:
    await _relative(owner, "has_mother", "Zeta")
    await _relative(owner, "has_father", "Omega")
    await _relative(owner, "has_parent", "Canary Parent")

    result = await _read_parents(owner)

    assert result.status is KnowledgeStatus.KNOWN
    assert result.female == ("Zeta",)
    assert result.male == ("Omega",)
    assert result.unlabelled == ("Canary Parent",)


async def test_the_parents_of_a_side_are_sorted(owner: int) -> None:
    await _relative(owner, "has_mother", "Zeta")
    await _relative(owner, "has_mother", "Omega")

    result = await _read_parents(owner)

    assert result.female == ("Omega", "Zeta")
    assert result.male == ()
    assert result.unlabelled == ()


async def test_the_names_of_the_parents_stay_out_of_the_representation(owner: int) -> None:
    await _relative(owner, "has_mother", "Zeta")

    assert "Zeta" not in repr(await _read_parents(owner))


async def test_an_owner_without_a_parent_is_unknown(owner: int) -> None:
    result = await _read_parents(owner)

    assert result.status is KnowledgeStatus.UNKNOWN
    assert (result.female, result.male, result.unlabelled) == ((), (), ())


async def test_a_denied_actor_is_unauthorized_and_learns_nothing(owner: int) -> None:
    await _relative(owner, "has_mother", "Zeta")
    other = await upsert_entity(name="Omega Visit", type="person")

    result = await _read_parents(owner, _face(other, HouseholdRole.ADULT))

    assert result.status is KnowledgeStatus.UNAUTHORIZED
    assert (result.female, result.male, result.unlabelled) == ((), (), ())


async def test_a_revoked_parent_is_not_read(owner: int) -> None:
    await _relative(owner, "has_father", "Zeta")
    async with db.transaction() as conn:
        await conn.execute("UPDATE entity_relations_v4 SET lifecycle = 'revoked'")

    assert (await _read_parents(owner)).status is KnowledgeStatus.UNKNOWN


async def test_get_parents_audits_like_get_relatives_does_for_has_parent(owner: int) -> None:
    await _relative(owner, "has_parent", "Zeta")
    tools = HouseholdKnowledgeTools(reader=PolicyGatedV4Reader())
    actor = _face(owner)
    relatives_id, parents_id = uuid4(), uuid4()

    await tools.get_relatives(
        owner_entity_id=owner,
        predicate="has_parent",
        actor=actor,
        consent=ConsentStatus.NOT_REQUIRED,
        correlation_id=relatives_id,
        requested_at=_NOW,
    )
    await tools.get_parents(
        owner_entity_id=owner,
        actor=actor,
        consent=ConsentStatus.NOT_REQUIRED,
        correlation_id=parents_id,
        requested_at=_NOW,
    )

    relatives_audit = await _audit_shapes(relatives_id)
    parents_audit = await _audit_shapes(parents_id)
    assert relatives_audit
    assert parents_audit == relatives_audit
    tool_rows = await db.get_conn().execute(
        "SELECT COUNT(*) FROM authorization_audit_events "
        "WHERE correlation_id = ? AND action = 'execute_household_tool'",
        (str(parents_id),),
    )
    row = await tool_rows.fetchone()
    await tool_rows.close()
    assert row is not None
    assert row[0] == 1
