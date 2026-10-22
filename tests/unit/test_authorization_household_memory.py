"""Unit tests for the household pair of capabilities (ADR 0022 decisions 3 and 4, Plan 0065).

`propose_household_memory` and `confirm_household_memory` are policy only: nothing consumes
them yet. The owner may write about the household they are guardian of: the children and the
pets (literals) and the children, the partner and the pets (relations), on `household` data,
at `strong` assurance (face and voice of the same person), never through a PIN token.

The expectations below restate the ADR with literal values and import no table from
`authorization`, so a wrong rule cannot agree with itself. The classification of the subject
(`subject_relation`, `fact_shape`) is the caller's, made before any read (ADR 0019 §6.2): the
policy is pure and never derives it from stored rows.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from itertools import combinations, product
from uuid import UUID

from pydantic import ValidationError
import pytest
from server.cognition.authorization import (
    PERSONAL_MEMORY_CAPABILITIES,
    AuthorizationRequest,
    ConsentStatus,
    DataSensitivity,
    DataVisibility,
    HouseholdFactShape,
    HouseholdSubject,
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

pytestmark = pytest.mark.unit

_REQUESTED_AT = datetime(2026, 10, 22, 12, tzinfo=UTC)
_CORRELATION_ID = UUID("44444444-4444-4444-4444-444444444444")
_OWNER_ID = 7
_OTHER_ID = 8

_PROPOSE = AuthorizationAction.PROPOSE_HOUSEHOLD_MEMORY
_CONFIRM = AuthorizationAction.CONFIRM_HOUSEHOLD_MEMORY
_PAIR = (_PROPOSE, _CONFIRM)

_LITERAL = HouseholdFactShape.LITERAL
_RELATION = HouseholdFactShape.RELATION
_OWNER = HouseholdSubject.OWNER
_CHILD = HouseholdSubject.CHILD
_PARTNER = HouseholdSubject.PARTNER
_PET = HouseholdSubject.PET
# Every classification a caller may send, including "not classified" (None).
_SUBJECTS_AND_NONE = [None, *HouseholdSubject]
_SHAPES_AND_NONE = [None, *HouseholdFactShape]

_HOUSEHOLD = frozenset({DataVisibility.HOUSEHOLD})
_PERSONAL = frozenset({DataVisibility.PERSONAL})
_NORMAL = frozenset({DataSensitivity.NORMAL})
_MEDICAL = frozenset({DataSensitivity.MEDICAL})
_ALL_CONSENTS = (
    ConsentStatus.NOT_REQUIRED,
    ConsentStatus.MISSING,
    ConsentStatus.REVOKED,
    ConsentStatus.GRANTED,
)

_ALLOWED = AuthorizationStatus.ALLOWED
_DENIED = AuthorizationStatus.DENIED
_ID_PREFIX = "cm3b.household-memory."
_ALLOWED_ID = f"{_ID_PREFIX}allowed"
_OWNER_ONLY_ID = f"{_ID_PREFIX}owner-only"
_SUBJECT_ID = f"{_ID_PREFIX}subject-not-allowed"
_ASSURANCE_ID = f"{_ID_PREFIX}assurance-required"
_GRANT_ID = f"{_ID_PREFIX}grant-scope"
_CONSENT_ID = f"{_ID_PREFIX}consent-required"
_UNRESOLVED_ID = "p0.5.identity-unresolved"
_GLOBAL_ASSURANCE_ID = "p0.5.assurance-required"
# Every policy id the pair may produce: its own closed outcomes plus the two generic gates.
_CLOSED_IDS = frozenset(
    {
        _ALLOWED_ID,
        _OWNER_ONLY_ID,
        _SUBJECT_ID,
        _ASSURANCE_ID,
        _GRANT_ID,
        _CONSENT_ID,
        _UNRESOLVED_ID,
        _GLOBAL_ASSURANCE_ID,
    }
)

# ADR 0022 decisions 3 and 4, restated: literals reach only the children and the pets (a partner
# literal waits for the `family` profile); relations also reach the partner; nobody may write
# the owner's own facts through the household pair.
_ALLOWED_SUBJECTS = {
    _LITERAL: frozenset({_CHILD, _PET}),
    _RELATION: frozenset({_CHILD, _PARTNER, _PET}),
}
_ALL_COMBINATIONS = list(product(HouseholdFactShape, HouseholdSubject))
# Categories that need granted consent even for the guardian; `child_data` is the guardian's own.
_CONSENT_CATEGORIES = frozenset({"biometric", "medical", "location"})
# Not covered by the pair at all (the repository refuses to store it until Step 0).
_UNCOVERED_CATEGORIES = frozenset({"security"})
_SENSITIVITY_VALUES = (
    "normal",
    "private",
    "biometric",
    "medical",
    "location",
    "child_data",
    "security",
)
_VISIBILITY_VALUES = ("public", "household", "adults", "personal", "private", "temporary")


def _subsets(values: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    """Return every non-empty subset of a literal value tuple, in a stable order."""
    return tuple(
        subset for size in range(1, len(values) + 1) for subset in combinations(values, size)
    )


_SENSITIVITY_SUBSETS = _subsets(_SENSITIVITY_VALUES)
_VISIBILITY_SUBSETS = _subsets(_VISIBILITY_VALUES)


def _evidence(
    source: IdentityEvidenceSource,
    evidence_id: str,
    *,
    person_id: int = _OWNER_ID,
    scope: str | None = None,
    spent: bool = False,
) -> IdentityEvidence:
    """Build one piece of identity evidence; a `local_unlock` item gets an expiry."""
    unlock = source is IdentityEvidenceSource.LOCAL_UNLOCK
    return IdentityEvidence(
        evidence_id=UUID(evidence_id),
        source=source,
        candidate_person_id=person_id,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False),
        observed_at=_REQUESTED_AT - timedelta(seconds=120),
        expires_at=_REQUESTED_AT + timedelta(seconds=60) if unlock else None,
        reference="canary-reference",
        grant_scope=scope,
        grant_spent=spent,
    )


def _face() -> IdentityEvidence:
    """The face of the owner on the turn."""
    return _evidence(IdentityEvidenceSource.FACE, "55555555-5555-5555-5555-555555555555")


def _voice() -> IdentityEvidence:
    """The verified voice of the same person on the same clip."""
    return _evidence(IdentityEvidenceSource.VOICE, "77777777-7777-7777-7777-777777777777")


def _pin(
    scope: str | None = None, *, spent: bool = True, person_id: int = _OWNER_ID
) -> IdentityEvidence:
    """The evidence an owner PIN grant leaves (spent or only peeked)."""
    return _evidence(
        IdentityEvidenceSource.LOCAL_UNLOCK,
        "66666666-6666-6666-6666-666666666666",
        person_id=person_id,
        scope=scope,
        spent=spent,
    )


def _actor(
    *,
    role: HouseholdRole = HouseholdRole.OWNER,
    assurance: IdentityAssurance = IdentityAssurance.STRONG,
    status: ActivePersonStatus = ActivePersonStatus.IDENTIFIED,
    person_id: int | None = _OWNER_ID,
    evidence: tuple[IdentityEvidence, ...] | None = None,
) -> ActivePersonContext:
    """Build one active person (no media, no database).

    Without an explicit `evidence`, a resolved actor carries a face and a voice, the evidence
    that yields `strong`; an unresolved one carries nothing.
    """
    if evidence is None:
        evidence = (_face(), _voice()) if person_id is not None else ()
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


def _face_only() -> ActivePersonContext:
    """The owner identified by a face alone (a photograph is enough): `basic`."""
    return _actor(assurance=IdentityAssurance.BASIC, evidence=(_face(),))


def _token_only(scope: str | None = None, *, spent: bool = True) -> ActivePersonContext:
    """The owner at `strong` through one PIN grant only (the bearer route)."""
    return _actor(assurance=IdentityAssurance.STRONG, evidence=(_pin(scope, spent=spent),))


def _decide(
    action: AuthorizationAction,
    *,
    actor: ActivePersonContext | None = None,
    subject: HouseholdSubject | None = _CHILD,
    shape: HouseholdFactShape | None = _LITERAL,
    visibility: frozenset[DataVisibility] = _HOUSEHOLD,
    sensitivity: frozenset[DataSensitivity] = _NORMAL,
    consent: ConsentStatus = ConsentStatus.NOT_REQUIRED,
    target: int | None = None,
) -> AuthorizationDecision:
    """Evaluate a well-formed household write unless a keyword overrides part of it."""
    return evaluate_authorization(
        AuthorizationRequest(
            actor=actor if actor is not None else _actor(),
            action=action,
            target_person_id=target,
            subject_relation=subject,
            fact_shape=shape,
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


def _visibility(values: tuple[str, ...]) -> frozenset[DataVisibility]:
    """Turn literal visibility values into the request's closed set."""
    return frozenset(DataVisibility(value) for value in values)


