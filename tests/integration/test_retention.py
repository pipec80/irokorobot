"""Integration tests for the retention purge job (Plan 0036, Group C).

`_run_once` must never raise: a failing purge is caught and logged so the background loop
keeps running on the next tick, and each part (conversations, candidates) has its own
transaction so one failing cannot undo the other. The dead-table purge went with those tables
(Plan 0085, migration 017).
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
import logging
from pathlib import Path
import sqlite3
from unittest.mock import AsyncMock
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
async def test_run_once_swallows_a_failure_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both parts failing must log and return, never crash the background loop."""
    monkeypatch.setattr(retention, "purge_records", AsyncMock(side_effect=RuntimeError("db")))
    monkeypatch.setattr(retention, "run_housekeeping", AsyncMock(side_effect=RuntimeError("db")))

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
async def test_a_failing_conversation_purge_does_not_stop_the_candidate_expiry(
    real_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The candidate housekeeping has its own transaction: one failure cannot roll back the other."""
    stale_id = await _insert_a_stale_canary(monkeypatch)
    monkeypatch.setattr(retention, "purge_records", AsyncMock(side_effect=RuntimeError("db")))

    await retention._run_once()

    expired = await candidates.get_candidate(stale_id)
    assert expired is not None
    assert (expired.status, expired.value_text) == (CandidateStatus.EXPIRED, None)
    assert _CANARY.encode() not in _file_bytes(real_db)


@pytest.mark.integration
@pytest.mark.usefixtures("real_db")
async def test_a_failing_candidate_housekeeping_does_not_stop_the_conversation_purge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purge = AsyncMock(return_value=0)
    monkeypatch.setattr(retention, "purge_records", purge)

    async def _fails(_conn: object, _now: datetime) -> int:
        raise RuntimeError("housekeeping broke")

    monkeypatch.setattr(retention, "run_housekeeping", _fails)

    await retention._run_once()

    purge.assert_awaited_once()


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

    assert "purge failed" not in caplog.text
    assert "checkpoint" in caplog.text.lower()
    assert "ValueError" in caplog.text
    assert leaked_text not in caplog.text


@pytest.mark.integration
@pytest.mark.usefixtures("real_db")
async def test_a_failed_purge_logs_the_exception_class_never_its_message(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(
        retention, "purge_records", AsyncMock(side_effect=sqlite3.OperationalError("pomelo"))
    )

    with caplog.at_level(logging.INFO, logger="server"):
        await retention._run_once()

    assert "Conversation purge failed" in caplog.text
    assert "OperationalError" in caplog.text
    assert "pomelo" not in caplog.text


@pytest.mark.integration
@pytest.mark.usefixtures("real_db")
async def test_the_retention_run_purges_conversations_even_with_the_switch_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Plan 0076: old records still expire after the record is switched off."""
    monkeypatch.setattr(settings, "conversation_record_enabled", False)
    purge = AsyncMock(return_value=0)
    monkeypatch.setattr(retention, "purge_records", purge)

    await retention._run_once()

    purge.assert_awaited_once()


@pytest.mark.integration
@pytest.mark.usefixtures("real_db")
async def test_a_failing_conversation_purge_does_not_stop_the_other_purges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(retention, "purge_records", AsyncMock(side_effect=RuntimeError("db")))
    reclaim = AsyncMock()
    monkeypatch.setattr(retention, "_reclaim_candidates", reclaim)

    await retention._run_once()

    reclaim.assert_awaited_once()
