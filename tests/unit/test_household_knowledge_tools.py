"""Unit tests for the closed P0.5-B2 household knowledge tools."""

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from server.cognition.authorization import AuthorizationRequest, ConsentStatus
from server.cognition.household_tools import (
    HouseholdKnowledgeTools,
    HouseholdToolName,
    PreferencePredicate,
)
from server.cognition.identity import ActivePersonContext, ActivePersonStatus, HouseholdRole
from server.cognition.models import (
    AuthorizationDecision,
    AuthorizationStatus,
    Confidence,
    ConfidenceBasis,
    KnowledgeStatus,
)
from server.memory.entity_labels import EntityLabel
from server.memory.policy_gated_v4_reader import PolicyGatedV4Reader
from server.memory.relational_v4 import AssertionLifecycle, EntityRelationV4, LiteralFactV4

_NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
_CORRELATION_ID = UUID("11111111-1111-1111-1111-111111111111")
_OWNER_ID = 7


def _actor(role: HouseholdRole, person_id: int | None) -> ActivePersonContext:
    """Build an explicit internal actor without using text as identity evidence."""
    return ActivePersonContext(
        person_id=person_id,
        display_name="Owner" if person_id is not None else None,
        status=ActivePersonStatus.IDENTIFIED
        if person_id is not None
        else ActivePersonStatus.UNKNOWN,
        confidence=Confidence(
            score=1.0 if person_id is not None else 0.0,
            basis=ConfidenceBasis.ASSERTED
            if person_id is not None
            else ConfidenceBasis.NOT_APPLICABLE,
            calibrated=False,
        ),
        role=role,
        evidence=(),
        resolved_at=_NOW,
    )


def _decision(
    request: AuthorizationRequest,
    status: AuthorizationStatus,
) -> AuthorizationDecision:
    """Return one decision scoped to the request without recording data values."""
    return AuthorizationDecision(
        decision=status,
        action=request.action,
        data_categories=frozenset({"household", "normal"}),
        policy_id="test.policy",
        reason="test decision",
        evaluated_at=request.requested_at,
        correlation_id=request.correlation_id,
    )


def _child_relation(child_id: int) -> EntityRelationV4:
    """Build one active v4 child relationship fixture."""
    return EntityRelationV4(
        id=child_id,
        source_entity_id=child_id,
        predicate="child_of",
        target_entity_id=_OWNER_ID,
        confidence=1.0,
        source_memory_id=None,
        asserted_at="2026-08-14T12:00:00+00:00",
        valid_from=None,
        valid_to=None,
        lifecycle=AssertionLifecycle.ACTIVE,
        visibility="household",
        sensitivity="child_data",
        superseded_at=None,
        superseded_by=None,
    )


def _literal(value: str, *, fact_id: int = 1) -> LiteralFactV4:
    """Build one active v4 literal fixture."""
    return LiteralFactV4(
        id=fact_id,
        subject_entity_id=_OWNER_ID,
        predicate="likes",
        value_text=value,
        confidence=1.0,
        source_memory_id=None,
        asserted_at="2026-08-14T12:00:00+00:00",
        valid_from=None,
        valid_to=None,
        lifecycle=AssertionLifecycle.ACTIVE,
        visibility="household",
        sensitivity="normal",
        superseded_at=None,
        superseded_by=None,
    )


@pytest.mark.asyncio
async def test_unknown_actor_is_audited_then_denied_before_child_reader() -> None:
    """Prevent unresolved actors from triggering either policy-gated reader or labels."""
    relation_reader = AsyncMock(return_value=[_child_relation(8)])
    label_reader = AsyncMock(return_value=EntityLabel(entity_id=8, display_name="Máximo"))
    tool_audit = AsyncMock()
    reader = PolicyGatedV4Reader(relation_reader=relation_reader)
    tools = HouseholdKnowledgeTools(
        reader=reader,
        audit_writer=tool_audit,
        label_reader=label_reader,
    )

    result = await tools.get_children(
        parent_entity_id=_OWNER_ID,
        actor=_actor(HouseholdRole.UNKNOWN, None),
        consent=ConsentStatus.GRANTED,
        correlation_id=_CORRELATION_ID,
        requested_at=_NOW,
    )

    assert result.tool_name is HouseholdToolName.GET_CHILDREN
    assert result.status is KnowledgeStatus.UNAUTHORIZED
    assert result.value is None
    assert result.reason == "household tool is not authorized"
    tool_audit.assert_awaited_once()
    relation_reader.assert_not_awaited()
    label_reader.assert_not_awaited()


