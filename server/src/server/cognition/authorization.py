"""Pure, fail-closed authorization contracts and household policy."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    HouseholdRole,
    IdentityAssurance,
    IdentityEvidence,
    IdentityEvidenceSource,
)
from server.cognition.models import (
    AuthorizationAction,
    AuthorizationDecision,
    AuthorizationStatus,
    require_aware_utc,
)

_StrictInteger = Annotated[int, Field(strict=True)]
_StrictUUID = Annotated[UUID, Field(strict=True)]

__all__ = [
    "ASSURANCE_RANK",
    "HIGH_ASSURANCE_CATEGORIES",
    "PERSONAL_MEMORY_CAPABILITIES",
    "PERSONAL_MEMORY_STRONG_CATEGORIES",
    "AuthorizationRequest",
    "ConsentStatus",
    "DataSensitivity",
    "DataVisibility",
    "HouseholdFactShape",
    "HouseholdSubject",
    "PersonalMemoryCapability",
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


class HouseholdSubject(StrEnum):
    """Closed relation between a household fact's subject and the owner (ADR 0022 decision 3)."""

    OWNER = "owner"
    CHILD = "child"
    PARTNER = "partner"
    PET = "pet"


class HouseholdFactShape(StrEnum):
    """Whether a household fact is a literal about its subject or a relation to another entity.

    The household pair treats the two differently: the partner may be the subject of a relation
    (name and relationship) but never of a literal (ADR 0022 decision 4).
    """

    LITERAL = "literal"
    RELATION = "relation"


