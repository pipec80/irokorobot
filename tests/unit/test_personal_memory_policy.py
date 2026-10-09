"""Unit tests for the personal-memory capabilities of the authorization policy (ADR 0019)."""

from datetime import UTC, datetime
from types import MappingProxyType
from typing import TYPE_CHECKING, cast
from uuid import UUID

import pytest
from server.cognition import authorization
from server.cognition.authorization import (
    ASSURANCE_RANK,
    HIGH_ASSURANCE_CATEGORIES,
    PERSONAL_MEMORY_CAPABILITIES,
    PERSONAL_MEMORY_STRONG_CATEGORIES,
    AuthorizationRequest,
    ConsentStatus,
    DataSensitivity,
    DataVisibility,
    PersonalMemoryCapability,
    evaluate_authorization,
)
from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    HouseholdRole,
    IdentityAssurance,
)
from server.cognition.models import (
    AuthorizationAction,
    AuthorizationDecision,
    AuthorizationStatus,
    Confidence,
    ConfidenceBasis,
)

if TYPE_CHECKING:
    from collections.abc import MutableMapping

pytestmark = pytest.mark.unit

_LEGACY_ACTIONS = frozenset(
    {
        "general_conversation",
        "read_household_data",
        "execute_household_tool",
        "propose_memory",
        "commit_memory",
        "manage_household_role",
        "enroll_biometric",
        "export_household_data",
        "delete_household_data",
        "consider_cloud_escalation",
        "propose_physical_action",
    }
)
_READ = AuthorizationAction.READ_PERSONAL_CONVERSATION_MEMORY
_PROPOSE = AuthorizationAction.PROPOSE_PERSONAL_MEMORY
_CONFIRM = AuthorizationAction.CONFIRM_PERSONAL_MEMORY
_CORRECT = AuthorizationAction.CORRECT_PERSONAL_MEMORY
_FORGET = AuthorizationAction.FORGET_PERSONAL_MEMORY
_PERSONAL_ONLY = frozenset({DataVisibility.PERSONAL})
_FORGET_VISIBILITIES = frozenset(
    {DataVisibility.PERSONAL, DataVisibility.PRIVATE, DataVisibility.TEMPORARY}
)
_SENSITIVE_LITERAL = frozenset(
    {
        DataSensitivity.BIOMETRIC,
        DataSensitivity.MEDICAL,
        DataSensitivity.LOCATION,
        DataSensitivity.CHILD_DATA,
        DataSensitivity.SECURITY,
    }
)
_ORDINARY_LITERAL = frozenset({DataSensitivity.NORMAL, DataSensitivity.PRIVATE})

# ADR 0019 §3, restated as literals. Owner amendment 2026-10-08: confirm needs STRONG.
_EXPECTED_TABLE = {
    _READ: PersonalMemoryCapability(
        min_assurance=IdentityAssurance.BASIC,
        consent_applies=True,
        requires_unlock=False,
        unlock_scope="personal_memory_read",
        visibilities=_PERSONAL_ONLY,
    ),
    _PROPOSE: PersonalMemoryCapability(
        min_assurance=IdentityAssurance.BASIC,
        consent_applies=True,
        requires_unlock=False,
        unlock_scope=None,
        visibilities=_PERSONAL_ONLY,
    ),
    _CONFIRM: PersonalMemoryCapability(
        min_assurance=IdentityAssurance.STRONG,
        consent_applies=True,
        requires_unlock=False,
        unlock_scope=None,
        visibilities=_PERSONAL_ONLY,
    ),
    _CORRECT: PersonalMemoryCapability(
        min_assurance=IdentityAssurance.BASIC,
        consent_applies=True,
        requires_unlock=False,
        unlock_scope=None,
        visibilities=_PERSONAL_ONLY,
    ),
    _FORGET: PersonalMemoryCapability(
        min_assurance=IdentityAssurance.STRONG,
        consent_applies=False,
        requires_unlock=True,
        unlock_scope="personal_memory_forget",
        visibilities=_FORGET_VISIBILITIES,
    ),
}