@pytest.mark.asyncio
async def test_consented_owner_authorizes_and_audits_before_child_labels() -> None:
    """Require tool and reader authorization/audit before relationship values."""
    calls: list[str] = []

    def policy(request: AuthorizationRequest) -> AuthorizationDecision:
        calls.append(f"policy:{request.action.value}")
        return _decision(request, AuthorizationStatus.ALLOWED)

    async def audit(
        request: AuthorizationRequest,
        _decision_value: AuthorizationDecision,
    ) -> None:
        calls.append(f"audit:{request.action.value}")

    async def relation_reader(**_kwargs: object) -> list[EntityRelationV4]:
        calls.append("raw:relations")
        return [_child_relation(8), _child_relation(9)]

    async def label_reader(*, entity_id: int) -> EntityLabel | None:
        calls.append(f"label:{entity_id}")
        return EntityLabel(
            entity_id=entity_id,
            display_name="Máximo" if entity_id == 8 else "Sofía",
        )

    reader = PolicyGatedV4Reader(
        policy_evaluator=policy,
        audit_writer=audit,
        relation_reader=relation_reader,
    )
    tools = HouseholdKnowledgeTools(
        reader=reader,
        policy_evaluator=policy,
        audit_writer=audit,
        label_reader=label_reader,
    )

    result = await tools.get_children(
        parent_entity_id=_OWNER_ID,
        actor=_actor(HouseholdRole.OWNER, _OWNER_ID),
        consent=ConsentStatus.GRANTED,
        correlation_id=_CORRELATION_ID,
        requested_at=_NOW,
    )

    assert result.status is KnowledgeStatus.KNOWN
    assert result.value == ("Máximo", "Sofía")
    assert calls == [
        "policy:execute_household_tool",
        "audit:execute_household_tool",
        "policy:read_household_data",
        "audit:read_household_data",
        "raw:relations",
        "label:8",
        "label:9",
    ]


@pytest.mark.asyncio
async def test_missing_child_label_returns_unknown_without_partial_names() -> None:
    """Avoid returning a partial child list when one exact entity label is absent."""

    async def relation_reader(**_kwargs: object) -> list[EntityRelationV4]:
        return [_child_relation(8), _child_relation(9)]

    async def label_reader(*, entity_id: int) -> EntityLabel | None:
        if entity_id == 8:
            return EntityLabel(entity_id=8, display_name="Máximo")
        return None

    reader = PolicyGatedV4Reader(
        policy_evaluator=lambda request: _decision(request, AuthorizationStatus.ALLOWED),
        audit_writer=AsyncMock(),
        relation_reader=relation_reader,
    )
    tools = HouseholdKnowledgeTools(
        reader=reader,
        policy_evaluator=lambda request: _decision(request, AuthorizationStatus.ALLOWED),
        audit_writer=AsyncMock(),
        label_reader=label_reader,
    )

    result = await tools.get_children(
        parent_entity_id=_OWNER_ID,
        actor=_actor(HouseholdRole.OWNER, _OWNER_ID),
        consent=ConsentStatus.GRANTED,
        correlation_id=_CORRELATION_ID,
        requested_at=_NOW,
    )

    assert result.status is KnowledgeStatus.UNKNOWN
    assert result.value is None


@pytest.mark.asyncio
async def test_count_children_counts_unique_source_entities() -> None:
    """Count relationships without loading labels or writing inverse relations."""
    relation_reader = AsyncMock(
        return_value=[_child_relation(8), _child_relation(8), _child_relation(9)]
    )
    reader = PolicyGatedV4Reader(
        policy_evaluator=lambda request: _decision(request, AuthorizationStatus.ALLOWED),
        audit_writer=AsyncMock(),
        relation_reader=relation_reader,
    )
    label_reader = AsyncMock()
    tools = HouseholdKnowledgeTools(
        reader=reader,
        policy_evaluator=lambda request: _decision(request, AuthorizationStatus.ALLOWED),
        audit_writer=AsyncMock(),
        label_reader=label_reader,
    )

    result = await tools.count_children(
        parent_entity_id=_OWNER_ID,
        actor=_actor(HouseholdRole.OWNER, _OWNER_ID),
        consent=ConsentStatus.GRANTED,
        correlation_id=_CORRELATION_ID,
        requested_at=_NOW,
    )

    assert result.tool_name is HouseholdToolName.COUNT_CHILDREN
    assert result.status is KnowledgeStatus.KNOWN
    assert result.value == 2
    label_reader.assert_not_awaited()