class AuthorizationRequest(BaseModel):
    """Minimum immutable inputs for one local policy decision.

    `subject_relation` and `fact_shape` classify a household write for the household pair of
    actions. Both are the caller's, made from the intent before any read (ADR 0019 §6.2), never
    derived from stored rows; the policy is pure. Every other action ignores them, and `None`
    means "not classified", which the household pair denies.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    actor: ActivePersonContext
    action: AuthorizationAction
    target_person_id: _StrictInteger | None = None
    subject_relation: HouseholdSubject | None = None
    fact_shape: HouseholdFactShape | None = None
    visibility: frozenset[DataVisibility] = Field(min_length=1)
    sensitivity: frozenset[DataSensitivity] = Field(min_length=1)
    consent: ConsentStatus
    correlation_id: _StrictUUID
    requested_at: datetime

    _validate_requested_at = field_validator("requested_at")(require_aware_utc)


_SENSITIVE_CATEGORIES = frozenset(
    {
        DataSensitivity.BIOMETRIC,
        DataSensitivity.MEDICAL,
        DataSensitivity.LOCATION,
        DataSensitivity.CHILD_DATA,
        DataSensitivity.SECURITY,
    }
)
# Categories whose reads need face-and-voice agreement or an owner unlock (ADR 0016
# §3). Only SECURITY today; others join when a capability declares them.
HIGH_ASSURANCE_CATEGORIES = frozenset({DataSensitivity.SECURITY})
# ADR 0019 §3: data of these categories raises the minimum assurance of EVERY personal-memory
# capability to `strong`, so a photograph of the owner cannot reach it. `security` is held by
# the generic gate above (HIGH_ASSURANCE_CATEGORIES, which must not change: it also governs the
# nine older actions); `child_data` stays at the capability minimum because ADR 0016 already
# accepts the owner's face for the child read.
PERSONAL_MEMORY_STRONG_CATEGORIES = frozenset(
    {DataSensitivity.BIOMETRIC, DataSensitivity.MEDICAL, DataSensitivity.LOCATION}
)

# `IdentityAssurance` is a str enum, so `<` on its members is alphabetical (`basic` < `none`).
# Compare assurance only through this rank (ADR 0019 §3).
ASSURANCE_RANK: Mapping[IdentityAssurance, int] = MappingProxyType(
    {
        IdentityAssurance.NONE: 0,
        IdentityAssurance.BASIC: 1,
        IdentityAssurance.STRONG: 2,
    }
)


@dataclass(frozen=True)
class PersonalMemoryCapability:
    """What one personal-memory action demands of the actor and the data (ADR 0019 §3).

    Attributes:
        min_assurance: Lowest identity assurance that may exercise the capability.
        consent_applies: Whether sensitive categories also need granted consent.
        requires_unlock: Whether an owner PIN grant spent for this operation is mandatory.
        unlock_scope: The one owner-unlock scope a PIN grant may carry, or None when a
            PIN grant never counts for this capability.
        visibilities: The only data visibilities the capability may touch.
    """

    min_assurance: IdentityAssurance
    consent_applies: bool
    requires_unlock: bool
    unlock_scope: str | None
    visibilities: frozenset[DataVisibility]


_PERSONAL_ONLY = frozenset({DataVisibility.PERSONAL})

# Scopes are plain strings: importing `OwnerUnlockScope` would create an import cycle with
# `owner_authentication`; a drift test pins them to its members.
PERSONAL_MEMORY_CAPABILITIES: Mapping[AuthorizationAction, PersonalMemoryCapability] = (
    MappingProxyType(
        {
            AuthorizationAction.READ_PERSONAL_CONVERSATION_MEMORY: PersonalMemoryCapability(
                min_assurance=IdentityAssurance.BASIC,
                consent_applies=True,
                requires_unlock=False,
                unlock_scope="personal_memory_read",
                visibilities=_PERSONAL_ONLY,
            ),
            AuthorizationAction.PROPOSE_PERSONAL_MEMORY: PersonalMemoryCapability(
                min_assurance=IdentityAssurance.BASIC,
                consent_applies=True,
                requires_unlock=False,
                unlock_scope=None,
                visibilities=_PERSONAL_ONLY,
            ),
            AuthorizationAction.CONFIRM_PERSONAL_MEMORY: PersonalMemoryCapability(
                min_assurance=IdentityAssurance.STRONG,
                consent_applies=True,
                requires_unlock=False,
                unlock_scope=None,
                visibilities=_PERSONAL_ONLY,
            ),
            AuthorizationAction.CORRECT_PERSONAL_MEMORY: PersonalMemoryCapability(
                min_assurance=IdentityAssurance.BASIC,
                consent_applies=True,
                requires_unlock=False,
                unlock_scope=None,
                visibilities=_PERSONAL_ONLY,
            ),
            AuthorizationAction.FORGET_PERSONAL_MEMORY: PersonalMemoryCapability(
                min_assurance=IdentityAssurance.STRONG,
                consent_applies=False,
                requires_unlock=True,
                unlock_scope="personal_memory_forget",
                visibilities=frozenset(
                    {DataVisibility.PERSONAL, DataVisibility.PRIVATE, DataVisibility.TEMPORARY}
                ),
            ),
        }
    )
)


def _lacks_required_assurance(request: AuthorizationRequest) -> bool:
    """Return whether a reserved request is made with less than `strong` assurance."""
    return (
        bool(request.sensitivity & HIGH_ASSURANCE_CATEGORIES)
        and request.actor.assurance is not IdentityAssurance.STRONG
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


def _personal_memory_decision(
    request: AuthorizationRequest, status: AuthorizationStatus, outcome: str, reason: str
) -> AuthorizationDecision:
    """Build a personal-memory decision whose reason never carries a protected value."""
    return _decision(request, status, f"cm1.personal-memory.{outcome}", reason)


def _is_own_data(request: AuthorizationRequest, capability: PersonalMemoryCapability) -> bool:
    """Return whether the data is the actor's own and of a visibility the capability reaches."""
    return (
        # Defence in depth: a missing target never matches, even if an actor id were absent.
        request.target_person_id is not None
        and request.target_person_id == request.actor.person_id
        and bool(request.visibility)
        and request.visibility <= capability.visibilities
    )


def _lacks_assurance(request: AuthorizationRequest, capability: PersonalMemoryCapability) -> bool:
    """Return whether the actor's assurance ranks below what this request needs.

    The need is `strong` when the data includes a category in
    `PERSONAL_MEMORY_STRONG_CATEGORIES`, else the capability's own minimum.
    """
    required = (
        IdentityAssurance.STRONG
        if request.sensitivity & PERSONAL_MEMORY_STRONG_CATEGORIES
        else capability.min_assurance
    )
    return ASSURANCE_RANK[request.actor.assurance] < ASSURANCE_RANK[required]


def _is_invalid_grant(
    item: IdentityEvidence, request: AuthorizationRequest, capability: PersonalMemoryCapability
) -> bool:
    """Return whether one `local_unlock` item cannot authorize this request.

    It must carry the capability's own scope, have been spent by this request, name the
    acting person and still be fresh at request time (ADR 0019 §4). An item with no
    expiry is never trusted: the registry always sets one.
    """
    return (
        capability.unlock_scope is None
        or item.grant_scope != capability.unlock_scope
        or not item.grant_spent
        or item.candidate_person_id != request.actor.person_id
        or item.expires_at is None
        or item.expires_at <= request.requested_at
    )


