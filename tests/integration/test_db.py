"""Integration tests for `db.py`'s connection lifecycle against a real SQLite DB.

`open_db`, `close_db`, `get_conn`, and `run_migrations` had no direct tests of
their own before Plan 0035 — every existing test only exercised them
indirectly, as setup/teardown for some other module's fixture. This file
closes that gap for the one production file this plan is allowed to touch.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from server.exceptions import BrainMemoryError
from server.settings import settings

from server import db


@pytest.fixture
async def clean_conn_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Path]:
    """Point at a fresh temp DB path without opening it — each test controls open/close."""
    db_path = tmp_path / "lifecycle-test.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)
    db._conn = None
    yield db_path
    if db._conn is not None:
        await db.close_db()
    db._conn = None


@pytest.mark.integration
async def test_get_conn_before_open_raises(clean_conn_state: Path) -> None:
    """Reading the connection before `open_db()` must fail clearly, not with `None`."""
    with pytest.raises(BrainMemoryError, match="open_db"):
        db.get_conn()


@pytest.mark.integration
async def test_open_db_makes_get_conn_succeed(clean_conn_state: Path) -> None:
    """The documented happy path: open, then read."""
    await db.open_db()

    assert db.get_conn() is not None


@pytest.mark.integration
async def test_open_db_is_idempotent(clean_conn_state: Path) -> None:
    """A second `open_db()` call must not replace or break the existing connection."""
    await db.open_db()
    first_conn = db.get_conn()

    await db.open_db()

    assert db.get_conn() is first_conn


@pytest.mark.integration
async def test_close_db_is_idempotent(clean_conn_state: Path) -> None:
    """A second `close_db()` call on an already-closed module must not raise."""
    await db.open_db()
    await db.close_db()

    await db.close_db()  # must not raise


@pytest.mark.integration
async def test_close_db_leaves_get_conn_raising(clean_conn_state: Path) -> None:
    """After closing, the module must not point at a stale or closed connection."""
    await db.open_db()
    await db.close_db()

    with pytest.raises(BrainMemoryError, match="open_db"):
        db.get_conn()


@pytest.mark.integration
async def test_run_migrations_reaches_the_latest_schema_version(
    clean_conn_state: Path,
) -> None:
    """A fresh DB must end up at the highest known migration version."""
    await db.open_db()
    await db.run_migrations()

    cursor = await db.get_conn().execute("PRAGMA user_version")
    row = await cursor.fetchone()
    await cursor.close()

    assert row is not None
    assert row[0] > 0


@pytest.mark.integration
async def test_run_migrations_is_idempotent(clean_conn_state: Path) -> None:
    """Running migrations twice on an up-to-date DB must be a no-op, not an error."""
    await db.open_db()
    await db.run_migrations()
    cursor = await db.get_conn().execute("PRAGMA user_version")
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    first_version = int(row[0])

    await db.run_migrations()  # must not raise, must not change the version

    cursor = await db.get_conn().execute("PRAGMA user_version")
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    assert int(row[0]) == first_version
