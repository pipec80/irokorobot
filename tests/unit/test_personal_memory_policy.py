"""Unit tests for the personal-memory capabilities of the authorization policy (ADR 0019)."""

from datetime import UTC, datetime, timedelta
from functools import cache
from itertools import combinations, product
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
    IdentityEvidence,
    IdentityEvidenceSource,
)
from server.cognition.models import (
    AuthorizationAction,
    AuthorizationDecision,
    AuthorizationStatus,
    Confidence,
    ConfidenceBasis,
)
from server.cognition.owner_authentication import OwnerUnlockScope

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


def _actor(
    *,
    role: HouseholdRole = HouseholdRole.OWNER,
    assurance: IdentityAssurance = IdentityAssurance.BASIC,
    status: ActivePersonStatus = ActivePersonStatus.IDENTIFIED,
    person_id: int | None = _OWNER_ID,
    evidence: tuple[IdentityEvidence, ...] = (),
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
        evidence=evidence,
        resolved_at=_REQUESTED_AT,
        assurance=assurance,
    )


def _strong_actor_for(action: AuthorizationAction) -> ActivePersonContext:
    """A strong owner who can exercise `action`: a spent forget grant, else face and voice."""
    return _pin_actor(_FORGET_SCOPE) if action is _FORGET else _face_voice_actor()


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
    actor = (
        _strong_actor_for(action)
        if assurance is IdentityAssurance.STRONG
        else _actor(assurance=assurance)
    )

    decision = _decide(action, actor=actor)

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


# --- grants carried by the evidence (ADR 0019 §4) -----------------------------

_READ_SCOPE = "personal_memory_read"
_FORGET_SCOPE = "personal_memory_forget"
_GRANT_SCOPE_ID = "cm1.personal-memory.grant-scope"
# Every scope string a grant could carry: the four real ones, a stranger and "none issued".
_ANY_GRANT_SCOPE = (
    "personal_protected_read",
    "biometric_admin",
    _READ_SCOPE,
    _FORGET_SCOPE,
    "anything",
    None,
)


def _pin_evidence(
    *, scope: str | None, spent: bool = True, kind: str = "owner"
) -> IdentityEvidence:
    """Build the evidence an owner PIN grant leaves.

    `kind` is `owner` (a fresh grant for the owner), `other_person` (a grant for someone
    else) or `expired` (a grant whose lifetime ended before the request).
    """
    return IdentityEvidence(
        evidence_id=UUID("66666666-6666-6666-6666-666666666666"),
        source=IdentityEvidenceSource.LOCAL_UNLOCK,
        candidate_person_id=_OTHER_ID if kind == "other_person" else _OWNER_ID,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.ASSERTED, calibrated=True),
        observed_at=_REQUESTED_AT - timedelta(seconds=120),
        expires_at=_REQUESTED_AT - timedelta(seconds=60)
        if kind == "expired"
        else _REQUESTED_AT + timedelta(seconds=60),
        reference="session-selection",
        grant_scope=scope,
        grant_spent=spent,
    )


def _voice_evidence() -> IdentityEvidence:
    """Build the voice evidence that corroborates the owner's face."""
    return IdentityEvidence(
        evidence_id=UUID("77777777-7777-7777-7777-777777777777"),
        source=IdentityEvidenceSource.VOICE,
        candidate_person_id=_OWNER_ID,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False),
        observed_at=_REQUESTED_AT,
        reference="in-turn-speaker-evidence",
    )


def _pin_actor(
    scope: str | None, *, spent: bool = True, kind: str = "owner"
) -> ActivePersonContext:
    """A strong owner identified by one PIN grant of `scope`, spent or only peeked."""
    return _actor(
        assurance=IdentityAssurance.STRONG,
        evidence=(_pin_evidence(scope=scope, spent=spent, kind=kind),),
    )


def _face_voice_actor() -> ActivePersonContext:
    """A hand-built strong owner whose evidence is a face and a voice, with no PIN item."""
    return _actor(
        assurance=IdentityAssurance.STRONG, evidence=(_face_evidence(), _voice_evidence())
    )


