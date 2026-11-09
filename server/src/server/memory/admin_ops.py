"""The local admin orchestrator: one change through a writer, one audit row (Plan 0073, ADR 0025).

Every admin edit goes through the canonical writers with the channel ``admin_local`` (decision 4);
the writer assigns the classification, never this module. A change to sensitive data (medical,
location, security), to a contact, or about anyone but the owner needs the owner's PIN, passed as
``owner_verified`` (the command verifies it offline). The write and its audit row commit or roll
back together: a closed refusal is audited and kept, an unexpected failure rolls back both. No
outcome, audit row or log holds a value, a name or a phone.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager, nullcontext
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from server import db
from server.exceptions import UnstorableValueError, WriteRefusedError
from server.memory.admin_audit import (
    AdminActorRole,
    AdminOperationKind,
    AdminOutcomeStatus,
    TargetKind,
    record_admin_operation,
)
from server.memory.canonical_writer import write_literal, write_relation
from server.memory.care_contacts import ContactRole, revoke_contact, write_contact
from server.memory.predicate_registry import resolve_predicate
from server.memory.relational_v4 import (
    list_active_relations,
    revoke_entity_relation,
    revoke_literal_fact,
)
from server.memory.write_types import ConflictPolicy, WriteChannel

if TYPE_CHECKING:
    from server.memory.relational_v4 import EntityRelationV4

__all__ = [
    "AdminActor",
    "AdminOutcome",
    "ContactTerms",
    "SideLabel",
    "apply_contact_edit",
    "apply_literal_edit",
    "apply_revoke",
    "apply_side_label",
    "requires_owner_verification",
]

type SideLabel = Literal["mother", "father", "daughter", "son"]

_CHANNEL: WriteChannel = WriteChannel.ADMIN_LOCAL
_POLICY: ConflictPolicy = ConflictPolicy.SUPERSEDE
_CHANGE = AdminOperationKind.CHANGE
# The sensitivities ADR 0025 decision 4 names for the owner's own data (``private`` is excluded).
_SENSITIVE = frozenset({"medical", "location", "security"})
_OWNER_NOT_VERIFIED = "owner_not_verified"
_UNSTORABLE = "unstorable_value"
_INVALID = "invalid_value"
# The sides of a relative or a child (Plan 0080 D-4, D-7): the predicate each side is stored as,
# the unlabelled row each kind of side starts from, and the markers a child may hold (one).
_SIDE_PREDICATES: dict[SideLabel, str] = {
    "mother": "has_mother",
    "father": "has_father",
    "daughter": "daughter_of",
    "son": "son_of",
}
_PARENT_SIDES = frozenset({"mother", "father"})
_PARENT_ROW = "has_parent"
_CHILD_ROW = "child_of"
_CHILD_MARKERS = ("daughter_of", "son_of")
_PARENT_SIDE_ROWS = ("has_mother", "has_father")
_PARENT_ROWS = (_PARENT_ROW, *_PARENT_SIDE_ROWS)
# An id that is not among the owner's active relations: unknown, revoked or somebody else's.
_NOT_AN_ACTIVE_RELATION = "not_an_active_relation"
_WRONG_RELATION_KIND = "wrong_relation_kind"
_ALREADY_LABELLED = "already_labelled"


@dataclass(frozen=True)
class AdminActor:
    """Who runs the operation; the label is free text kept out of the ``repr`` and the logs."""

    label: str = field(repr=False)
    role: AdminActorRole


@dataclass(frozen=True)
class AdminOutcome:
    """What one admin operation did; ``reason`` is a closed word or ``None``."""

    operation: AdminOperationKind
    status: AdminOutcomeStatus
    reason: str | None = None


@dataclass(frozen=True)
class ContactTerms:
    """The terms of a contact edit; its ``repr`` omits the phones and the relationship."""

    phone: str = field(repr=False)
    phone_alt: str | None = field(default=None, repr=False)
    relationship: str | None = field(default=None, repr=False)
    call_order: int | None = None
    has_key: bool = False
    may_receive_health_info: bool = False
    may_view_activity: bool = False


def requires_owner_verification(
    *, target_kind: TargetKind, predicate: str | None, subject_is_owner: bool
) -> bool:
    """Return whether the owner's PIN is required (ADR 0025 decision 4).

    A contact, anyone but the owner, or a ``medical``/``location``/``security`` predicate needs
    it; the owner's own ``normal`` or ``private`` data does not. An unknown predicate is treated
    as requiring it (conservative).

    Args:
        target_kind: What the operation acts on.
        predicate: The predicate id, for a pool edit; ``None`` for a contact.
        subject_is_owner: Whether the subject is the owner themselves.

    Returns:
        Whether the owner's verification is required.
    """
    if target_kind is TargetKind.CARE_CONTACT or not subject_is_owner:
        return True
    if predicate is None:
        return True
    definition = resolve_predicate(predicate)
    if definition is None:
        return True
    return definition.default_sensitivity in _SENSITIVE


def _transaction(manage_transaction: bool) -> AbstractAsyncContextManager[object]:
    """Own a transaction, or join the one the caller owns (``db.transaction`` is not reentrant)."""
    return db.transaction() if manage_transaction else nullcontext()


async def _audit(
    actor: AdminActor,
    *,
    operation: AdminOperationKind,
    target_kind: TargetKind,
    field_id: str | None,
    target_entity_id: int | None,
    status: AdminOutcomeStatus,
    reason: str | None,
    now: str,
) -> None:
    """Append the one audit row of an operation, inside the caller's transaction."""
    await record_admin_operation(
        actor_label=actor.label,
        actor_role=actor.role,
        operation=operation,
        target_kind=target_kind,
        field_id=field_id,
        target_entity_id=target_entity_id,
        outcome=status,
        reason=reason,
        recorded_at=now,
        manage_transaction=False,
    )


