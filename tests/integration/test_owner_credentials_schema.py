"""Integration tests for additive owner PIN credential storage."""

from pathlib import Path

import pytest
from server.memory.declarative import upsert_entity
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