def _sensitivity(values: tuple[str, ...]) -> frozenset[DataSensitivity]:
    """Turn literal sensitivity values into the request's closed set."""
    return frozenset(DataSensitivity(value) for value in values)


# --- the vocabulary is closed --------------------------------------------------------------


def test_the_subject_and_shape_vocabularies_are_closed() -> None:
    assert [item.value for item in HouseholdSubject] == ["owner", "child", "partner", "pet"]
    assert [item.value for item in HouseholdFactShape] == ["literal", "relation"]
    assert [item.value for item in _PAIR] == [
        "propose_household_memory",
        "confirm_household_memory",
    ]


def test_the_request_defaults_to_no_classification_and_rejects_an_unknown_one() -> None:
    payload = {
        "actor": _actor(),
        "action": AuthorizationAction.READ_HOUSEHOLD_DATA,
        "visibility": _HOUSEHOLD,
        "sensitivity": _NORMAL,
        "consent": ConsentStatus.NOT_REQUIRED,
        "correlation_id": _CORRELATION_ID,
        "requested_at": _REQUESTED_AT,
    }

    plain = AuthorizationRequest.model_validate(payload)

    assert plain.subject_relation is None
    assert plain.fact_shape is None
    with pytest.raises(ValidationError):
        AuthorizationRequest.model_validate({**payload, "subject_relation": "friend"})
    with pytest.raises(ValidationError):
        AuthorizationRequest.model_validate({**payload, "fact_shape": "sentence"})


