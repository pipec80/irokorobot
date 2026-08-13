"""Policy-gated runtime reads for relational-memory v4."""

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from server.cognition.authorization import (
    AuthorizationRequest,
    ConsentStatus,
    DataSensitivity,
    DataVisibility,
    evaluate_authorization,
)
from server.cognition.identity import ActivePersonContext
from server.cognition.models import (
    AuthorizationAction,
    AuthorizationDecision,
    AuthorizationStatus,
    KnowledgeStatus,
)
from server.memory.household_authorization import record_authorization_decision
from server.memory.predicate_registry import PredicateDefinition, PredicateKind, resolve_predicate
from server.memory.relational_v4 import (
    EntityRelationV4,
    LiteralFactV4,
    get_active_entity_relations,
    get_active_literal_facts,
)

__all__ = ["LiteralReadResult", "PolicyGatedV4Reader", "RelationReadResult"]

type PolicyEvaluator = Callable[[AuthorizationRequest], AuthorizationDecision]
type AuditWriter = Callable[[AuthorizationRequest, AuthorizationDecision], Awaitable[None]]


class LiteralReader(Protocol):
    """Raw literal-read boundary injected into the policy-gated reader."""

    def __call__(
        self,
        *,
        subject_entity_id: int,
        definition: PredicateDefinition,
    ) -> Awaitable[list[LiteralFactV4]]:
        """Return active raw v4 literal rows."""
        ...


class RelationReader(Protocol):
    """Raw relation-read boundary injected into the policy-gated reader."""

    def __call__(
        self,
        *,
        definition: PredicateDefinition,
        source_entity_id: int | None = None,
        target_entity_id: int | None = None,
    ) -> Awaitable[list[EntityRelationV4]]:
        """Return active raw v4 relation rows."""
        ...


class LiteralReadResult(BaseModel):
    """Immutable outcome of one policy-gated literal-fact read."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: KnowledgeStatus
    facts: tuple[LiteralFactV4, ...] = ()
    reason: str | None = None


class RelationReadResult(BaseModel):
    """Immutable outcome of one policy-gated entity-relation read."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: KnowledgeStatus
    relations: tuple[EntityRelationV4, ...] = ()
    reason: str | None = None


