"""Integration tests for the retention purge job (Plan 0036, Group C).

`_run_once` had no test of its own before this plan — its four DELETEs now
share one `db.transaction()` instead of a bare commit, and it must still
never raise: a failing purge is caught and logged so the background loop
keeps running on the next tick.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
import logging
from pathlib import Path
from uuid import uuid4

import pytest
from server.memory import candidates, retention
from server.memory.candidate_types import CandidateChannel, CandidateStatus, ProposedCandidate
from server.memory.declarative import upsert_entity
from server.settings import settings

from server import db


@pytest.fixture
async def real_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Path]:
    """Open a fresh temporary real SQLite DB with the full app schema applied."""
    db_path = tmp_path / "retention-test.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)
    monkeypatch.setattr(candidates, "_checkpoint_pending", False)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield db_path
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


@pytest.mark.integration
@pytest.mark.usefixtures("real_db")
async def test_run_once_expires_and_scrubs_a_lapsed_candidate_whatever_the_kill_switch_says(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR 0021 decision 6: the hourly job reclaims candidate values, switch on or off."""
    owner = await upsert_entity(name="Canary Owner", type="person")
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
    # The fresh one goes in first: a store entry runs its own housekeeping, so inserting it
    # after the stale one would expire the stale one before the retention job ever ran.
    fresh = await candidates.insert_candidate(
        ProposedCandidate(predicate="likes", value_text="el jazz", value_key="jazz"),
        subject_person_id=owner,
        asserted_by_person_id=owner,
        channel=CandidateChannel.VOICE_CLASSIC,
        correlation_id=uuid4(),
        now=datetime.now(UTC),
    )
    stale = await candidates.insert_candidate(
        ProposedCandidate(predicate="likes", value_text="el mate", value_key="mate"),
        subject_person_id=owner,
        asserted_by_person_id=owner,
        channel=CandidateChannel.VOICE_CLASSIC,
        correlation_id=uuid4(),
        now=datetime.now(UTC) - timedelta(days=2),
    )
    monkeypatch.setattr(settings, "memory_candidates_enabled", False)
    assert stale.candidate_id is not None
    assert fresh.candidate_id is not None
    before = await candidates.get_candidate(stale.candidate_id)
    assert before is not None
    assert before.status is CandidateStatus.PROPOSED  # lapsed on the clock, still live in the row

    await retention._run_once()

    expired = await candidates.get_candidate(stale.candidate_id)
    kept = await candidates.get_candidate(fresh.candidate_id)
    assert expired is not None
    assert (expired.status, expired.value_text) == (CandidateStatus.EXPIRED, None)
    assert kept is not None
    assert (kept.status, kept.value_text) == (CandidateStatus.PROPOSED, "el jazz")


_CANARY = "zumo de pomelo rosado"


def _file_bytes(db_path: Path) -> bytes:
    """The database file and its write-ahead log, concatenated as an attacker would read them."""
    pieces = [db_path.read_bytes()]
    wal = db_path.with_name(db_path.name + "-wal")
    if wal.exists():
        pieces.append(wal.read_bytes())
    return b"".join(pieces)


async def _insert_a_stale_canary(monkeypatch: pytest.MonkeyPatch) -> int:
    """Store a candidate that lapsed two days ago, holding the canary value."""
    owner = await upsert_entity(name="Canary Owner", type="person")
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
    stale = await candidates.insert_candidate(
        ProposedCandidate(predicate="likes", value_text=_CANARY, value_key="pomelo"),
        subject_person_id=owner,
        asserted_by_person_id=owner,
        channel=CandidateChannel.VOICE_CLASSIC,
        correlation_id=uuid4(),
        now=datetime.now(UTC) - timedelta(days=2),
    )
    assert stale.candidate_id is not None
    monkeypatch.setattr(settings, "memory_candidates_enabled", False)
    return stale.candidate_id


@pytest.mark.integration
async def test_run_once_physically_scrubs_a_lapsed_candidate_from_the_file_and_the_log(
    real_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The job erases the value and truncates the log: the bytes are gone, not just unreferenced."""
    stale_id = await _insert_a_stale_canary(monkeypatch)
    assert _CANARY.encode() in _file_bytes(real_db)  # non-vacuous: the value is on disk now

    await retention._run_once()

    expired = await candidates.get_candidate(stale_id)
    assert expired is not None
    assert expired.status is CandidateStatus.EXPIRED
    assert _CANARY.encode() not in _file_bytes(real_db)


@pytest.mark.integration
async def test_a_failing_sensor_purge_does_not_stop_the_candidate_expiry(
    real_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The candidate housekeeping has its own transaction: one failure cannot roll back the other."""
    stale_id = await _insert_a_stale_canary(monkeypatch)
    monkeypatch.setattr(retention, "_SQL_SENSOR_READINGS", "NOT VALID SQL")

    await retention._run_once()

    expired = await candidates.get_candidate(stale_id)
    assert expired is not None
    assert (expired.status, expired.value_text) == (CandidateStatus.EXPIRED, None)
    assert _CANARY.encode() not in _file_bytes(real_db)


@pytest.mark.integration
@pytest.mark.usefixtures("real_db")
async def test_a_failing_candidate_housekeeping_does_not_undo_the_sensor_purge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = db.get_conn()
    await conn.execute(
        "INSERT INTO sensor_readings (sensor_id, sensor_type, value, unit, created_at) "
        "VALUES ('s1', 'temp', 1.0, 'C', datetime('now', '-100 hours'))"
    )
    await conn.commit()

    async def _fails(_conn: object, _now: datetime) -> int:
        raise RuntimeError("housekeeping broke")

    monkeypatch.setattr(retention, "run_housekeeping", _fails)

    await retention._run_once()

    cursor = await conn.execute("SELECT COUNT(*) FROM sensor_readings")
    assert await cursor.fetchone() == (0,)
    await cursor.close()


@pytest.mark.integration
@pytest.mark.usefixtures("real_db")
async def test_a_checkpoint_error_after_the_commit_is_not_reported_as_a_failed_purge(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    leaked_text = "pomelo-in-an-exception-message"

    async def _raises(_scrubbed: int) -> None:
        raise ValueError(leaked_text)

    monkeypatch.setattr(retention, "checkpoint_after_scrub", _raises)

    with caplog.at_level(logging.INFO, logger="server"):
        await retention._run_once()

    assert "Retention purge failed" not in caplog.text
    assert "checkpoint" in caplog.text.lower()
    assert "ValueError" in caplog.text
    assert leaked_text not in caplog.text


@pytest.mark.integration
@pytest.mark.usefixtures("real_db")
async def test_a_failed_purge_logs_the_exception_class_never_its_message(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(retention, "_SQL_SENSOR_READINGS", "NOT VALID SQL pomelo")

    with caplog.at_level(logging.INFO, logger="server"):
        await retention._run_once()

    assert "Retention purge failed" in caplog.text
    assert "OperationalError" in caplog.text
    assert "pomelo" not in caplog.text
