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

from server import db
from server.exceptions import UnstorableValueError, WriteRefusedError
from server.memory.admin_audit import (
    AdminActorRole,
    AdminOperationKind,
    AdminOutcomeStatus,
    TargetKind,
    record_admin_operation,
)
from server.memory.canonical_writer import write_literal
from server.memory.care_contacts import ContactRole, write_contact
from server.memory.predicate_registry import resolve_predicate
from server.memory.write_types import ConflictPolicy, WriteChannel

__all__ = [
    "AdminActor",
    "AdminOutcome",
    "ContactTerms",
    "apply_contact_edit",
    "apply_literal_edit",
    "requires_owner_verification",
]

_CHANNEL: WriteChannel = WriteChannel.ADMIN_LOCAL
_POLICY: ConflictPolicy = ConflictPolicy.SUPERSEDE
# The sensitivities ADR 0025 decision 4 names for the owner's own data (``private`` is excluded).
_SENSITIVE = frozenset({"medical", "location", "security"})
_OWNER_NOT_VERIFIED = "owner_not_verified"
_UNSTORABLE = "unstorable_value"
_INVALID = "invalid_value"


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
