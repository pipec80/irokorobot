"""Closed deterministic household tools over the policy-gated v4 reader."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
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
from server.memory.entity_labels import EntityLabel, get_person_label, get_pet_label
from server.memory.household_authorization import record_authorization_decision
from server.memory.policy_gated_v4_reader import PolicyGatedV4Reader
from server.memory.predicate_registry import PredicateDefinition, resolve_predicate

__all__ = [
    "ChildBirthdays",
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
    GET_RELATIVES = "get_relatives"


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


@dataclass(frozen=True)
class ChildBirthdays:
    """The owner's children with their birth dates, for the spoken birthday question.

    Attributes:
        status: ``KNOWN`` when the children were read, ``UNAUTHORIZED`` when any policy step
            refused, ``UNKNOWN`` when there is no authorized record.
        children: ``(label, ISO date or None)`` per child, sorted by label; ``None`` when the
            child has no date or more than one (the contradiction is not chosen between). Hidden
            from ``repr``: it carries names and dates.
    """

    status: KnowledgeStatus
    children: tuple[tuple[str, str | None], ...] = field(default=(), repr=False)


def _required_predicate(alias: str) -> PredicateDefinition:
    """Resolve a registered predicate required by this closed module."""
    definition = resolve_predicate(alias)
    if definition is None:
        raise RuntimeError(f"required predicate {alias!r} is not registered")
    return definition


_CHILD_OF = _required_predicate("child_of")
_BIRTH_DATE = _required_predicate("birth_date")
# The relations «¿cómo se llaman mis papás?» reads (ADR 0028 decision 9), and which end of the
# row the owner stands on: the relatives point from the owner, a pet to the owner, and the
# partner may be on either end (the relation is symmetric).
_FROM_THE_OWNER = frozenset({"has_parent", "has_sibling", "has_grandparent", "has_grandchild"})
_TO_THE_OWNER = frozenset({"pet_of"})
_EITHER_END = frozenset({"partner_of"})
_PET = "pet_of"


class HouseholdKnowledgeTools:
    """Authorize, audit, and execute narrow household tools over v4 storage."""

    def __init__(
        self,
        *,
        reader: PolicyGatedV4Reader,
        policy_evaluator: PolicyEvaluator = evaluate_authorization,
        audit_writer: AuditWriter = record_authorization_decision,
        label_reader: PersonLabelReader = get_person_label,
        pet_label_reader: PersonLabelReader = get_pet_label,
    ) -> None:
        """Create a tool service with explicit policy, reader, and label seams.

        Args:
            reader: Reader that independently authorizes/audits every v4 read.
            policy_evaluator: Deterministic local tool-execution policy.
            audit_writer: Local safe audit sink for tool-execution decisions.
            label_reader: Exact person-label lookup used after relation approval.
            pet_label_reader: The same for a pet, read only for ``pet_of``.
        """
        self._reader = reader
        self._policy_evaluator = policy_evaluator
        self._audit_writer = audit_writer
        self._label_reader = label_reader
        self._pet_label_reader = pet_label_reader

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
        child_ids = await self._child_ids(
            parent_entity_id=parent_entity_id,
            actor=actor,
            consent=consent,
            correlation_id=correlation_id,
            requested_at=requested_at,
        )
        if isinstance(child_ids, HouseholdToolResult):
            return child_ids
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

    async def get_children_birthdays(
        self,
        *,
        parent_entity_id: int,
        actor: ActivePersonContext,
        consent: ConsentStatus,
        correlation_id: UUID,
        requested_at: datetime,
    ) -> ChildBirthdays:
        """Return each child's label and birth date for one authorized parent (Plan 0079 D-10).

        It composes the paths that exist: the ``child_of`` read of ``get_children`` for the
        children, then ``get_person_birth_date`` per child, so every step is authorized and
        audited by the code that already does so and no new policy path exists.

        Args:
            parent_entity_id: Parent entity selected by a trusted internal seam.
            actor: Trusted active household actor.
            consent: Trusted scoped consent for child data.
            correlation_id: Request-scoped audit correlation ID.
            requested_at: Aware request timestamp.

        Returns:
            The children sorted by label, each with its ISO date or ``None``; ``UNAUTHORIZED``
            as a whole when any step was refused; ``UNKNOWN`` without a known list of children.
        """
        child_ids = await self._child_ids(
            parent_entity_id=parent_entity_id,
            actor=actor,
            consent=consent,
            correlation_id=correlation_id,
            requested_at=requested_at,
        )
        if isinstance(child_ids, HouseholdToolResult):
            return ChildBirthdays(status=child_ids.status)
        children: list[tuple[str, str | None]] = []
        for child_id in child_ids:
            label = await self._label_reader(entity_id=child_id)
            if label is None:
                return ChildBirthdays(status=KnowledgeStatus.UNKNOWN)
            born = await self.get_person_birth_date(
                person_entity_id=child_id,
                actor=actor,
                consent=consent,
                correlation_id=correlation_id,
                requested_at=requested_at,
            )
            if born.status is KnowledgeStatus.UNAUTHORIZED:
                return ChildBirthdays(status=KnowledgeStatus.UNAUTHORIZED)
            known = born.value if born.status is KnowledgeStatus.KNOWN else None
            children.append((label.display_name, known if isinstance(known, str) else None))
        return ChildBirthdays(
            status=KnowledgeStatus.KNOWN,
            children=tuple(sorted(children, key=lambda child: child[0])),
        )

    async def _child_ids(
        self,
        *,
        parent_entity_id: int,
        actor: ActivePersonContext,
        consent: ConsentStatus,
        correlation_id: UUID,
        requested_at: datetime,
    ) -> tuple[int, ...] | HouseholdToolResult:
        """Authorize, audit and read the ``child_of`` relations: the child ids, or the refusal.

        The refusal is the ``get_children`` result, which ``get_children_birthdays`` maps to its
        own status.
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
        return tuple(dict.fromkeys(relation.source_entity_id for relation in read.relations))

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

    async def get_relatives(
        self,
        *,
        owner_entity_id: int,
        predicate: str,
        actor: ActivePersonContext,
        consent: ConsentStatus,
        correlation_id: UUID,
        requested_at: datetime,
    ) -> HouseholdToolResult:
        """Return the names of the owner's relatives, partner or pets of one relation, sorted.

        Args:
            owner_entity_id: The owner, selected by a trusted internal seam.
            predicate: ``has_parent``, ``has_sibling``, ``has_grandparent``, ``has_grandchild``,
                ``partner_of`` or ``pet_of``.
            actor: Trusted active household actor.
            consent: Trusted scoped consent state.
            correlation_id: Request-scoped audit correlation ID.
            requested_at: Aware request timestamp.

        Returns:
            Known names, an explicit absence, or a non-disclosing denial.

        Raises:
            ValueError: If *predicate* is not one of the relatives relations.
        """
        if predicate not in _FROM_THE_OWNER | _TO_THE_OWNER | _EITHER_END:
            raise ValueError("not one of the relatives relations")
        definition = _required_predicate(predicate)
        allowed = await self._authorize_tool(
            actor=actor,
            target_person_id=owner_entity_id,
            definition=definition,
            consent=consent,
            correlation_id=correlation_id,
            requested_at=requested_at,
        )
        if not allowed:
            return _unauthorized(HouseholdToolName.GET_RELATIVES)
        ids: list[int] = []
        for owner_is_source in _owner_ends(predicate):
            read = await self._reader.read_active_relations(
                actor=actor,
                predicate_alias=definition.canonical_id,
                source_entity_id=owner_entity_id if owner_is_source else None,
                target_entity_id=None if owner_is_source else owner_entity_id,
                consent=consent,
                correlation_id=correlation_id,
                requested_at=requested_at,
            )
            if read.status is KnowledgeStatus.UNAUTHORIZED:
                return _unauthorized(HouseholdToolName.GET_RELATIVES)
            ids += [
                relation.target_entity_id if owner_is_source else relation.source_entity_id
                for relation in read.relations
            ]
        return await self._relatives_result(predicate, owner_entity_id, ids)

    async def _relatives_result(
        self, predicate: str, owner_entity_id: int, ids: list[int]
    ) -> HouseholdToolResult:
        """Label the related entities; nothing related is an explicit absence."""
        read_label = self._pet_label_reader if predicate == _PET else self._label_reader
        names: list[str] = []
        for entity_id in dict.fromkeys(ids):
            if entity_id == owner_entity_id:
                continue
            label = await read_label(entity_id=entity_id)
            if label is None:
                return _unknown(HouseholdToolName.GET_RELATIVES, "relative label is unavailable")
            names.append(label.display_name)
        if not names:
            return _unknown(HouseholdToolName.GET_RELATIVES, "no active authorized record")
        return HouseholdToolResult(
            tool_name=HouseholdToolName.GET_RELATIVES,
            status=KnowledgeStatus.KNOWN,
            value=tuple(sorted(names)),
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


def _owner_ends(predicate: str) -> tuple[bool, ...]:
    """Whether the owner is the source (``True``) or the target (``False``) of each read."""
    if predicate in _FROM_THE_OWNER:
        return (True,)
    if predicate in _TO_THE_OWNER:
        return (False,)
    return (True, False)


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
