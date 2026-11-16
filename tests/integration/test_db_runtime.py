"""Integration tests for the SQLite runtime check and the clean start of `db.open_db()`.

Plan 0085, decisions D-1 and D-2: the runtime is checked (SQLite floor, FTS5, sqlite-vec
version) and a failed start leaves no connection or lock behind.
"""

from collections.abc import AsyncIterator
import dataclasses
import logging
from pathlib import Path

import aiosqlite
import pytest
from server.exceptions import BrainMemoryError
from server.settings import settings

from server import db


@pytest.fixture
async def clean_conn_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Path]:
    """Point at a fresh temp DB path without opening it; each test controls open/close."""
    db_path = tmp_path / "runtime-test.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)
    db._conn = None
    yield db_path
    await db.close_db()
    db._conn = None


@pytest.fixture
async def real_report(clean_conn_state: Path) -> db.RuntimeReport:
    """Return the report of the real runtime, read through a really opened connection."""
    await db.open_db()
    return await db._read_runtime(db.get_conn())


@pytest.mark.integration
async def test_the_real_runtime_passes_the_check(clean_conn_state: Path) -> None:
    """The runtime this project pins satisfies every assertion."""
    await db.open_db()

    report = await db.check_runtime(db.get_conn())

    assert report.sqlite_version >= db.SQLITE_FLOOR
    assert report.fts5 is True
    assert report.vec_version == db.SQLITE_VEC_VERSION


@pytest.mark.integration
async def test_a_sqlite_older_than_the_floor_is_refused(real_report: db.RuntimeReport) -> None:
    """SQLite 3.41 is below the 3.42 floor."""
    old = dataclasses.replace(real_report, sqlite_version=(3, 41, 2))

    with pytest.raises(BrainMemoryError, match=r"older than 3\.42"):
        db._require_supported(old)


@pytest.mark.integration
async def test_a_sqlite_without_fts5_is_refused(real_report: db.RuntimeReport) -> None:
    """A SQLite built without FTS5 cannot host the search index."""
    no_fts = dataclasses.replace(real_report, fts5=False)

    with pytest.raises(BrainMemoryError, match="without FTS5"):
        db._require_supported(no_fts)


@pytest.mark.integration
async def test_a_different_sqlite_vec_is_refused(real_report: db.RuntimeReport) -> None:
    """Only the pinned sqlite-vec version is accepted."""
    other = dataclasses.replace(real_report, vec_version="v0.1.10")

    with pytest.raises(BrainMemoryError, match="sqlite-vec version mismatch"):
        db._require_supported(other)


@pytest.mark.integration
async def test_open_db_refuses_to_start_on_a_bad_report_and_leaves_nothing_behind(
    clean_conn_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A runtime that fails the check stops the start and releases the connection."""
    real_read = db._read_runtime

    async def old_sqlite(conn: aiosqlite.Connection) -> db.RuntimeReport:
        return dataclasses.replace(await real_read(conn), sqlite_version=(3, 41, 0))

    monkeypatch.setattr(db, "_read_runtime", old_sqlite)

    with pytest.raises(BrainMemoryError, match=r"older than 3\.42"):
        await db.open_db()

    assert db.is_open() is False
    assert db._write_lock is None


@pytest.mark.integration
async def test_a_failed_start_leaves_nothing_behind(
    clean_conn_state: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A failure after `connect` closes the connection; the next start is clean and usable."""
    connections: list[aiosqlite.Connection] = []
    real_connect = aiosqlite.connect

    async def spy_connect(path: Path) -> aiosqlite.Connection:
        conn = await real_connect(path)
        connections.append(conn)
        return conn

    monkeypatch.setattr(db.aiosqlite, "connect", spy_connect)
    with monkeypatch.context() as broken:
        broken.setattr(db.sqlite_vec, "loadable_path", lambda: str(tmp_path / "missing-vec"))
        with pytest.raises(BrainMemoryError, match="Failed to open SQLite"):
            await db.open_db()

    assert len(connections) == 1
    with pytest.raises(ValueError, match="no active connection"):
        await connections[0].execute("SELECT 1")
    assert db.is_open() is False
    assert db._write_lock is None

    await db.open_db()
    await db.run_migrations()
    async with db.transaction() as conn:
        await conn.execute("INSERT INTO meta (key, value) VALUES (?, ?)", ("restart", "ok"))
    cursor = await db.get_conn().execute("SELECT value FROM meta WHERE key = 'restart'")
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    assert row[0] == "ok"


@pytest.mark.integration
async def test_the_versions_are_logged_once_on_open(
    clean_conn_state: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """One INFO record reports the runtime versions."""
    with caplog.at_level(logging.INFO, logger="server.db"):
        await db.open_db()

    records = [r for r in caplog.records if r.getMessage().startswith("SQLite runtime")]
    assert len(records) == 1
    assert records[0].levelno == logging.INFO