async def apply_literal_edit(
    *,
    actor: AdminActor,
    owner_entity_id: int,
    subject_entity_id: int,
    predicate: str,
    value: str,
    kind: AdminOperationKind,
    now: str,
    owner_verified: bool,
    manage_transaction: bool = True,
) -> AdminOutcome:
    """Add or change one pool literal through the canonical writer, and audit it.

    Args:
        actor: Who runs it (for the audit).
        owner_entity_id: The household owner (asserter and confirmer).
        subject_entity_id: The entity the fact is about (the owner, a child or a pet).
        predicate: A registered literal predicate or alias.
        value: The raw value; the writer normalizes it.
        kind: ``add`` or ``change``.
        now: UTC ISO 8601; shared by the write and the audit row.
        owner_verified: Whether the owner's PIN was verified (required for sensitive data).
        manage_transaction: ``False`` joins the caller's open transaction.

    Returns:
        The outcome; a closed refusal is reported and audited, never raised.
    """
    subject_is_owner = subject_entity_id == owner_entity_id
    async with _transaction(manage_transaction):
        if (
            requires_owner_verification(
                target_kind=TargetKind.POOL_LITERAL,
                predicate=predicate,
                subject_is_owner=subject_is_owner,
            )
            and not owner_verified
        ):
            return await _refused(
                actor,
                kind,
                TargetKind.POOL_LITERAL,
                predicate,
                subject_entity_id,
                _OWNER_NOT_VERIFIED,
                now,
            )
        status, reason = await _attempt_literal(
            owner_entity_id, subject_entity_id, predicate, value, now
        )
        await _audit(
            actor,
            operation=kind,
            target_kind=TargetKind.POOL_LITERAL,
            field_id=predicate,
            target_entity_id=subject_entity_id,
            status=status,
            reason=reason,
            now=now,
        )
        return AdminOutcome(kind, status, reason)


