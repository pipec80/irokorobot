"""Integration acceptance tests for the minimal personal owner setup service."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
import sys

from pydantic import SecretStr
import pytest
from server.cognition.identity import HouseholdRole
from server.cognition.pin_credentials import hash_pin, verify_pin
from server.exceptions import BrainMemoryError
from server.memory.declarative import upsert_entity
from server.memory.household_authorization import (
    bootstrap_initial_owner,
    get_active_role,
    revoke_active_role,
)
from server.memory.meta import get_flag
from server.memory.owner_credentials import (
    get_active_owner_pin_credential,
    save_owner_pin_credential,
)
from server.personal_setup import (
    PersonalSetupInput,
    apply_personal_setup,
    check_db_available,
    read_personal_setup_status,
    run_personal_setup_wizard,
)
from server.settings import settings

from server import db, personal_setup

_GUARD_TIMEOUT_S = 5.0


@pytest.fixture
async def setup_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Open a fresh temporary database with every migration applied."""
    db_path = tmp_path / "personal-setup.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield
    await db.close_db()
    db._conn = None


def _valid_input(*, pin: str = "482173") -> PersonalSetupInput:
    """Build the north-star confirmed setup input."""
    return PersonalSetupInput(
        owner_name="Pipec",
        child_names=("Joaquín", "Martina"),
        pin=SecretStr(pin),
    )


async def _entities_named(names: tuple[str, ...]) -> int:
    """Count entities whose name is exactly one of the given labels."""
    placeholders = ",".join("?" for _ in names)
    cursor = await db.get_conn().execute(
        f"SELECT COUNT(*) FROM entities WHERE type = 'person' AND name IN ({placeholders})",  # noqa: S608
        names,
    )
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    return int(row[0])


@pytest.mark.integration
async def test_setup_from_empty_database_establishes_owner_children_and_credential(
    setup_db: None,
) -> None:
    """The confirmed north-star input creates exactly the described household."""
    result = await apply_personal_setup(_valid_input())

    assert await get_active_role(result.owner_entity_id) is HouseholdRole.OWNER
    assert len(result.child_entity_ids) == 2

    credential = await get_active_owner_pin_credential()
    assert credential is not None
    assert credential.person_entity_id == result.owner_entity_id
    assert verify_pin("482173", credential.encoded) is True

    dump_cursor = await db.get_conn().execute("SELECT * FROM owner_pin_credentials")
    dump_rows = await dump_cursor.fetchall()
    await dump_cursor.close()
    for row in dump_rows:
        assert "482173" not in repr(tuple(row))

    assert result.personal_security_ready is True
    assert await get_flag("onboarding_complete") is None


@pytest.mark.integration
async def test_setup_rejects_duplicate_child_names_after_accent_folding(setup_db: None) -> None:
    """Case/accent-equivalent child names are rejected before any write."""
    with pytest.raises(ValueError, match="duplicate child name"):
        await apply_personal_setup(
            PersonalSetupInput(
                owner_name="Pipec",
                child_names=("Joaquín", "JOAQUIN"),
                pin=SecretStr("482173"),
            )
        )
    assert await _entities_named(("Pipec", "Joaquín", "JOAQUIN")) == 0


@pytest.mark.integration
async def test_setup_rejects_children_before_owner_confirmation(setup_db: None) -> None:
    """A mismatched active owner blocks the call before any child is written."""
    other_owner_id = await db.get_conn().execute(
        "INSERT INTO entities (name, type, attributes, aliases) VALUES ('Ada', 'person', '{}', '[]')"
    )
    ada_id = other_owner_id.lastrowid
    await other_owner_id.close()
    await db.get_conn().commit()
    assert ada_id is not None
    await bootstrap_initial_owner(
        person_entity_id=int(ada_id), confirmed_person_entity_id=int(ada_id)
    )

    with pytest.raises(ValueError, match="active owner"):
        await apply_personal_setup(_valid_input())

    assert await _entities_named(("Joaquín", "Martina")) == 0


@pytest.mark.integration
async def test_setup_rejects_a_second_active_owner(setup_db: None) -> None:
    """Rerunning with a different owner name never creates a second owner."""
    await apply_personal_setup(_valid_input())

    with pytest.raises(ValueError, match="active owner"):
        await apply_personal_setup(
            PersonalSetupInput(
                owner_name="Someone Else",
                child_names=("Joaquín", "Martina"),
                pin=SecretStr("482173"),
            )
        )


