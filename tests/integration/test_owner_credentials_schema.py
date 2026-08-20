"""Integration tests for additive owner PIN credential storage."""

import logging
from pathlib import Path

import pytest
from server.cognition.pin_credentials import hash_pin, verify_pin
from server.memory.declarative import upsert_entity
from server.memory.household_authorization import bootstrap_initial_owner
from server.memory.owner_credentials import (
    get_active_owner_pin_credential,
    revoke_owner_pin_credential,
    save_owner_pin_credential,
)
from server.settings import settings

from server import db


@pytest.fixture
async def credentials_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[misc]
    """Open a fresh temporary database with migration 6 applied."""
    db_path = tmp_path / "owner-credentials.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield
    await db.close_db()
    db._conn = None


async def _table_columns(table: str) -> set[str]:
    """Return the column names of one table in the open database."""
    cursor = await db.get_conn().execute(f"PRAGMA table_info({table})")
    rows = await cursor.fetchall()
    await cursor.close()
    return {str(row[1]) for row in rows}


@pytest.mark.integration
async def test_migration_six_adds_owner_pin_credentials_table(credentials_db: None) -> None:
    """Migration 6 must be additive and expose the expected credential columns."""
    conn = db.get_conn()
    version_cursor = await conn.execute("PRAGMA user_version")
    assert await version_cursor.fetchone() == (6,)
    await version_cursor.close()

    tables_cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    tables = {str(row[0]) for row in await tables_cursor.fetchall()}
    await tables_cursor.close()
    assert "owner_pin_credentials" in tables

    columns = await _table_columns("owner_pin_credentials")
    assert columns == {
        "id",
        "person_entity_id",
        "algorithm",
        "parameters_json",
        "salt",
        "verifier",
        "created_at",
        "updated_at",
        "revoked_at",
    }

    foreign_key_cursor = await conn.execute("PRAGMA foreign_key_check")
    assert await foreign_key_cursor.fetchall() == []
    await foreign_key_cursor.close()


@pytest.mark.integration
async def test_foreign_keys_are_enabled(credentials_db: None) -> None:
    """The connection must enforce FK constraints for the new credential table."""
    cursor = await db.get_conn().execute("PRAGMA foreign_keys")
    row = await cursor.fetchone()
    await cursor.close()
    assert row == (1,)


async def _insert_credential(*, person_entity_id: int, salt: bytes, verifier: bytes) -> None:
    """Insert one raw credential row and commit it."""
    conn = db.get_conn()
    await conn.execute(
        "INSERT INTO owner_pin_credentials "
        "(person_entity_id, algorithm, parameters_json, salt, verifier) "
        "VALUES (?, 'scrypt', '{}', ?, ?)",
        (person_entity_id, salt, verifier),
    )
    await conn.commit()


@pytest.mark.integration
async def test_credential_requires_an_existing_entity(credentials_db: None) -> None:
    """A credential row cannot reference a missing entity."""
    with pytest.raises(Exception, match="FOREIGN KEY constraint failed"):
        await _insert_credential(person_entity_id=999999, salt=b"0" * 16, verifier=b"1" * 32)


@pytest.mark.integration
async def test_only_one_active_credential_per_owner(credentials_db: None) -> None:
    """The unique partial index rejects a second active credential for one owner."""
    person_id = await upsert_entity(name="Pipec", type="person")
    await _insert_credential(person_entity_id=person_id, salt=b"0" * 16, verifier=b"1" * 32)

    with pytest.raises(Exception, match="UNIQUE constraint failed"):
        await _insert_credential(person_entity_id=person_id, salt=b"2" * 16, verifier=b"3" * 32)


async def _credential_row_count() -> int:
    """Return the total credential row count, active and revoked."""
    cursor = await db.get_conn().execute("SELECT COUNT(*) FROM owner_pin_credentials")
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    return int(row[0])


async def _bootstrap_owner(name: str) -> int:
    """Create and bootstrap one owner entity for repository tests."""
    person_id = await upsert_entity(name=name, type="person")
    await bootstrap_initial_owner(person_entity_id=person_id, confirmed_person_entity_id=person_id)
    return person_id