async def _attempt_literal(
    owner_entity_id: int, subject_entity_id: int, predicate: str, value: str, now: str
) -> tuple[AdminOutcomeStatus, str | None]:
    """Run the literal write and map a closed refusal to a status and a reason."""
    try:
        await write_literal(
            owner_entity_id=owner_entity_id,
            subject_entity_id=subject_entity_id,
            predicate=predicate,
            value=value,
            channel=_CHANNEL,
            confirmed_at=now,
            asserted_at=now,
            on_conflict=_POLICY,
            manage_transaction=False,
        )
    except WriteRefusedError as exc:
        return AdminOutcomeStatus.REFUSED, exc.reason
    except UnstorableValueError:
        return AdminOutcomeStatus.REFUSED, _UNSTORABLE
    except ValueError:
        return AdminOutcomeStatus.REFUSED, _INVALID
    return AdminOutcomeStatus.APPLIED, None


async def apply_contact_edit(
    *,
    actor: AdminActor,
    owner_entity_id: int,
    contact_entity_id: int,
    role: ContactRole,
    terms: ContactTerms,
    kind: AdminOperationKind,
    now: str,
    owner_verified: bool,
    manage_transaction: bool = True,
) -> AdminOutcome:
    """Add or change one care contact through the contacts writer, and audit it.

    A contact always needs the owner's PIN (ADR 0025 decision 4). Args mirror
    ``apply_literal_edit``; ``terms`` carries the phone, the optional second phone, the
    relationship, the order and the flags.

    Returns:
        The outcome; a closed refusal is reported and audited, never raised.
    """
    async with _transaction(manage_transaction):
        if not owner_verified:
            return await _refused(
                actor,
                kind,
                TargetKind.CARE_CONTACT,
                role.value,
                contact_entity_id,
                _OWNER_NOT_VERIFIED,
                now,
            )
        status, reason = await _attempt_contact(
            owner_entity_id, contact_entity_id, role, terms, now
        )
        await _audit(
            actor,
            operation=kind,
            target_kind=TargetKind.CARE_CONTACT,
            field_id=role.value,
            target_entity_id=contact_entity_id,
            status=status,
            reason=reason,
            now=now,
        )
        return AdminOutcome(kind, status, reason)


async def _attempt_contact(
    owner_entity_id: int,
    contact_entity_id: int,
    role: ContactRole,
    terms: ContactTerms,
    now: str,
) -> tuple[AdminOutcomeStatus, str | None]:
    """Run the contact write and map a closed refusal to a status and a reason."""
    try:
        await write_contact(
            owner_entity_id=owner_entity_id,
            contact_entity_id=contact_entity_id,
            role=role,
            phone=terms.phone,
            channel=_CHANNEL,
            confirmed_at=now,
            phone_alt=terms.phone_alt,
            relationship=terms.relationship,
            call_order=terms.call_order,
            has_key=terms.has_key,
            may_receive_health_info=terms.may_receive_health_info,
            may_view_activity=terms.may_view_activity,
            on_conflict=_POLICY,
            manage_transaction=False,
        )
    except WriteRefusedError as exc:
        return AdminOutcomeStatus.REFUSED, exc.reason
    except ValueError:
        return AdminOutcomeStatus.REFUSED, _INVALID
    return AdminOutcomeStatus.APPLIED, None


