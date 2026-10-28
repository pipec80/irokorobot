"""Migration 012 and the admin audit (Plan 0073 Task 1, ADR 0025 decision 4).

One audit row per mutating admin operation: actor, role, channel, operation, the field or section
id and the affected entity, outcome and time — never a value, a name or a phone. The table is
append-only and this module is the only place with SQL on it. Labels are canaries.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import TYPE_CHECKING

import pytest
from server.memory.admin_audit import (
    AdminActorRole,
    AdminAuditEntry,
    AdminOperationKind,
    AdminOutcomeStatus,
    TargetKind,
    list_admin_operations,
    record_admin_operation,
)
from server.memory.declarative import upsert_entity
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_NOW = "2026-10-27T10:00:00.000000+00:00"
_LATER = "2026-10-27T11:00:00.000000+00:00"
_LABEL = "Canary Admin"


@pytest.fixture
async def admin_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "admin-audit.db")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        yield
    finally:
        await db.close_db()
        db._conn = None


async def _scalar(sql: str, *params: object) -> object:
    cursor = await db.get_conn().execute(sql, params)
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    return row[0]


async def _tables() -> set[str]:
    cursor = await db.get_conn().execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    names = {str(row[0]) for row in await cursor.fetchall()}
    await cursor.close()
    return names


async def _record(
    *,
    actor_label: str = _LABEL,
    actor_role: AdminActorRole = AdminActorRole.BUILDER,
    operation: AdminOperationKind = AdminOperationKind.CHANGE,
    target_kind: TargetKind = TargetKind.POOL_LITERAL,
    field_id: str | None = "medication",
    target_entity_id: int | None = None,
    outcome: AdminOutcomeStatus = AdminOutcomeStatus.APPLIED,
    reason: str | None = None,
    recorded_at: str = _NOW,
) -> AdminAuditEntry:
    return await record_admin_operation(
        actor_label=actor_label,
        actor_role=actor_role,
        operation=operation,
        target_kind=target_kind,
        field_id=field_id,
        target_entity_id=target_entity_id,
        outcome=outcome,
        reason=reason,
        recorded_at=recorded_at,
    )


# --- the migration --------------------------------------------------------------------------------


async def test_migrations_reach_version_twelve_with_the_table(admin_db: None) -> None:
    assert await _scalar("PRAGMA user_version") == 12
    assert "admin_audit" in await _tables()


async def test_a_version_eleven_database_upgrades_without_losing_a_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "upgrade-v11.db")
    db._conn = None
    try:
        await db.open_db()
        full_list = db._MIGRATIONS
        monkeypatch.setattr(db, "_MIGRATIONS", tuple(m for m in full_list if m[0] <= 11))
        await db.run_migrations()
        owner = await upsert_entity(name="Canary Owner", type="person")
        assert "admin_audit" not in await _tables()

        monkeypatch.setattr(db, "_MIGRATIONS", full_list)
        await db.run_migrations()

        assert await _scalar("PRAGMA user_version") == 12
        assert "admin_audit" in await _tables()
        assert await _scalar("SELECT COUNT(*) FROM entities") == 1
        assert owner > 0
    finally:
        await db.close_db()
        db._conn = None


async def test_running_the_migrations_twice_changes_nothing(admin_db: None) -> None:
    await _record()
    await db.run_migrations()
    assert await _scalar("PRAGMA user_version") == 12
    assert await _scalar("SELECT COUNT(*) FROM admin_audit") == 1


# --- the repository -------------------------------------------------------------------------------


async def test_record_and_list_most_recent_first(admin_db: None) -> None:
    first = await _record(field_id="likes", recorded_at=_NOW)
    second = await _record(
        operation=AdminOperationKind.REVOKE, field_id="home_address", recorded_at=_LATER
    )
    rows = await list_admin_operations()
    assert [row.id for row in rows] == [second.id, first.id]
    assert rows[0].operation is AdminOperationKind.REVOKE
    assert rows[0].outcome is AdminOutcomeStatus.APPLIED


async def test_target_entity_id_is_set_null_when_the_entity_is_deleted(admin_db: None) -> None:
    owner = await upsert_entity(name="Canary Owner", type="person")
    await _record(target_entity_id=owner)
    await db.get_conn().execute("DELETE FROM entities WHERE id = ?", (owner,))
    await db.get_conn().commit()
    rows = await list_admin_operations()
    assert rows[0].target_entity_id is None


# --- every CHECK rejects a value outside its list (raw SQL: the last line of defence) -------------


@pytest.mark.parametrize(
    "column, bad",
    [
        ("actor_role", "stranger"),
        ("channel", "voice_classic"),
        ("operation", "edit"),
        ("target_kind", "secret"),
        ("outcome", "maybe"),
    ],
)
async def test_each_check_rejects_a_value_outside_its_list(
    admin_db: None, column: str, bad: str
) -> None:
    good: dict[str, object] = {
        "recorded_at": _NOW,
        "actor_label": _LABEL,
        "actor_role": "builder",
        "channel": "admin_local",
        "operation": "change",
        "target_kind": "pool_literal",
        "field_id": "medication",
        "outcome": "applied",
    }
    good[column] = bad
    names = ", ".join(good)
    marks = ", ".join("?" for _ in good)
    insert = f"INSERT INTO admin_audit ({names}) VALUES ({marks})"  # noqa: S608
    with pytest.raises(sqlite3.IntegrityError):
        await db.get_conn().execute(insert, tuple(good.values()))


@pytest.mark.parametrize("label", ["", "x" * 81, "Canary\x00Admin"])
async def test_a_bad_actor_label_is_refused(admin_db: None, label: str) -> None:
    with pytest.raises(ValueError):  # noqa: PT011
        await _record(actor_label=label)


async def test_no_value_or_label_reaches_a_log_or_the_repr(
    admin_db: None, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        entry = await _record(actor_label="Canary Secret Label")
    assert "Canary Secret Label" not in caplog.text
    assert "Canary Secret Label" not in repr(entry)
