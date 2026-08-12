"""Unit tests for the pure, fail-closed household authorization policy."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from server.cognition.authorization import (
    AuthorizationRequest,
    ConsentStatus,
    DataSensitivity,
    DataVisibility,
    evaluate_authorization,
)
from server.cognition.identity import ActivePersonContext, ActivePersonStatus, HouseholdRole
from server.cognition.models import (
    AuthorizationAction,
    AuthorizationStatus,
    Confidence,
    ConfidenceBasis,
)

_REQUESTED_AT = datetime(2026, 8, 12, 12, tzinfo=UTC)
_CORRELATION_ID = UUID("11111111-1111-1111-1111-111111111111")


def _actor(
    *,
    role: HouseholdRole,
    status: ActivePersonStatus = ActivePersonStatus.IDENTIFIED,
    person_id: int | None = 7,
) -> ActivePersonContext:
    """Build a minimal active person for pure authorization cases."""
    return ActivePersonContext(
        person_id=person_id,
        display_name="Ada" if person_id is not None else None,
        status=status,
        confidence=Confidence(
            score=1.0 if person_id is not None else 0.0,
            basis=ConfidenceBasis.ASSERTED,
            calibrated=False,
        ),
        role=role,
        evidence=(),
        resolved_at=_REQUESTED_AT,
    )


def _request(
    actor: ActivePersonContext,
    *,
    action: AuthorizationAction,
    visibility: frozenset[DataVisibility] = frozenset({DataVisibility.HOUSEHOLD}),
    sensitivity: frozenset[DataSensitivity] = frozenset({DataSensitivity.NORMAL}),
    consent: ConsentStatus = ConsentStatus.NOT_REQUIRED,
    target_person_id: int | None = None,
) -> AuthorizationRequest:
    """Build one request without database, prompt, or media content."""
    return AuthorizationRequest(
        actor=actor,
        action=action,
        target_person_id=target_person_id,
        visibility=visibility,
        sensitivity=sensitivity,
        consent=consent,
        correlation_id=_CORRELATION_ID,
        requested_at=_REQUESTED_AT,
    )


@pytest.mark.parametrize("status", [ActivePersonStatus.UNKNOWN, ActivePersonStatus.AMBIGUOUS])
def test_unknown_or_ambiguous_actor_never_reads_household_data(
    status: ActivePersonStatus,
) -> None:
    """Protected retrieval must fail before a role or confidence can matter."""
    actor = _actor(role=HouseholdRole.UNKNOWN, status=status, person_id=None)

    decision = evaluate_authorization(
        _request(actor, action=AuthorizationAction.READ_HOUSEHOLD_DATA)
    )

    assert decision.decision is AuthorizationStatus.DENIED
    assert decision.policy_id == "p0.5.identity-unresolved"


@pytest.mark.parametrize("status", [ActivePersonStatus.UNKNOWN, ActivePersonStatus.AMBIGUOUS])
def test_general_conversation_is_allowed_without_identity(
    status: ActivePersonStatus,
) -> None:
    """General conversation must not require a household identity."""
    actor = _actor(role=HouseholdRole.UNKNOWN, status=status, person_id=None)

    decision = evaluate_authorization(
        _request(
            actor,
            action=AuthorizationAction.GENERAL_CONVERSATION,
            visibility=frozenset({DataVisibility.PUBLIC}),
        )
    )

    assert decision.decision is AuthorizationStatus.ALLOWED
    assert decision.policy_id == "p0.5.general-conversation"


def test_general_conversation_cannot_carry_protected_categories() -> None:
    """A generic action name must not bypass classified household data policy."""
    actor = _actor(role=HouseholdRole.UNKNOWN, status=ActivePersonStatus.UNKNOWN, person_id=None)

    decision = evaluate_authorization(
        _request(actor, action=AuthorizationAction.GENERAL_CONVERSATION)
    )

    assert decision.decision is AuthorizationStatus.DENIED
    assert decision.policy_id == "p0.5.general-conversation-unclassified"


def test_probable_actor_never_reads_household_data() -> None:
    """A plausible identity is insufficient for protected retrieval."""
    actor = _actor(role=HouseholdRole.OWNER, status=ActivePersonStatus.PROBABLE)

    decision = evaluate_authorization(
        _request(actor, action=AuthorizationAction.READ_HOUSEHOLD_DATA)
    )

    assert decision.decision is AuthorizationStatus.DENIED
    assert decision.policy_id == "p0.5.identity-unresolved"


def test_child_can_read_only_own_normal_personal_data() -> None:
    """A child never gets family access merely by having a household role."""
    child = _actor(role=HouseholdRole.CHILD, person_id=8)

    own = evaluate_authorization(
        _request(
            child,
            action=AuthorizationAction.READ_HOUSEHOLD_DATA,
            target_person_id=8,
            visibility=frozenset({DataVisibility.PERSONAL}),
        )
    )
    other = evaluate_authorization(
        _request(
            child,
            action=AuthorizationAction.READ_HOUSEHOLD_DATA,
            target_person_id=7,
            visibility=frozenset({DataVisibility.PERSONAL}),
        )
    )

    assert own.decision is AuthorizationStatus.ALLOWED
    assert other.decision is AuthorizationStatus.DENIED


def test_owner_biometric_enrollment_requires_subject_consent() -> None:
    """Owner authority cannot replace the subject's biometric consent."""
    owner = _actor(role=HouseholdRole.OWNER)
    missing = evaluate_authorization(
        _request(
            owner,
            action=AuthorizationAction.ENROLL_BIOMETRIC,
            sensitivity=frozenset({DataSensitivity.BIOMETRIC}),
            consent=ConsentStatus.MISSING,
            target_person_id=8,
        )
    )
    granted = evaluate_authorization(
        _request(
            owner,
            action=AuthorizationAction.ENROLL_BIOMETRIC,
            sensitivity=frozenset({DataSensitivity.BIOMETRIC}),
            consent=ConsentStatus.GRANTED,
            target_person_id=8,
        )
    )
    revoked = evaluate_authorization(
        _request(
            owner,
            action=AuthorizationAction.ENROLL_BIOMETRIC,
            sensitivity=frozenset({DataSensitivity.BIOMETRIC}),
            consent=ConsentStatus.REVOKED,
            target_person_id=8,
        )
    )

    assert missing.decision is AuthorizationStatus.DENIED
    assert granted.decision is AuthorizationStatus.ALLOWED
    assert revoked.decision is AuthorizationStatus.DENIED


def test_public_household_read_by_child_requires_confirmation_not_access() -> None:
    """Confirmation-required outcomes never become an implicit data grant."""
    child = _actor(role=HouseholdRole.CHILD, person_id=8)

    decision = evaluate_authorization(
        _request(
            child,
            action=AuthorizationAction.READ_HOUSEHOLD_DATA,
            visibility=frozenset({DataVisibility.PUBLIC}),
        )
    )

    assert decision.decision is AuthorizationStatus.REQUIRES_CONFIRMATION