async def apply_revoke(
    *,
    actor: AdminActor,
    target_kind: TargetKind,
    target_id: int,
    subject_is_owner: bool,
    predicate: str | None,
    now: str,
    owner_verified: bool,
    manage_transaction: bool = True,
) -> AdminOutcome:
    """Revoke one datum to inactive (never a hard delete) and audit it.

    Args:
        actor: Who runs it (for the audit).
        target_kind: Which repository the row lives in.
        target_id: The row id (a fact, relation or contact id — not an entity id).
        subject_is_owner: Whether the affected subject is the owner (for the PIN rule).
        predicate: The predicate id for a pool row, or ``None`` for a contact.
        now: UTC ISO 8601; shared by the revoke and the audit row.
        owner_verified: Whether the owner's PIN was verified (required for a contact, a
            non-owner subject or a sensitive predicate).
        manage_transaction: ``False`` joins the caller's open transaction.

    Returns:
        The outcome; a second revoke of the same id is still ``applied`` (a no-op).
    """
    async with _transaction(manage_transaction):
        if (
            requires_owner_verification(
                target_kind=target_kind, predicate=predicate, subject_is_owner=subject_is_owner
            )
            and not owner_verified
        ):
            return await _refused(
                actor,
                AdminOperationKind.REVOKE,
                target_kind,
                predicate,
                None,
                _OWNER_NOT_VERIFIED,
                now,
            )
        match target_kind:
            case TargetKind.POOL_LITERAL:
                await revoke_literal_fact(target_id, revoked_at=now, manage_transaction=False)
            case TargetKind.POOL_RELATION:
                await revoke_entity_relation(target_id, revoked_at=now, manage_transaction=False)
            case TargetKind.CARE_CONTACT:
                await revoke_contact(target_id, revoked_at=now, manage_transaction=False)
        await _audit(
            actor,
            operation=AdminOperationKind.REVOKE,
            target_kind=target_kind,
            field_id=predicate,
            target_entity_id=None,
            status=AdminOutcomeStatus.APPLIED,
            reason=None,
            now=now,
        )
        return AdminOutcome(AdminOperationKind.REVOKE, AdminOutcomeStatus.APPLIED, None)


async def apply_side_label(
    *,
    actor: AdminActor,
    owner_entity_id: int,
    relation_id: int,
    side: SideLabel,
    now: str,
    owner_verified: bool,
    manage_transaction: bool = True,
) -> AdminOutcome:
    """Say which side a relative or a child is, through the canonical writer, and audit it.

    Plan 0080 D-7. A parent side (``mother``, ``father``) takes an active ``has_parent`` row of
    the owner, or a ``has_mother`` / ``has_father`` row to switch to the other side, writes the
    new side to the same person and revokes the old row, in one transaction. A child side
    (``daughter``, ``son``) takes an active ``child_of`` row to the owner and writes the
    ``daughter_of`` or ``son_of`` marker for the same child beside it; the ``child_of`` row stays active. Any other row, a row that is not
    active, not the owner's or unknown, a child that already holds a marker, or a missing PIN is
    refused with a closed reason and writes nothing. The audit row holds the new predicate and
    the person's entity id, never a name.

    Args:
        actor: Who runs it (for the audit).
        owner_entity_id: The household owner (asserter and confirmer).
        relation_id: The id of the row to label (from ``list``).
        side: Which side the person is.
        now: UTC ISO 8601; shared by the write, the revoke and the audit row.
        owner_verified: Whether the owner's PIN was verified (always required: a third party).
        manage_transaction: ``False`` joins the caller's open transaction.

    Returns:
        The outcome; a closed refusal is reported and audited, never raised.
    """
    new_predicate = _SIDE_PREDICATES[side]
    is_parent = side in _PARENT_SIDES
    async with _transaction(manage_transaction):
        if not owner_verified:
            return await _refused(
                actor,
                _CHANGE,
                TargetKind.POOL_RELATION,
                new_predicate,
                None,
                _OWNER_NOT_VERIFIED,
                now,
            )
        active = await list_active_relations(owner_entity_id)
        relation = next((row for row in active if row.id == relation_id), None)
        refusal = _side_refusal(
            relation, active, owner_entity_id, new_predicate, is_parent=is_parent
        )
        status, reason = AdminOutcomeStatus.REFUSED, refusal
        if relation is not None and refusal is None:
            status, reason = await _attempt_side(
                owner_entity_id, relation, new_predicate, is_parent=is_parent, now=now
            )
        await _audit(
            actor,
            operation=_CHANGE,
            target_kind=TargetKind.POOL_RELATION,
            field_id=new_predicate,
            target_entity_id=_person_of(relation, is_parent=is_parent),
            status=status,
            reason=reason,
            now=now,
        )
        return AdminOutcome(_CHANGE, status, reason)


