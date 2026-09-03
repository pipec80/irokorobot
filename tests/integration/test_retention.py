"""Integration tests for the retention purge job (Plan 0036, Group C).

`_run_once` had no test of its own before this plan — its four DELETEs now
share one `db.transaction()` instead of a bare commit, and it must still
never raise: a failing purge is caught and logged so the background loop
keeps running on the next tick.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from server.memory import retention
from server.settings import settings

from server import db


@pytest.fixture
async def real_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Open a fresh temporary real SQLite DB with the full app schema applied."""
    db_path = tmp_path / "retention-test.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield
    await db.close_db()
    db._conn = None


@pytest.mark.integration
@pytest.mark.usefixtures("real_db")
async def test_run_once_purges_only_expired_rows() -> None:
    """A fresh and an expired row of the same kind must be told apart."""
    conn = db.get_conn()
    await conn.execute(
        "INSERT INTO sensor_readings (sensor_id, sensor_type, value, unit, created_at) "
        "VALUES ('s1', 'temp', 1.0, 'C', datetime('now', '-100 hours'))"
    )
    await conn.execute(
        "INSERT INTO sensor_readings (sensor_id, sensor_type, value, unit, created_at) "
        "VALUES ('s1', 'temp', 2.0, 'C', datetime('now'))"
    )
    await conn.commit()

    await retention._run_once()

    cursor = await conn.execute("SELECT value FROM sensor_readings")
    rows = await cursor.fetchall()
    await cursor.close()
    assert [row[0] for row in rows] == [2.0], "only the expired row should have been purged"


@pytest.mark.integration
@pytest.mark.usefixtures("real_db")
async def test_run_once_swallows_a_failure_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A broken purge must log and return, never crash the background loop."""
    monkeypatch.setattr(retention, "_SQL_SENSOR_READINGS", "NOT VALID SQL")

    await retention._run_once()
