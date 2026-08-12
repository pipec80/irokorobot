"""Pure, fail-closed authorization contracts and household policy."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from server.cognition.identity import ActivePersonContext, ActivePersonStatus, HouseholdRole
from server.cognition.models import AuthorizationAction, AuthorizationDecision, AuthorizationStatus

_StrictInteger = Annotated[int, Field(strict=True)]
_StrictUUID = Annotated[UUID, Field(strict=True)]

__all__ = [
    "AuthorizationRequest",
    "ConsentStatus",
    "DataSensitivity",
    "DataVisibility",
    "evaluate_authorization",
]


class DataVisibility(StrEnum):
    """Closed visibility categories used before household retrieval."""

    PUBLIC = "public"
    HOUSEHOLD = "household"
    ADULTS = "adults"
    PERSONAL = "personal"
    PRIVATE = "private"
    TEMPORARY = "temporary"


class DataSensitivity(StrEnum):
    """Closed sensitivity categories used before household retrieval."""

    NORMAL = "normal"
    PRIVATE = "private"
    BIOMETRIC = "biometric"
    MEDICAL = "medical"
    LOCATION = "location"
    CHILD_DATA = "child_data"
    SECURITY = "security"


class ConsentStatus(StrEnum):
    """Consent state carried by a typed authorization request."""

    NOT_REQUIRED = "not_required"
    GRANTED = "granted"
    MISSING = "missing"
    REVOKED = "revoked"


def _require_aware_utc(value: datetime) -> datetime:
    """Reject naive timestamps and normalize aware timestamps to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