def _person_of(relation: EntityRelationV4 | None, *, is_parent: bool) -> int | None:
    """Return the person a row names: the parent it points to, or the child it starts from."""
    if relation is None:
        return None
    if relation.predicate not in (_PARENT_ROWS if is_parent else (_CHILD_ROW,)):
        return None
    return relation.target_entity_id if is_parent else relation.source_entity_id


def _side_refusal(
    relation: EntityRelationV4 | None,
    active: list[EntityRelationV4],
    owner_entity_id: int,
    new_predicate: str,
    *,
    is_parent: bool,
) -> str | None:
    """Return why the row cannot take the label, or ``None`` when it can.

    ``relation`` was picked from ``active`` (the owner's active relations), so an id that is
    unknown, revoked or another owner's is simply absent. A parent row may be unlabelled
    (``has_parent``) or already sided (``has_mother``, ``has_father``: switched to the other side).
    """
    if relation is None:
        return _NOT_AN_ACTIVE_RELATION
    if relation.predicate not in (_PARENT_ROWS if is_parent else (_CHILD_ROW,)):
        return _WRONG_RELATION_KIND
    if relation.predicate == new_predicate:
        return _ALREADY_LABELLED
    owned = relation.source_entity_id if is_parent else relation.target_entity_id
    if owned != owner_entity_id:
        return _NOT_AN_ACTIVE_RELATION
    # One person holds at most one side: a child one marker, a parent one of mother or father.
    markers, person = (
        (_PARENT_SIDE_ROWS, relation.target_entity_id)
        if is_parent
        else (_CHILD_MARKERS, relation.source_entity_id)
    )
    if any(
        row.id != relation.id
        and row.predicate in markers
        and row.source_entity_id == (owner_entity_id if is_parent else person)
        and row.target_entity_id == (person if is_parent else owner_entity_id)
        for row in active
    ):
        return _ALREADY_LABELLED
    return None


async def _attempt_side(
    owner_entity_id: int,
    relation: EntityRelationV4,
    new_predicate: str,
    *,
    is_parent: bool,
    now: str,
) -> tuple[AdminOutcomeStatus, str | None]:
    """Write the sided relation (and retire the unlabelled parent row), mapping a closed refusal.

    An unexpected failure propagates so the caller's transaction rolls the write back.
    """
    person = relation.target_entity_id if is_parent else relation.source_entity_id
    try:
        await write_relation(
            owner_entity_id=owner_entity_id,
            source_entity_id=owner_entity_id if is_parent else person,
            predicate=new_predicate,
            target_entity_id=person if is_parent else owner_entity_id,
            channel=_CHANNEL,
            confirmed_at=now,
            asserted_at=now,
            on_conflict=_POLICY,
            manage_transaction=False,
        )
    except WriteRefusedError as exc:
        return AdminOutcomeStatus.REFUSED, exc.reason
    except UnstorableValueError:
        return AdminOutcomeStatus.REFUSED, _UNSTORABLE
    except ValueError:
        return AdminOutcomeStatus.REFUSED, _INVALID
    if is_parent:
        await revoke_entity_relation(relation.id, revoked_at=now, manage_transaction=False)
    return AdminOutcomeStatus.APPLIED, None


async def _refused(
    actor: AdminActor,
    kind: AdminOperationKind,
    target_kind: TargetKind,
    field_id: str | None,
    target_entity_id: int | None,
    reason: str,
    now: str,
) -> AdminOutcome:
    """Audit and return a refusal without touching a writer."""
    await _audit(
        actor,
        operation=kind,
        target_kind=target_kind,
        field_id=field_id,
        target_entity_id=target_entity_id,
        status=AdminOutcomeStatus.REFUSED,
        reason=reason,
        now=now,
    )
    return AdminOutcome(kind, AdminOutcomeStatus.REFUSED, reason)
