"""The admin audit: one row per mutating admin operation (Plan 0073, ADR 0025 decision 4).

Every `add`, `change` or `revoke` run through ``iroko-admin`` writes one row here: the actor's
label and role, the channel (always ``admin_local``), the operation, the target kind, the field or
section id, the affected entity, the outcome and the time. It holds **no household value**: no
value, name or phone ever reaches a row, a log or a ``repr``. The table is append-only (forgetting
is CM-6). This module is the only place with SQL on ``admin_audit`` (an architecture guard says so).
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager, nullcontext
from dataclasses import dataclass, field
from enum import StrEnum
import logging
import re

from server import db
from server.db import get_conn

__all__ = [
    "AdminActorRole",
    "AdminAuditEntry",
    "AdminOperationKind",
    "AdminOutcomeStatus",
    "TargetKind",
    "list_admin_operations",
    "record_admin_operation",
]

logger = logging.getLogger(__name__)

_EVENT = "memory.admin_audit"
_CHANNEL = "admin_local"
_MAX_LABEL = 80
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_COLUMNS = (
    "id, recorded_at, actor_label, actor_role, channel, operation, target_kind, field_id, "
    "target_entity_id, outcome, reason"
)


class AdminActorRole(StrEnum):
    """Who ran the operation; in Phase 0 the operator is the owner/builder (ADR 0025 decision 3)."""

    OWNER = "owner"
    BUILDER = "builder"


class AdminOperationKind(StrEnum):
    """The mutating operations the admin audits."""

    ADD = "add"
    CHANGE = "change"
    REVOKE = "revoke"


class TargetKind(StrEnum):
    """What an operation acted on."""

    POOL_LITERAL = "pool_literal"
    POOL_RELATION = "pool_relation"
    CARE_CONTACT = "care_contact"


class AdminOutcomeStatus(StrEnum):
    """Whether the operation was applied or refused."""

    APPLIED = "applied"
    REFUSED = "refused"


@dataclass(frozen=True)
class AdminAuditEntry:
    """One ``admin_audit`` row; its ``repr`` omits the actor's label (its only free text)."""

    id: int
    recorded_at: str
    actor_label: str = field(repr=False)
    actor_role: AdminActorRole
    channel: str
    operation: AdminOperationKind
    target_kind: TargetKind
    field_id: str | None
    target_entity_id: int | None
    outcome: AdminOutcomeStatus
    reason: str | None


def _row(values: tuple[object, ...]) -> AdminAuditEntry:
    """Build an entry from a row selected with ``_COLUMNS``."""
    (
        row_id,
        recorded_at,
        actor_label,
        actor_role,
        channel,
        operation,
        target_kind,
        field_id,
        target_entity_id,
        outcome,
        reason,
    ) = values
    return AdminAuditEntry(
        id=int(str(row_id)),
        recorded_at=str(recorded_at),
        actor_label=str(actor_label),
        actor_role=AdminActorRole(str(actor_role)),
        channel=str(channel),
        operation=AdminOperationKind(str(operation)),
        target_kind=TargetKind(str(target_kind)),
        field_id=None if field_id is None else str(field_id),
        target_entity_id=None if target_entity_id is None else int(str(target_entity_id)),
        outcome=AdminOutcomeStatus(str(outcome)),
        reason=None if reason is None else str(reason),
    )


def _transaction(manage_transaction: bool) -> AbstractAsyncContextManager[object]:
    """Own a transaction, or join the one the caller owns (``db.transaction`` is not reentrant)."""
    return db.transaction() if manage_transaction else nullcontext()


def _validated_label(actor_label: str) -> str:
    """Return the label, or raise a ``ValueError`` that holds none of it."""
    if not 1 <= len(actor_label) <= _MAX_LABEL or _CONTROL_CHARACTERS.search(actor_label):
        raise ValueError("the actor label must be 1 to 80 printable characters")
    return actor_label


async def record_admin_operation(
    *,
    actor_label: str,
    actor_role: AdminActorRole,
    operation: AdminOperationKind,
    target_kind: TargetKind,
    field_id: str | None,
    target_entity_id: int | None,
    outcome: AdminOutcomeStatus,
    reason: str | None,
    recorded_at: str,
    manage_transaction: bool = True,
) -> AdminAuditEntry:
    """Append one audit row for a mutating admin operation; it holds no household value.

    Args:
        actor_label: The operator's free-text label (never logged or shown in a ``repr``).
        actor_role: ``owner`` or ``builder``.
        operation: ``add``, ``change`` or ``revoke``.
        target_kind: What the operation acted on.
        field_id: A catalogue id (``medication``) or a contact role; never a value.
        target_entity_id: The affected entity, or ``None``.
        outcome: ``applied`` or ``refused``.
        reason: A closed word for a refusal, or ``None``.
        recorded_at: When it happened, as UTC ISO 8601.
        manage_transaction: ``False`` joins the caller's open transaction.

    Returns:
        The stored row.

    Raises:
        ValueError: For a label outside 1 to 80 printable characters.
    """
    label = _validated_label(actor_label)
    role = AdminActorRole(actor_role)
    op = AdminOperationKind(operation)
    kind = TargetKind(target_kind)
    status = AdminOutcomeStatus(outcome)
    async with _transaction(manage_transaction):
        cursor = await get_conn().execute(
            "INSERT INTO admin_audit (recorded_at, actor_label, actor_role, channel, operation, "
            "target_kind, field_id, target_entity_id, outcome, reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                recorded_at,
                label,
                role.value,
                _CHANNEL,
                op.value,
                kind.value,
                field_id,
                target_entity_id,
                status.value,
                reason,
            ),
        )
        row_id = cursor.lastrowid
        await cursor.close()
        if row_id is None:
            raise RuntimeError("INSERT into admin_audit returned no row id")
        (stored,) = await _fetch(f"SELECT {_COLUMNS} FROM admin_audit WHERE id = ?", row_id)  # noqa: S608
    _announce(stored, committed=manage_transaction)
    return stored


async def list_admin_operations(limit: int = 50) -> tuple[AdminAuditEntry, ...]:
    """Return the most recent admin operations first (no value, for the ``audit`` sub-command).

    Args:
        limit: How many rows to return, newest first.

    Returns:
        The audit rows, most recent first.
    """
    return await _fetch(
        f"SELECT {_COLUMNS} FROM admin_audit ORDER BY recorded_at DESC, id DESC LIMIT ?",  # noqa: S608
        limit,
    )


async def _fetch(sql: str, *params: object) -> tuple[AdminAuditEntry, ...]:
    cursor = await get_conn().execute(sql, params)
    rows = await cursor.fetchall()
    await cursor.close()
    return tuple(_row(tuple(row)) for row in rows)


def _announce(entry: AdminAuditEntry, *, committed: bool) -> None:
    """Log one audit row by id and closed fields, never the label, the field id or a value."""
    logger.log(
        logging.INFO if committed else logging.DEBUG,
        "Admin operation %s",
        "recorded" if committed else "staged",
        extra={
            "event": _EVENT,
            "row_id": entry.id,
            "operation": entry.operation.value,
            "target_kind": entry.target_kind.value,
            "outcome": entry.outcome.value,
        },
    )
