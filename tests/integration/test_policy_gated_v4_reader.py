"""Integration coverage for the P0.5-B1 policy-gated v4 reader."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from server.cognition.authorization import ConsentStatus
from server.cognition.identity import ActivePersonContext, ActivePersonStatus, HouseholdRole
from server.cognition.models import Confidence, ConfidenceBasis, KnowledgeStatus
from server.memory.declarative import upsert_entity
from server.memory.household_authorization import bootstrap_initial_owner
from server.memory.policy_gated_v4_reader import PolicyGatedV4Reader
from server.memory.predicate_registry import PredicateDefinition, resolve_predicate
from server.memory.relational_v4 import assert_entity_relation, assert_literal_fact
from server.settings import settings

from server import db

_NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
_PREFERENCE_CORRELATION_ID = UUID("44444444-4444-4444-4444-444444444444")
_CHILD_DENIED_CORRELATION_ID = UUID("55555555-5555-5555-5555-555555555555")
_CHILD_ALLOWED_CORRELATION_ID = UUID("66666666-6666-6666-6666-666666666666")


@pytest.fixture
async def policy_reader_db(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[None]:
    """Open a disposable SQLite database with migrations one through five."""
    db_path = tmp_path / "policy-gated-v4-reader.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield
    await db.close_db()
    db._conn = None


def _predicate(alias: str) -> PredicateDefinition:
    """Resolve one known v4 predicate for a real SQLite fixture."""
    definition = resolve_predicate(alias)
    assert definition is not None
    return definition


def _identified_owner(owner_id: int) -> ActivePersonContext:
    """Build an explicit internal owner actor without deriving identity."""
    return ActivePersonContext(
        person_id=owner_id,
        display_name="Owner",
        status=ActivePersonStatus.IDENTIFIED,
        confidence=Confidence(
            score=1.0,
            basis=ConfidenceBasis.ASSERTED,
            calibrated=False,
        ),
        role=HouseholdRole.OWNER,
        evidence=(),
        resolved_at=_NOW,
    )


async def _owner_id() -> int:
    """Create and explicitly bootstrap one fixture owner."""
    owner_id = await upsert_entity(name="Owner", type="person")
    await bootstrap_initial_owner(
        person_entity_id=owner_id,
        confirmed_person_entity_id=owner_id,
    )
    return owner_id


async def _read_audit_rows(correlation_id: UUID) -> list[tuple[str, str, str, str, str]]:
    """Return only safe persisted audit fields for one deterministic turn."""
    cursor = await db.get_conn().execute(
        "SELECT action, data_categories, decision, policy_id, reason "
        "FROM authorization_audit_events WHERE correlation_id = ?",
        (str(correlation_id),),
    )
    rows = await cursor.fetchall()
    await cursor.close()
    return [(str(row[0]), str(row[1]), str(row[2]), str(row[3]), str(row[4])) for row in rows]


@pytest.mark.integration
async def test_owner_reads_normal_preference_and_audit_never_contains_value(
    policy_reader_db: None,
) -> None:
    """Return an allowed preference while retaining only safe audit metadata."""
    owner_id = await _owner_id()
    await assert_literal_fact(
        subject_entity_id=owner_id,
        definition=_predicate("le_gusta"),
        value="robotica",
    )

    result = await PolicyGatedV4Reader().read_active_literals(
        actor=_identified_owner(owner_id),
        subject_entity_id=owner_id,
        predicate_alias="le_gusta",
        consent=ConsentStatus.NOT_REQUIRED,
        correlation_id=_PREFERENCE_CORRELATION_ID,
        requested_at=_NOW,
    )

    assert result.status is KnowledgeStatus.KNOWN
    assert [fact.value_text for fact in result.facts] == ["robotica"]
    rows = await _read_audit_rows(_PREFERENCE_CORRELATION_ID)
    assert len(rows) == 1
    assert rows[0][:4] == (
        "read_household_data",
        "household,normal",
        "allowed",
        "p0.5.owner-household",
    )
    assert all("robotica" not in field for row in rows for field in row)


@pytest.mark.integration
async def test_child_relation_requires_consent_before_target_read(
    policy_reader_db: None,
) -> None:
    """Keep child relationship rows hidden until a trusted consent state exists."""
    owner_id = await _owner_id()
    child_id = await upsert_entity(name="Child", type="person")
    await assert_entity_relation(
        source_entity_id=child_id,
        target_entity_id=owner_id,
        definition=_predicate("hijo_de"),
    )
    reader = PolicyGatedV4Reader()

    denied = await reader.read_active_relations(
        actor=_identified_owner(owner_id),
        predicate_alias="hijo_de",
        target_entity_id=owner_id,
        consent=ConsentStatus.NOT_REQUIRED,
        correlation_id=_CHILD_DENIED_CORRELATION_ID,
        requested_at=_NOW,
    )
    allowed = await reader.read_active_relations(
        actor=_identified_owner(owner_id),
        predicate_alias="hijo_de",
        target_entity_id=owner_id,
        consent=ConsentStatus.GRANTED,
        correlation_id=_CHILD_ALLOWED_CORRELATION_ID,
        requested_at=_NOW,
    )

    assert denied.status is KnowledgeStatus.UNAUTHORIZED
    assert denied.relations == ()
    assert allowed.status is KnowledgeStatus.KNOWN
    assert [relation.source_entity_id for relation in allowed.relations] == [child_id]
    assert await _read_audit_rows(_CHILD_DENIED_CORRELATION_ID) == [
        (
            "read_household_data",
            "child_data,household",
            "denied",
            "p0.5.consent-required",
            "Required consent is absent or revoked.",
        )
    ]
    assert await _read_audit_rows(_CHILD_ALLOWED_CORRELATION_ID) == [
        (
            "read_household_data",
            "child_data,household",
            "allowed",
            "p0.5.owner-sensitive-consent",
            "Owner policy permits this consented sensitive request.",
        )
    ]
