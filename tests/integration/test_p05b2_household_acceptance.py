"""Disposable SQLite acceptance tests for the complete P0.5-B2 family seam."""

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

import pytest
from server.cognition.authorization import ConsentStatus
from server.cognition.household_tools import (
    HouseholdKnowledgeTools,
    HouseholdToolName,
    PreferencePredicate,
)
from server.cognition.identity import ActivePersonContext, ActivePersonStatus, HouseholdRole
from server.cognition.models import Confidence, ConfidenceBasis, KnowledgeStatus
from server.memory.declarative import upsert_entity
from server.memory.household_authorization import bootstrap_initial_owner
from server.memory.policy_gated_v4_reader import PolicyGatedV4Reader
from server.memory.predicate_registry import PredicateDefinition, resolve_predicate
from server.memory.relational_v4 import assert_entity_relation, assert_literal_fact
from server.settings import settings

from server import db

_NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
_CHILDREN_CORRELATION_ID = UUID("10000000-0000-0000-0000-000000000001")
_COUNT_CORRELATION_ID = UUID("10000000-0000-0000-0000-000000000002")
_PREFERENCES_CORRELATION_ID = UUID("10000000-0000-0000-0000-000000000003")
_AGE_CORRELATION_ID = UUID("10000000-0000-0000-0000-000000000004")
_DENIED_CORRELATION_ID = UUID("10000000-0000-0000-0000-000000000005")


@pytest.fixture
async def p05b2_db(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[None]:
    """Open one isolated SQLite database at the current P0 migration version."""
    db_path = tmp_path / "p05b2-household-acceptance.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield
    await db.close_db()
    db._conn = None


def _predicate(alias: str) -> PredicateDefinition:
    """Resolve one closed v4 predicate for an acceptance fixture."""
    definition = resolve_predicate(alias)
    assert definition is not None
    return definition


def _owner_actor(owner_id: int) -> ActivePersonContext:
    """Build the explicit trusted owner required by the internal seam."""
    return ActivePersonContext(
        person_id=owner_id,
        display_name="Felipe",
        status=ActivePersonStatus.IDENTIFIED,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.ASSERTED, calibrated=False),
        role=HouseholdRole.OWNER,
        evidence=(),
        resolved_at=_NOW,
    )


async def _audit_rows(correlation_id: UUID) -> list[tuple[str, str, str, str, str]]:
    """Read only safe audit metadata for one request correlation ID."""
    cursor = await db.get_conn().execute(
        "SELECT action, data_categories, decision, policy_id, reason "
        "FROM authorization_audit_events WHERE correlation_id = ? ORDER BY id",
        (str(correlation_id),),
    )
    rows = await cursor.fetchall()
    await cursor.close()
    return [(str(row[0]), str(row[1]), str(row[2]), str(row[3]), str(row[4])) for row in rows]


def _assert_audit_has_no_values(
    rows: list[tuple[str, str, str, str, str]],
    values: tuple[str, ...],
) -> None:
    """Ensure authorization audit metadata never stores protected data values."""
    assert all(value not in field for row in rows for field in row for value in values)