def _has_invalid_grant(request: AuthorizationRequest, capability: PersonalMemoryCapability) -> bool:
    """Return whether an owner PIN grant is missing where required or does not count.

    Every `local_unlock` item must be valid for this capability; a capability with no scope
    accepts no PIN grant at all.
    """
    grants = [
        item
        for item in request.actor.evidence
        if item.source is IdentityEvidenceSource.LOCAL_UNLOCK
    ]
    if capability.requires_unlock and not grants:
        return True
    return any(_is_invalid_grant(item, request, capability) for item in grants)


def _lacks_consent(request: AuthorizationRequest, capability: PersonalMemoryCapability) -> bool:
    """Return whether sensitive data is requested without granted consent."""
    return (
        capability.consent_applies
        and _has_sensitive_data(request)
        and request.consent is not ConsentStatus.GRANTED
    )


def _evaluate_personal_memory(
    request: AuthorizationRequest, capability: PersonalMemoryCapability
) -> AuthorizationDecision:
    """Evaluate one personal-memory capability in the fixed order of ADR 0019 §5.

    The generic gates (identity resolved; `security` data needs `strong`) have already run.
    The result is never `REQUIRES_CONFIRMATION`.
    """
    if request.actor.role is not HouseholdRole.OWNER:
        return _personal_memory_decision(
            request,
            AuthorizationStatus.DENIED,
            "owner-only",
            "Personal memory is reserved for the household owner.",
        )
    if not _is_own_data(request, capability):
        return _personal_memory_decision(
            request,
            AuthorizationStatus.DENIED,
            "own-data-only",
            "Personal memory covers only the actor's own data.",
        )
    if _lacks_assurance(request, capability):
        return _personal_memory_decision(
            request,
            AuthorizationStatus.DENIED,
            "assurance-required",
            "This personal memory request needs stronger identity assurance.",
        )
    if _has_invalid_grant(request, capability):
        return _personal_memory_decision(
            request,
            AuthorizationStatus.DENIED,
            "grant-scope",
            "An owner unlock spent for exactly this operation is required.",
        )
    if _lacks_consent(request, capability):
        return _personal_memory_decision(
            request,
            AuthorizationStatus.DENIED,
            "consent-required",
            "Required consent is absent or revoked.",
        )
    return _personal_memory_decision(
        request,
        AuthorizationStatus.ALLOWED,
        "allowed",
        "Policy permits this request on the owner's own personal memory.",
    )


# ADR 0022 decisions 3 and 4: the household pair is evaluated apart from the personal table above.
# It is not about the actor's own data, and its consent rule depends on the category, so it does
# not fit `PersonalMemoryCapability`.
_HOUSEHOLD_MEMORY_ACTIONS = frozenset(
    {AuthorizationAction.PROPOSE_HOUSEHOLD_MEMORY, AuthorizationAction.CONFIRM_HOUSEHOLD_MEMORY}
)
_HOUSEHOLD_ONLY = frozenset({DataVisibility.HOUSEHOLD})
# Who the owner may write about, by the shape of the fact. A literal about the partner (birth
# date, tastes, health) waits for the `family` profile, where that adult enrolls and decides;
# a relation (name and relationship) is allowed. The owner's own facts are `personal`.
_HOUSEHOLD_SUBJECTS: Mapping[HouseholdFactShape, frozenset[HouseholdSubject]] = MappingProxyType(
    {
        HouseholdFactShape.LITERAL: frozenset({HouseholdSubject.CHILD, HouseholdSubject.PET}),
        HouseholdFactShape.RELATION: frozenset(
            {HouseholdSubject.CHILD, HouseholdSubject.PARTNER, HouseholdSubject.PET}
        ),
    }
)
# Every sensitive category but `child_data` needs granted consent: the owner speaks for a child
# as guardian, so the child's own data needs none (ADR 0022 decision 3).
_HOUSEHOLD_CONSENT_CATEGORIES = _SENSITIVE_CATEGORIES - frozenset({DataSensitivity.CHILD_DATA})


def _household_memory_decision(
    request: AuthorizationRequest, status: AuthorizationStatus, outcome: str, reason: str
) -> AuthorizationDecision:
    """Build a household-memory decision whose reason never carries a protected value."""
    return _decision(request, status, f"cm3b.household-memory.{outcome}", reason)


