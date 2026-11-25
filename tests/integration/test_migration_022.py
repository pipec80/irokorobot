"""Migration 022: the audit kind of an export of the household data (Plan 0087 Task 1, D-7).

``admin_audit`` is rebuilt, as migration 013 did, to accept the target kind ``household_data``;
every row, id and index of a database at version 21 survives it. Labels are canaries.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import sqlite3
from typing import TYPE_CHECKING

import pytest
from server.memory.admin_audit import (
    AdminActorRole,
    AdminOperationKind,
    AdminOutcomeStatus,
    TargetKind,
    record_admin_operation,
)
from server.memory.declarative import upsert_entity
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path

pytestmark = pytest.mark.integration

_NOW = "2026-11-19T10:00:00.000000+00:00"
_LABEL = "Canary Admin"
_COLUMNS = (
    "id, recorded_at, actor_label, actor_role, channel, operation, target_kind, field_id, "
    "target_entity_id, outcome, reason"
)
_INDEXES = {"admin_audit_recorded_at_idx", "admin_audit_target_entity_id_idx"}


@asynccontextmanager
async def _built_at(
    version: int, path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[tuple[db.Migration, ...]]:
    """A database built by the real migrations up to *version*; yields the full migration list."""
    monkeypatch.setattr(settings, "brain_db_path", path)
    db._conn = None
    try:
        await db.open_db()
        every_migration = db._MIGRATIONS
        monkeypatch.setattr(db, "_MIGRATIONS", tuple(m for m in every_migration if m[0] <= version))
        await db.run_migrations()
        yield every_migration
    finally:
        await db.close_db()
        db._conn = None


async def _rows(sql: str, *params: object) -> list[tuple[object, ...]]:
    cursor = await db.get_conn().execute(sql, params)
    rows = [tuple(row) for row in await cursor.fetchall()]
    await cursor.close()
    return rows


async def _insert_v21(target_kind: str, field_id: str, entity: int | None, outcome: str) -> None:
    await db.get_conn().execute(
        "INSERT INTO admin_audit (recorded_at, actor_label, actor_role, channel, operation, "
        "target_kind, field_id, target_entity_id, outcome, reason) "
        "VALUES (?, ?, 'owner', 'admin_local', 'export', ?, ?, ?, ?, ?)",
        (_NOW, _LABEL, target_kind, field_id, entity, outcome, None),
    )


async def _export_row(target_kind: str) -> None:
    await db.get_conn().execute(
        "INSERT INTO admin_audit (recorded_at, actor_label, actor_role, channel, operation, "
        "target_kind, field_id, target_entity_id, outcome, reason) "
        "VALUES (?, ?, 'owner', 'admin_local', 'export', ?, 'all', NULL, 'applied', NULL)",
        (_NOW, _LABEL, target_kind),
    )


async def test_migration_022_keeps_every_audit_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with _built_at(21, tmp_path / "v21.db", monkeypatch) as every_migration:
        owner = await upsert_entity(name="Canary Owner", type="person")
        await _insert_v21("conversation_record", "3", owner, "applied")
        await _insert_v21("pool_literal", "medication", None, "refused")
        await _insert_v21("care_contact", "doctor", owner, "applied")
        await db.get_conn().commit()
        before = await _rows(f"SELECT {_COLUMNS} FROM admin_audit ORDER BY id")  # noqa: S608
        with pytest.raises(sqlite3.IntegrityError):
            await _export_row("household_data")
        await db.get_conn().rollback()

        monkeypatch.setattr(db, "_MIGRATIONS", tuple(m for m in every_migration if m[0] <= 22))
        await db.run_migrations()

        assert await _rows("PRAGMA user_version") == [(22,)]
        assert await _rows(f"SELECT {_COLUMNS} FROM admin_audit ORDER BY id") == before  # noqa: S608
        indexes = await _rows(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'admin_audit'"
        )
        assert {str(name) for (name,) in indexes} >= _INDEXES
        assert await _rows("PRAGMA foreign_key_check") == []
        entry = await record_admin_operation(
            actor_label=_LABEL,
            actor_role=AdminActorRole.OWNER,
            operation=AdminOperationKind.EXPORT,
            target_kind=TargetKind.HOUSEHOLD_DATA,
            field_id="all",
            target_entity_id=None,
            outcome=AdminOutcomeStatus.APPLIED,
            reason=None,
            recorded_at=_NOW,
        )
        assert entry.id > max(int(str(row[0])) for row in before)


async def test_022_accepts_an_export_and_still_refuses_an_unknown_kind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with _built_at(22, tmp_path / "v22.db", monkeypatch):
        entry = await record_admin_operation(
            actor_label=_LABEL,
            actor_role=AdminActorRole.OWNER,
            operation=AdminOperationKind.EXPORT,
            target_kind=TargetKind.HOUSEHOLD_DATA,
            field_id="person:7",
            target_entity_id=None,
            outcome=AdminOutcomeStatus.REFUSED,
            reason="pin",
            recorded_at=_NOW,
        )
        assert entry.target_kind is TargetKind.HOUSEHOLD_DATA
        with pytest.raises(sqlite3.IntegrityError):
            await _export_row("household_secrets")
