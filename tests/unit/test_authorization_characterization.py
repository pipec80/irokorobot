"""Characterization guard: the eleven pre-existing authorization actions never change.

Plan 0060 adds personal-memory actions to the policy. This file pins the exact decision of
every action that existed before, over a fixed grid, so a new action cannot shift an old one
by accident. The grid uses literal value tuples (never enum iteration): a new enum member
therefore cannot silently enter it, and a renamed or removed value fails loudly.

The expected digests and counts below were recorded at main 29cfbc0.
"""

from collections import Counter
from datetime import UTC, datetime
from functools import cache
from hashlib import sha256
from itertools import combinations, product
from uuid import UUID

import pytest
from server.cognition.authorization import (
    AuthorizationRequest,
    ConsentStatus,
    DataSensitivity,
    DataVisibility,
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
    Confidence,
    ConfidenceBasis,
)

pytestmark = pytest.mark.unit

_REQUESTED_AT = datetime(2026, 8, 12, 12, tzinfo=UTC)
_CORRELATION_ID = UUID("11111111-1111-1111-1111-111111111111")

_LEGACY_ACTIONS = (
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
)
_ROLES = ("owner", "adult", "child", "guest", "unknown")
_ASSURANCES = ("none", "basic", "strong")
_VISIBILITIES = ("public", "household", "adults", "personal", "private", "temporary")
_SENSITIVITIES = (
    "normal",
    "private",
    "biometric",
    "medical",
    "location",
    "child_data",
    "security",
)
_CONSENTS = ("not_required", "granted", "missing", "revoked")
_PERSON_ID = 7
_TARGETS = (None, 7, 8)
_PASS_B_ROLES = ("owner", "adult", "child")
_PASS_B_VISIBILITIES = (("personal",), ("household",))