def test_a_grant_counts_only_for_its_own_operation_and_only_once_spent() -> None:
    """Read and forget each accept one scope; every other scope, and a peek, is refused."""
    for action, own in ((_READ, _READ_SCOPE), (_FORGET, _FORGET_SCOPE)):
        for scope in _ANY_GRANT_SCOPE:
            decision = _decide(action, actor=_pin_actor(scope))
            if scope == own:
                _assert_outcome(decision, _ALLOWED, _ALLOWED_ID)
            else:
                _assert_outcome(decision, _DENIED, _GRANT_SCOPE_ID)
        peeked = _decide(action, actor=_pin_actor(own, spent=False))
        _assert_outcome(peeked, _DENIED, _GRANT_SCOPE_ID)


def test_propose_confirm_and_correct_have_no_pin_route() -> None:
    """Any PIN item denies them, whatever its scope: a spent read grant is the example."""
    for action in (_PROPOSE, _CONFIRM, _CORRECT):
        _assert_outcome(_decide(action, actor=_pin_actor(_READ_SCOPE)), _DENIED, _GRANT_SCOPE_ID)


def test_a_hand_built_strong_actor_reads_and_confirms_but_cannot_forget() -> None:
    both = _face_voice_actor()

    _assert_outcome(_decide(_READ, actor=both), _ALLOWED, _ALLOWED_ID)
    _assert_outcome(_decide(_CONFIRM, actor=both), _ALLOWED, _ALLOWED_ID)
    _assert_outcome(_decide(_FORGET, actor=both), _DENIED, _GRANT_SCOPE_ID)


@pytest.mark.parametrize(
    "category", [DataSensitivity.BIOMETRIC, DataSensitivity.MEDICAL, DataSensitivity.LOCATION]
)
def test_a_spent_read_grant_reads_strong_categories_but_the_writes_have_no_pin_route(
    category: DataSensitivity,
) -> None:
    """The PIN makes the actor strong, so it reaches the read; propose and correct stay face-only."""
    sensitivity = frozenset({category})
    grant = _pin_actor(_READ_SCOPE)

    read = _decide(_READ, actor=grant, sensitivity=sensitivity, consent=GRANTED)

    _assert_outcome(read, _ALLOWED, _ALLOWED_ID)
    for action in (_PROPOSE, _CORRECT):
        write = _decide(action, actor=grant, sensitivity=sensitivity, consent=GRANTED)
        _assert_outcome(write, _DENIED, _GRANT_SCOPE_ID)


def test_proposing_and_correcting_medical_data_is_reachable_only_through_face_and_voice() -> None:
    both = _face_voice_actor()
    face_only = _actor(assurance=IdentityAssurance.BASIC, evidence=(_face_evidence(),))

    for action in (_PROPOSE, _CORRECT):
        reached = _decide(action, actor=both, sensitivity=_MEDICAL, consent=GRANTED)
        photographed = _decide(action, actor=face_only, sensitivity=_MEDICAL, consent=GRANTED)
        _assert_outcome(reached, _ALLOWED, _ALLOWED_ID)
        _assert_outcome(photographed, _DENIED, _ASSURANCE_ID)


def test_every_pin_item_must_carry_the_right_scope_and_be_spent() -> None:
    right = _pin_evidence(scope=_FORGET_SCOPE)
    wrong = right.model_copy(
        update={
            "evidence_id": UUID("88888888-8888-8888-8888-888888888888"),
            "grant_scope": _READ_SCOPE,
        }
    )
    mixed = _actor(assurance=IdentityAssurance.STRONG, evidence=(right, wrong))
    face_and_grant = _actor(assurance=IdentityAssurance.STRONG, evidence=(_face_evidence(), right))

    _assert_outcome(_decide(_FORGET, actor=mixed), _DENIED, _GRANT_SCOPE_ID)
    _assert_outcome(_decide(_FORGET, actor=face_and_grant), _ALLOWED, _ALLOWED_ID)


