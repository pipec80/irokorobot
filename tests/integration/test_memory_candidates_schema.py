"""Migration 009 and the connection's physical-scrub settings (ADR 0021 decision 6)."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pytest
from server.exceptions import BrainMemoryError
from server.memory.declarative import upsert_entity
from server.memory.predicate_registry import resolve_predicate
from server.memory.relational_v4 import assert_literal_fact
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_INSERT = (
    "INSERT INTO memory_candidates "
    "(subject_person_id, asserted_by_person_id, predicate, value_text, value_key, status, "
    "channel, source_correlation_id, proposed_at, expires_at) "
    "VALUES (?, ?, 'likes', ?, ?, ?, 'voice_classic', 'corr-1', "
    "'2026-10-14T10:00:00+00:00', '2026-10-15T10:00:00+00:00')"
)


@pytest.fixture
async def candidate_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Path]:
    """Open a fresh database with every migration applied."""
    db_path = tmp_path / "candidates-schema.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield db_path
    await db.close_db()
    db._conn = None


async def _owner() -> int:
    return await upsert_entity(name="Canary Owner", type="person")


async def _insert(owner: int, value: str | None, key: str | None, status: str) -> None:
    conn = db.get_conn()
    await conn.execute(_INSERT, (owner, owner, value, key, status))
    await conn.commit()


async def test_the_schema_is_at_version_nine_with_the_candidate_table(candidate_db: Path) -> None:
    conn = db.get_conn()
    cursor = await conn.execute("PRAGMA user_version")
    assert await cursor.fetchone() == (9,)
    await cursor.close()

    cursor = await conn.execute("PRAGMA table_info(memory_candidates)")
    columns = [str(row[1]) for row in await cursor.fetchall()]
    await cursor.close()

    assert columns == [
        "id",
        "subject_person_id",
        "asserted_by_person_id",
        "predicate",
        "value_text",
        "value_key",
        "status",
        "channel",
        "source_correlation_id",
        "offer_correlation_id",
        "resolution_correlation_id",
        "proposed_at",
        "offered_at",
        "resolved_at",
        "expires_at",
        "offer_count",
        "promoted_fact_id",
    ]


@pytest.mark.parametrize("status", ["proposed", "offered"])
async def test_a_live_candidate_must_carry_its_value_and_key(
    candidate_db: Path, status: str
) -> None:
    owner = await _owner()

    await _insert(owner, "el mate", "mate", status)
    for value, key in ((None, None), ("el mate", None), (None, "mate")):
        with pytest.raises(sqlite3.IntegrityError):
            await _insert(owner, value, key, status)


@pytest.mark.parametrize("status", ["confirmed", "rejected", "expired"])
async def test_a_resolved_candidate_cannot_keep_a_value(candidate_db: Path, status: str) -> None:
    owner = await _owner()

    await _insert(owner, None, None, status)
    for value, key in (("el mate", "mate"), ("el mate", None), (None, "mate")):
        with pytest.raises(sqlite3.IntegrityError):
            await _insert(owner, value, key, status)


async def test_resolving_a_row_without_scrubbing_it_is_refused(candidate_db: Path) -> None:
    owner = await _owner()
    await _insert(owner, "el mate", "mate", "proposed")

    with pytest.raises(sqlite3.IntegrityError):
        await db.get_conn().execute("UPDATE memory_candidates SET status = 'confirmed'")


async def test_status_and_channel_are_closed_sets(candidate_db: Path) -> None:
    owner = await _owner()
    conn = db.get_conn()

    with pytest.raises(sqlite3.IntegrityError):
        await conn.execute(_INSERT, (owner, owner, None, None, "disputed"))
    with pytest.raises(sqlite3.IntegrityError):
        await conn.execute(
            "INSERT INTO memory_candidates (subject_person_id, asserted_by_person_id, predicate, "
            "status, channel, source_correlation_id, proposed_at, expires_at) VALUES "
            "(?, ?, 'likes', 'expired', 'chat', 'c', 'a', 'b')",
            (owner, owner),
        )


async def test_the_same_live_value_cannot_be_stored_twice_but_may_return_after_resolving(
    candidate_db: Path,
) -> None:
    owner = await _owner()
    conn = db.get_conn()
    await _insert(owner, "el mate", "mate", "proposed")

    with pytest.raises(sqlite3.IntegrityError):
        await _insert(owner, "El Mate", "mate", "offered")
    await conn.execute(
        "UPDATE memory_candidates SET status = 'rejected', value_text = NULL, value_key = NULL"
    )
    await conn.commit()
    await _insert(owner, "el mate", "mate", "proposed")


async def test_deleting_the_subject_removes_its_candidates(candidate_db: Path) -> None:
    owner = await _owner()
    await _insert(owner, "el mate", "mate", "proposed")
    conn = db.get_conn()

    await conn.execute("DELETE FROM entities WHERE id = ?", (owner,))
    await conn.commit()

    cursor = await conn.execute("SELECT COUNT(*) FROM memory_candidates")
    assert await cursor.fetchone() == (0,)
    await cursor.close()


async def test_deleting_the_promoted_fact_only_clears_the_link(candidate_db: Path) -> None:
    owner = await _owner()
    likes = resolve_predicate("likes")
    assert likes is not None
    fact = await assert_literal_fact(subject_entity_id=owner, definition=likes, value="el mate")
    conn = db.get_conn()
    await conn.execute(_INSERT, (owner, owner, None, None, "confirmed"))
    await conn.execute("UPDATE memory_candidates SET promoted_fact_id = ?", (fact.id,))
    await conn.commit()

    await conn.execute("DELETE FROM literal_facts_v4 WHERE id = ?", (fact.id,))
    await conn.commit()

    cursor = await conn.execute("SELECT promoted_fact_id FROM memory_candidates")
    assert await cursor.fetchone() == (None,)
    await cursor.close()


async def test_the_connection_overwrites_deleted_content(candidate_db: Path) -> None:
    """`secure_delete` is ON (1), not FAST (2): a scrubbed value must not survive in free pages."""
    cursor = await db.get_conn().execute("PRAGMA secure_delete")

    assert await cursor.fetchone() == (1,)
    await cursor.close()


async def test_a_checkpoint_empties_the_write_ahead_log(candidate_db: Path) -> None:
    owner = await _owner()
    await _insert(owner, "el mate", "mate", "proposed")
    wal = candidate_db.with_name(candidate_db.name + "-wal")
    assert wal.exists()
    assert wal.stat().st_size > 0

    assert await db.checkpoint_wal() is True

    assert wal.stat().st_size == 0


async def test_a_checkpoint_pinned_by_another_reader_reports_false_and_does_not_raise(
    candidate_db: Path,
) -> None:
    """An operator's shell reading the file only postpones the scrub; it must not fail a caller."""
    owner = await _owner()
    await _insert(owner, "el mate", "mate", "proposed")
    reader = sqlite3.connect(candidate_db)
    reader.execute("BEGIN")
    reader.execute("SELECT COUNT(*) FROM memory_candidates").fetchall()
    try:
        assert await db.checkpoint_wal() is False
    finally:
        reader.close()

    assert await db.checkpoint_wal() is True


