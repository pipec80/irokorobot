"""Local repositories for household roles and safe authorization audit events."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from server.cognition.authorization import AuthorizationRequest
from server.cognition.identity import HouseholdRole
from server.cognition.models import AuthorizationAction, AuthorizationDecision, AuthorizationStatus
from server.db import get_conn

__all__ = [
    "HouseholdRoleAssignment",
    "assign_household_role",
    "bootstrap_initial_owner",
    "get_active_role",
    "record_authorization_decision",
    "revoke_active_role",
]


@dataclass(frozen=True)
class HouseholdRoleAssignment:
    """One durable role assignment without authorization semantics by itself."""

    id: int
    person_entity_id: int
    role: HouseholdRole
    grantor_entity_id: int | None
    reason: str
    granted_at: str
    revoked_at: str | None


async def _entity_type(entity_id: int) -> str | None:
    """Return an entity type without inferring a person from its name."""
    cursor = await get_conn().execute("SELECT type FROM entities WHERE id = ?", (entity_id,))
    row = await cursor.fetchone()
    await cursor.close()
    return str(row[0]) if row is not None else None


async def _active_owner_exists() -> bool:
    """Return whether the local household already has an active owner."""
    cursor = await get_conn().execute(
        "SELECT 1 FROM household_role_assignments WHERE role = 'owner' AND revoked_at IS NULL"
    )
    row = await cursor.fetchone()
    await cursor.close()
    return row is not None


async def _get_assignment(assignment_id: int) -> HouseholdRoleAssignment:
    """Load one assignment that was just committed by this repository."""
    cursor = await get_conn().execute(
        "SELECT person_entity_id, role, grantor_entity_id, reason, granted_at, revoked_at "
        "FROM household_role_assignments WHERE id = ?",
        (assignment_id,),
    )
    row = await cursor.fetchone()
    await cursor.close()
    if row is None:
        raise RuntimeError("new household role assignment was not found")
    return HouseholdRoleAssignment(
        id=assignment_id,
        person_entity_id=int(row[0]),
        role=HouseholdRole(str(row[1])),
        grantor_entity_id=int(row[2]) if row[2] is not None else None,
        reason=str(row[3]),
        granted_at=str(row[4]),
        revoked_at=str(row[5]) if row[5] is not None else None,
    )


async def get_active_role(person_entity_id: int) -> HouseholdRole:
    """Return one active persisted role or the safe unknown outcome."""
    cursor = await get_conn().execute(
        "SELECT role FROM household_role_assignments "
        "WHERE person_entity_id = ? AND revoked_at IS NULL",
        (person_entity_id,),
    )
    row = await cursor.fetchone()
    await cursor.close()
    return HouseholdRole(str(row[0])) if row is not None else HouseholdRole.UNKNOWN


async def _record_event(
    *,
    actor_entity_id: int | None,
    target_entity_id: int | None,
    action: AuthorizationAction,
    data_categories: frozenset[str],
    decision: AuthorizationStatus,
    policy_id: str,
    reason: str,
    correlation_id: str,
    evaluated_at: str,
    expires_at: str | None,
) -> None:
    """Append a safe audit event without a protected value or media payload."""
    cursor = await get_conn().execute(
        "INSERT INTO authorization_audit_events "
        "(actor_entity_id, target_entity_id, action, data_categories, decision, policy_id, reason, "
        "correlation_id, evaluated_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            actor_entity_id,
            target_entity_id,
            action.value,
            ",".join(sorted(data_categories)),
            decision.value,
            policy_id,
            reason,
            correlation_id,
            evaluated_at,
            expires_at,
        ),
    )
    await cursor.close()


async def record_authorization_decision(
    request: AuthorizationRequest,
    decision: AuthorizationDecision,
) -> None:
    """Persist one evaluated policy outcome as a safe append-only audit event."""
    await _record_event(
        actor_entity_id=request.actor.person_id,
        target_entity_id=request.target_person_id,
        action=decision.action,
        data_categories=decision.data_categories,
        decision=decision.decision,
        policy_id=decision.policy_id,
        reason=decision.reason,
        correlation_id=str(decision.correlation_id),
        evaluated_at=decision.evaluated_at.isoformat(),
        expires_at=decision.expires_at.isoformat() if decision.expires_at is not None else None,
    )
    await get_conn().commit()


async def bootstrap_initial_owner(
    *,
    person_entity_id: int,
    confirmed_person_entity_id: int,
) -> HouseholdRoleAssignment:
    """Create the sole initial owner from an explicit local entity-ID confirmation.

    Args:
        person_entity_id: Existing person entity selected by the local operator.
        confirmed_person_entity_id: The same integer ID repeated deliberately.

    Returns:
        The durable owner assignment.

    Raises:
        ValueError: If confirmation, entity type, or singleton owner checks fail.
    """
    if person_entity_id != confirmed_person_entity_id:
        raise ValueError("initial owner requires matching confirmation entity ID")
    if await _entity_type(person_entity_id) != "person":
        raise ValueError("initial owner entity must be a person")
    if await _active_owner_exists():
        raise ValueError("an active owner already exists")

    conn = get_conn()
    await conn.execute("BEGIN IMMEDIATE")
    try:
        cursor = await conn.execute(
            "INSERT INTO household_role_assignments "
            "(person_entity_id, role, grantor_entity_id, reason) VALUES (?, 'owner', NULL, ?)",
            (person_entity_id, "Explicit local initial-owner bootstrap"),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("INSERT into household_role_assignments returned no lastrowid")
        assignment_id = int(cursor.lastrowid)
        await cursor.close()
        await _record_event(
            actor_entity_id=None,
            target_entity_id=person_entity_id,
            action=AuthorizationAction.MANAGE_HOUSEHOLD_ROLE,
            data_categories=frozenset({"household", "normal"}),
            decision=AuthorizationStatus.ALLOWED,
            policy_id="p0.5.local-owner-bootstrap",
            reason="Initial owner established by explicit local entity-ID confirmation.",
            correlation_id=str(uuid4()),
            evaluated_at=datetime.now(UTC).isoformat(),
            expires_at=None,
        )
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise

    return await _get_assignment(assignment_id)


async def assign_household_role(
    *,
    person_entity_id: int,
    role: HouseholdRole,
    grantor_entity_id: int,
) -> HouseholdRoleAssignment:
    """Assign a non-owner household role through an internal local service.

    Args:
        person_entity_id: Existing person entity receiving the role.
        role: Adult, child, or guest role to assign.
        grantor_entity_id: Existing active owner approving the assignment.

    Returns:
        The durable role assignment.

    Raises:
        ValueError: If an entity is not a person, the grantor is not the active
            owner, or the target already has an active role.
    """
    if role in {HouseholdRole.UNKNOWN, HouseholdRole.OWNER}:
        raise ValueError("only non-owner household roles may be assigned here")
    if await _entity_type(person_entity_id) != "person":
        raise ValueError("household role entity must be a person")
    if await _entity_type(grantor_entity_id) != "person":
        raise ValueError("role grantor entity must be a person")
    if await get_active_role(grantor_entity_id) is not HouseholdRole.OWNER:
        raise ValueError("role assignment requires an active owner grantor")
    if await get_active_role(person_entity_id) is not HouseholdRole.UNKNOWN:
        raise ValueError("person already has an active household role")

    conn = get_conn()
    await conn.execute("BEGIN IMMEDIATE")
    try:
        cursor = await conn.execute(
            "INSERT INTO household_role_assignments "
            "(person_entity_id, role, grantor_entity_id, reason) VALUES (?, ?, ?, ?)",
            (
                person_entity_id,
                role.value,
                grantor_entity_id,
                "Internal local household role assignment",
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("INSERT into household_role_assignments returned no lastrowid")
        assignment_id = int(cursor.lastrowid)
        await cursor.close()
        await _record_event(
            actor_entity_id=grantor_entity_id,
            target_entity_id=person_entity_id,
            action=AuthorizationAction.MANAGE_HOUSEHOLD_ROLE,
            data_categories=frozenset({"household", "normal"}),
            decision=AuthorizationStatus.ALLOWED,
            policy_id="p0.5.internal-role-assignment",
            reason="Active owner assigned a local household role.",
            correlation_id=str(uuid4()),
            evaluated_at=datetime.now(UTC).isoformat(),
            expires_at=None,
        )
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise

    return await _get_assignment(assignment_id)


async def revoke_active_role(*, person_entity_id: int) -> None:
    """Logically revoke one active role while retaining its assignment history."""
    conn = get_conn()
    cursor = await conn.execute(
        "UPDATE household_role_assignments SET revoked_at = datetime('now') "
        "WHERE person_entity_id = ? AND revoked_at IS NULL",
        (person_entity_id,),
    )
    updated = cursor.rowcount
    await cursor.close()
    if updated != 1:
        await conn.rollback()
        raise ValueError("no active household role exists for this person")
    await _record_event(
        actor_entity_id=None,
        target_entity_id=person_entity_id,
        action=AuthorizationAction.MANAGE_HOUSEHOLD_ROLE,
        data_categories=frozenset({"household", "normal"}),
        decision=AuthorizationStatus.ALLOWED,
        policy_id="p0.5.local-role-revocation",
        reason="Local role assignment was revoked.",
        correlation_id=str(uuid4()),
        evaluated_at=datetime.now(UTC).isoformat(),
        expires_at=None,
    )
    await conn.commit()