class PolicyGatedV4Reader:
    """Authorize and audit bounded v4 reads before raw storage access."""

    def __init__(
        self,
        *,
        policy_evaluator: PolicyEvaluator = evaluate_authorization,
        audit_writer: AuditWriter = record_authorization_decision,
        literal_reader: LiteralReader = get_active_literal_facts,
        relation_reader: RelationReader = get_active_entity_relations,
    ) -> None:
        """Create a reader with injectable policy, audit, and storage seams.

        Args:
            policy_evaluator: Pure local evaluator for one request.
            audit_writer: Safe local decision-audit writer.
            literal_reader: Raw v4 literal repository boundary.
            relation_reader: Raw v4 relation repository boundary.
        """
        self._policy_evaluator = policy_evaluator
        self._audit_writer = audit_writer
        self._literal_reader = literal_reader
        self._relation_reader = relation_reader

    async def read_active_literals(
        self,
        *,
        actor: ActivePersonContext,
        subject_entity_id: int,
        predicate_alias: str,
        consent: ConsentStatus,
        correlation_id: UUID,
        requested_at: datetime,
    ) -> LiteralReadResult:
        """Read authorized active literals for one subject and closed predicate.

        Args:
            actor: Trusted active-person context supplied by an internal adapter.
            subject_entity_id: Integer entity ID whose literal facts are requested.
            predicate_alias: Closed v4 literal predicate alias.
            consent: Trusted consent state for this exact request.
            correlation_id: Request-scoped correlation identifier.
            requested_at: Aware request timestamp.

        Returns:
            Known rows, an explicit permitted absence, or a non-disclosing
            unauthorized result.
        """
        definition = _definition_for_kind(predicate_alias, PredicateKind.LITERAL)
        if definition is None:
            return LiteralReadResult(status=KnowledgeStatus.UNKNOWN)

        decision = await self._authorize(
            actor=actor,
            target_person_id=subject_entity_id,
            definition=definition,
            consent=consent,
            correlation_id=correlation_id,
            requested_at=requested_at,
        )
        if decision.decision is not AuthorizationStatus.ALLOWED:
            return LiteralReadResult(
                status=KnowledgeStatus.UNAUTHORIZED,
                reason="household data is not authorized",
            )

        facts = await self._literal_reader(
            subject_entity_id=subject_entity_id,
            definition=definition,
        )
        if not facts:
            return LiteralReadResult(
                status=KnowledgeStatus.UNKNOWN,
                reason="no active authorized record",
            )
        return LiteralReadResult(status=KnowledgeStatus.KNOWN, facts=tuple(facts))

    async def read_active_relations(
        self,
        *,
        actor: ActivePersonContext,
        predicate_alias: str,
        source_entity_id: int | None = None,
        target_entity_id: int | None = None,
        consent: ConsentStatus,
        correlation_id: UUID,
        requested_at: datetime,
    ) -> RelationReadResult:
        """Read authorized active relations for exactly one entity endpoint.

        Args:
            actor: Trusted active-person context supplied by an internal adapter.
            predicate_alias: Closed v4 relation predicate alias.
            source_entity_id: Optional source relation endpoint.
            target_entity_id: Optional target relation endpoint.
            consent: Trusted consent state for this exact request.
            correlation_id: Request-scoped correlation identifier.
            requested_at: Aware request timestamp.

        Returns:
            Known rows, an explicit permitted absence, or a non-disclosing
            unauthorized result.

        Raises:
            ValueError: If zero or both entity endpoint filters are supplied.
        """
        if (source_entity_id is None) == (target_entity_id is None):
            raise ValueError("relation reads require exactly one entity endpoint")
        definition = _definition_for_kind(predicate_alias, PredicateKind.RELATION)
        if definition is None:
            return RelationReadResult(status=KnowledgeStatus.UNKNOWN)

        selected_entity_id = source_entity_id if source_entity_id is not None else target_entity_id
        if selected_entity_id is None:
            raise RuntimeError("validated relation endpoint was unexpectedly absent")
        decision = await self._authorize(
            actor=actor,
            target_person_id=selected_entity_id,
            definition=definition,
            consent=consent,
            correlation_id=correlation_id,
            requested_at=requested_at,
        )
        if decision.decision is not AuthorizationStatus.ALLOWED:
            return RelationReadResult(
                status=KnowledgeStatus.UNAUTHORIZED,
                reason="household data is not authorized",
            )

        relations = await self._relation_reader(
            definition=definition,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
        )
        if not relations:
            return RelationReadResult(
                status=KnowledgeStatus.UNKNOWN,
                reason="no active authorized record",
            )
        return RelationReadResult(status=KnowledgeStatus.KNOWN, relations=tuple(relations))

    async def _authorize(
        self,
        *,
        actor: ActivePersonContext,
        target_person_id: int,
        definition: PredicateDefinition,
        consent: ConsentStatus,
        correlation_id: UUID,
        requested_at: datetime,
    ) -> AuthorizationDecision:
        """Evaluate and audit one predicate-classified read before storage access."""
        request = AuthorizationRequest(
            actor=actor,
            action=AuthorizationAction.READ_HOUSEHOLD_DATA,
            target_person_id=target_person_id,
            visibility=frozenset({DataVisibility(definition.default_visibility)}),
            sensitivity=frozenset({DataSensitivity(definition.default_sensitivity)}),
            consent=consent,
            correlation_id=correlation_id,
            requested_at=requested_at,
        )
        decision = self._policy_evaluator(request)
        await self._audit_writer(request, decision)
        return decision


def _definition_for_kind(
    predicate_alias: str,
    expected_kind: PredicateKind,
) -> PredicateDefinition | None:
    """Resolve one closed predicate only when it has the expected storage kind."""
    definition = resolve_predicate(predicate_alias)
    return definition if definition is not None and definition.kind is expected_kind else None