def test_the_pair_is_not_part_of_the_personal_memory_table() -> None:
    """A separate evaluation path: the table pinned by ADR 0019 does not list the pair."""
    assert not set(_PAIR) & set(PERSONAL_MEMORY_CAPABILITIES)


# --- the subject check (ADR 0022 decisions 3 and 4) ----------------------------------------


@pytest.mark.parametrize("action", _PAIR)
@pytest.mark.parametrize("shape, subject", _ALL_COMBINATIONS)
def test_the_pair_allows_exactly_the_subjects_of_decision_3(
    action: AuthorizationAction, shape: HouseholdFactShape, subject: HouseholdSubject
) -> None:
    """Strong owner, household data: allowed for the listed (shape, subject) pairs only."""
    decision = _decide(action, shape=shape, subject=subject)

    if subject in _ALLOWED_SUBJECTS[shape]:
        _assert_outcome(decision, _ALLOWED, _ALLOWED_ID)
    else:
        _assert_outcome(decision, _DENIED, _SUBJECT_ID)
    assert decision.action is action


@pytest.mark.parametrize("action", _PAIR)
def test_a_partner_literal_is_denied_while_a_partner_relation_is_allowed(
    action: AuthorizationAction,
) -> None:
    """ADR 0022 decision 4: for another adult only the name and the relationship are written."""
    _assert_outcome(_decide(action, shape=_LITERAL, subject=_PARTNER), _DENIED, _SUBJECT_ID)
    _assert_outcome(_decide(action, shape=_RELATION, subject=_PARTNER), _ALLOWED, _ALLOWED_ID)


@pytest.mark.parametrize("action", _PAIR)
@pytest.mark.parametrize("shape", [_LITERAL, _RELATION])
def test_the_owner_is_never_a_household_subject(
    action: AuthorizationAction, shape: HouseholdFactShape
) -> None:
    """The owner's own facts are `personal`; the household pair never writes them."""
    _assert_outcome(_decide(action, shape=shape, subject=_OWNER), _DENIED, _SUBJECT_ID)


