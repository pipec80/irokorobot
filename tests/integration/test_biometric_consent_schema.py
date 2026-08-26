"""Integration tests for biometric consent grant/revoke storage (Plan 0029,
Task 1) — real temp DB, synthetic embedding, no face model involved (that
stays out of CI)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import numpy as np
import pytest
from server.memory.biometric_consent import (
    grant_face_consent,
    has_active_face_consent,
    revoke_face_consent,
)
from server.memory.declarative import upsert_entity
from server.settings import settings
from server.vision.faces import enroll_face

from server import db


@pytest.fixture
async def memory_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[misc]
    """Provide a clean temporary DB (runs all migrations) for each test."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)

    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield db_path
    await db.close_db()
    db._conn = None


def _unit_vector(axis: int) -> np.ndarray:
    """Return a 512-d unit vector along *axis* — a synthetic 'face'."""
    vec = np.zeros(512, dtype=np.float32)
    vec[axis] = 1.0
    return vec


async def _table_columns(table: str) -> set[str]:
    """Return the column names of one table in the open database."""
    cursor = await db.get_conn().execute(f"PRAGMA table_info({table})")
    rows = await cursor.fetchall()
    await cursor.close()
    return {str(row[1]) for row in rows}


async def _face_profile_count(entity_id: int) -> int:
    """Return how many face_profiles rows remain for *entity_id*."""
    cursor = await db.get_conn().execute(
        "SELECT COUNT(*) FROM face_profiles WHERE entity_id = ?", (entity_id,)
    )
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    return int(row[0])


async def _vec_faces_count_for_entity(entity_id: int) -> int:
    """Return how many vec_faces rows still pair with *entity_id*'s profiles."""
    cursor = await db.get_conn().execute(
        "SELECT COUNT(*) FROM vec_faces AS v "
        "JOIN face_profiles AS p ON p.id = v.rowid "
        "WHERE p.entity_id = ?",
        (entity_id,),
    )
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    return int(row[0])


@pytest.mark.integration
async def test_migration_seven_creates_face_consent_grants_table(memory_db: Path) -> None:
    """Migration 7 must create face_consent_grants with the expected columns."""
    conn = db.get_conn()
    version_cursor = await conn.execute("PRAGMA user_version")
    assert await version_cursor.fetchone() == (7,)
    await version_cursor.close()

    tables_cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    tables = {str(row[0]) for row in await tables_cursor.fetchall()}
    await tables_cursor.close()
    assert "face_consent_grants" in tables

    columns = await _table_columns("face_consent_grants")
    assert columns == {
        "id",
        "person_entity_id",
        "purpose",
        "granted_at",
        "revoked_at",
    }


@pytest.mark.integration
async def test_second_grant_for_same_person_is_idempotent(
    memory_db: Path,
) -> None:
    """Granting consent twice for the same person does not raise and reuses the row."""
    person_id = await upsert_entity(name="Pipec", type="person")

    first_grant_id = await grant_face_consent(person_id)
    second_grant_id = await grant_face_consent(person_id)

    assert first_grant_id == second_grant_id

    cursor = await db.get_conn().execute(
        "SELECT COUNT(*) FROM face_consent_grants WHERE person_entity_id = ?",
        (person_id,),
    )
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    assert row[0] == 1


@pytest.mark.integration
async def test_revoke_purges_face_profiles_and_vec_faces(memory_db: Path) -> None:
    """Revoking consent purges every face_profiles + vec_faces row for the person."""
    person_id = await upsert_entity(name="Pipec", type="person")
    await grant_face_consent(person_id)
    await enroll_face(person_id, _unit_vector(0), label="Pipec")

    assert await _face_profile_count(person_id) == 1
    assert await _vec_faces_count_for_entity(person_id) == 1

    await revoke_face_consent(person_id)

    assert await _face_profile_count(person_id) == 0
    assert await _vec_faces_count_for_entity(person_id) == 0


@pytest.mark.integration
async def test_revoke_is_idempotent_when_already_revoked_and_no_profiles(
    memory_db: Path,
) -> None:
    """Calling revoke a second time (already revoked, no profiles) does not raise."""
    person_id = await upsert_entity(name="Pipec", type="person")
    await grant_face_consent(person_id)
    await enroll_face(person_id, _unit_vector(0), label="Pipec")
    await revoke_face_consent(person_id)

    # Second call: no active grant, no face_profiles rows left.
    await revoke_face_consent(person_id)


@pytest.mark.integration
async def test_has_active_face_consent_reflects_grant_and_revoke(memory_db: Path) -> None:
    """has_active_face_consent is True right after grant, False after revoke."""
    person_id = await upsert_entity(name="Pipec", type="person")

    await grant_face_consent(person_id)
    assert await has_active_face_consent(person_id) is True

    await revoke_face_consent(person_id)
    assert await has_active_face_consent(person_id) is False


@pytest.mark.integration
async def test_has_active_face_consent_false_when_never_granted(memory_db: Path) -> None:
    """A person who was never granted consent has no active consent."""
    person_id = await upsert_entity(name="Stranger", type="person")

    assert await has_active_face_consent(person_id) is False
