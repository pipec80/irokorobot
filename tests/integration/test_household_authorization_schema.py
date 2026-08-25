"""Integration tests for additive household authorization storage."""

from datetime import datetime
from pathlib import Path

import pytest
from server.cognition.identity import HouseholdRole
from server.memory.declarative import assert_fact, upsert_entity
from server.memory.household_authorization import (
    assign_household_role,
    bootstrap_initial_owner,
    get_active_role,
    revoke_active_role,
)
from server.settings import settings

from server import db


@pytest.fixture
async def authorization_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[misc]
    """Open a fresh temporary database with migration 5 applied."""
    db_path = tmp_path / "household-authorization.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield
    await db.close_db()
    db._conn = None


async def _audit_count() -> int:
    """Return the number of append-only authorization audit rows."""
    cursor = await db.get_conn().execute("SELECT COUNT(*) FROM authorization_audit_events")
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    return int(row[0])


@pytest.mark.integration
async def test_migration_five_adds_role_and_safe_audit_tables(authorization_db: None) -> None:
    """Authorization storage must be additive and keep legacy/v4 data intact."""
    conn = db.get_conn()
    version_cursor = await conn.execute("PRAGMA user_version")
    assert await version_cursor.fetchone() == (7,)
    await version_cursor.close()

    tables_cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    tables = {str(row[0]) for row in await tables_cursor.fetchall()}
    await tables_cursor.close()
    assert {"household_role_assignments", "authorization_audit_events"} <= tables

    columns_cursor = await conn.execute("PRAGMA table_info(authorization_audit_events)")
    columns = {str(row[1]) for row in await columns_cursor.fetchall()}
    await columns_cursor.close()
    assert {"prompt", "message", "response", "raw_audio", "raw_image", "embedding"}.isdisjoint(
        columns
    )

    person_id = await upsert_entity(name="Ada", type="person")
    await assert_fact(entity_id=person_id, predicate="alias", object_value="A")
    legacy_cursor = await conn.execute("SELECT COUNT(*) FROM facts")
    legacy_before = await legacy_cursor.fetchone()
    await legacy_cursor.close()

    await bootstrap_initial_owner(person_entity_id=person_id, confirmed_person_entity_id=person_id)

    audit_cursor = await conn.execute("SELECT evaluated_at FROM authorization_audit_events")
    audit_row = await audit_cursor.fetchone()
    await audit_cursor.close()
    assert audit_row is not None
    assert datetime.fromisoformat(str(audit_row[0])).tzinfo is not None

    legacy_after_cursor = await conn.execute("SELECT COUNT(*) FROM facts")
    assert await legacy_after_cursor.fetchone() == legacy_before
    await legacy_after_cursor.close()
    foreign_key_cursor = await conn.execute("PRAGMA foreign_key_check")
    assert await foreign_key_cursor.fetchall() == []
    await foreign_key_cursor.close()


@pytest.mark.integration
async def test_initial_owner_bootstrap_requires_matching_person_and_is_singleton(
    authorization_db: None,
) -> None:
    """A local operator cannot bootstrap a name, non-person, or second owner."""
    ada_id = await upsert_entity(name="Ada", type="person")
    beau_id = await upsert_entity(name="Beau", type="person")
    kitchen_id = await upsert_entity(name="Kitchen", type="place")

    with pytest.raises(ValueError, match="matching confirmation"):
        await bootstrap_initial_owner(person_entity_id=ada_id, confirmed_person_entity_id=beau_id)
    with pytest.raises(ValueError, match="must be a person"):
        await bootstrap_initial_owner(
            person_entity_id=kitchen_id,
            confirmed_person_entity_id=kitchen_id,
        )
    assert await _audit_count() == 0

    assignment = await bootstrap_initial_owner(
        person_entity_id=ada_id,
        confirmed_person_entity_id=ada_id,
    )

    assert assignment.role is HouseholdRole.OWNER
    assert await get_active_role(ada_id) is HouseholdRole.OWNER
    assert await _audit_count() == 1

    with pytest.raises(ValueError, match="active owner"):
        await bootstrap_initial_owner(person_entity_id=beau_id, confirmed_person_entity_id=beau_id)
    assert await get_active_role(beau_id) is HouseholdRole.UNKNOWN
    assert await _audit_count() == 1


@pytest.mark.integration
async def test_role_revocation_preserves_assignment_history(authorization_db: None) -> None:
    """Logical rollback revokes a role without removing its assignment record."""
    ada_id = await upsert_entity(name="Ada", type="person")
    await bootstrap_initial_owner(person_entity_id=ada_id, confirmed_person_entity_id=ada_id)

    await revoke_active_role(person_entity_id=ada_id)

    assert await get_active_role(ada_id) is HouseholdRole.UNKNOWN
    cursor = await db.get_conn().execute(
        "SELECT role, revoked_at FROM household_role_assignments WHERE person_entity_id = ?",
        (ada_id,),
    )
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    assert row[0] == HouseholdRole.OWNER.value
    assert row[1] is not None


@pytest.mark.integration
async def test_internal_role_assignment_requires_an_active_owner(
    authorization_db: None,
) -> None:
    """Only the local household role repository may create non-owner roles."""
    ada_id = await upsert_entity(name="Ada", type="person")
    beau_id = await upsert_entity(name="Beau", type="person")

    with pytest.raises(ValueError, match="active owner"):
        await assign_household_role(
            person_entity_id=beau_id,
            role=HouseholdRole.ADULT,
            grantor_entity_id=ada_id,
        )

    await bootstrap_initial_owner(person_entity_id=ada_id, confirmed_person_entity_id=ada_id)
    assignment = await assign_household_role(
        person_entity_id=beau_id,
        role=HouseholdRole.ADULT,
        grantor_entity_id=ada_id,
    )

    assert assignment.role is HouseholdRole.ADULT
    assert assignment.grantor_entity_id == ada_id
    assert await get_active_role(beau_id) is HouseholdRole.ADULT