@pytest.mark.parametrize("action", _PAIR)
@pytest.mark.parametrize(
    "subject, shape",
    [(None, _LITERAL), (None, _RELATION), (_CHILD, None), (_PET, None), (None, None)],
)
def test_an_unclassified_request_is_denied(
    action: AuthorizationAction,
    subject: HouseholdSubject | None,
    shape: HouseholdFactShape | None,
) -> None:
    """Both classifications are the caller's; a missing one is never guessed."""
    _assert_outcome(_decide(action, subject=subject, shape=shape), _DENIED, _SUBJECT_ID)


@pytest.mark.parametrize("action", _PAIR)
def test_only_household_visibility_is_reachable(action: AuthorizationAction) -> None:
    """All 63 visibility sets: allowed exactly for {household}; `personal` is never reachable."""
    for values in _VISIBILITY_SUBSETS:
        decision = _decide(action, visibility=_visibility(values))

        if values == ("household",):
            _assert_outcome(decision, _ALLOWED, _ALLOWED_ID)
        else:
            _assert_outcome(decision, _DENIED, _SUBJECT_ID)


@pytest.mark.parametrize("action", _PAIR)
def test_a_request_with_no_visibility_is_not_household_data(action: AuthorizationAction) -> None:
    """`AuthorizationRequest` forbids an empty set; the policy must not rely on that alone."""
    request = AuthorizationRequest.model_construct(
        actor=_actor(),
        action=action,
        target_person_id=None,
        subject_relation=_CHILD,
        fact_shape=_LITERAL,
        visibility=frozenset(),
        sensitivity=_NORMAL,
        consent=ConsentStatus.NOT_REQUIRED,
        correlation_id=_CORRELATION_ID,
        requested_at=_REQUESTED_AT,
    )

    _assert_outcome(evaluate_authorization(request), _DENIED, _SUBJECT_ID)


@pytest.mark.parametrize("action", _PAIR)
def test_the_target_person_plays_no_part(action: AuthorizationAction) -> None:
    """The subject is carried by the closed fields; comparing an id would be an oracle."""
    decisions = [_decide(action, target=target) for target in (None, _OWNER_ID, _OTHER_ID)]

    for decision in decisions:
        _assert_outcome(decision, _ALLOWED, _ALLOWED_ID)


# --- who may use the pair ------------------------------------------------------------------


@pytest.mark.parametrize("role", [HouseholdRole.ADULT, HouseholdRole.CHILD, HouseholdRole.GUEST])
@pytest.mark.parametrize("action", _PAIR)
def test_only_the_owner_may_use_the_pair_and_nobody_is_asked_to_confirm(
    action: AuthorizationAction, role: HouseholdRole
) -> None:
    """A visitor, another adult and a minor are denied, never `requires_confirmation`."""
    decision = _decide(action, actor=_actor(role=role), consent=ConsentStatus.GRANTED)

    _assert_outcome(decision, _DENIED, _OWNER_ONLY_ID)
    assert decision.decision is not AuthorizationStatus.REQUIRES_CONFIRMATION


@pytest.mark.parametrize("role", [HouseholdRole.ADULT, HouseholdRole.CHILD, HouseholdRole.GUEST])
@pytest.mark.parametrize("action", _PAIR)
def test_a_non_owner_learns_nothing_about_the_subject(
    action: AuthorizationAction, role: HouseholdRole
) -> None:
    """The role is judged before the subject: one answer for every classification and visibility."""
    answers = set()
    for subject, shape, visibility in product(
        _SUBJECTS_AND_NONE, _SHAPES_AND_NONE, (_HOUSEHOLD, _PERSONAL)
    ):
        decision = _decide(
            action, actor=_actor(role=role), subject=subject, shape=shape, visibility=visibility
        )
        answers.add((decision.decision, decision.policy_id, decision.reason))

    assert len(answers) == 1
    assert next(iter(answers))[:2] == (_DENIED, _OWNER_ONLY_ID)


