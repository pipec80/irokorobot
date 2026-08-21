"""Minimal local personal owner/children/PIN bootstrap orchestration.

Connects existing v4 entity, relation, owner-role, and credential
repositories into one confirmed, restart-safe setup for the ``personal``
profile. Each repository keeps its own transaction; this module does not
wrap them in a second outer transaction.
"""

import argparse
import asyncio
from collections.abc import Callable
import getpass
import logging
import sys
import unicodedata

from pydantic import BaseModel, ConfigDict, SecretStr

from server import db
from server.cognition.identity import HouseholdRole
from server.cognition.pin_credentials import hash_pin, verify_pin
from server.db import get_conn
from server.exceptions import BrainMemoryError
from server.memory.declarative import upsert_entity
from server.memory.entity_labels import get_person_label
from server.memory.household_authorization import bootstrap_initial_owner, get_active_role
from server.memory.meta import get_flag
from server.memory.owner_credentials import (
    get_active_owner_pin_credential,
    save_owner_pin_credential,
)
from server.memory.predicate_registry import PredicateDefinition, resolve_predicate
from server.memory.relational_v4 import assert_entity_relation, get_active_entity_relations

__all__ = [
    "PersonalSetupInput",
    "PersonalSetupResult",
    "PersonalSetupStatus",
    "apply_personal_setup",
    "main",
    "read_personal_setup_status",
    "run_personal_setup_wizard",
]

type ReadText = Callable[[str], str]
type ReadSecret = Callable[[str], str]
type WriteText = Callable[[str], None]

_CONFIRMATION_TOKEN = "SI"  # noqa: S105 — literal wizard confirmation word, not a secret

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


def _split_names(line: str) -> list[str]:
    """Split one free-text line into individual names by comma or whitespace."""
    parts = [part.strip() for part in line.replace(",", " ").split(" ")]
    return [part for part in parts if part]


async def run_personal_setup_wizard(
    *, read_text: ReadText, read_secret: ReadSecret, write_text: WriteText
) -> PersonalSetupResult | None:
    """Run the local confirm-before-write owner/children/PIN setup wizard.

    Prompts in order for the owner name, child names, and PIN, shows a
    redacted summary, and applies the setup only after an exact ``SI``
    confirmation. Never prints the PIN, its verifier, or any token.

    Args:
        read_text: Adapter that prompts for and returns one line of text.
        read_secret: Adapter that prompts for and returns one secret line.
        write_text: Adapter that writes one line of output.

    Returns:
        The applied setup result, or None if the wizard was cancelled.

    Raises:
        ValueError: If the confirmed input is rejected by `apply_personal_setup`.
    """
    owner_name = read_text("Owner name: ").strip()
    if not owner_name:
        write_text("Setup cancelled: owner name is required.")
        return None

    children_line = read_text("Child names (comma or space separated): ").strip()
    if not children_line:
        write_text("Setup cancelled: at least one child name is required.")
        return None
    child_names = tuple(_split_names(children_line))

    pin = read_secret("PIN (6-12 digits): ")
    pin_confirmation = read_secret("Confirm PIN: ")
    if pin != pin_confirmation:
        write_text("Setup cancelled: PIN confirmation did not match.")
        return None

    write_text(f"Owner: {owner_name}")
    write_text(f"Children: {', '.join(child_names)}")
    write_text("PIN: ******")
    confirmation = read_text(f"Type {_CONFIRMATION_TOKEN} to confirm: ")
    if confirmation != _CONFIRMATION_TOKEN:
        write_text("Setup cancelled.")
        return None

    result = await apply_personal_setup(
        PersonalSetupInput(owner_name=owner_name, child_names=child_names, pin=SecretStr(pin))
    )
    write_text(
        f"Setup complete. owner_entity_id={result.owner_entity_id} "
        f"child_entity_ids={result.child_entity_ids} "
        f"personal_security_ready={result.personal_security_ready}"
    )
    return result