# --- structure of the capability table --------------------------------------


def test_the_capability_table_is_exactly_the_one_in_adr_0019() -> None:
    """One literal table: five new actions, nothing else, no capability accepts no assurance."""
    assert dict(PERSONAL_MEMORY_CAPABILITIES) == _EXPECTED_TABLE
    for capability in PERSONAL_MEMORY_CAPABILITIES.values():
        assert capability.min_assurance is not IdentityAssurance.NONE
        assert capability.visibilities


def test_every_action_is_either_legacy_or_a_personal_memory_capability() -> None:
    all_values = {action.value for action in AuthorizationAction}
    new_values = {action.value for action in PERSONAL_MEMORY_CAPABILITIES}

    assert all_values == _LEGACY_ACTIONS | new_values
    assert not _LEGACY_ACTIONS & new_values


def test_requiring_an_unlock_implies_naming_the_scope_it_must_carry() -> None:
    for capability in PERSONAL_MEMORY_CAPABILITIES.values():
        assert not capability.requires_unlock or capability.unlock_scope is not None


def test_every_sensitivity_is_ordinary_or_sensitive_never_both_nor_neither() -> None:
    """Adding a DataSensitivity member fails here until it is classified."""
    sensitive = authorization._SENSITIVE_CATEGORIES

    for category in DataSensitivity:
        assert (category in _ORDINARY_LITERAL) != (category in sensitive), category.value
    assert sensitive == _SENSITIVE_LITERAL
    assert _ORDINARY_LITERAL | sensitive == set(DataSensitivity)


def test_high_assurance_categories_are_sensitive_categories() -> None:
    assert HIGH_ASSURANCE_CATEGORIES <= authorization._SENSITIVE_CATEGORIES
    assert set(HIGH_ASSURANCE_CATEGORIES) == {DataSensitivity.SECURITY}


def test_the_categories_that_raise_the_minimum_to_strong_are_biometric_medical_location() -> None:
    """ADR 0019 §3 (owner decision D-10): a photograph of the owner must not reach these."""
    strong = PERSONAL_MEMORY_STRONG_CATEGORIES

    assert strong == {
        DataSensitivity.BIOMETRIC,
        DataSensitivity.MEDICAL,
        DataSensitivity.LOCATION,
    }
    assert strong <= authorization._SENSITIVE_CATEGORIES
    assert not strong & HIGH_ASSURANCE_CATEGORIES  # security stays on the generic gate
    assert DataSensitivity.CHILD_DATA not in strong  # ADR 0016 accepts the face for that read


def test_assurance_rank_is_total_and_not_lexicographic() -> None:
    """`IdentityAssurance` is a str enum: comparing members orders them alphabetically."""
    assert IdentityAssurance.BASIC < IdentityAssurance.NONE  # the trap, documented
    assert set(ASSURANCE_RANK) == set(IdentityAssurance)
    assert (
        ASSURANCE_RANK[IdentityAssurance.NONE]
        < ASSURANCE_RANK[IdentityAssurance.BASIC]
        < ASSURANCE_RANK[IdentityAssurance.STRONG]
    )


def test_the_tables_are_read_only() -> None:
    capabilities = cast(
        "MutableMapping[AuthorizationAction, PersonalMemoryCapability]",
        PERSONAL_MEMORY_CAPABILITIES,
    )
    ranks = cast("MutableMapping[IdentityAssurance, int]", ASSURANCE_RANK)

    with pytest.raises(TypeError):
        capabilities[_FORGET] = PERSONAL_MEMORY_CAPABILITIES[_READ]
    with pytest.raises(TypeError):
        ranks[IdentityAssurance.NONE] = 9
    with pytest.raises(TypeError):
        del capabilities[_READ]


# --- evaluation (ADR 0019 §2, §3 and §5) -------------------------------------