@pytest.mark.parametrize("action", _PAIR)
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
    unknown_role = _actor(role=HouseholdRole.UNKNOWN)

    for actor in (probable, unknown, unknown_role):
        _assert_outcome(_decide(action, actor=actor), _DENIED, _UNRESOLVED_ID)


# --- assurance: face and voice of the same person ------------------------------------------


@pytest.mark.parametrize("action", _PAIR)
@pytest.mark.parametrize("assurance", [IdentityAssurance.NONE, IdentityAssurance.BASIC])
def test_below_strong_assurance_is_denied(
    action: AuthorizationAction, assurance: IdentityAssurance
) -> None:
    """A face alone (`basic`) is enough for a photograph; the pair needs the voice as well."""
    actor = _actor(assurance=assurance, evidence=(_face(),))

    _assert_outcome(_decide(action, actor=actor), _DENIED, _ASSURANCE_ID)


@pytest.mark.parametrize("action", _PAIR)
def test_the_owner_with_face_and_voice_is_allowed_and_with_a_face_alone_is_not(
    action: AuthorizationAction,
) -> None:
    both = _actor(assurance=IdentityAssurance.STRONG, evidence=(_face(), _voice()))

    _assert_outcome(_decide(action, actor=both), _ALLOWED, _ALLOWED_ID)
    _assert_outcome(_decide(action, actor=_face_only()), _DENIED, _ASSURANCE_ID)


@pytest.mark.parametrize("assurance", [IdentityAssurance.NONE, IdentityAssurance.BASIC])
@pytest.mark.parametrize("action", _PAIR)
def test_security_data_below_strong_is_stopped_by_the_existing_global_gate(
    action: AuthorizationAction, assurance: IdentityAssurance
) -> None:
    """The generic gate runs first, so it keeps its own id and runs before the owner rule."""
    security = frozenset({DataSensitivity.SECURITY})
    adult = _actor(role=HouseholdRole.ADULT, assurance=assurance, evidence=(_face(),))
    owner = _actor(assurance=assurance, evidence=(_face(),))

    for actor in (adult, owner):
        decision = _decide(action, actor=actor, sensitivity=security, consent=ConsentStatus.GRANTED)
        _assert_outcome(decision, _DENIED, _GLOBAL_ASSURANCE_ID)


# --- no PIN route --------------------------------------------------------------------------


@pytest.mark.parametrize("spent", [True, False])
@pytest.mark.parametrize(
    "scope",
    [
        "personal_protected_read",
        "biometric_admin",
        "personal_memory_read",
        "personal_memory_forget",
        None,
    ],
)
@pytest.mark.parametrize("action", _PAIR)
def test_a_token_holder_is_denied_whatever_the_scope_and_even_when_spent(
    action: AuthorizationAction, scope: str | None, spent: bool
) -> None:
    """The PIN makes the actor `strong` (the bearer route) but the pair has none."""
    actor = _token_only(scope, spent=spent)

    assert actor.assurance is IdentityAssurance.STRONG
    _assert_outcome(_decide(action, actor=actor), _DENIED, _GRANT_ID)


@pytest.mark.parametrize("action", _PAIR)
def test_a_token_beside_a_face_and_a_voice_still_denies(action: AuthorizationAction) -> None:
    """Any `local_unlock` item denies, even a spent one that names the owner."""
    for grant in (_pin("personal_memory_read"), _pin(None), _pin("anything", person_id=_OTHER_ID)):
        actor = _actor(evidence=(_face(), _voice(), grant))

        _assert_outcome(_decide(action, actor=actor), _DENIED, _GRANT_ID)


@pytest.mark.parametrize("action", _PAIR)
def test_a_manual_selection_is_not_a_pin_grant(action: AuthorizationAction) -> None:
    """Only `local_unlock` evidence trips the PIN rule; a manual item is ignored by it."""
    manual = _pin().model_copy(update={"source": IdentityEvidenceSource.MANUAL})
    actor = _actor(evidence=(_face(), _voice(), manual))

    _assert_outcome(_decide(action, actor=actor), _ALLOWED, _ALLOWED_ID)


# --- consent -------------------------------------------------------------------------------