class AuthorizationRequest(BaseModel):
    """Minimum immutable inputs for one local policy decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    actor: ActivePersonContext
    action: AuthorizationAction
    target_person_id: _StrictInteger | None = None
    visibility: frozenset[DataVisibility] = Field(min_length=1)
    sensitivity: frozenset[DataSensitivity] = Field(min_length=1)
    consent: ConsentStatus
    correlation_id: _StrictUUID
    requested_at: datetime

    _validate_requested_at = field_validator("requested_at")(_require_aware_utc)


_SENSITIVE_CATEGORIES = frozenset(
    {
        DataSensitivity.BIOMETRIC,
        DataSensitivity.MEDICAL,
        DataSensitivity.LOCATION,
        DataSensitivity.CHILD_DATA,
        DataSensitivity.SECURITY,
    }
)


def _categories(request: AuthorizationRequest) -> frozenset[str]:
    """Return safe category labels without accessing a protected value."""
    return frozenset(
        {category.value for category in request.visibility}
        | {category.value for category in request.sensitivity}
    )


def _decision(
    request: AuthorizationRequest,
    status: AuthorizationStatus,
    policy_id: str,
    reason: str,
) -> AuthorizationDecision:
    """Build one request-scoped immutable decision."""
    return AuthorizationDecision(
        decision=status,
        action=request.action,
        data_categories=_categories(request),
        policy_id=policy_id,
        reason=reason,
        evaluated_at=request.requested_at,
        correlation_id=request.correlation_id,
    )


def _is_resolved_actor(request: AuthorizationRequest) -> bool:
    """Return whether policy may consider a resolved, role-bearing actor."""
    return (
        request.actor.status is ActivePersonStatus.IDENTIFIED
        and request.actor.person_id is not None
        and request.actor.role is not HouseholdRole.UNKNOWN
    )


def _has_sensitive_data(request: AuthorizationRequest) -> bool:
    """Return whether a request includes a high-sensitivity category."""
    return bool(request.sensitivity & _SENSITIVE_CATEGORIES)


def _is_own_normal_personal_data(request: AuthorizationRequest) -> bool:
    """Return whether an actor requests only their own normal personal data."""
    return (
        request.target_person_id == request.actor.person_id
        and request.visibility == frozenset({DataVisibility.PERSONAL})
        and request.sensitivity == frozenset({DataSensitivity.NORMAL})
    )


def _evaluate_sensitive_read(request: AuthorizationRequest) -> AuthorizationDecision:
    """Evaluate an otherwise protected read containing sensitive data."""
    role = request.actor.role
    if request.consent is not ConsentStatus.GRANTED:
        return _decision(
            request,
            AuthorizationStatus.DENIED,
            "p0.5.consent-required",
            "Required consent is absent or revoked.",
        )
    if role is HouseholdRole.OWNER:
        return _decision(
            request,
            AuthorizationStatus.ALLOWED,
            "p0.5.owner-sensitive-consent",
            "Owner policy permits this consented sensitive request.",
        )
    return _decision(
        request,
        AuthorizationStatus.REQUIRES_CONFIRMATION,
        "p0.5.sensitive-confirmation",
        "Sensitive data requires an explicit scoped confirmation.",
    )


def _evaluate_public_read(request: AuthorizationRequest) -> AuthorizationDecision:
    """Evaluate a normal public household read without protected data values."""
    role = request.actor.role
    if role in {HouseholdRole.OWNER, HouseholdRole.ADULT}:
        return _decision(
            request,
            AuthorizationStatus.ALLOWED,
            "p0.5.household-public",
            "Policy permits public household data for this role.",
        )
    if role is HouseholdRole.CHILD:
        return _decision(
            request,
            AuthorizationStatus.REQUIRES_CONFIRMATION,
            "p0.5.child-public-confirmation",
            "Child access requires a scoped confirmation.",
        )
    return _decision(
        request,
        AuthorizationStatus.DENIED,
        "p0.5.protected-default-deny",
        "No policy grants this protected household request.",
    )


def _evaluate_normal_household_read(request: AuthorizationRequest) -> AuthorizationDecision:
    """Evaluate normal household reads outside the public and own-data cases."""
    role = request.actor.role
    if role is HouseholdRole.OWNER and request.visibility <= {
        DataVisibility.HOUSEHOLD,
        DataVisibility.ADULTS,
    }:
        return _decision(
            request,
            AuthorizationStatus.ALLOWED,
            "p0.5.owner-household",
            "Owner policy permits normal household data.",
        )
    if role is HouseholdRole.ADULT and request.visibility == frozenset({DataVisibility.HOUSEHOLD}):
        return _decision(
            request,
            AuthorizationStatus.ALLOWED,
            "p0.5.adult-household",
            "Adult policy permits normal household data.",
        )

    return _decision(
        request,
        AuthorizationStatus.DENIED,
        "p0.5.protected-default-deny",
        "No policy grants this protected household request.",
    )


def _evaluate_read(request: AuthorizationRequest) -> AuthorizationDecision:
    """Evaluate protected data reads and deterministic family-tool prerequisites."""
    if _has_sensitive_data(request):
        return _evaluate_sensitive_read(request)
    if _is_own_normal_personal_data(request):
        return _decision(
            request,
            AuthorizationStatus.ALLOWED,
            "p0.5.own-normal-personal",
            "Policy permits the actor's own normal personal data.",
        )
    if request.visibility == frozenset({DataVisibility.PUBLIC}):
        return _evaluate_public_read(request)
    return _evaluate_normal_household_read(request)


def _evaluate_memory_proposal(request: AuthorizationRequest) -> AuthorizationDecision:
    """Evaluate a proposed durable memory update without persisting it."""
    if request.actor.role is HouseholdRole.OWNER:
        return _decision(
            request,
            AuthorizationStatus.ALLOWED,
            "p0.5.owner-memory-proposal",
            "Owner policy permits a memory proposal.",
        )
    if request.actor.role in {HouseholdRole.ADULT, HouseholdRole.CHILD}:
        return _decision(
            request,
            AuthorizationStatus.REQUIRES_CONFIRMATION,
            "p0.5.memory-proposal-confirmation",
            "Memory proposals require a scoped confirmation.",
        )
    return _decision(
        request,
        AuthorizationStatus.DENIED,
        "p0.5.default-deny",
        "No policy grants this request.",
    )


def _evaluate_owner_administration(request: AuthorizationRequest) -> AuthorizationDecision:
    """Evaluate an owner-only administrative operation."""
    if request.actor.role is HouseholdRole.OWNER:
        return _decision(
            request,
            AuthorizationStatus.ALLOWED,
            "p0.5.owner-administration",
            "Owner policy permits this administrative request.",
        )
    return _decision(
        request,
        AuthorizationStatus.DENIED,
        "p0.5.default-deny",
        "No policy grants this request.",
    )


def _evaluate_sensitive_owner_action(request: AuthorizationRequest) -> AuthorizationDecision:
    """Evaluate a sensitive owner action requiring explicit subject consent."""
    if request.actor.role is HouseholdRole.OWNER and request.consent is ConsentStatus.GRANTED:
        return _decision(
            request,
            AuthorizationStatus.ALLOWED,
            "p0.5.owner-consented-sensitive-action",
            "Owner policy permits this consented sensitive action.",
        )
    if request.actor.role is HouseholdRole.OWNER:
        return _decision(
            request,
            AuthorizationStatus.DENIED,
            "p0.5.consent-required",
            "Required consent is absent or revoked.",
        )
    return _decision(
        request,
        AuthorizationStatus.DENIED,
        "p0.5.default-deny",
        "No policy grants this request.",
    )


def _evaluate_physical_action_proposal(request: AuthorizationRequest) -> AuthorizationDecision:
    """Evaluate only whether a later body safety layer may receive a proposal."""
    if request.actor.role in {HouseholdRole.OWNER, HouseholdRole.ADULT}:
        return _decision(
            request,
            AuthorizationStatus.ALLOWED,
            "p0.5.physical-action-proposal",
            "Policy permits only a later safety-gated action proposal.",
        )
    return _decision(
        request,
        AuthorizationStatus.DENIED,
        "p0.5.default-deny",
        "No policy grants this request.",
    )


def _evaluate_resolved_request(request: AuthorizationRequest) -> AuthorizationDecision:
    """Evaluate a request after the caller has established a trusted actor."""
    if request.action in {
        AuthorizationAction.READ_HOUSEHOLD_DATA,
        AuthorizationAction.EXECUTE_HOUSEHOLD_TOOL,
    }:
        return _evaluate_read(request)
    if request.action is AuthorizationAction.PROPOSE_MEMORY:
        return _evaluate_memory_proposal(request)
    if request.action in {
        AuthorizationAction.COMMIT_MEMORY,
        AuthorizationAction.MANAGE_HOUSEHOLD_ROLE,
        AuthorizationAction.EXPORT_HOUSEHOLD_DATA,
        AuthorizationAction.DELETE_HOUSEHOLD_DATA,
    }:
        return _evaluate_owner_administration(request)
    if request.action in {
        AuthorizationAction.ENROLL_BIOMETRIC,
        AuthorizationAction.CONSIDER_CLOUD_ESCALATION,
    }:
        return _evaluate_sensitive_owner_action(request)
    if request.action is AuthorizationAction.PROPOSE_PHYSICAL_ACTION:
        return _evaluate_physical_action_proposal(request)
    return _decision(
        request,
        AuthorizationStatus.DENIED,
        "p0.5.default-deny",
        "No policy grants this request.",
    )


def evaluate_authorization(request: AuthorizationRequest) -> AuthorizationDecision:
    """Evaluate one request with a deterministic, local, fail-closed policy."""
    if request.action is AuthorizationAction.GENERAL_CONVERSATION:
        if request.visibility != frozenset(
            {DataVisibility.PUBLIC}
        ) or request.sensitivity != frozenset({DataSensitivity.NORMAL}):
            return _decision(
                request,
                AuthorizationStatus.DENIED,
                "p0.5.general-conversation-unclassified",
                "General conversation cannot carry protected data categories.",
            )
        return _decision(
            request,
            AuthorizationStatus.ALLOWED,
            "p0.5.general-conversation",
            "Policy permits general conversation without protected context.",
        )
    if not _is_resolved_actor(request):
        return _decision(
            request,
            AuthorizationStatus.DENIED,
            "p0.5.identity-unresolved",
            "A resolved household role is required for this request.",
        )
    return _evaluate_resolved_request(request)