@pytest.mark.integration
async def test_save_requires_an_active_owner_role(credentials_db: None) -> None:
    """Only a person with an active owner role may receive a PIN credential."""
    non_owner_id = await upsert_entity(name="Guest", type="person")
    with pytest.raises(ValueError, match="active owner role"):
        await save_owner_pin_credential(
            person_entity_id=non_owner_id, credential=hash_pin("482173")
        )


@pytest.mark.integration
async def test_save_then_read_preserves_bytes_and_parameters(credentials_db: None) -> None:
    """A saved credential round-trips its encoded fields exactly."""
    owner_id = await _bootstrap_owner("Pipec")
    encoded = hash_pin("482173")

    saved = await save_owner_pin_credential(person_entity_id=owner_id, credential=encoded)
    active = await get_active_owner_pin_credential()

    assert active is not None
    assert active.id == saved.id
    assert active.person_entity_id == owner_id
    assert active.encoded == encoded


@pytest.mark.integration
async def test_reusing_the_same_verified_pin_does_not_insert_a_row(credentials_db: None) -> None:
    """A caller that verifies a matching PIN must not call save again."""
    owner_id = await _bootstrap_owner("Pipec")
    initial = await save_owner_pin_credential(
        person_entity_id=owner_id, credential=hash_pin("482173")
    )

    active = await get_active_owner_pin_credential()
    assert active is not None
    assert verify_pin("482173", active.encoded) is True

    unchanged = await get_active_owner_pin_credential()
    assert unchanged is not None
    assert unchanged.id == initial.id
    assert await _credential_row_count() == 1


@pytest.mark.integration
async def test_rotating_to_a_different_pin_leaves_exactly_one_active_credential(
    credentials_db: None,
) -> None:
    """A genuinely different PIN atomically rotates the active credential."""
    owner_id = await _bootstrap_owner("Pipec")
    first = await save_owner_pin_credential(
        person_entity_id=owner_id, credential=hash_pin("482173")
    )

    second = await save_owner_pin_credential(
        person_entity_id=owner_id, credential=hash_pin("999999")
    )

    active = await get_active_owner_pin_credential()
    assert active is not None
    assert active.id == second.id
    assert active.id != first.id
    assert verify_pin("999999", active.encoded) is True
    assert await _credential_row_count() == 2

    revoked_cursor = await db.get_conn().execute(
        "SELECT revoked_at FROM owner_pin_credentials WHERE id = ?", (first.id,)
    )
    revoked_row = await revoked_cursor.fetchone()
    await revoked_cursor.close()
    assert revoked_row is not None
    assert revoked_row[0] is not None


@pytest.mark.integration
async def test_revoke_leaves_no_active_credential(credentials_db: None) -> None:
    """Revoking the active credential clears it without deleting history."""
    owner_id = await _bootstrap_owner("Pipec")
    await save_owner_pin_credential(person_entity_id=owner_id, credential=hash_pin("482173"))

    await revoke_owner_pin_credential(person_entity_id=owner_id)

    assert await get_active_owner_pin_credential() is None
    with pytest.raises(ValueError, match="no active owner PIN credential"):
        await revoke_owner_pin_credential(person_entity_id=owner_id)


@pytest.mark.integration
async def test_no_repository_log_contains_pin_salt_or_verifier(
    credentials_db: None, caplog: pytest.LogCaptureFixture
) -> None:
    """No repository log record may contain the PIN, salt, or verifier bytes."""
    owner_id = await _bootstrap_owner("Pipec")
    encoded = hash_pin("482173")

    with caplog.at_level(logging.DEBUG, logger="server.memory.owner_credentials"):
        await save_owner_pin_credential(person_entity_id=owner_id, credential=encoded)
        await get_active_owner_pin_credential()
        await revoke_owner_pin_credential(person_entity_id=owner_id)

    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert "482173" not in joined
    assert str(encoded.salt) not in joined
    assert str(encoded.verifier) not in joined