def test_the_consent_categories_and_the_ordinary_ones_cover_every_sensitivity() -> None:
    """Adding a `DataSensitivity` member fails here until it is classified."""
    ordinary = {"normal", "private", "child_data"}

    classified = ordinary | _CONSENT_CATEGORIES | _UNCOVERED_CATEGORIES
    assert classified == {item.value for item in DataSensitivity}
    assert len(classified) == len(ordinary) + len(_CONSENT_CATEGORIES) + len(_UNCOVERED_CATEGORIES)


@pytest.mark.parametrize("action", _PAIR)
def test_consent_is_required_exactly_for_the_non_child_sensitive_categories(
    action: AuthorizationAction,
) -> None:
    """All 127 sensitivity sets x 4 consents: biometric/medical/location need it, security is out."""
    for values, consent in product(_SENSITIVITY_SUBSETS, _ALL_CONSENTS):
        decision = _decide(action, sensitivity=_sensitivity(values), consent=consent)

        needs_consent = bool(_CONSENT_CATEGORIES & set(values))
        if _UNCOVERED_CATEGORIES & set(values):
            _assert_outcome(decision, _DENIED, _SUBJECT_ID)
        elif needs_consent and consent is not ConsentStatus.GRANTED:
            _assert_outcome(decision, _DENIED, _CONSENT_ID)
        else:
            _assert_outcome(decision, _ALLOWED, _ALLOWED_ID)


@pytest.mark.parametrize("consent", _ALL_CONSENTS)
@pytest.mark.parametrize("action", _PAIR)
def test_consent_is_not_applied_to_normal_and_child_data(
    action: AuthorizationAction, consent: ConsentStatus
) -> None:
    """The guardian speaks for the child: `child_data` needs no separate consent."""
    for values in (("normal",), ("child_data",), ("normal", "child_data")):
        decision = _decide(action, sensitivity=_sensitivity(values), consent=consent)

        _assert_outcome(decision, _ALLOWED, _ALLOWED_ID)


@pytest.mark.parametrize("category", ["medical", "location", "biometric"])
@pytest.mark.parametrize("action", _PAIR)
def test_another_sensitive_category_needs_granted_consent(
    action: AuthorizationAction, category: str
) -> None:
    sensitivity = frozenset({DataSensitivity(category)})

    for consent in (ConsentStatus.NOT_REQUIRED, ConsentStatus.MISSING, ConsentStatus.REVOKED):
        denied = _decide(action, sensitivity=sensitivity, consent=consent)
        _assert_outcome(denied, _DENIED, _CONSENT_ID)
    granted = _decide(action, sensitivity=sensitivity, consent=ConsentStatus.GRANTED)
    _assert_outcome(granted, _ALLOWED, _ALLOWED_ID)


# --- evaluation order (ADR 0019 §5: owner, subject, assurance, grant, consent) --------------


def test_the_checks_run_in_the_fixed_order() -> None:
    missing = ConsentStatus.MISSING
    adult = _actor(role=HouseholdRole.ADULT)
    basic_with_a_token = _actor(assurance=IdentityAssurance.BASIC, evidence=(_pin("anything"),))

    owner_first = _decide(_PROPOSE, actor=adult, subject=_OWNER, shape=None)
    subject_before_assurance = _decide(_PROPOSE, actor=_face_only(), subject=_OWNER)
    assurance_before_grant = _decide(_PROPOSE, actor=basic_with_a_token)
    grant_before_consent = _decide(
        _PROPOSE, actor=_token_only("anything"), sensitivity=_MEDICAL, consent=missing
    )
    consent_last = _decide(_PROPOSE, sensitivity=_MEDICAL, consent=missing)

    _assert_outcome(owner_first, _DENIED, _OWNER_ONLY_ID)
    _assert_outcome(subject_before_assurance, _DENIED, _SUBJECT_ID)
    _assert_outcome(_decide(_PROPOSE, actor=_face_only()), _DENIED, _ASSURANCE_ID)
    _assert_outcome(assurance_before_grant, _DENIED, _ASSURANCE_ID)
    _assert_outcome(grant_before_consent, _DENIED, _GRANT_ID)
    _assert_outcome(consent_last, _DENIED, _CONSENT_ID)


