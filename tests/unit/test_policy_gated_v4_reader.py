"""Unit tests for the P0.5-B1 policy-gated v4 reader."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from server.cognition.authorization import (
    AuthorizationRequest,
    ConsentStatus,
)
from server.cognition.identity import ActivePersonContext, ActivePersonStatus, HouseholdRole
from server.cognition.models import (
    AuthorizationDecision,
    AuthorizationStatus,
    Confidence,
    ConfidenceBasis,
    KnowledgeStatus,
)
from server.memory.policy_gated_v4_reader import PolicyGatedV4Reader
from server.memory.relational_v4 import AssertionLifecycle, EntityRelationV4, LiteralFactV4

_NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
_CORRELATION_ID = UUID("22222222-2222-2222-2222-222222222222")


def _actor(role: HouseholdRole, person_id: int | None) -> ActivePersonContext:
    """Build a trusted test actor without deriving identity from text."""
    return ActivePersonContext(
        person_id=person_id,
        display_name="Ada" if person_id is not None else None,
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


def _literal_fact() -> LiteralFactV4:
    """Return one complete immutable v4 literal fixture."""
    return LiteralFactV4(
        id=1,
        subject_entity_id=7,
        predicate="likes",
        value_text="robotica",
        confidence=1.0,
        source_memory_id=None,
        asserted_at="2026-08-12T12:00:00+00:00",
        valid_from=None,
        valid_to=None,
        lifecycle=AssertionLifecycle.ACTIVE,
        visibility="household",
        sensitivity="normal",
        superseded_at=None,
        superseded_by=None,
    )


def _child_relation() -> EntityRelationV4:
    """Return one complete immutable child relationship fixture."""
    return EntityRelationV4(
        id=2,
        source_entity_id=8,
        predicate="child_of",
        target_entity_id=7,
        confidence=1.0,
        source_memory_id=None,
        asserted_at="2026-08-12T12:00:00+00:00",
        valid_from=None,
        valid_to=None,
        lifecycle=AssertionLifecycle.ACTIVE,
        visibility="household",
        sensitivity="child_data",
        superseded_at=None,
        superseded_by=None,
    )


def _allowed_decision(request: AuthorizationRequest, calls: list[str]) -> AuthorizationDecision:
    """Return one deterministic allowed decision while recording its order."""
    calls.append("policy")
    return AuthorizationDecision(
        decision=AuthorizationStatus.ALLOWED,
        action=request.action,
        data_categories=frozenset({"household", "normal"}),
        policy_id="test.allowed",
        reason="safe test reason",
        evaluated_at=request.requested_at,
        correlation_id=request.correlation_id,
    )


@pytest.mark.asyncio
async def test_unknown_actor_is_audited_and_cannot_read_preferences() -> None:
    """Prevent an unresolved identity from invoking the raw v4 literal reader."""
    literal_reader = AsyncMock(return_value=[_literal_fact()])
    audit_writer = AsyncMock()
    reader = PolicyGatedV4Reader(
        literal_reader=literal_reader,
        audit_writer=audit_writer,
    )

    result = await reader.read_active_literals(
        actor=_actor(HouseholdRole.UNKNOWN, None),
        subject_entity_id=7,
        predicate_alias="le_gusta",
        consent=ConsentStatus.NOT_REQUIRED,
        correlation_id=_CORRELATION_ID,
        requested_at=_NOW,
    )

    assert result.status is KnowledgeStatus.UNAUTHORIZED
    assert result.facts == ()
    assert result.reason == "household data is not authorized"
    audit_writer.assert_awaited_once()
    literal_reader.assert_not_awaited()


@pytest.mark.asyncio
async def test_allowed_read_audits_before_raw_literal_reader() -> None:
    """Require policy then audit before a permitted raw literal read happens."""
    calls: list[str] = []

    async def audit(
        _request: AuthorizationRequest,
        _decision: AuthorizationDecision,
    ) -> None:
        calls.append("audit")

    async def literal_reader(**_kwargs: object) -> list[LiteralFactV4]:
        calls.append("raw")
        return [_literal_fact()]

    reader = PolicyGatedV4Reader(
        policy_evaluator=lambda request: _allowed_decision(request, calls),
        audit_writer=audit,
        literal_reader=literal_reader,
    )

    result = await reader.read_active_literals(
        actor=_actor(HouseholdRole.OWNER, 7),
        subject_entity_id=7,
        predicate_alias="le_gusta",
        consent=ConsentStatus.NOT_REQUIRED,
        correlation_id=_CORRELATION_ID,
        requested_at=_NOW,
    )

    assert calls == ["policy", "audit", "raw"]
    assert result.status is KnowledgeStatus.KNOWN
    assert result.facts == (_literal_fact(),)
    assert result.reason is None


@pytest.mark.asyncio
async def test_allowed_empty_literal_read_is_unknown() -> None:
    """Represent a permitted absence without inventing a household fact."""
    calls: list[str] = []
    literal_reader = AsyncMock(return_value=[])
    reader = PolicyGatedV4Reader(
        policy_evaluator=lambda request: _allowed_decision(request, calls),
        audit_writer=AsyncMock(),
        literal_reader=literal_reader,
    )

    result = await reader.read_active_literals(
        actor=_actor(HouseholdRole.OWNER, 7),
        subject_entity_id=7,
        predicate_alias="le_gusta",
        consent=ConsentStatus.NOT_REQUIRED,
        correlation_id=_CORRELATION_ID,
        requested_at=_NOW,
    )

    assert result.status is KnowledgeStatus.UNKNOWN
    assert result.facts == ()
    assert result.reason == "no active authorized record"
    literal_reader.assert_awaited_once()


@pytest.mark.asyncio
async def test_unsupported_or_wrong_kind_predicate_skips_all_collaborators() -> None:
    """Reject an unsupported or mismatched predicate before policy and storage."""
    literal_reader = AsyncMock()
    relation_reader = AsyncMock()
    policy_evaluator = AsyncMock()
    audit_writer = AsyncMock()
    reader = PolicyGatedV4Reader(
        policy_evaluator=policy_evaluator,
        audit_writer=audit_writer,
        literal_reader=literal_reader,
        relation_reader=relation_reader,
    )

    unsupported = await reader.read_active_literals(
        actor=_actor(HouseholdRole.OWNER, 7),
        subject_entity_id=7,
        predicate_alias="edad",
        consent=ConsentStatus.NOT_REQUIRED,
        correlation_id=_CORRELATION_ID,
        requested_at=_NOW,
    )
    wrong_kind = await reader.read_active_relations(
        actor=_actor(HouseholdRole.OWNER, 7),
        predicate_alias="le_gusta",
        target_entity_id=7,
        consent=ConsentStatus.NOT_REQUIRED,
        correlation_id=_CORRELATION_ID,
        requested_at=_NOW,
    )

    assert unsupported.status is KnowledgeStatus.UNKNOWN
    assert wrong_kind.status is KnowledgeStatus.UNKNOWN
    policy_evaluator.assert_not_called()
    audit_writer.assert_not_awaited()
    literal_reader.assert_not_awaited()
    relation_reader.assert_not_awaited()


@pytest.mark.asyncio
async def test_child_relation_requires_consent_before_raw_reader() -> None:
    """Reject sensitive child relationships before their raw values are read."""
    relation_reader = AsyncMock(return_value=[_child_relation()])
    audit_writer = AsyncMock()
    reader = PolicyGatedV4Reader(
        relation_reader=relation_reader,
        audit_writer=audit_writer,
    )

    result = await reader.read_active_relations(
        actor=_actor(HouseholdRole.OWNER, 7),
        predicate_alias="hijo_de",
        target_entity_id=7,
        consent=ConsentStatus.NOT_REQUIRED,
        correlation_id=_CORRELATION_ID,
        requested_at=_NOW,
    )

    assert result.status is KnowledgeStatus.UNAUTHORIZED
    assert result.relations == ()
    assert result.reason == "household data is not authorized"
    audit_writer.assert_awaited_once()
    relation_reader.assert_not_awaited()


@pytest.mark.asyncio
async def test_relation_requires_exactly_one_endpoint_before_collaborators() -> None:
    """Reject broad or conflicting relation queries before any policy/read work."""
    policy_evaluator = AsyncMock()
    audit_writer = AsyncMock()
    relation_reader = AsyncMock()
    reader = PolicyGatedV4Reader(
        policy_evaluator=policy_evaluator,
        audit_writer=audit_writer,
        relation_reader=relation_reader,
    )

    with pytest.raises(ValueError, match="exactly one"):
        await reader.read_active_relations(
            actor=_actor(HouseholdRole.OWNER, 7),
            predicate_alias="hijo_de",
            source_entity_id=8,
            target_entity_id=7,
            consent=ConsentStatus.GRANTED,
            correlation_id=_CORRELATION_ID,
            requested_at=_NOW,
        )
    with pytest.raises(ValueError, match="exactly one"):
        await reader.read_active_relations(
            actor=_actor(HouseholdRole.OWNER, 7),
            predicate_alias="hijo_de",
            consent=ConsentStatus.GRANTED,
            correlation_id=_CORRELATION_ID,
            requested_at=_NOW,
        )

    policy_evaluator.assert_not_called()
    audit_writer.assert_not_awaited()
    relation_reader.assert_not_awaited()
