"""Closed deterministic household tools over the policy-gated v4 reader."""

from collections.abc import Awaitable, Callable
from datetime import date, datetime
from enum import StrEnum
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
from server.cognition.calendar_tools import calculate_age
from server.cognition.identity import ActivePersonContext
from server.cognition.models import (
    AuthorizationAction,
    AuthorizationDecision,
    AuthorizationStatus,
    KnowledgeStatus,
)
from server.memory.entity_labels import EntityLabel, get_person_label
from server.memory.household_authorization import record_authorization_decision
from server.memory.policy_gated_v4_reader import PolicyGatedV4Reader
from server.memory.predicate_registry import PredicateDefinition, resolve_predicate

__all__ = [
    "HouseholdKnowledgeTools",
    "HouseholdToolName",
    "HouseholdToolResult",
    "PreferencePredicate",
]

type PolicyEvaluator = Callable[[AuthorizationRequest], AuthorizationDecision]
type AuditWriter = Callable[[AuthorizationRequest, AuthorizationDecision], Awaitable[None]]


class PersonLabelReader(Protocol):
    """Resolve one exact person label after an authorized relationship read."""

    def __call__(self, *, entity_id: int) -> Awaitable[EntityLabel | None]:
        """Return an exact person label or no label for the supplied ID."""
        ...


class HouseholdToolName(StrEnum):
    """Closed deterministic household tools available in P0.5-B2."""

    GET_CHILDREN = "get_children"
    COUNT_CHILDREN = "count_children"
    GET_PREFERENCES = "get_preferences"
    GET_PERSON_BIRTH_DATE = "get_person_birth_date"
    CALCULATE_PERSON_AGE = "calculate_person_age"


class PreferencePredicate(StrEnum):
    """Closed normal-sensitivity preference predicates available to the tools."""

    LIKES = "likes"
    DISLIKES = "dislikes"
    PREFERS = "prefers"