# --- the whole grid, against an oracle written from the ADR ---------------------------------


def _grid_actors() -> list[tuple[str, ActivePersonContext]]:
    """Return 33 labelled actors: 15 by face and voice, 15 by one token, 3 not identified."""
    labelled: list[tuple[str, ActivePersonContext]] = []
    for role, assurance in product(HouseholdRole, IdentityAssurance):
        name = f"{role.value}-{assurance.value}"
        both = _actor(role=role, assurance=assurance, evidence=(_face(), _voice()))
        token = _actor(role=role, assurance=assurance, evidence=(_pin("personal_memory_read"),))
        labelled.extend([(f"{name}-face-voice", both), (f"{name}-token", token)])
    labelled.append(
        (
            "owner-probable",
            _actor(status=ActivePersonStatus.PROBABLE, assurance=IdentityAssurance.NONE),
        )
    )
    for status in (ActivePersonStatus.UNKNOWN, ActivePersonStatus.AMBIGUOUS):
        unresolved = _actor(
            role=HouseholdRole.UNKNOWN,
            status=status,
            assurance=IdentityAssurance.NONE,
            person_id=None,
        )
        labelled.append((f"unknown-{status.value}", unresolved))
    return labelled


def _is_allowed_by_the_adr(
    label: str,
    subject: HouseholdSubject | None,
    shape: HouseholdFactShape | None,
    visibility: frozenset[DataVisibility],
) -> bool:
    """State the rule: an identified owner at `strong` by face and voice, household data only."""
    return (
        label == "owner-strong-face-voice"
        and visibility == _HOUSEHOLD
        and subject is not None
        and shape is not None
        and subject in _ALLOWED_SUBJECTS[shape]
    )


@pytest.mark.parametrize("action", _PAIR)
def test_the_whole_grid_agrees_with_the_adr_and_never_asks_for_confirmation(
    action: AuthorizationAction,
) -> None:
    """33 actors x 5 subjects x 3 shapes x 3 visibility sets: only one actor is ever allowed."""
    actors = _grid_actors()
    assert len(actors) == 33
    mismatches = []
    for (label, actor), subject, shape, visibility in product(
        actors,
        _SUBJECTS_AND_NONE,
        _SHAPES_AND_NONE,
        (_HOUSEHOLD, _PERSONAL, _HOUSEHOLD | _PERSONAL),
    ):
        decision = _decide(action, actor=actor, subject=subject, shape=shape, visibility=visibility)
        want = _is_allowed_by_the_adr(label, subject, shape, visibility)
        if (
            (decision.decision is _ALLOWED) != want
            or decision.decision is AuthorizationStatus.REQUIRES_CONFIRMATION
            or decision.policy_id not in _CLOSED_IDS
        ):
            mismatches.append((label, subject, shape, visibility, decision.policy_id))

    assert not mismatches, mismatches[:3]


# --- decisions carry only safe labels ------------------------------------------------------


@pytest.mark.parametrize("action", _PAIR)
def test_decisions_carry_the_requested_action_and_only_safe_labels(
    action: AuthorizationAction,
) -> None:
    vocabulary = {item.value for item in DataVisibility} | {item.value for item in DataSensitivity}
    cases = [
        _decide(action),
        _decide(action, actor=_actor(role=HouseholdRole.GUEST)),
        _decide(action, subject=_OWNER),
        _decide(action, actor=_face_only()),
        _decide(action, actor=_token_only()),
        _decide(action, sensitivity=_MEDICAL),
    ]

    for decision in cases:
        assert decision.action is action
        assert decision.data_categories <= vocabulary
        assert "Ada" not in decision.reason
        assert not any(char.isdigit() for char in decision.reason)
    assert {decision.policy_id for decision in cases} == _CLOSED_IDS - {
        _UNRESOLVED_ID,
        _GLOBAL_ASSURANCE_ID,
    }


# --- the five personal capabilities are untouched -------------------------------------------