async def test_a_checkpoint_with_a_cursor_open_on_the_shared_connection_does_not_raise(
    candidate_db: Path,
) -> None:
    owner = await _owner()
    await _insert(owner, "el mate", "mate", "proposed")
    # Many rows and one fetch: the statement stays active, as a coroutine between an execute
    # and its fetchall would leave it.
    cursor = await db.get_conn().execute("SELECT * FROM sqlite_master")
    await cursor.fetchone()

    outcome = await db.checkpoint_wal()
    await cursor.close()

    assert isinstance(outcome, bool)
    assert await db.checkpoint_wal() is True


async def test_a_checkpoint_restores_the_normal_busy_timeout(candidate_db: Path) -> None:
    await db.checkpoint_wal()

    cursor = await db.get_conn().execute("PRAGMA busy_timeout")
    assert await cursor.fetchone() == (5000,)
    await cursor.close()


class _Cursor:
    """A cursor that reports a finished (non-busy) checkpoint."""

    async def fetchone(self) -> tuple[int, int, int]:
        return (0, 0, 0)

    async def close(self) -> None:
        return None


class _ConnectionThatCannotRestoreTheTimeout:
    """Stands in for the connection: the busy-timeout restore (and optionally more) fails.

    A closed aiosqlite connection raises ``ValueError`` from ``execute``.
    """

    def __init__(self, *, fail_checkpoint: bool) -> None:
        self._fail_checkpoint = fail_checkpoint
        self._timeouts = 0

    async def execute(self, sql: str) -> _Cursor:
        if sql.startswith("PRAGMA busy_timeout"):
            self._timeouts += 1
            if self._timeouts > 1:  # the first sets the short wait, the second restores it
                raise ValueError("no active connection")
            return _Cursor()
        if self._fail_checkpoint:
            raise ValueError("no active connection")
        return _Cursor()


async def test_a_finished_checkpoint_survives_a_failed_busy_timeout_restore(
    candidate_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The log was truncated: a restore that raises must not turn that into an error."""
    real = db._conn
    monkeypatch.setattr(db, "_conn", _ConnectionThatCannotRestoreTheTimeout(fail_checkpoint=False))
    try:
        assert await db.checkpoint_wal() is True
    finally:
        monkeypatch.setattr(db, "_conn", real)


async def test_a_checkpoint_that_fails_on_a_closed_connection_reports_false_not_raises(
    candidate_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both the checkpoint and the restore raise ValueError: the caller still gets ``False``."""
    real = db._conn
    monkeypatch.setattr(db, "_conn", _ConnectionThatCannotRestoreTheTimeout(fail_checkpoint=True))
    try:
        assert await db.checkpoint_wal() is False
    finally:
        monkeypatch.setattr(db, "_conn", real)


async def test_a_checkpoint_without_an_open_database_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(db, "_conn", None)

    with pytest.raises(BrainMemoryError):
        await db.checkpoint_wal()