def _subsets(values: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    """Return every non-empty subset of a literal value tuple, in a stable order."""
    return tuple(
        subset for size in range(1, len(values) + 1) for subset in combinations(values, size)
    )


def _actor(
    *,
    role: str,
    status: ActivePersonStatus,
    assurance: str,
    person_id: int | None,
) -> ActivePersonContext:
    """Build one pre-validated active person without media or database content."""
    return ActivePersonContext(
        person_id=person_id,
        display_name="Ada" if person_id is not None else None,
        status=status,
        confidence=Confidence(
            score=1.0 if person_id is not None else 0.0,
            basis=ConfidenceBasis.ASSERTED,
            calibrated=False,
        ),
        role=HouseholdRole(role),
        evidence=(),
        resolved_at=_REQUESTED_AT,
        assurance=IdentityAssurance(assurance),
    )


def _identified(role: str, assurance: str) -> ActivePersonContext:
    """Return an identified person 7 with one role and assurance."""
    return _actor(
        role=role,
        status=ActivePersonStatus.IDENTIFIED,
        assurance=assurance,
        person_id=_PERSON_ID,
    )


def _all_actors() -> tuple[ActivePersonContext, ...]:
    """Return the 18 actors of pass A: 15 identified, one probable owner, two unresolved."""
    identified = tuple(_identified(role, assurance) for role in _ROLES for assurance in _ASSURANCES)
    probable_owner = _actor(
        role="owner",
        status=ActivePersonStatus.PROBABLE,
        assurance="none",
        person_id=_PERSON_ID,
    )
    unknown = _actor(
        role="unknown", status=ActivePersonStatus.UNKNOWN, assurance="none", person_id=None
    )
    ambiguous = _actor(
        role="unknown", status=ActivePersonStatus.AMBIGUOUS, assurance="none", person_id=None
    )
    return (*identified, probable_owner, unknown, ambiguous)


def _line(
    action: str,
    actor: ActivePersonContext,
    target: int | None,
    visibility: tuple[str, ...],
    sensitivity: tuple[str, ...],
    consent: str,
) -> str:
    """Evaluate one case and render it as one canonical, value-only line."""
    request = AuthorizationRequest.model_construct(
        actor=actor,
        action=AuthorizationAction(action),
        target_person_id=target,
        visibility=frozenset(DataVisibility(item) for item in visibility),
        sensitivity=frozenset(DataSensitivity(item) for item in sensitivity),
        consent=ConsentStatus(consent),
        correlation_id=_CORRELATION_ID,
        requested_at=_REQUESTED_AT,
    )
    decision = evaluate_authorization(request)
    left = "|".join(
        (
            action,
            actor.role.value,
            actor.status.value,
            actor.assurance.value,
            str(target),
            ",".join(sorted(visibility)),
            ",".join(sorted(sensitivity)),
            consent,
        )
    )
    right = "|".join(
        (
            decision.decision.value,
            decision.policy_id,
            ",".join(sorted(decision.data_categories)),
            decision.reason,
        )
    )
    return f"{left} -> {right}"


def _grid_cases(action: str) -> tuple[str, ...]:
    """Return the canonical lines of both passes for one action."""
    visibilities = _subsets(_VISIBILITIES)
    sensitivities = _subsets(_SENSITIVITIES)
    normal = ("normal",)
    pass_a = (
        _line(action, actor, target, visibility, normal, "not_required")
        for actor, target, visibility in product(_all_actors(), _TARGETS, visibilities)
    )
    pass_b_actors = tuple(
        _identified(role, assurance) for role in _PASS_B_ROLES for assurance in _ASSURANCES
    )
    pass_b = (
        _line(action, actor, _PERSON_ID, visibility, sensitivity, consent)
        for actor, sensitivity, consent, visibility in product(
            pass_b_actors, sensitivities, _CONSENTS, _PASS_B_VISIBILITIES
        )
    )
    return (*pass_a, *pass_b)


@cache
def _characterize(action: str) -> tuple[str, dict[tuple[str, str], int], int]:
    """Return (digest, (decision, policy_id) counts, case count) for one action."""
    lines = _grid_cases(action)
    counts: Counter[tuple[str, str]] = Counter()
    for line in lines:
        outcome = line.split(" -> ", maxsplit=1)[1].split("|")
        counts[(outcome[0], outcome[1])] += 1
    digest = sha256("\n".join(lines).encode("utf-8")).hexdigest()
    return digest, dict(counts), len(lines)


# Recorded at main 29cfbc0.
_EXPECTED_DIGESTS: dict[str, str] = {
    "general_conversation": ("45ae2d0642f8fbfbeb5ea7a2f4cd1e1b5a5487a5ab01e97a5473d52f6461c638"),
    "read_household_data": ("dd378d2f1c75fa7ca09aca3a137fb09aa11d7f35f55ca5d8c9cea9f2b05523c6"),
    "execute_household_tool": ("0b9de2733707a882238b887d99624f5306c0e1394ad7de8b524925b15b9fa7f7"),
    "propose_memory": ("1a66187ddf8212a1f5a08bae175b8da2236cfb6e59b96564a62ac8acd9743743"),
    "commit_memory": ("56b0f98d4ae17bb5b5d7e68b266df3f752bf429ff193d950fc88253c18c3407a"),
    "manage_household_role": ("10e8e49deca66537dad7ebc4a05d2181a1e738eae9c16855449ced9ad90176eb"),
    "enroll_biometric": ("fea4b8d850f64302c906f7f7cdb727c2259ec2566c087c67f6c4b9b2bd234902"),
    "export_household_data": ("b585ee06d63c0f07d02b5ad38c97ce087ed8d17062870845dcbd55e8941ff6fe"),
    "delete_household_data": ("79addcdc97888ca7da9d5fa2957ef131eeffbf5a4e212760293987628a957557"),
    "consider_cloud_escalation": (
        "aa691a4c88c764ade6254529d2608753e7e44f12f1da59217512c58e9f44db30"
    ),
    "propose_physical_action": ("1c89aadbb5b591fc19f2fd63c4a44157f4140f9e25acbd811ae6b06384c4e4a7"),
}
_EXPECTED_COUNTS: dict[str, dict[tuple[str, str], int]] = {
    "general_conversation": {
        ("allowed", "p0.5.general-conversation"): 54,
        ("denied", "p0.5.general-conversation-unclassified"): 12492,
    },
    "read_household_data": {
        ("allowed", "p0.5.adult-household"): 45,
        ("allowed", "p0.5.household-public"): 18,
        ("allowed", "p0.5.own-normal-personal"): 48,
        ("allowed", "p0.5.owner-household"): 63,
        ("allowed", "p0.5.owner-sensitive-consent"): 488,
        ("denied", "p0.5.assurance-required"): 3072,
        ("denied", "p0.5.consent-required"): 4392,
        ("denied", "p0.5.identity-unresolved"): 1134,
        ("denied", "p0.5.protected-default-deny"): 2301,
        ("requires_confirmation", "p0.5.child-public-confirmation"): 9,
        ("requires_confirmation", "p0.5.sensitive-confirmation"): 976,
    },
    "execute_household_tool": {
        ("allowed", "p0.5.adult-household"): 45,
        ("allowed", "p0.5.household-public"): 18,
        ("allowed", "p0.5.own-normal-personal"): 48,
        ("allowed", "p0.5.owner-household"): 63,
        ("allowed", "p0.5.owner-sensitive-consent"): 488,
        ("denied", "p0.5.assurance-required"): 3072,
        ("denied", "p0.5.consent-required"): 4392,
        ("denied", "p0.5.identity-unresolved"): 1134,
        ("denied", "p0.5.protected-default-deny"): 2301,
        ("requires_confirmation", "p0.5.child-public-confirmation"): 9,
        ("requires_confirmation", "p0.5.sensitive-confirmation"): 976,
    },
    "propose_memory": {
        ("allowed", "p0.5.owner-memory-proposal"): 2591,
        ("denied", "p0.5.assurance-required"): 3072,
        ("denied", "p0.5.default-deny"): 567,
        ("denied", "p0.5.identity-unresolved"): 1134,
        ("requires_confirmation", "p0.5.memory-proposal-confirmation"): 5182,
    },
    "commit_memory": {
        ("allowed", "p0.5.owner-administration"): 2591,
        ("denied", "p0.5.assurance-required"): 3072,
        ("denied", "p0.5.default-deny"): 5749,
        ("denied", "p0.5.identity-unresolved"): 1134,
    },
    "manage_household_role": {
        ("allowed", "p0.5.owner-administration"): 2591,
        ("denied", "p0.5.assurance-required"): 3072,
        ("denied", "p0.5.default-deny"): 5749,
        ("denied", "p0.5.identity-unresolved"): 1134,
    },
    "enroll_biometric": {
        ("allowed", "p0.5.owner-consented-sensitive-action"): 506,
        ("denied", "p0.5.assurance-required"): 3072,
        ("denied", "p0.5.consent-required"): 2085,
        ("denied", "p0.5.default-deny"): 5749,
        ("denied", "p0.5.identity-unresolved"): 1134,
    },
    "export_household_data": {
        ("allowed", "p0.5.owner-administration"): 2591,
        ("denied", "p0.5.assurance-required"): 3072,
        ("denied", "p0.5.default-deny"): 5749,
        ("denied", "p0.5.identity-unresolved"): 1134,
    },
    "delete_household_data": {
        ("allowed", "p0.5.owner-administration"): 2591,
        ("denied", "p0.5.assurance-required"): 3072,
        ("denied", "p0.5.default-deny"): 5749,
        ("denied", "p0.5.identity-unresolved"): 1134,
    },
    "consider_cloud_escalation": {
        ("allowed", "p0.5.owner-consented-sensitive-action"): 506,
        ("denied", "p0.5.assurance-required"): 3072,
        ("denied", "p0.5.consent-required"): 2085,
        ("denied", "p0.5.default-deny"): 5749,
        ("denied", "p0.5.identity-unresolved"): 1134,
    },
    "propose_physical_action": {
        ("allowed", "p0.5.physical-action-proposal"): 5182,
        ("denied", "p0.5.assurance-required"): 3072,
        ("denied", "p0.5.default-deny"): 3158,
        ("denied", "p0.5.identity-unresolved"): 1134,
    },
}
_EXPECTED_GRID_SIZE = 138006


@pytest.mark.parametrize("action", _LEGACY_ACTIONS)
def test_legacy_action_decisions_are_unchanged(action: str) -> None:
    """Every decision, policy id, category set and reason of an old action is pinned."""
    digest, _, _ = _characterize(action)

    assert digest == _EXPECTED_DIGESTS[action]


@pytest.mark.parametrize("action", _LEGACY_ACTIONS)
def test_legacy_decision_counts_are_unchanged(action: str) -> None:
    """The (decision, policy id) histogram stays readable when the digest above fails."""
    _, counts, _ = _characterize(action)

    assert counts == _EXPECTED_COUNTS[action]


def test_characterization_grid_size_is_pinned() -> None:
    """A silently shrunken grid would weaken both pins above."""
    assert sum(_characterize(action)[2] for action in _LEGACY_ACTIONS) == _EXPECTED_GRID_SIZE
