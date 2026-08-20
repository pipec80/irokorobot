"""Integration acceptance tests for the minimal personal owner setup service."""

from collections.abc import AsyncIterator
from pathlib import Path

from pydantic import SecretStr
import pytest
from server.cognition.identity import HouseholdRole
from server.cognition.pin_credentials import verify_pin
from server.memory.household_authorization import bootstrap_initial_owner, get_active_role
from server.memory.meta import get_flag
from server.memory.owner_credentials import get_active_owner_pin_credential
from server.personal_setup import PersonalSetupInput, apply_personal_setup
from server.settings import settings

from server import db


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
        child_names=("Máximo", "Dominga"),
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
                child_names=("Máximo", "MAXIMO"),
                pin=SecretStr("482173"),
            )
        )
    assert await _entities_named(("Pipec", "Máximo", "MAXIMO")) == 0


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

    assert await _entities_named(("Máximo", "Dominga")) == 0


@pytest.mark.integration
async def test_setup_rejects_a_second_active_owner(setup_db: None) -> None:
    """Rerunning with a different owner name never creates a second owner."""
    await apply_personal_setup(_valid_input())

    with pytest.raises(ValueError, match="active owner"):
        await apply_personal_setup(
            PersonalSetupInput(
                owner_name="Someone Else",
                child_names=("Máximo", "Dominga"),
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


@pytest.mark.integration
async def test_partial_failure_is_safely_resumable(setup_db: None) -> None:
    """An invalid PIN fails after entities are written; a valid rerun still converges."""
    with pytest.raises(ValueError, match="6 to 12 ASCII digits"):
        await apply_personal_setup(
            PersonalSetupInput(
                owner_name="Pipec",
                child_names=("Máximo", "Dominga"),
                pin=SecretStr("bad"),
            )
        )

    assert await _entities_named(("Pipec", "Máximo", "Dominga")) == 3
    assert await get_active_owner_pin_credential() is None

    result = await apply_personal_setup(_valid_input())

    assert await _entities_named(("Pipec", "Máximo", "Dominga")) == 3
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