_REQUESTED_AT = datetime(2026, 10, 8, 12, tzinfo=UTC)
_CORRELATION_ID = UUID("33333333-3333-3333-3333-333333333333")
_OWNER_ID = 7
_OTHER_ID = 8
_NORMAL = frozenset({DataSensitivity.NORMAL})
_MEDICAL = frozenset({DataSensitivity.MEDICAL})
_SECURITY = frozenset({DataSensitivity.SECURITY})
_NEW_ACTIONS = (_READ, _PROPOSE, _CONFIRM, _CORRECT, _FORGET)
_NON_FORGET = (_READ, _PROPOSE, _CONFIRM, _CORRECT)
_BASIC_ACTIONS = (_READ, _PROPOSE, _CORRECT)
_STRONG_ACTIONS = (_CONFIRM, _FORGET)
GRANTED = ConsentStatus.GRANTED
_ALL_CONSENTS = (
    ConsentStatus.NOT_REQUIRED,
    ConsentStatus.MISSING,
    ConsentStatus.REVOKED,
    ConsentStatus.GRANTED,
)

_ALLOWED = AuthorizationStatus.ALLOWED
_DENIED = AuthorizationStatus.DENIED
_ALLOWED_ID = "cm1.personal-memory.allowed"
_OWNER_ONLY_ID = "cm1.personal-memory.owner-only"
_OWN_DATA_ID = "cm1.personal-memory.own-data-only"
_ASSURANCE_ID = "cm1.personal-memory.assurance-required"
_CONSENT_ID = "cm1.personal-memory.consent-required"
_GLOBAL_ASSURANCE_ID = "p0.5.assurance-required"
_UNRESOLVED_ID = "p0.5.identity-unresolved"
_DEFAULT_DENY_ID = "p0.5.default-deny"


def _visibility_id(visibility: frozenset[DataVisibility]) -> str:
    """Render a visibility set as a stable pytest id."""
    return "+".join(sorted(item.value for item in visibility))


def _actor(
    *,
    role: HouseholdRole = HouseholdRole.OWNER,
    assurance: IdentityAssurance = IdentityAssurance.BASIC,
    status: ActivePersonStatus = ActivePersonStatus.IDENTIFIED,
    person_id: int | None = _OWNER_ID,
) -> ActivePersonContext:
    """Build one active person for a pure personal-memory case (no media, no database)."""
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
        assurance=assurance,
    )


def _strong_actor_for(action: AuthorizationAction) -> ActivePersonContext:
    """A hand-built strong owner (no evidence) who can exercise `action`."""
    del action
    return _actor(assurance=IdentityAssurance.STRONG)


def _decide(
    action: AuthorizationAction,
    *,
    actor: ActivePersonContext | None = None,
    target: int | None = _OWNER_ID,
    visibility: frozenset[DataVisibility] = _PERSONAL_ONLY,
    sensitivity: frozenset[DataSensitivity] = _NORMAL,
    consent: ConsentStatus = ConsentStatus.NOT_REQUIRED,
) -> AuthorizationDecision:
    """Evaluate the owner's own ordinary personal data unless a keyword overrides it."""
    return evaluate_authorization(
        AuthorizationRequest(
            actor=actor if actor is not None else _actor(),
            action=action,
            target_person_id=target,
            visibility=visibility,
            sensitivity=sensitivity,
            consent=consent,
            correlation_id=_CORRELATION_ID,
            requested_at=_REQUESTED_AT,
        )
    )


def _assert_outcome(
    decision: AuthorizationDecision, status: AuthorizationStatus, policy_id: str
) -> None:
    """Assert a decision's fully qualified policy id, then its status."""
    assert decision.policy_id == policy_id
    assert decision.decision is status