def test_a_grant_for_another_person_next_to_a_strong_owner_authorizes_nothing() -> None:
    """A spent forget grant of someone else must not ride on the owner's face and voice."""
    foreign = _pin_evidence(scope=_FORGET_SCOPE, kind="other_person")
    owner = _actor(
        assurance=IdentityAssurance.STRONG,
        evidence=(_face_evidence(), _voice_evidence(), foreign),
    )

    _assert_outcome(_decide(_FORGET, actor=owner), _DENIED, _GRANT_SCOPE_ID)


def test_an_expired_grant_authorizes_nothing_even_when_marked_spent() -> None:
    expired = _pin_actor(_FORGET_SCOPE, kind="expired")

    _assert_outcome(_decide(_FORGET, actor=expired), _DENIED, _GRANT_SCOPE_ID)


def test_a_grant_expiring_exactly_at_request_time_authorizes_nothing() -> None:
    """The boundary is closed: `expires_at == requested_at` is already expired."""
    boundary = _pin_evidence(scope=_FORGET_SCOPE).model_copy(update={"expires_at": _REQUESTED_AT})
    owner = _actor(assurance=IdentityAssurance.STRONG, evidence=(boundary,))

    _assert_outcome(_decide(_FORGET, actor=owner), _DENIED, _GRANT_SCOPE_ID)


def test_a_grant_without_an_expiry_authorizes_nothing() -> None:
    """The registry always sets an expiry; an item without one is not a trusted grant."""
    unbounded = _pin_evidence(scope=_FORGET_SCOPE).model_copy(update={"expires_at": None})
    owner = _actor(assurance=IdentityAssurance.STRONG, evidence=(unbounded,))

    _assert_outcome(_decide(_FORGET, actor=owner), _DENIED, _GRANT_SCOPE_ID)


@pytest.mark.parametrize("action", [_READ, _PROPOSE, _CONFIRM, _CORRECT, _FORGET])
def test_a_request_with_no_visibility_is_not_the_owners_own_data(
    action: AuthorizationAction,
) -> None:
    """`AuthorizationRequest` forbids an empty set; the policy must not rely on that alone."""
    request = AuthorizationRequest.model_construct(
        actor=_strong_actor_for(action),
        action=action,
        target_person_id=_OWNER_ID,
        visibility=frozenset(),
        sensitivity=_NORMAL,
        consent=ConsentStatus.NOT_REQUIRED,
        correlation_id=_CORRELATION_ID,
        requested_at=_REQUESTED_AT,
    )

    _assert_outcome(evaluate_authorization(request), _DENIED, _OWN_DATA_ID)


def test_a_grant_is_judged_after_assurance_and_before_consent() -> None:
    wrong_scope_no_consent = _decide(
        _READ, actor=_pin_actor(_FORGET_SCOPE), sensitivity=_MEDICAL, consent=ConsentStatus.MISSING
    )
    low_assurance_wrong_scope = _decide(
        _FORGET,
        actor=_actor(
            assurance=IdentityAssurance.BASIC, evidence=(_pin_evidence(scope=_READ_SCOPE),)
        ),
    )

    _assert_outcome(wrong_scope_no_consent, _DENIED, _GRANT_SCOPE_ID)
    _assert_outcome(low_assurance_wrong_scope, _DENIED, _ASSURANCE_ID)


def test_a_manual_selection_is_not_a_pin_grant() -> None:
    """Only `local_unlock` evidence triggers the grant rules; a manual one is ignored."""
    manual = _pin_evidence(scope=None).model_copy(update={"source": IdentityEvidenceSource.MANUAL})
    actor = _actor(assurance=IdentityAssurance.BASIC, evidence=(manual,))

    _assert_outcome(_decide(_READ, actor=actor), _ALLOWED, _ALLOWED_ID)


def test_the_unlock_scope_enum_and_the_table_scopes_agree() -> None:
    table_scopes = {
        capability.unlock_scope
        for capability in PERSONAL_MEMORY_CAPABILITIES.values()
        if capability.unlock_scope is not None
    }

    assert [scope.value for scope in OwnerUnlockScope] == [
        "personal_protected_read",
        "biometric_admin",
        "personal_memory_read",
        "personal_memory_forget",
    ]
    assert table_scopes == {
        OwnerUnlockScope.PERSONAL_MEMORY_READ.value,
        OwnerUnlockScope.PERSONAL_MEMORY_FORGET.value,
    }