@pytest.mark.asyncio
async def test_preferences_preserve_multiple_active_values() -> None:
    """Return all active preference siblings rather than superseding one in memory."""
    literal_reader = AsyncMock(return_value=[_literal("café"), _literal("robótica", fact_id=2)])
    reader = PolicyGatedV4Reader(
        policy_evaluator=lambda request: _decision(request, AuthorizationStatus.ALLOWED),
        audit_writer=AsyncMock(),
        literal_reader=literal_reader,
    )
    tools = HouseholdKnowledgeTools(
        reader=reader,
        policy_evaluator=lambda request: _decision(request, AuthorizationStatus.ALLOWED),
        audit_writer=AsyncMock(),
        label_reader=AsyncMock(),
    )

    result = await tools.get_preferences(
        person_entity_id=_OWNER_ID,
        preference=PreferencePredicate.LIKES,
        actor=_actor(HouseholdRole.OWNER, _OWNER_ID),
        consent=ConsentStatus.NOT_REQUIRED,
        correlation_id=_CORRELATION_ID,
        requested_at=_NOW,
    )

    assert result.tool_name is HouseholdToolName.GET_PREFERENCES
    assert result.status is KnowledgeStatus.KNOWN
    assert result.value == ("café", "robótica")
    literal_reader.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_person_birth_date_returns_one_strict_active_value() -> None:
    """Expose a birth date only through the consent-gated v4 tool boundary."""
    birth = _literal("2017-12-29").model_copy(
        update={"predicate": "birth_date", "subject_entity_id": 8}
    )
    literal_reader = AsyncMock(return_value=[birth])
    reader = PolicyGatedV4Reader(
        policy_evaluator=lambda request: _decision(request, AuthorizationStatus.ALLOWED),
        audit_writer=AsyncMock(),
        literal_reader=literal_reader,
    )
    tools = HouseholdKnowledgeTools(
        reader=reader,
        policy_evaluator=lambda request: _decision(request, AuthorizationStatus.ALLOWED),
        audit_writer=AsyncMock(),
        label_reader=AsyncMock(),
    )

    result = await tools.get_person_birth_date(
        person_entity_id=8,
        actor=_actor(HouseholdRole.OWNER, _OWNER_ID),
        consent=ConsentStatus.GRANTED,
        correlation_id=_CORRELATION_ID,
        requested_at=_NOW,
    )

    assert result.tool_name is HouseholdToolName.GET_PERSON_BIRTH_DATE
    assert result.status is KnowledgeStatus.KNOWN
    assert result.value == "2017-12-29"


@pytest.mark.asyncio
async def test_birth_date_requires_consent_before_reader() -> None:
    """Block child data before either raw v4 read or deterministic age calculation."""
    literal_reader = AsyncMock(return_value=[_literal("2017-12-29")])
    tool_audit = AsyncMock()
    reader = PolicyGatedV4Reader(literal_reader=literal_reader)
    tools = HouseholdKnowledgeTools(
        reader=reader,
        audit_writer=tool_audit,
        label_reader=AsyncMock(),
    )

    result = await tools.calculate_person_age(
        person_entity_id=8,
        actor=_actor(HouseholdRole.OWNER, _OWNER_ID),
        consent=ConsentStatus.NOT_REQUIRED,
        correlation_id=_CORRELATION_ID,
        requested_at=_NOW,
        on_date=date(2026, 8, 14),
    )

    assert result.tool_name is HouseholdToolName.CALCULATE_PERSON_AGE
    assert result.status is KnowledgeStatus.UNAUTHORIZED
    assert result.value is None
    tool_audit.assert_awaited_once()
    literal_reader.assert_not_awaited()


@pytest.mark.asyncio
async def test_age_uses_one_birth_date_and_rejects_inconsistent_active_rows() -> None:
    """Calculate from one v4 birth date and never choose between competing values."""
    birth = _literal("2017-12-29")
    birth = birth.model_copy(update={"predicate": "birth_date", "subject_entity_id": 8})
    conflicting = birth.model_copy(update={"id": 2, "value_text": "2018-12-29"})
    literal_reader = AsyncMock(return_value=[birth])
    reader = PolicyGatedV4Reader(
        policy_evaluator=lambda request: _decision(request, AuthorizationStatus.ALLOWED),
        audit_writer=AsyncMock(),
        literal_reader=literal_reader,
    )
    tools = HouseholdKnowledgeTools(
        reader=reader,
        policy_evaluator=lambda request: _decision(request, AuthorizationStatus.ALLOWED),
        audit_writer=AsyncMock(),
        label_reader=AsyncMock(),
    )

    known = await tools.calculate_person_age(
        person_entity_id=8,
        actor=_actor(HouseholdRole.OWNER, _OWNER_ID),
        consent=ConsentStatus.GRANTED,
        correlation_id=_CORRELATION_ID,
        requested_at=_NOW,
        on_date=date(2026, 8, 14),
    )
    literal_reader.return_value = [birth, conflicting]
    contradictory = await tools.calculate_person_age(
        person_entity_id=8,
        actor=_actor(HouseholdRole.OWNER, _OWNER_ID),
        consent=ConsentStatus.GRANTED,
        correlation_id=_CORRELATION_ID,
        requested_at=_NOW,
        on_date=date(2026, 8, 14),
    )

    assert known.status is KnowledgeStatus.KNOWN
    assert known.value == 8
    assert contradictory.status is KnowledgeStatus.CONTRADICTORY
    assert contradictory.value is None