@pytest.mark.integration
async def test_same_pin_rerun_is_idempotent(setup_db: None) -> None:
    """Rerunning the exact same confirmed input converges without duplicates."""
    first = await apply_personal_setup(_valid_input())
    second = await apply_personal_setup(_valid_input())

    assert second.owner_entity_id == first.owner_entity_id
    assert set(second.child_entity_ids) == set(first.child_entity_ids)
    assert second.personal_security_ready is True

    credential_cursor = await db.get_conn().execute("SELECT COUNT(*) FROM owner_pin_credentials")
    credential_row = await credential_cursor.fetchone()
    await credential_cursor.close()
    assert credential_row is not None
    assert int(credential_row[0]) == 1

    role_cursor = await db.get_conn().execute("SELECT COUNT(*) FROM household_role_assignments")
    role_row = await role_cursor.fetchone()
    await role_cursor.close()
    assert role_row is not None
    assert int(role_row[0]) == 1


@pytest.mark.integration
async def test_different_confirmed_pin_rotates_one_active_credential(setup_db: None) -> None:
    """A genuinely new confirmed PIN rotates the credential without duplicating people."""
    first = await apply_personal_setup(_valid_input(pin="482173"))
    second = await apply_personal_setup(_valid_input(pin="999999"))

    assert second.owner_entity_id == first.owner_entity_id
    assert set(second.child_entity_ids) == set(first.child_entity_ids)

    credential = await get_active_owner_pin_credential()
    assert credential is not None
    assert verify_pin("999999", credential.encoded) is True
    assert verify_pin("482173", credential.encoded) is False

    total_cursor = await db.get_conn().execute("SELECT COUNT(*) FROM owner_pin_credentials")
    total_row = await total_cursor.fetchone()
    await total_cursor.close()
    assert total_row is not None
    assert int(total_row[0]) == 2


def _setup_names() -> tuple[str, ...]:
    """Every entity name the confirmed north-star input creates."""
    data = _valid_input()
    return (data.owner_name, *data.child_names)


@pytest.mark.integration
async def test_malformed_pin_is_rejected_before_any_write(setup_db: None) -> None:
    """A PIN that could never be stored is refused before a single entity exists."""
    with pytest.raises(ValueError, match="6 to 12 ASCII digits"):
        await apply_personal_setup(
            PersonalSetupInput(
                owner_name="Owner", child_names=("Ana", "Juan"), pin=SecretStr("bad")
            )
        )

    assert await _entities_named(("Owner", "Ana", "Juan")) == 0
    assert await get_active_owner_pin_credential() is None