# --- exhaustive matrix against an oracle written from the ADR, not from the tables ------
#
# The oracle below deliberately imports no table from `authorization`: it restates ADR 0019
# §2, §3, §4 and §5 with literal values, so a wrong table row cannot agree with itself. Because
# it only ever answers "allowed" or "denied", agreeing with it also proves that no cell asks
# for confirmation, that raising assurance never turns an allow into a deny, that widening
# the category set never turns a deny into an allow, that withdrawing consent never allows
# what granted consent denied, and that a peeked grant is never better than a spent one.

_ASSURANCE_VALUES = ("none", "basic", "strong")
_ROLE_VALUES = ("owner", "adult", "child", "guest", "unknown")
_VISIBILITY_VALUES = ("public", "household", "adults", "personal", "private", "temporary")
_SENSITIVITY_VALUES = (
    "normal",
    "private",
    "biometric",
    "medical",
    "location",
    "child_data",
    "security",
)
_CONSENT_VALUES = ("not_required", "granted", "missing", "revoked")
_ACTION_VALUES = (
    "read_personal_conversation_memory",
    "propose_personal_memory",
    "confirm_personal_memory",
    "correct_personal_memory",
    "forget_personal_memory",
)
_FORGET_VALUE = "forget_personal_memory"
_ORACLE_RANK = {"none": 0, "basic": 1, "strong": 2}
_ORACLE_MIN_RANK = {
    "read_personal_conversation_memory": 1,
    "propose_personal_memory": 1,
    "confirm_personal_memory": 2,
    "correct_personal_memory": 1,
    "forget_personal_memory": 2,
}
_ORACLE_SENSITIVE = frozenset({"biometric", "medical", "location", "child_data", "security"})
_ORACLE_STRONG_CATEGORIES = frozenset({"biometric", "medical", "location"})
_ORACLE_PERSONAL = frozenset({"personal"})
_ORACLE_VISIBILITIES = {
    "read_personal_conversation_memory": _ORACLE_PERSONAL,
    "propose_personal_memory": _ORACLE_PERSONAL,
    "confirm_personal_memory": _ORACLE_PERSONAL,
    "correct_personal_memory": _ORACLE_PERSONAL,
    "forget_personal_memory": frozenset({"personal", "private", "temporary"}),
}
_ORACLE_UNLOCK_SCOPE = {
    "read_personal_conversation_memory": "personal_memory_read",
    "forget_personal_memory": "personal_memory_forget",
}
_MATRIX_ALLOWED = ("allowed", "cm1.personal-memory.allowed")

# A PIN item as (scope it carries, spent?, kind); None means the actor holds only a face item.
type Pin = tuple[str | None, bool, str] | None
_FORGET_PIN: Pin = ("personal_memory_forget", True, "owner")
_PIN_SCOPES = (
    "personal_protected_read",
    "biometric_admin",
    "personal_memory_read",
    "personal_memory_forget",
    None,
)
# Every PIN state the matrix visits: none; each scope spent or only peeked; and a spent grant
# of the two real scopes that belongs to another person or has expired.
_PIN_STATES: tuple[Pin, ...] = (
    None,
    *((scope, spent, "owner") for scope in _PIN_SCOPES for spent in (True, False)),
    *(
        (scope, True, kind)
        for scope in ("personal_memory_read", "personal_memory_forget")
        for kind in ("other_person", "expired")
    ),
)


