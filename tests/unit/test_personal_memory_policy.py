"""Unit tests for the personal-memory capabilities of the authorization policy (ADR 0019)."""

from typing import TYPE_CHECKING, cast

import pytest
from server.cognition import authorization
from server.cognition.authorization import (
    ASSURANCE_RANK,
    HIGH_ASSURANCE_CATEGORIES,
    PERSONAL_MEMORY_CAPABILITIES,
    PERSONAL_MEMORY_STRONG_CATEGORIES,
    DataSensitivity,
    DataVisibility,
    PersonalMemoryCapability,
)
from server.cognition.identity import IdentityAssurance
from server.cognition.models import AuthorizationAction

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