class PersonalSetupStatus(BaseModel):
    """Non-secret aggregate status of the local personal setup."""

    model_config = ConfigDict(frozen=True)

    schema_version: int
    owner_count: int
    active_child_relation_count: int
    active_credential_count: int
    personal_security_ready: bool
    onboarding_complete: bool


async def read_personal_setup_status() -> PersonalSetupStatus:
    """Read only non-secret aggregate counts and derived readiness.

    Returns:
        Schema version, owner/child-relation/credential counts, derived
        `personal_security_ready`, and the separate legacy onboarding state.
    """
    conn = get_conn()
    version_cursor = await conn.execute("PRAGMA user_version")
    version_row = await version_cursor.fetchone()
    await version_cursor.close()
    schema_version = int(version_row[0]) if version_row else 0

    owner_cursor = await conn.execute(
        "SELECT COUNT(*) FROM household_role_assignments WHERE role = 'owner' AND revoked_at IS NULL"
    )
    owner_row = await owner_cursor.fetchone()
    await owner_cursor.close()
    owner_count = int(owner_row[0]) if owner_row else 0

    relation_cursor = await conn.execute(
        "SELECT COUNT(*) FROM entity_relations_v4 WHERE predicate = ? AND lifecycle = 'active'",
        (_CHILD_OF.canonical_id,),
    )
    relation_row = await relation_cursor.fetchone()
    await relation_cursor.close()
    active_child_relation_count = int(relation_row[0]) if relation_row else 0

    credential_cursor = await conn.execute(
        "SELECT COUNT(*) FROM owner_pin_credentials WHERE revoked_at IS NULL"
    )
    credential_row = await credential_cursor.fetchone()
    await credential_cursor.close()
    active_credential_count = int(credential_row[0]) if credential_row else 0

    onboarding_complete = await get_flag("onboarding_complete") is not None

    return PersonalSetupStatus(
        schema_version=schema_version,
        owner_count=owner_count,
        active_child_relation_count=active_child_relation_count,
        active_credential_count=active_credential_count,
        personal_security_ready=(
            owner_count == 1 and active_child_relation_count >= 1 and active_credential_count == 1
        ),
        onboarding_complete=onboarding_complete,
    )


def _print_status(status: PersonalSetupStatus, write_text: WriteText) -> None:
    """Print one status snapshot — non-secret aggregate values only."""
    write_text(f"schema_version={status.schema_version}")
    write_text(f"owner_count={status.owner_count}")
    write_text(f"active_child_relation_count={status.active_child_relation_count}")
    write_text(f"active_credential_count={status.active_credential_count}")
    write_text(f"personal_security_ready={status.personal_security_ready}")
    write_text(f"onboarding_complete={status.onboarding_complete}")


async def _preflight_lock_check() -> None:
    """Fail fast and clearly if another process holds the database lock.

    Raises:
        BrainMemoryError: If the database cannot be locked immediately.
    """
    conn = get_conn()
    try:
        await conn.execute("BEGIN IMMEDIATE")
        await conn.execute("ROLLBACK")
    except Exception as exc:
        raise BrainMemoryError(
            "Database is locked — stop `just run-server` and `just run-robot` first."
        ) from exc


async def _run(command: str | None) -> None:
    """Open the database, run the requested command, and always close it."""
    await db.open_db()
    try:
        await db.run_migrations()
        if command == "status":
            status = await read_personal_setup_status()
            _print_status(status, print)
            return
        await _preflight_lock_check()
        await run_personal_setup_wizard(
            read_text=input, read_secret=getpass.getpass, write_text=print
        )
    finally:
        await db.close_db()


def main() -> None:
    """CLI entrypoint for `personal-setup` — the setup wizard or `status`."""
    parser = argparse.ArgumentParser(description="Local personal owner/children/PIN setup.")
    parser.add_argument("command", nargs="?", choices=["status"], default=None)
    args = parser.parse_args()
    try:
        asyncio.run(_run(args.command))
    except BrainMemoryError as exc:
        print(str(exc))  # noqa: T201 — CLI adapter, not application logging
        sys.exit(1)