_ASSURANCE_CASES = [
    *((action, IdentityAssurance.STRONG, _ALLOWED_ID) for action in _NEW_ACTIONS),
    *((action, IdentityAssurance.BASIC, _ALLOWED_ID) for action in _BASIC_ACTIONS),
    *((action, IdentityAssurance.BASIC, _ASSURANCE_ID) for action in _STRONG_ACTIONS),
    *((action, IdentityAssurance.NONE, _ASSURANCE_ID) for action in _NEW_ACTIONS),
]


@pytest.mark.parametrize("action, assurance, policy_id", _ASSURANCE_CASES)
def test_assurance_is_compared_by_rank_against_each_actions_minimum(
    action: AuthorizationAction, assurance: IdentityAssurance, policy_id: str
) -> None:
    """Read, propose and correct need `basic`; confirm and forget need `strong`; none never."""
    decision = _decide(action, actor=_actor(assurance=assurance))

    assert decision.policy_id == policy_id
    assert decision.action is action


@pytest.mark.parametrize("assurance", [IdentityAssurance.NONE, IdentityAssurance.BASIC])
@pytest.mark.parametrize("action", _NEW_ACTIONS)
def test_security_data_below_strong_is_stopped_by_the_existing_global_gate(
    action: AuthorizationAction, assurance: IdentityAssurance
) -> None:
    decision = _decide(
        action,
        actor=_actor(assurance=assurance),
        sensitivity=_SECURITY,
        consent=ConsentStatus.GRANTED,
    )

    _assert_outcome(decision, _DENIED, _GLOBAL_ASSURANCE_ID)


@pytest.mark.parametrize("action", _NON_FORGET)
def test_sensitive_data_needs_granted_consent(action: AuthorizationAction) -> None:
    """One example per outcome; the 127-subset matrix below covers every category."""
    strong = _strong_actor_for(action)

    for consent in (ConsentStatus.NOT_REQUIRED, ConsentStatus.MISSING, ConsentStatus.REVOKED):
        _assert_outcome(
            _decide(action, actor=strong, sensitivity=_MEDICAL, consent=consent),
            _DENIED,
            _CONSENT_ID,
        )
    granted = _decide(action, actor=strong, sensitivity=_MEDICAL, consent=ConsentStatus.GRANTED)
    _assert_outcome(granted, _ALLOWED, _ALLOWED_ID)


def test_forget_ignores_consent_even_when_it_was_revoked() -> None:
    """Withdrawing consent is a reason to erase: it must never block erasure."""
    outcomes = {
        consent: _decide(
            _FORGET,
            actor=_strong_actor_for(_FORGET),
            sensitivity=_SECURITY,
            consent=consent,
        )
        for consent in _ALL_CONSENTS
    }

    for decision in outcomes.values():
        _assert_outcome(decision, _ALLOWED, _ALLOWED_ID)
    assert outcomes[ConsentStatus.REVOKED] == outcomes[ConsentStatus.GRANTED]


@pytest.mark.parametrize("action", _NEW_ACTIONS)
def test_private_sensitivity_behaves_like_normal(action: AuthorizationAction) -> None:
    strong = _strong_actor_for(action)

    private = _decide(action, actor=strong, sensitivity=frozenset({DataSensitivity.PRIVATE}))
    normal = _decide(action, actor=strong)

    _assert_outcome(private, _ALLOWED, _ALLOWED_ID)
    assert (private.decision, private.policy_id) == (normal.decision, normal.policy_id)


@pytest.mark.parametrize("role", [HouseholdRole.ADULT, HouseholdRole.CHILD, HouseholdRole.GUEST])
@pytest.mark.parametrize("action", _NEW_ACTIONS)
def test_only_the_owner_may_use_personal_memory_and_is_never_asked_to_confirm(
    action: AuthorizationAction, role: HouseholdRole
) -> None:
    actor = _actor(role=role, assurance=IdentityAssurance.STRONG)

    decision = _decide(action, actor=actor, consent=ConsentStatus.GRANTED)

    _assert_outcome(decision, _DENIED, _OWNER_ONLY_ID)
    assert decision.decision is not AuthorizationStatus.REQUIRES_CONFIRMATION