def _is_allowed_household_subject(request: AuthorizationRequest) -> bool:
    """Return whether the request is household data about a subject the owner may write about.

    The visibility must be exactly `household`, and the caller must have classified both the
    subject and the shape of the fact; a missing classification is never guessed.
    """
    if (
        not request.visibility
        or not request.visibility <= _HOUSEHOLD_ONLY
        or request.subject_relation is None
        or request.fact_shape is None
    ):
        return False
    return request.subject_relation in _HOUSEHOLD_SUBJECTS[request.fact_shape]


def _lacks_strong_assurance(request: AuthorizationRequest) -> bool:
    """Return whether the actor's assurance ranks below `strong` (face and voice together)."""
    return ASSURANCE_RANK[request.actor.assurance] < ASSURANCE_RANK[IdentityAssurance.STRONG]


def _holds_pin_grant(request: AuthorizationRequest) -> bool:
    """Return whether the actor carries any owner PIN grant, spent or not.

    The pair has no PIN route, like a personal capability with no unlock scope: a bearer
    token proves the PIN, not the speaker, and the household pair writes on the speaker's word.
    """
    return any(
        item.source is IdentityEvidenceSource.LOCAL_UNLOCK for item in request.actor.evidence
    )


def _lacks_household_consent(request: AuthorizationRequest) -> bool:
    """Return whether a category that needs consent is requested without it granted."""
    return (
        bool(request.sensitivity & _HOUSEHOLD_CONSENT_CATEGORIES)
        and request.consent is not ConsentStatus.GRANTED
    )


def _evaluate_household_memory(request: AuthorizationRequest) -> AuthorizationDecision:
    """Evaluate one household-memory action in the fixed order of ADR 0019 §5.

    The generic gates (identity resolved; `security` data needs `strong`) have already run.
    Owner only, then the subject, the assurance, the PIN route and the consent. Every outcome
    is closed and the result is never `REQUIRES_CONFIRMATION`.
    """
    if request.actor.role is not HouseholdRole.OWNER:
        return _household_memory_decision(
            request,
            AuthorizationStatus.DENIED,
            "owner-only",
            "Household memory is reserved for the household owner.",
        )
    if not _is_allowed_household_subject(request):
        return _household_memory_decision(
            request,
            AuthorizationStatus.DENIED,
            "subject-not-allowed",
            "This household memory request names data the policy does not cover.",
        )
    if _lacks_strong_assurance(request):
        return _household_memory_decision(
            request,
            AuthorizationStatus.DENIED,
            "assurance-required",
            "This household memory request needs face and voice agreement.",
        )
    if _holds_pin_grant(request):
        return _household_memory_decision(
            request,
            AuthorizationStatus.DENIED,
            "grant-scope",
            "An owner unlock does not authorize household memory.",
        )
    if _lacks_household_consent(request):
        return _household_memory_decision(
            request,
            AuthorizationStatus.DENIED,
            "consent-required",
            "Required consent is absent or revoked.",
        )
    return _household_memory_decision(
        request,
        AuthorizationStatus.ALLOWED,
        "allowed",
        "Policy permits this request on the owner's household memory.",
    )


def _evaluate_legacy_request(request: AuthorizationRequest) -> AuthorizationDecision:
    """Evaluate one of the pre-existing actions; anything unlisted is denied."""
    if request.action in {
        AuthorizationAction.READ_HOUSEHOLD_DATA,
        AuthorizationAction.EXECUTE_HOUSEHOLD_TOOL,
    }:
        return _evaluate_read(request)
    if request.action in {
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


def _evaluate_resolved_request(request: AuthorizationRequest) -> AuthorizationDecision:
    """Evaluate a request after the caller has established a trusted actor.

    An action absent from `PERSONAL_MEMORY_CAPABILITIES` and from the household pair falls
    through to the legacy evaluation, whose last branch is the default deny.
    """
    capability = PERSONAL_MEMORY_CAPABILITIES.get(request.action)
    if capability is not None:
        return _evaluate_personal_memory(request, capability)
    if request.action in _HOUSEHOLD_MEMORY_ACTIONS:
        return _evaluate_household_memory(request)
    return _evaluate_legacy_request(request)


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
    if _lacks_required_assurance(request):
        return _decision(
            request,
            AuthorizationStatus.DENIED,
            "p0.5.assurance-required",
            "Reserved data needs face and voice agreement or an owner unlock.",
        )
    return _evaluate_resolved_request(request)