class HouseholdToolResult(BaseModel):
    """Immutable, non-generative result from one closed household tool."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool_name: HouseholdToolName
    status: KnowledgeStatus
    value: str | int | tuple[str, ...] | None = None
    reason: str | None = None


def _required_predicate(alias: str) -> PredicateDefinition:
    """Resolve a registered predicate required by this closed module."""
    definition = resolve_predicate(alias)
    if definition is None:
        raise RuntimeError(f"required predicate {alias!r} is not registered")
    return definition


_CHILD_OF = _required_predicate("child_of")
_BIRTH_DATE = _required_predicate("birth_date")


class HouseholdKnowledgeTools:
    """Authorize, audit, and execute narrow household tools over v4 storage."""

    def __init__(
        self,
        *,
        reader: PolicyGatedV4Reader,
        policy_evaluator: PolicyEvaluator = evaluate_authorization,
        audit_writer: AuditWriter = record_authorization_decision,
        label_reader: PersonLabelReader = get_person_label,
    ) -> None:
        """Create a tool service with explicit policy, reader, and label seams.

        Args:
            reader: Reader that independently authorizes/audits every v4 read.
            policy_evaluator: Deterministic local tool-execution policy.
            audit_writer: Local safe audit sink for tool-execution decisions.
            label_reader: Exact person-label lookup used after relation approval.
        """
        self._reader = reader
        self._policy_evaluator = policy_evaluator
        self._audit_writer = audit_writer
        self._label_reader = label_reader

    async def get_children(
        self,
        *,
        parent_entity_id: int,
        actor: ActivePersonContext,
        consent: ConsentStatus,
        correlation_id: UUID,
        requested_at: datetime,
    ) -> HouseholdToolResult:
        """Return all exact child labels for one authorized parent entity.

        Args:
            parent_entity_id: Parent entity selected by a trusted internal seam.
            actor: Trusted active household actor.
            consent: Trusted scoped consent for child data.
            correlation_id: Request-scoped audit correlation ID.
            requested_at: Aware request timestamp.

        Returns:
            Known complete labels, an explicit absence, or a non-disclosing denial.
        """
        allowed = await self._authorize_tool(
            actor=actor,
            target_person_id=parent_entity_id,
            definition=_CHILD_OF,
            consent=consent,
            correlation_id=correlation_id,
            requested_at=requested_at,
        )
        if not allowed:
            return _unauthorized(HouseholdToolName.GET_CHILDREN)
        read = await self._reader.read_active_relations(
            actor=actor,
            predicate_alias=_CHILD_OF.canonical_id,
            target_entity_id=parent_entity_id,
            consent=consent,
            correlation_id=correlation_id,
            requested_at=requested_at,
        )
        if read.status is KnowledgeStatus.UNAUTHORIZED:
            return _unauthorized(HouseholdToolName.GET_CHILDREN)
        if read.status is not KnowledgeStatus.KNOWN:
            return _unknown(HouseholdToolName.GET_CHILDREN, read.reason)

        child_ids = tuple(dict.fromkeys(relation.source_entity_id for relation in read.relations))
        labels: list[str] = []
        for child_id in child_ids:
            label = await self._label_reader(entity_id=child_id)
            if label is None:
                return _unknown(HouseholdToolName.GET_CHILDREN, "child label is unavailable")
            labels.append(label.display_name)
        return HouseholdToolResult(
            tool_name=HouseholdToolName.GET_CHILDREN,
            status=KnowledgeStatus.KNOWN,
            value=tuple(labels),
        )

    async def count_children(
        self,
        *,
        parent_entity_id: int,
        actor: ActivePersonContext,
        consent: ConsentStatus,
        correlation_id: UUID,
        requested_at: datetime,
    ) -> HouseholdToolResult:
        """Count unique active child entities for one authorized parent.

        Args:
            parent_entity_id: Parent entity selected by a trusted internal seam.
            actor: Trusted active household actor.
            consent: Trusted scoped consent for child data.
            correlation_id: Request-scoped audit correlation ID.
            requested_at: Aware request timestamp.

        Returns:
            A deterministic count, explicit absence, or non-disclosing denial.
        """
        allowed = await self._authorize_tool(
            actor=actor,
            target_person_id=parent_entity_id,
            definition=_CHILD_OF,
            consent=consent,
            correlation_id=correlation_id,
            requested_at=requested_at,
        )
        if not allowed:
            return _unauthorized(HouseholdToolName.COUNT_CHILDREN)
        read = await self._reader.read_active_relations(
            actor=actor,
            predicate_alias=_CHILD_OF.canonical_id,
            target_entity_id=parent_entity_id,
            consent=consent,
            correlation_id=correlation_id,
            requested_at=requested_at,
        )
        if read.status is KnowledgeStatus.UNAUTHORIZED:
            return _unauthorized(HouseholdToolName.COUNT_CHILDREN)
        if read.status is not KnowledgeStatus.KNOWN:
            return _unknown(HouseholdToolName.COUNT_CHILDREN, read.reason)
        return HouseholdToolResult(
            tool_name=HouseholdToolName.COUNT_CHILDREN,
            status=KnowledgeStatus.KNOWN,
            value=len({relation.source_entity_id for relation in read.relations}),
        )

    async def get_preferences(
        self,
        *,
        person_entity_id: int,
        preference: PreferencePredicate,
        actor: ActivePersonContext,
        consent: ConsentStatus,
        correlation_id: UUID,
        requested_at: datetime,
    ) -> HouseholdToolResult:
        """Return all active values of one closed preference predicate.

        Args:
            person_entity_id: Person entity selected by a trusted internal seam.
            preference: Closed preference predicate to read.
            actor: Trusted active household actor.
            consent: Trusted scoped consent state.
            correlation_id: Request-scoped audit correlation ID.
            requested_at: Aware request timestamp.

        Returns:
            All active values, explicit absence, or a non-disclosing denial.
        """
        definition = _required_predicate(preference.value)
        allowed = await self._authorize_tool(
            actor=actor,
            target_person_id=person_entity_id,
            definition=definition,
            consent=consent,
            correlation_id=correlation_id,
            requested_at=requested_at,
        )
        if not allowed:
            return _unauthorized(HouseholdToolName.GET_PREFERENCES)
        read = await self._reader.read_active_literals(
            actor=actor,
            subject_entity_id=person_entity_id,
            predicate_alias=definition.canonical_id,
            consent=consent,
            correlation_id=correlation_id,
            requested_at=requested_at,
        )
        if read.status is KnowledgeStatus.UNAUTHORIZED:
            return _unauthorized(HouseholdToolName.GET_PREFERENCES)
        if read.status is not KnowledgeStatus.KNOWN:
            return _unknown(HouseholdToolName.GET_PREFERENCES, read.reason)
        return HouseholdToolResult(
            tool_name=HouseholdToolName.GET_PREFERENCES,
            status=KnowledgeStatus.KNOWN,
            value=tuple(fact.value_text for fact in read.facts),
        )

    async def get_person_birth_date(
        self,
        *,
        person_entity_id: int,
        actor: ActivePersonContext,
        consent: ConsentStatus,
        correlation_id: UUID,
        requested_at: datetime,
    ) -> HouseholdToolResult:
        """Return one authorized birth date without deriving an age.

        Args:
            person_entity_id: Person entity selected by a trusted internal seam.
            actor: Trusted active household actor.
            consent: Trusted scoped consent for child data.
            correlation_id: Request-scoped audit correlation ID.
            requested_at: Aware request timestamp.

        Returns:
            One strict ISO birth date, explicit absence, contradiction, or denial.
        """
        return await self._birth_date_result(
            tool_name=HouseholdToolName.GET_PERSON_BIRTH_DATE,
            person_entity_id=person_entity_id,
            actor=actor,
            consent=consent,
            correlation_id=correlation_id,
            requested_at=requested_at,
        )

    async def calculate_person_age(
        self,
        *,
        person_entity_id: int,
        actor: ActivePersonContext,
        consent: ConsentStatus,
        correlation_id: UUID,
        requested_at: datetime,
        on_date: date,
    ) -> HouseholdToolResult:
        """Calculate completed years from one authorized strict ISO birth date.

        Args:
            person_entity_id: Person entity selected by a trusted internal seam.
            actor: Trusted active household actor.
            consent: Trusted scoped consent for child data.
            correlation_id: Request-scoped audit correlation ID.
            requested_at: Aware request timestamp.
            on_date: Deterministic local date on which to calculate completed years.

        Returns:
            A deterministic age, explicit absence/contradiction, or denial.
        """
        birth_date = await self._birth_date_result(
            tool_name=HouseholdToolName.CALCULATE_PERSON_AGE,
            person_entity_id=person_entity_id,
            actor=actor,
            consent=consent,
            correlation_id=correlation_id,
            requested_at=requested_at,
        )
        if birth_date.status is not KnowledgeStatus.KNOWN or not isinstance(birth_date.value, str):
            return birth_date
        age = calculate_age(birth_date.value, on_date)
        return HouseholdToolResult(
            tool_name=HouseholdToolName.CALCULATE_PERSON_AGE,
            status=age.status,
            value=age.value,
            reason=age.reason,
        )

    async def _birth_date_result(
        self,
        *,
        tool_name: HouseholdToolName,
        person_entity_id: int,
        actor: ActivePersonContext,
        consent: ConsentStatus,
        correlation_id: UUID,
        requested_at: datetime,
    ) -> HouseholdToolResult:
        """Read exactly one authorized current birth date for one tool invocation."""
        allowed = await self._authorize_tool(
            actor=actor,
            target_person_id=person_entity_id,
            definition=_BIRTH_DATE,
            consent=consent,
            correlation_id=correlation_id,
            requested_at=requested_at,
        )
        if not allowed:
            return _unauthorized(tool_name)
        read = await self._reader.read_active_literals(
            actor=actor,
            subject_entity_id=person_entity_id,
            predicate_alias=_BIRTH_DATE.canonical_id,
            consent=consent,
            correlation_id=correlation_id,
            requested_at=requested_at,
        )
        if read.status is KnowledgeStatus.UNAUTHORIZED:
            return _unauthorized(tool_name)
        if read.status is not KnowledgeStatus.KNOWN:
            return _unknown(tool_name, read.reason)
        if len(read.facts) != 1:
            return HouseholdToolResult(
                tool_name=tool_name,
                status=KnowledgeStatus.CONTRADICTORY,
                reason="multiple active birth dates",
            )
        return HouseholdToolResult(
            tool_name=tool_name,
            status=KnowledgeStatus.KNOWN,
            value=read.facts[0].value_text,
        )

    async def _authorize_tool(
        self,
        *,
        actor: ActivePersonContext,
        target_person_id: int,
        definition: PredicateDefinition,
        consent: ConsentStatus,
        correlation_id: UUID,
        requested_at: datetime,
    ) -> bool:
        """Evaluate and audit tool execution before any reader or label call."""
        request = AuthorizationRequest(
            actor=actor,
            action=AuthorizationAction.EXECUTE_HOUSEHOLD_TOOL,
            target_person_id=target_person_id,
            visibility=frozenset({DataVisibility(definition.default_visibility)}),
            sensitivity=frozenset({DataSensitivity(definition.default_sensitivity)}),
            consent=consent,
            correlation_id=correlation_id,
            requested_at=requested_at,
        )
        decision = self._policy_evaluator(request)
        await self._audit_writer(request, decision)
        return decision.decision is AuthorizationStatus.ALLOWED


def _unauthorized(tool_name: HouseholdToolName) -> HouseholdToolResult:
    """Return the one non-disclosing denial shared by all household tools."""
    return HouseholdToolResult(
        tool_name=tool_name,
        status=KnowledgeStatus.UNAUTHORIZED,
        reason="household tool is not authorized",
    )


def _unknown(tool_name: HouseholdToolName, reason: str | None) -> HouseholdToolResult:
    """Return an explicit permitted absence without inventing a household value."""
    return HouseholdToolResult(
        tool_name=tool_name,
        status=KnowledgeStatus.UNKNOWN,
        reason=reason,
    )
