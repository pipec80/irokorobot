"""Migration 023: the documents' tables, their indexes and the audit kinds (Plan 0088 Task B1, D-8).

Canary rows only.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import sqlite3
import struct
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
    from collections.abc import AsyncGenerator, AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_NOW = "2026-11-23T10:00:00.000000+00:00"
_SHA = "a" * 64
_DIM = 768


@asynccontextmanager
async def _built_at(
    version: int, path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[tuple[db.Migration, ...]]:
    """A database built by the real migrations up to *version*; yields the full list."""
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


@pytest.fixture
async def owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    async with _built_at(23, tmp_path / "docs.db", monkeypatch):
        yield await upsert_entity(name="Canary Owner", type="person")


async def _scalar(sql: str, *params: object) -> object:
    cursor = await db.get_conn().execute(sql, params)
    row = await cursor.fetchone()
    await cursor.close()
    return None if row is None else row[0]


async def _source(
    owner: int,
    *,
    sha: str = _SHA,
    loader: int | None = None,
    values: dict[str, object] | None = None,
) -> int:
    row = {
        "title": "Manual canario",
        "format": "md",
        "level": "normal",
        "channel": "admin_local",
        "loaded_at": _NOW,
        "sections": 1,
        "characters": 10,
    } | (values or {})
    cursor = await db.get_conn().execute(
        "INSERT INTO document_sources (owner_entity_id, title, file_sha256, format, level, "
        "channel, loaded_at, loaded_by_entity_id, sections, characters) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            owner,
            row["title"],
            sha,
            row["format"],
            row["level"],
            row["channel"],
            row["loaded_at"],
            loader,
            row["sections"],
            row["characters"],
        ),
    )
    source_id = int(cursor.lastrowid or 0)
    await cursor.close()
    return source_id


async def _section(source: int, position: int, body: str) -> int:
    cursor = await db.get_conn().execute(
        "INSERT INTO document_sections (source_id, position, heading, body, body_sha256) "
        "VALUES (?, ?, '', ?, ?)",
        (source, position, body, _SHA),
    )
    section_id = int(cursor.lastrowid or 0)
    await cursor.close()
    return section_id


async def _vector(section: int, owner: int, level: str, source: int) -> None:
    await db.get_conn().execute(
        "INSERT INTO document_sections_vec (rowid, owner_entity_id, level, source_id, embedding) "
        "VALUES (?, ?, ?, ?, ?)",
        (section, owner, level, source, struct.pack(f"{_DIM}f", *([1.0] + [0.0] * (_DIM - 1)))),
    )


async def test_the_schema_is_at_version_23(owner: int) -> None:
    assert await _scalar("PRAGMA user_version") == 23
    assert db.latest_schema_version() == 23


@pytest.mark.parametrize(
    "column, value",
    [
        ("title", ""),
        ("title", "x" * 121),
        ("format", "docx"),
        ("level", "security"),
        ("channel", "voice"),
        ("loaded_at", "2026-11-23"),
        ("sections", -1),
    ],
)
async def test_a_source_outside_its_checks_is_refused(
    owner: int, column: str, value: object
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        await _source(owner, values={column: value})


async def test_the_same_file_twice_for_one_owner_is_refused(owner: int) -> None:
    other = await upsert_entity(name="Canary Other", type="person")
    await _source(owner)
    await _source(other)
    with pytest.raises(sqlite3.IntegrityError):
        await _source(owner)


async def test_a_section_body_is_bounded_and_immutable(owner: int) -> None:
    source = await _source(owner)
    with pytest.raises(sqlite3.IntegrityError):
        await _section(source, 0, "")
    with pytest.raises(sqlite3.IntegrityError):
        await _section(source, 0, "x" * 1201)
    section = await _section(source, 0, "zzcanaryzz filtro")
    with pytest.raises(sqlite3.IntegrityError):
        await _section(source, 0, "another body at the same position")
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        await db.get_conn().execute(
            "UPDATE document_sections SET body = 'changed' WHERE id = ?", (section,)
        )


async def test_deleting_a_source_removes_its_sections_words_and_vectors(owner: int) -> None:
    source = await _source(owner)
    section = await _section(source, 0, "zzcanaryzz filtro")
    await _vector(section, owner, "normal", source)
    assert (
        await _scalar(
            "SELECT COUNT(*) FROM document_sections_fts WHERE document_sections_fts MATCH 'zzcanaryzz'"
        )
        == 1
    )

    await db.get_conn().execute("DELETE FROM document_sources WHERE id = ?", (source,))

    assert await _scalar("SELECT COUNT(*) FROM document_sections") == 0
    assert await _scalar("SELECT COUNT(*) FROM document_sections_fts_docsize") == 0
    assert await _scalar("SELECT COUNT(*) FROM document_sections_vec") == 0


async def test_deleting_the_loader_keeps_the_source(owner: int) -> None:
    loader = await upsert_entity(name="Canary Builder", type="person")
    source = await _source(owner, loader=loader)
    await db.get_conn().execute("DELETE FROM entities WHERE id = ?", (loader,))
    assert (
        await _scalar(
            "SELECT loaded_by_entity_id IS NULL FROM document_sources WHERE id = ?", source
        )
        == 1
    )


async def test_the_level_and_source_filters_hold_inside_the_knn(owner: int) -> None:
    first = await _source(owner, sha="1" * 64)
    second = await _source(owner, sha="2" * 64, values={"level": "sensitive"})
    near_first = await _section(first, 0, "uno")
    near_second = await _section(second, 0, "dos")
    await _vector(near_first, owner, "normal", first)
    await _vector(near_second, owner, "sensitive", second)
    query = struct.pack(f"{_DIM}f", *([1.0] + [0.0] * (_DIM - 1)))

    cursor = await db.get_conn().execute(
        "SELECT rowid FROM document_sections_vec WHERE embedding MATCH ? AND k = 5 "
        "AND owner_entity_id = ? AND level IN ('normal') AND source_id IN (?, ?)",
        (query, owner, first, second),
    )
    rows = [int(row[0]) for row in await cursor.fetchall()]
    await cursor.close()

    assert rows == [near_first]


async def test_migration_023_keeps_the_audit_and_accepts_a_document_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with _built_at(22, tmp_path / "v22.db", monkeypatch) as every_migration:
        await db.get_conn().execute(
            "INSERT INTO admin_audit (recorded_at, actor_label, actor_role, channel, operation, "
            "target_kind, field_id, target_entity_id, outcome, reason) "
            "VALUES (?, 'Canary Admin', 'owner', 'admin_local', 'export', 'household_data', "
            "'all', NULL, 'applied', NULL)",
            (_NOW,),
        )
        await db.get_conn().commit()
        monkeypatch.setattr(db, "_MIGRATIONS", every_migration)
        await db.run_migrations()

        assert await _scalar("SELECT COUNT(*) FROM admin_audit") == 1
        entry = await record_admin_operation(
            actor_label="Canary Admin",
            actor_role=AdminActorRole.OWNER,
            operation=AdminOperationKind.LIST,
            target_kind=TargetKind.DOCUMENT,
            field_id=None,
            target_entity_id=None,
            outcome=AdminOutcomeStatus.APPLIED,
            reason=None,
            recorded_at=_NOW,
        )
        assert entry.target_kind is TargetKind.DOCUMENT
        assert await _scalar("PRAGMA foreign_key_check") is None