def test_the_generic_security_gate_runs_before_the_owner_only_rule() -> None:
    """An adult at basic asking for SECURITY data is stopped by the generic gate, not owner-only."""
    adult = _actor(role=HouseholdRole.ADULT)

    gate = _decide(_READ, actor=adult, sensitivity=_SECURITY, consent=ConsentStatus.GRANTED)
    plain = _decide(_READ, actor=adult)

    _assert_outcome(gate, _DENIED, _GLOBAL_ASSURANCE_ID)
    _assert_outcome(plain, _DENIED, _OWNER_ONLY_ID)


@pytest.mark.parametrize("action", _NEW_ACTIONS)
def test_an_unresolved_actor_is_stopped_by_the_existing_identity_gate(
    action: AuthorizationAction,
) -> None:
    probable = _actor(status=ActivePersonStatus.PROBABLE, assurance=IdentityAssurance.NONE)
    unknown = _actor(
        role=HouseholdRole.UNKNOWN,
        status=ActivePersonStatus.UNKNOWN,
        assurance=IdentityAssurance.NONE,
        person_id=None,
    )
    unknown_role = _actor(role=HouseholdRole.UNKNOWN, assurance=IdentityAssurance.STRONG)

    for actor in (probable, unknown, unknown_role):
        _assert_outcome(_decide(action, actor=actor), _DENIED, _UNRESOLVED_ID)


def test_forget_reaches_personal_private_and_temporary_data_but_not_household_data() -> None:
    forgetting = _strong_actor_for(_FORGET)
    private = frozenset({DataVisibility.PRIVATE})
    temporary = frozenset({DataVisibility.TEMPORARY})
    household = frozenset({DataVisibility.PERSONAL, DataVisibility.HOUSEHOLD})

    _assert_outcome(_decide(_FORGET, actor=forgetting, visibility=private), _ALLOWED, _ALLOWED_ID)
    _assert_outcome(_decide(_FORGET, actor=forgetting, visibility=temporary), _ALLOWED, _ALLOWED_ID)
    _assert_outcome(_decide(_FORGET, actor=forgetting, visibility=household), _DENIED, _OWN_DATA_ID)
    # The other four reach only {personal}: {private} is already too wide for them.
    strong = _strong_actor_for(_READ)
    _assert_outcome(_decide(_READ, actor=strong, visibility=private), _DENIED, _OWN_DATA_ID)


def test_non_owner_with_foreign_data_low_assurance_and_no_consent_is_owner_only_first() -> None:
    actor = _actor(role=HouseholdRole.ADULT, assurance=IdentityAssurance.NONE)

    decision = _decide(
        _READ,
        actor=actor,
        target=_OTHER_ID,
        sensitivity=_MEDICAL,
        consent=ConsentStatus.MISSING,
    )

    _assert_outcome(decision, _DENIED, _OWNER_ONLY_ID)


def test_owner_with_foreign_data_and_no_assurance_is_own_data_only_before_assurance() -> None:
    actor = _actor(assurance=IdentityAssurance.NONE)

    _assert_outcome(_decide(_READ, actor=actor, target=_OTHER_ID), _DENIED, _OWN_DATA_ID)


def test_owner_with_own_data_no_assurance_and_no_consent_is_assurance_before_consent() -> None:
    actor = _actor(assurance=IdentityAssurance.NONE)

    decision = _decide(_READ, actor=actor, sensitivity=_MEDICAL, consent=ConsentStatus.MISSING)

    _assert_outcome(decision, _DENIED, _ASSURANCE_ID)


def test_enough_assurance_with_missing_consent_is_consent_required() -> None:
    """Child data stays at the capability minimum, so `basic` reaches the consent rule."""
    decision = _decide(
        _READ, sensitivity=frozenset({DataSensitivity.CHILD_DATA}), consent=ConsentStatus.MISSING
    )

    _assert_outcome(decision, _DENIED, _CONSENT_ID)