def _subsets(values: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    """Return every non-empty subset of a literal value tuple, in a stable order."""
    return tuple(
        subset for size in range(1, len(values) + 1) for subset in combinations(values, size)
    )


_SENSITIVITY_SUBSETS = _subsets(_SENSITIVITY_VALUES)
_VISIBILITY_SUBSETS = _subsets(_VISIBILITY_VALUES)


def _face_evidence() -> IdentityEvidence:
    """Build the one piece of evidence a face-identified owner carries (no PIN grant)."""
    return IdentityEvidence(
        evidence_id=UUID("55555555-5555-5555-5555-555555555555"),
        source=IdentityEvidenceSource.FACE,
        candidate_person_id=_OWNER_ID,
        confidence=Confidence(score=0.95, basis=ConfidenceBasis.MEASURED, calibrated=True),
        observed_at=_REQUESTED_AT,
        reference="face-turn",
    )


def _best_pin(action: str) -> Pin:
    """The grant state that lets the owner exercise `action`: only forget needs a PIN grant."""
    return _FORGET_PIN if action == _FORGET_VALUE else None


@cache
def _matrix_actor(
    role: str, status: str, assurance: str, person_id: int | None, pin: Pin
) -> ActivePersonContext:
    """Return one actor for the matrices.

    A resolved actor carries either one PIN item (when `pin` is given) or one face item;
    an unresolved actor carries no evidence. A legitimate PIN item names the owner and is
    still fresh at the request time.
    """
    if person_id is None:
        evidence: tuple[IdentityEvidence, ...] = ()
    elif pin is None:
        evidence = (_face_evidence(),)
    else:
        evidence = (_pin_evidence(scope=pin[0], spent=pin[1], kind=pin[2]),)
    return _actor(
        role=HouseholdRole(role),
        status=ActivePersonStatus(status),
        assurance=IdentityAssurance(assurance),
        person_id=person_id,
        evidence=evidence,
    )


@cache
def _matrix_outcome(
    action: str,
    actor: tuple[str, str, str, int | None],
    target: int | None,
    visibility: tuple[str, ...],
    sensitivity: tuple[str, ...],
    consent: str,
    pin: Pin,
) -> tuple[str, str]:
    """Evaluate one matrix case and return (status, policy id).

    The request is built with `model_construct` to keep the sweeps fast; the inputs are
    literal values, so there is nothing for validation to reject.
    """
    request = AuthorizationRequest.model_construct(
        actor=_matrix_actor(*actor, pin),
        action=AuthorizationAction(action),
        target_person_id=target,
        visibility=frozenset(DataVisibility(item) for item in visibility),
        sensitivity=frozenset(DataSensitivity(item) for item in sensitivity),
        consent=ConsentStatus(consent),
        correlation_id=_CORRELATION_ID,
        requested_at=_REQUESTED_AT,
    )
    decision = evaluate_authorization(request)
    return decision.decision.value, decision.policy_id


def _owner_outcome(
    action: str, assurance: str, sensitivity: tuple[str, ...], consent: str, pin: Pin
) -> tuple[str, str]:
    """Evaluate the identified owner (person 7) on their own {personal} data."""
    return _matrix_outcome(
        action,
        ("owner", "identified", assurance, _OWNER_ID),
        _OWNER_ID,
        ("personal",),
        sensitivity,
        consent,
        pin,
    )


def _grant_is_valid(action: str, pin: Pin) -> bool:
    """ADR 0019 §4: forget needs a spent forget grant; read accepts only a spent read grant.

    A grant must also name the owner and still be fresh; propose, confirm and correct accept
    no PIN item at all.
    """
    if pin is None:
        return action != _FORGET_VALUE
    scope, spent, kind = pin
    wanted = _ORACLE_UNLOCK_SCOPE.get(action)
    return wanted is not None and spent and scope == wanted and kind == "owner"


def _oracle(
    action: str, assurance: str, sensitivity: tuple[str, ...], consent: str, pin: Pin
) -> tuple[str, str]:
    """State the ADR's rule for an identified owner acting on their own personal data."""
    rank = _ORACLE_RANK[assurance]
    if "security" in sensitivity and rank < _ORACLE_RANK["strong"]:
        return "denied", "p0.5.assurance-required"
    # Owner decision D-10: biometric, medical or location data needs `strong` whatever the action.
    needed = (
        _ORACLE_RANK["strong"]
        if _ORACLE_STRONG_CATEGORIES & set(sensitivity)
        else _ORACLE_MIN_RANK[action]
    )
    if rank < needed:
        return "denied", "cm1.personal-memory.assurance-required"
    if not _grant_is_valid(action, pin):
        return "denied", "cm1.personal-memory.grant-scope"
    needs_consent = action != _FORGET_VALUE and _ORACLE_SENSITIVE & set(sensitivity)
    if needs_consent and consent != "granted":
        return "denied", "cm1.personal-memory.consent-required"
    return _MATRIX_ALLOWED


def test_the_matrix_sizes_are_the_ones_the_adr_argues_over() -> None:
    assert len(_SENSITIVITY_SUBSETS) == 127
    assert len(_VISIBILITY_SUBSETS) == 63


@pytest.mark.parametrize("assurance", _ASSURANCE_VALUES)
@pytest.mark.parametrize("action", _ACTION_VALUES)
def test_the_owner_matrix_agrees_with_the_oracle_in_every_cell(action: str, assurance: str) -> None:
    """127 sensitivity sets x 4 consents x 15 PIN states per (action, assurance)."""
    mismatches = [
        (sensitivity, consent, pin, got, want)
        for sensitivity, consent, pin in product(_SENSITIVITY_SUBSETS, _CONSENT_VALUES, _PIN_STATES)
        if (got := _owner_outcome(action, assurance, sensitivity, consent, pin))
        != (want := _oracle(action, assurance, sensitivity, consent, pin))
    ]

    assert not mismatches, mismatches[:3]
    if action == _FORGET_VALUE:  # erasure never depends on consent, revoked or not
        for sensitivity, pin in product(_SENSITIVITY_SUBSETS, _PIN_STATES):
            granted = _owner_outcome(action, assurance, sensitivity, "granted", pin)
            for consent in _CONSENT_VALUES:
                assert _owner_outcome(action, assurance, sensitivity, consent, pin) == granted


def _gate_oracle(
    action: str,
    actor: tuple[str, str, str, int | None],
    target: int | None,
    visibility: tuple[str, ...],
) -> bool:
    """Allowed only for an identified owner on their own data of a reachable visibility.

    Sensitivity is normal and consent granted in this sweep, and every actor holds the grant
    state its action needs (`_best_pin`), so only the identity, target, visibility and
    assurance gates can deny.
    """
    role, status, assurance, _ = actor
    return (
        role == "owner"
        and status == "identified"
        and target == _OWNER_ID
        and set(visibility) <= _ORACLE_VISIBILITIES[action]
        and _ORACLE_RANK[assurance] >= _ORACLE_MIN_RANK[action]
    )


def _all_actors() -> tuple[tuple[str, str, str, int | None], ...]:
    """Return the 18 actors: 15 identified, a probable owner, an unknown and an ambiguous one."""
    identified = tuple(
        (role, "identified", assurance, _OWNER_ID)
        for role in _ROLE_VALUES
        for assurance in _ASSURANCE_VALUES
    )
    return (
        *identified,
        ("owner", "probable", "none", _OWNER_ID),
        ("unknown", "unknown", "none", None),
        ("unknown", "ambiguous", "none", None),
    )


@pytest.mark.parametrize("action", _ACTION_VALUES)
def test_only_an_identified_owner_on_own_reachable_data_is_ever_allowed(action: str) -> None:
    """18 actors x 3 targets (none, own, foreign) x 63 visibility sets: 3 402 cells per action."""
    actors = _all_actors()
    assert len(actors) == 18
    mismatches = []
    for actor, target, visibility in product(
        actors, (None, _OWNER_ID, _OTHER_ID), _VISIBILITY_SUBSETS
    ):
        status, _ = _matrix_outcome(
            action, actor, target, visibility, ("normal",), "granted", _best_pin(action)
        )
        want = _gate_oracle(action, actor, target, visibility)
        if (status == "allowed") != want or status == "requires_confirmation":
            mismatches.append((actor, target, visibility, status))

    assert not mismatches, mismatches[:3]


def test_forget_is_never_allowed_to_any_actor_without_a_spent_forget_grant() -> None:
    """18 actors x 3 targets x 63 visibility sets, face-only evidence: not one forget."""
    allowed = [
        (actor, target, visibility)
        for actor, target, visibility in product(
            _all_actors(), (None, _OWNER_ID, _OTHER_ID), _VISIBILITY_SUBSETS
        )
        if _matrix_outcome(_FORGET_VALUE, actor, target, visibility, ("normal",), "granted", None)[
            0
        ]
        == "allowed"
    ]

    assert not allowed, allowed[:3]