@pytest.mark.integration
async def test_failure_after_the_children_is_safely_resumable(
    setup_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A storage failure after the entities are written converges on a rerun."""
    real_confirm_credential = personal_setup._confirm_credential

    async def failing(**_kwargs: object) -> None:
        raise BrainMemoryError("disk full")

    monkeypatch.setattr(personal_setup, "_confirm_credential", failing)
    with pytest.raises(BrainMemoryError, match="disk full"):
        await apply_personal_setup(_valid_input())

    assert await _entities_named(_setup_names()) == len(_setup_names())
    assert await get_active_owner_pin_credential() is None

    monkeypatch.setattr(personal_setup, "_confirm_credential", real_confirm_credential)
    result = await apply_personal_setup(_valid_input())

    assert await _entities_named(_setup_names()) == len(_setup_names())
    assert result.personal_security_ready is True
    role_cursor = await db.get_conn().execute("SELECT COUNT(*) FROM household_role_assignments")
    role_row = await role_cursor.fetchone()
    await role_cursor.close()
    assert role_row is not None
    assert int(role_row[0]) == 1


@pytest.mark.integration
async def test_setup_never_marks_extended_onboarding_complete(setup_db: None) -> None:
    """The minimal setup never touches the legacy onboarding completion flag."""
    await apply_personal_setup(_valid_input())
    assert await get_flag("onboarding_complete") is None


class _ScriptedIO:
    """Fake read/write adapters that replay scripted answers in call order."""

    def __init__(self, *, text_answers: list[str], secret_answers: list[str]) -> None:
        self._text_answers = list(text_answers)
        self._secret_answers = list(secret_answers)
        self.outputs: list[str] = []

    def read_text(self, prompt: str) -> str:
        del prompt
        return self._text_answers.pop(0)

    def read_secret(self, prompt: str) -> str:
        del prompt
        return self._secret_answers.pop(0)

    def write_text(self, line: str) -> None:
        self.outputs.append(line)


async def _child_relation_count() -> int:
    """Return the number of active child_of relations across the household."""
    cursor = await db.get_conn().execute(
        "SELECT COUNT(*) FROM entity_relations_v4 WHERE predicate = 'child_of' AND lifecycle = 'active'"
    )
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    return int(row[0])


@pytest.mark.integration
async def test_wizard_cancels_on_blank_owner_name(setup_db: None) -> None:
    """A blank first answer cancels before any write."""
    io = _ScriptedIO(text_answers=[""], secret_answers=[])

    result = await run_personal_setup_wizard(
        read_text=io.read_text, read_secret=io.read_secret, write_text=io.write_text
    )

    assert result is None
    assert await _entities_named(("Pipec",)) == 0


@pytest.mark.integration
@pytest.mark.parametrize("children_line", ["", " , , "])
async def test_wizard_accepts_an_owner_without_children(setup_db: None, children_line: str) -> None:
    """A blank children answer completes an owner + PIN setup with no children."""
    io = _ScriptedIO(
        text_answers=["Owner", children_line, "SI"],
        secret_answers=["482173", "482173"],
    )

    result = await run_personal_setup_wizard(
        read_text=io.read_text, read_secret=io.read_secret, write_text=io.write_text
    )

    assert result is not None
    assert result.child_entity_ids == ()
    assert result.personal_security_ready is True
    assert "Children: (none)" in io.outputs
    assert await _child_relation_count() == 0


@pytest.mark.integration
@pytest.mark.parametrize("children_line", ["Ana María, Juan", "Ana   María,  , Juan,"])
async def test_wizard_keeps_compound_names_and_splits_on_commas_only(
    setup_db: None, children_line: str
) -> None:
    """A compound name stays one child; only commas separate children."""
    io = _ScriptedIO(
        text_answers=["Owner", children_line, "SI"],
        secret_answers=["482173", "482173"],
    )

    result = await run_personal_setup_wizard(
        read_text=io.read_text, read_secret=io.read_secret, write_text=io.write_text
    )

    assert result is not None
    assert len(result.child_entity_ids) == 2
    assert await _entities_named(("Ana María", "Juan")) == 2
    assert "Children: Ana María, Juan" in io.outputs


@pytest.mark.integration
async def test_wizard_cancels_on_a_malformed_pin_before_any_write(setup_db: None) -> None:
    """A PIN outside the 6-12 digit rule cancels the wizard with no entity written."""
    io = _ScriptedIO(text_answers=["Owner", "Ana"], secret_answers=["abc", "abc"])

    result = await run_personal_setup_wizard(
        read_text=io.read_text, read_secret=io.read_secret, write_text=io.write_text
    )

    assert result is None
    assert any("6 to 12 ASCII digits" in line for line in io.outputs)
    assert "abc" not in " ".join(io.outputs)
    assert await _entities_named(("Owner", "Ana")) == 0


def test_the_cli_reports_a_rejected_submission_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A ValueError from the setup service exits 1 with its message, not a traceback."""

    async def rejected(_command: str | None) -> None:
        raise ValueError("child_names must not contain a duplicate child name")

    monkeypatch.setattr(personal_setup, "_run", rejected)
    monkeypatch.setattr(sys, "argv", ["personal-setup"])

    with pytest.raises(SystemExit) as caught:
        personal_setup.main()

    assert caught.value.code == 1
    assert "duplicate child name" in capsys.readouterr().out


@pytest.mark.integration
async def test_wizard_cancels_on_pin_mismatch(setup_db: None) -> None:
    """A mismatched PIN confirmation cancels before any write."""
    io = _ScriptedIO(
        text_answers=["Pipec", "Joaquín, Martina"],
        secret_answers=["482173", "482174"],
    )

    result = await run_personal_setup_wizard(
        read_text=io.read_text, read_secret=io.read_secret, write_text=io.write_text
    )

    assert result is None
    assert await _entities_named(("Pipec", "Joaquín", "Martina")) == 0


@pytest.mark.integration
async def test_wizard_cancels_on_non_si_confirmation(setup_db: None) -> None:
    """Any confirmation other than the literal SI cancels before any write."""
    io = _ScriptedIO(
        text_answers=["Pipec", "Joaquín, Martina", "yes"],
        secret_answers=["482173", "482173"],
    )

    result = await run_personal_setup_wizard(
        read_text=io.read_text, read_secret=io.read_secret, write_text=io.write_text
    )

    assert result is None
    assert await _entities_named(("Pipec", "Joaquín", "Martina")) == 0


@pytest.mark.integration
async def test_wizard_summary_redacts_pin_and_shows_only_names(setup_db: None) -> None:
    """The pre-confirmation summary never prints the PIN digits."""
    io = _ScriptedIO(
        text_answers=["Pipec", "Joaquín, Martina", "NO"],
        secret_answers=["482173", "482173"],
    )

    await run_personal_setup_wizard(
        read_text=io.read_text, read_secret=io.read_secret, write_text=io.write_text
    )

    joined = "\n".join(io.outputs)
    assert "Pipec" in joined
    assert "Joaquín" in joined
    assert "Martina" in joined
    assert "******" in joined
    assert "482173" not in joined


@pytest.mark.integration
async def test_wizard_success_applies_setup_and_never_prints_secret(setup_db: None) -> None:
    """A confirmed SI answer applies the setup and never echoes the PIN."""
    io = _ScriptedIO(
        text_answers=["Pipec", "Joaquín, Martina", "SI"],
        secret_answers=["482173", "482173"],
    )

    result = await run_personal_setup_wizard(
        read_text=io.read_text, read_secret=io.read_secret, write_text=io.write_text
    )

    assert result is not None
    assert result.personal_security_ready is True
    assert await _entities_named(("Pipec", "Joaquín", "Martina")) == 3
    assert await _child_relation_count() == 2

    joined = "\n".join(io.outputs)
    assert str(result.owner_entity_id) in joined
    assert "482173" not in joined


@pytest.mark.integration
async def test_check_db_available_passes_when_nothing_holds_the_lock(setup_db: None) -> None:
    """The happy path: no other transaction is open, so the probe is silent."""
    await check_db_available()  # must not raise


@pytest.mark.integration
async def test_check_db_available_raises_when_a_transaction_is_already_open(
    setup_db: None,
) -> None:
    """`check_db_available` is a deliberate exception to Plan 0036's ownership rule.

    It issues its own `BEGIN IMMEDIATE` + `ROLLBACK` directly, bypassing
    `db.transaction()`'s asyncio lock on purpose — it exists to fail fast on
    an *external* OS-level lock (another `just run-server` process), which a
    coroutine-level lock cannot detect. This test proves it still works
    correctly even against a transaction held by this same process.
    """
    holds_lock = asyncio.Event()
    may_release = asyncio.Event()

    async def hold_transaction() -> None:
        async with db.transaction() as conn:
            await conn.execute("INSERT INTO meta (key, value) VALUES ('probe', 'x')")
            holds_lock.set()
            await asyncio.wait_for(may_release.wait(), timeout=_GUARD_TIMEOUT_S)

    holder = asyncio.create_task(hold_transaction())
    await asyncio.wait_for(holds_lock.wait(), timeout=_GUARD_TIMEOUT_S)

    with pytest.raises(BrainMemoryError, match="locked"):
        await check_db_available()

    may_release.set()
    await asyncio.wait_for(holder, timeout=_GUARD_TIMEOUT_S)


@pytest.mark.integration
async def test_status_is_ready_after_a_confirmed_setup(setup_db: None) -> None:
    """The owner-scoped status agrees with a completed wizard setup."""
    await apply_personal_setup(_valid_input())

    status = await read_personal_setup_status()

    assert status.personal_security_ready is True


@pytest.mark.integration
async def test_status_is_ready_for_an_owner_without_children(setup_db: None) -> None:
    """Owner + PIN is a complete personal setup; children are optional."""
    owner = await upsert_entity(name="Owner", type="person")
    await bootstrap_initial_owner(person_entity_id=owner, confirmed_person_entity_id=owner)
    await save_owner_pin_credential(person_entity_id=owner, credential=hash_pin("482173"))

    status = await read_personal_setup_status()

    assert status.active_child_relation_count == 0
    assert status.personal_security_ready is True


@pytest.mark.integration
async def test_status_rejects_a_credential_belonging_to_another_person(setup_db: None) -> None:
    """One owner and one credential are insufficient when their person IDs differ."""
    result = await apply_personal_setup(_valid_input())
    other = await upsert_entity(name="Canary Other", type="person")
    # Deliberately seed an incoherent legacy row in the temporary test database.
    # The public credential writer correctly rejects a non-owner.
    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE owner_pin_credentials SET person_entity_id = ? WHERE person_entity_id = ?",
            (other, result.owner_entity_id),
        )

    status = await read_personal_setup_status()

    assert status.owner_count == 1
    assert status.active_credential_count == 1
    assert status.personal_security_ready is False


@pytest.mark.integration
async def test_revoking_the_owner_role_revokes_the_pin_credential(setup_db: None) -> None:
    """A person who is no longer the owner keeps no usable PIN credential."""
    result = await apply_personal_setup(_valid_input())

    await revoke_active_role(person_entity_id=result.owner_entity_id)

    assert await get_active_owner_pin_credential() is None


@pytest.mark.integration
async def test_status_is_not_ready_after_the_owner_role_moves(setup_db: None) -> None:
    """A successor owner without a credential is not a ready setup."""
    result = await apply_personal_setup(_valid_input())
    await revoke_active_role(person_entity_id=result.owner_entity_id)
    successor = await upsert_entity(name="Successor", type="person")
    await bootstrap_initial_owner(person_entity_id=successor, confirmed_person_entity_id=successor)

    status = await read_personal_setup_status()

    assert status.owner_count == 1
    assert status.active_credential_count == 0
    assert status.personal_security_ready is False