_STRONG_CATEGORY_CASES = [
    (action, category)
    for action in _BASIC_ACTIONS
    for category in (DataSensitivity.BIOMETRIC, DataSensitivity.MEDICAL, DataSensitivity.LOCATION)
]


@pytest.mark.parametrize("action, category", _STRONG_CATEGORY_CASES)
def test_a_photograph_of_the_owner_cannot_reach_biometric_medical_or_location_memory(
    action: AuthorizationAction, category: DataSensitivity
) -> None:
    """Owner decision D-10: a face alone (`basic`) is denied even with granted consent."""
    sensitivity = frozenset({category})
    face_only = _actor(assurance=IdentityAssurance.BASIC)

    photographed = _decide(action, actor=face_only, sensitivity=sensitivity, consent=GRANTED)
    strong = _decide(
        action, actor=_strong_actor_for(action), sensitivity=sensitivity, consent=GRANTED
    )

    _assert_outcome(photographed, _DENIED, _ASSURANCE_ID)
    _assert_outcome(strong, _ALLOWED, _ALLOWED_ID)


@pytest.mark.parametrize("action", _BASIC_ACTIONS)
def test_child_data_stays_at_the_capability_minimum(action: AuthorizationAction) -> None:
    """ADR 0016 already accepts the owner's face for the child read."""
    decision = _decide(action, sensitivity=frozenset({DataSensitivity.CHILD_DATA}), consent=GRANTED)

    _assert_outcome(decision, _ALLOWED, _ALLOWED_ID)


def test_a_mixed_set_with_one_strong_category_needs_strong_assurance() -> None:
    mixed = frozenset({DataSensitivity.NORMAL, DataSensitivity.MEDICAL})

    _assert_outcome(_decide(_READ, sensitivity=mixed, consent=GRANTED), _DENIED, _ASSURANCE_ID)


def test_assurance_is_judged_before_consent_for_a_strong_category() -> None:
    """A medical read at `basic` with missing consent is told about assurance first."""
    decision = _decide(_READ, sensitivity=_MEDICAL, consent=ConsentStatus.MISSING)

    _assert_outcome(decision, _DENIED, _ASSURANCE_ID)


def test_an_action_missing_from_the_table_falls_back_to_the_default_deny(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(authorization, "PERSONAL_MEMORY_CAPABILITIES", MappingProxyType({}))

    for action in _NEW_ACTIONS:
        _assert_outcome(_decide(action), _DENIED, _DEFAULT_DENY_ID)


def test_removing_one_action_from_the_table_denies_only_that_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reduced = {k: v for k, v in PERSONAL_MEMORY_CAPABILITIES.items() if k is not _FORGET}
    monkeypatch.setattr(authorization, "PERSONAL_MEMORY_CAPABILITIES", MappingProxyType(reduced))

    forget = _decide(_FORGET, actor=_strong_actor_for(_FORGET))

    _assert_outcome(forget, _DENIED, _DEFAULT_DENY_ID)
    _assert_outcome(_decide(_READ), _ALLOWED, _ALLOWED_ID)


def test_decisions_carry_the_requested_action_and_only_safe_labels() -> None:
    vocabulary = {item.value for item in DataVisibility} | {item.value for item in DataSensitivity}
    cases = [
        _decide(_READ),
        _decide(_READ, target=_OTHER_ID),
        _decide(_READ, actor=_actor(role=HouseholdRole.ADULT)),
        _decide(_READ, actor=_actor(assurance=IdentityAssurance.NONE)),
        _decide(_READ, sensitivity=_MEDICAL),
    ]

    for decision in cases:
        assert decision.action is _READ
        assert decision.data_categories <= vocabulary
        assert "Ada" not in decision.reason
        assert not any(char.isdigit() for char in decision.reason)
        assert decision.policy_id.startswith(("cm1.personal-memory.", "p0.5."))