_READ = AuthorizationAction.READ_PERSONAL_CONVERSATION_MEMORY
_PROPOSE_PERSONAL = AuthorizationAction.PROPOSE_PERSONAL_MEMORY
_CONFIRM_PERSONAL = AuthorizationAction.CONFIRM_PERSONAL_MEMORY
_CORRECT = AuthorizationAction.CORRECT_PERSONAL_MEMORY
_FORGET = AuthorizationAction.FORGET_PERSONAL_MEMORY
_PERSONAL_ALLOWED = "cm1.personal-memory.allowed"
_PERSONAL_OWN_DATA = "cm1.personal-memory.own-data-only"
_PERSONAL_OWNER_ONLY = "cm1.personal-memory.owner-only"
_PERSONAL_ASSURANCE = "cm1.personal-memory.assurance-required"
_PERSONAL_GRANT = "cm1.personal-memory.grant-scope"


def _adult() -> ActivePersonContext:
    """An adult of the household at `strong`."""
    return _actor(role=HouseholdRole.ADULT)


# (action, actor factory, target, visibility, expected status, expected policy id): hard-coded
# from the decisions the five capabilities gave before the pair existed (ADR 0019).
type PersonalCase = tuple[
    AuthorizationAction,
    Callable[[], ActivePersonContext],
    int | None,
    frozenset[DataVisibility],
    AuthorizationStatus,
    str,
]
_PERSONAL_CASES: list[PersonalCase] = [
    (_READ, _face_only, _OWNER_ID, _PERSONAL, _ALLOWED, _PERSONAL_ALLOWED),
    (_PROPOSE_PERSONAL, _face_only, _OWNER_ID, _PERSONAL, _ALLOWED, _PERSONAL_ALLOWED),
    (_CORRECT, _face_only, _OWNER_ID, _PERSONAL, _ALLOWED, _PERSONAL_ALLOWED),
    (_CONFIRM_PERSONAL, _face_only, _OWNER_ID, _PERSONAL, _DENIED, _PERSONAL_ASSURANCE),
    (_CONFIRM_PERSONAL, _actor, _OWNER_ID, _PERSONAL, _ALLOWED, _PERSONAL_ALLOWED),
    (_FORGET, _actor, _OWNER_ID, _PERSONAL, _DENIED, _PERSONAL_GRANT),
    (_READ, _face_only, _OWNER_ID, _HOUSEHOLD, _DENIED, _PERSONAL_OWN_DATA),
    (_PROPOSE_PERSONAL, _actor, _OTHER_ID, _PERSONAL, _DENIED, _PERSONAL_OWN_DATA),
    (_PROPOSE_PERSONAL, _actor, None, _PERSONAL, _DENIED, _PERSONAL_OWN_DATA),
    (_CORRECT, _adult, _OWNER_ID, _PERSONAL, _DENIED, _PERSONAL_OWNER_ONLY),
]


@pytest.mark.parametrize(
    "subject, shape", [(None, None), (_CHILD, _LITERAL), (_PARTNER, _RELATION)]
)
@pytest.mark.parametrize(
    "action, make_actor, target, visibility, status, policy_id", _PERSONAL_CASES
)
def test_the_five_personal_capabilities_give_the_same_decisions_as_before(
    action: AuthorizationAction,
    make_actor: Callable[[], ActivePersonContext],
    target: int | None,
    visibility: frozenset[DataVisibility],
    status: AuthorizationStatus,
    policy_id: str,
    subject: HouseholdSubject | None,
    shape: HouseholdFactShape | None,
) -> None:
    """The new fields exist on the request but the personal capabilities never read them."""
    decision = _decide(
        action,
        actor=make_actor(),
        target=target,
        visibility=visibility,
        subject=subject,
        shape=shape,
    )

    _assert_outcome(decision, status, policy_id)


def test_a_spent_forget_grant_still_forgets_and_a_household_fact_is_still_not_personal() -> None:
    forgetting = _token_only("personal_memory_forget")

    allowed = _decide(_FORGET, actor=forgetting, target=_OWNER_ID, visibility=_PERSONAL)
    household = _decide(_PROPOSE_PERSONAL, target=_OWNER_ID, visibility=_HOUSEHOLD)

    _assert_outcome(allowed, _ALLOWED, _PERSONAL_ALLOWED)
    _assert_outcome(household, _DENIED, _PERSONAL_OWN_DATA)
