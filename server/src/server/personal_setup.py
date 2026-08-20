"""Minimal local personal owner/children/PIN bootstrap orchestration.

Connects existing v4 entity, relation, owner-role, and credential
repositories into one confirmed, restart-safe setup for the ``personal``
profile. Each repository keeps its own transaction; this module does not
wrap them in a second outer transaction.
"""

import logging
import unicodedata

from pydantic import BaseModel, ConfigDict, SecretStr

from server.cognition.identity import HouseholdRole
from server.cognition.pin_credentials import hash_pin, verify_pin
from server.memory.declarative import upsert_entity
from server.memory.entity_labels import get_person_label
from server.memory.household_authorization import bootstrap_initial_owner, get_active_role
from server.memory.owner_credentials import (
    get_active_owner_pin_credential,
    save_owner_pin_credential,
)
from server.memory.predicate_registry import PredicateDefinition, resolve_predicate
from server.memory.relational_v4 import assert_entity_relation, get_active_entity_relations

__all__ = ["PersonalSetupInput", "PersonalSetupResult", "apply_personal_setup"]

logger = logging.getLogger(__name__)


def _required_predicate(alias: str) -> PredicateDefinition:
    """Resolve a registered predicate required by this closed setup flow."""
    definition = resolve_predicate(alias)
    if definition is None:
        raise RuntimeError(f"required predicate {alias!r} is not registered")
    return definition


_CHILD_OF = _required_predicate("child_of")


def _fold_name(name: str) -> str:
    """Fold a name to accent- and case-insensitive form for comparison."""
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


class PersonalSetupInput(BaseModel):
    """One immutable confirmed local setup submission."""

    model_config = ConfigDict(frozen=True)

    owner_name: str
    child_names: tuple[str, ...]
    pin: SecretStr


class PersonalSetupResult(BaseModel):
    """Result of one applied setup, with readiness derived by rereading."""

    model_config = ConfigDict(frozen=True)

    owner_entity_id: int
    child_entity_ids: tuple[int, ...]
    personal_security_ready: bool


def _validate_input(data: PersonalSetupInput) -> None:
    """Reject an incomplete or inconsistent submission before any write.

    Raises:
        ValueError: If the owner name is blank, no child name is given, a
            child name is blank, or two child names fold to the same name.
    """
    if not data.owner_name.strip():
        raise ValueError("owner_name must not be blank")
    if not data.child_names:
        raise ValueError("child_names must include at least one child")
    if any(not name.strip() for name in data.child_names):
        raise ValueError("child_names must not contain a blank name")

    folded_names = [_fold_name(name) for name in data.child_names]
    if len(set(folded_names)) != len(folded_names):
        raise ValueError("child_names must not contain a duplicate child name")


async def _confirm_owner_entity(owner_name: str) -> int:
    """Resolve or bootstrap the sole owner, requiring the same entity on rerun.

    Raises:
        ValueError: If a different entity already holds the active owner role.
    """
    owner_entity_id = await upsert_entity(name=owner_name, type="person")
    if await get_active_role(owner_entity_id) is HouseholdRole.OWNER:
        return owner_entity_id
    await bootstrap_initial_owner(
        person_entity_id=owner_entity_id, confirmed_person_entity_id=owner_entity_id
    )
    return owner_entity_id


async def _confirm_children(
    *, owner_entity_id: int, child_names: tuple[str, ...]
) -> tuple[int, ...]:
    """Create each child entity and its active child_of relation to the owner."""
    child_entity_ids: list[int] = []
    for child_name in child_names:
        child_id = await upsert_entity(name=child_name, type="person")
        await assert_entity_relation(
            source_entity_id=child_id,
            target_entity_id=owner_entity_id,
            definition=_CHILD_OF,
        )
        child_entity_ids.append(child_id)
    return tuple(child_entity_ids)


async def _confirm_credential(*, owner_entity_id: int, pin: SecretStr) -> None:
    """Reuse the active PIN credential when unchanged, else rotate it.

    Raises:
        ValueError: If the candidate PIN is not 6 to 12 ASCII digits.
    """
    active = await get_active_owner_pin_credential()
    candidate = pin.get_secret_value()
    if (
        active is not None
        and active.person_entity_id == owner_entity_id
        and verify_pin(candidate, active.encoded)
    ):
        return
    encoded = hash_pin(candidate)
    await save_owner_pin_credential(person_entity_id=owner_entity_id, credential=encoded)


async def _derive_readiness(*, owner_entity_id: int, child_names: tuple[str, ...]) -> bool:
    """Reread owner role, active child relations/labels, and credential.

    Returns:
        True only if the owner role, the exact confirmed child labels, and
        an active credential for this owner all independently verify.
    """
    if await get_active_role(owner_entity_id) is not HouseholdRole.OWNER:
        return False

    relations = await get_active_entity_relations(
        definition=_CHILD_OF, target_entity_id=owner_entity_id
    )
    expected_names = {_fold_name(name) for name in child_names}
    active_labels: set[str] = set()
    for relation in relations:
        label = await get_person_label(entity_id=relation.source_entity_id)
        if label is None:
            return False
        active_labels.add(_fold_name(label.display_name))
    if active_labels != expected_names:
        return False

    credential = await get_active_owner_pin_credential()
    return credential is not None and credential.person_entity_id == owner_entity_id


async def apply_personal_setup(data: PersonalSetupInput) -> PersonalSetupResult:
    """Apply one confirmed personal setup submission.

    Establishes the sole owner, confirmed active child relationships, and the
    active PIN credential. Idempotent: rerunning the same confirmed input
    converges without duplicating the owner, children, or credential.

    Args:
        data: The complete confirmed local setup submission.

    Returns:
        The resulting entity IDs and a readiness flag derived by rereading
        persisted state — never a stored shortcut.

    Raises:
        ValueError: If the input is invalid, a different owner is already
            active, or the candidate PIN is malformed.
    """
    _validate_input(data)
    owner_entity_id = await _confirm_owner_entity(data.owner_name)
    child_entity_ids = await _confirm_children(
        owner_entity_id=owner_entity_id, child_names=data.child_names
    )
    await _confirm_credential(owner_entity_id=owner_entity_id, pin=data.pin)

    ready = await _derive_readiness(owner_entity_id=owner_entity_id, child_names=data.child_names)
    return PersonalSetupResult(
        owner_entity_id=owner_entity_id,
        child_entity_ids=child_entity_ids,
        personal_security_ready=ready,
    )