@pytest.mark.integration
async def test_consented_owner_uses_v4_tools_for_children_preferences_and_age(
    p05b2_db: None,
) -> None:
    """Prove the positive P0 seam uses v4 relationships and literal facts only."""
    owner_id = await upsert_entity(name="Felipe", type="person")
    maximo_id = await upsert_entity(name="Máximo", type="person")
    sofia_id = await upsert_entity(name="Sofía", type="person")
    await bootstrap_initial_owner(
        person_entity_id=owner_id,
        confirmed_person_entity_id=owner_id,
    )
    await assert_entity_relation(
        source_entity_id=maximo_id,
        target_entity_id=owner_id,
        definition=_predicate("hijo_de"),
    )
    await assert_entity_relation(
        source_entity_id=sofia_id,
        target_entity_id=owner_id,
        definition=_predicate("hijo_de"),
    )
    await assert_literal_fact(
        subject_entity_id=owner_id,
        definition=_predicate("le_gusta"),
        value="café",
    )
    await assert_literal_fact(
        subject_entity_id=owner_id,
        definition=_predicate("le_gusta"),
        value="robótica",
    )
    await assert_literal_fact(
        subject_entity_id=maximo_id,
        definition=_predicate("fecha_nacimiento"),
        value="2017-12-29",
    )
    tools = HouseholdKnowledgeTools(reader=PolicyGatedV4Reader())
    owner = _owner_actor(owner_id)

    children = await tools.get_children(
        parent_entity_id=owner_id,
        actor=owner,
        consent=ConsentStatus.GRANTED,
        correlation_id=_CHILDREN_CORRELATION_ID,
        requested_at=_NOW,
    )
    count = await tools.count_children(
        parent_entity_id=owner_id,
        actor=owner,
        consent=ConsentStatus.GRANTED,
        correlation_id=_COUNT_CORRELATION_ID,
        requested_at=_NOW,
    )
    preferences = await tools.get_preferences(
        person_entity_id=owner_id,
        preference=PreferencePredicate.LIKES,
        actor=owner,
        consent=ConsentStatus.NOT_REQUIRED,
        correlation_id=_PREFERENCES_CORRELATION_ID,
        requested_at=_NOW,
    )
    age = await tools.calculate_person_age(
        person_entity_id=maximo_id,
        actor=owner,
        consent=ConsentStatus.GRANTED,
        correlation_id=_AGE_CORRELATION_ID,
        requested_at=_NOW,
        on_date=date(2026, 8, 14),
    )

    assert children.tool_name is HouseholdToolName.GET_CHILDREN
    assert children.status is KnowledgeStatus.KNOWN
    assert children.value == ("Máximo", "Sofía")
    assert count.tool_name is HouseholdToolName.COUNT_CHILDREN
    assert count.status is KnowledgeStatus.KNOWN
    assert count.value == 2
    assert preferences.status is KnowledgeStatus.KNOWN
    assert preferences.value == ("café", "robótica")
    assert age.tool_name is HouseholdToolName.CALCULATE_PERSON_AGE
    assert age.status is KnowledgeStatus.KNOWN
    assert age.value == 8

    for correlation_id in (
        _CHILDREN_CORRELATION_ID,
        _COUNT_CORRELATION_ID,
        _PREFERENCES_CORRELATION_ID,
        _AGE_CORRELATION_ID,
    ):
        rows = await _audit_rows(correlation_id)
        assert [row[0] for row in rows] == [
            "execute_household_tool",
            "read_household_data",
        ]
        _assert_audit_has_no_values(
            rows,
            ("Máximo", "Sofía", "2017-12-29", "café", "robótica", "8"),
        )


@pytest.mark.integration
async def test_missing_consent_audits_tool_without_reading_child_relation(
    p05b2_db: None,
) -> None:
    """Prove denied child data creates no second reader audit event or data result."""
    owner_id = await upsert_entity(name="Felipe", type="person")
    child_id = await upsert_entity(name="Máximo", type="person")
    await bootstrap_initial_owner(
        person_entity_id=owner_id,
        confirmed_person_entity_id=owner_id,
    )
    await assert_entity_relation(
        source_entity_id=child_id,
        target_entity_id=owner_id,
        definition=_predicate("hijo_de"),
    )
    tools = HouseholdKnowledgeTools(reader=PolicyGatedV4Reader())

    result = await tools.get_children(
        parent_entity_id=owner_id,
        actor=_owner_actor(owner_id),
        consent=ConsentStatus.NOT_REQUIRED,
        correlation_id=_DENIED_CORRELATION_ID,
        requested_at=_NOW,
    )

    assert result.status is KnowledgeStatus.UNAUTHORIZED
    assert result.value is None
    rows = await _audit_rows(_DENIED_CORRELATION_ID)
    assert [row[0] for row in rows] == ["execute_household_tool"]
    assert rows[0][2] == "denied"
    _assert_audit_has_no_values(rows, ("Felipe", "Máximo"))
