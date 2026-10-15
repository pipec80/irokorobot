"""Integration tests for the candidate store (ADR 0021 decision 6) over a temporary SQLite."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta, timezone
import logging
import sqlite3
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from server.exceptions import BrainMemoryError
from server.memory import candidates, retention
from server.memory.candidate_types import CandidateChannel, CandidateStatus, ProposedCandidate
from server.memory.candidates import InsertStatus, iso_utc
from server.memory.declarative import upsert_entity
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_T0 = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)
_CANARY = "zumo de pomelo rosado"


def _proposal(
    value: str = "el mate", key: str = "mate", predicate: str = "likes"
) -> ProposedCandidate:
    return ProposedCandidate(predicate=predicate, value_text=value, value_key=key)


@pytest.fixture
async def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Path]:
    """A fresh database, with the candidate subsystem on."""
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "candidates.db")
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
    # The owed-checkpoint flag is process state: every test starts as a fresh process.
    monkeypatch.setattr(candidates, "_checkpoint_pending", False)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield tmp_path / "candidates.db"
    await db.close_db()
    db._conn = None


async def _person(name: str = "Canary Owner") -> int:
    return await upsert_entity(name=name, type="person")


async def _insert(
    owner: int, proposal: ProposedCandidate | None = None, *, now: datetime = _T0
) -> candidates.InsertResult:
    return await candidates.insert_candidate(
        proposal or _proposal(),
        subject_person_id=owner,
        asserted_by_person_id=owner,
        channel=CandidateChannel.VOICE_CLASSIC,
        correlation_id=uuid4(),
        now=now,
    )


async def _status(candidate_id: int) -> CandidateStatus:
    candidate = await candidates.get_candidate(candidate_id)
    assert candidate is not None
    return candidate.status


@pytest.mark.usefixtures("store")
async def test_an_accepted_candidate_is_stored_live_with_its_deadline() -> None:
    owner = await _person()
    correlation = UUID(int=42)

    result = await candidates.insert_candidate(
        _proposal(),
        subject_person_id=owner,
        asserted_by_person_id=owner,
        channel=CandidateChannel.VOICE_STREAM,
        correlation_id=correlation,
        now=_T0,
    )

    assert result.status is InsertStatus.INSERTED
    assert result.candidate_id is not None
    stored = await candidates.get_candidate(result.candidate_id)
    assert stored is not None
    assert (stored.predicate, stored.value_text, stored.value_key) == ("likes", "el mate", "mate")
    assert stored.status is CandidateStatus.PROPOSED
    assert stored.channel is CandidateChannel.VOICE_STREAM
    assert stored.subject_person_id == stored.asserted_by_person_id == owner
    assert stored.source_correlation_id == str(correlation)
    assert stored.proposed_at == iso_utc(_T0)
    assert stored.expires_at == iso_utc(
        _T0 + timedelta(seconds=settings.memory_candidate_ttl_seconds)
    )
    assert stored.offer_count == 0
    assert stored.promoted_fact_id is None


def test_the_one_clock_is_utc_iso_and_refuses_a_naive_moment() -> None:
    assert iso_utc(_T0) == "2026-10-14T10:00:00.000000+00:00"
    assert iso_utc(_T0.astimezone(timezone(timedelta(hours=-3)))) == iso_utc(_T0)
    with pytest.raises(ValueError, match="timezone-aware"):
        iso_utc(datetime(2026, 10, 14, 10, 0))


@pytest.mark.usefixtures("store")
async def test_a_repeated_statement_is_a_no_op_insert() -> None:
    owner = await _person()
    first = await _insert(owner, _proposal("el mate", "mate"))

    second = await _insert(owner, _proposal("El Mate", "mate"))

    assert first.status is InsertStatus.INSERTED
    assert second.status is InsertStatus.DUPLICATE
    assert second.candidate_id is None
    cursor = await db.get_conn().execute("SELECT COUNT(*) FROM memory_candidates")
    assert await cursor.fetchone() == (1,)
    await cursor.close()


@pytest.mark.usefixtures("store")
async def test_the_same_key_under_another_predicate_is_a_different_candidate() -> None:
    owner = await _person()
    await _insert(owner, _proposal("el mate", "mate", "likes"))

    other = await _insert(owner, _proposal("el mate", "mate", "dislikes"))

    assert other.status is InsertStatus.INSERTED


@pytest.mark.usefixtures("store")
async def test_at_the_cap_a_new_candidate_is_refused_and_nothing_is_evicted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "memory_candidate_max_live", 2)
    owner = await _person()
    first = await _insert(owner, _proposal("el mate", "mate"))
    second = await _insert(owner, _proposal("el jazz", "jazz"))

    refused = await _insert(owner, _proposal("el rock", "rock"))

    assert refused.status is InsertStatus.CAPACITY
    assert first.candidate_id is not None
    assert second.candidate_id is not None
    assert await _status(first.candidate_id) is CandidateStatus.PROPOSED
    assert await _status(second.candidate_id) is CandidateStatus.PROPOSED


@pytest.mark.usefixtures("store")
async def test_a_duplicate_at_the_cap_is_still_a_duplicate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "memory_candidate_max_live", 1)
    owner = await _person()
    await _insert(owner, _proposal("el mate", "mate"))

    again = await _insert(owner, _proposal("el mate", "mate"))

    assert again.status is InsertStatus.DUPLICATE


@pytest.mark.usefixtures("store")
async def test_the_precheck_names_the_refusal_without_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The proposal asks before it audits, so "allowed" is not logged for a sure refusal."""
    monkeypatch.setattr(settings, "memory_candidate_max_live", 1)
    owner = await _person()
    mate = _proposal("el mate", "mate")
    assert await candidates.precheck_insert(mate, subject_person_id=owner) is None

    await _insert(owner, mate)

    assert await candidates.precheck_insert(mate, subject_person_id=owner) is InsertStatus.DUPLICATE
    jazz = _proposal("el jazz", "jazz")
    assert await candidates.precheck_insert(jazz, subject_person_id=owner) is InsertStatus.CAPACITY
    monkeypatch.setattr(settings, "memory_candidates_enabled", False)
    assert await candidates.precheck_insert(jazz, subject_person_id=owner) is InsertStatus.DISABLED
    cursor = await db.get_conn().execute("SELECT COUNT(*) FROM memory_candidates")
    assert await cursor.fetchone() == (1,)
    await cursor.close()


@pytest.mark.usefixtures("store")
async def test_the_cap_counts_each_person_apart(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "memory_candidate_max_live", 1)
    owner = await _person("Canary Owner")
    visitor = await _person("Canary Visitor")
    await _insert(owner, _proposal("el mate", "mate"))

    other = await _insert(visitor, _proposal("el jazz", "jazz"))

    assert other.status is InsertStatus.INSERTED


@pytest.mark.usefixtures("store")
async def test_a_lapsed_candidate_is_expired_and_scrubbed_at_the_next_store_entry() -> None:
    owner = await _person()
    stale = await _insert(owner, _proposal("el mate", "mate"))
    later = _T0 + timedelta(seconds=settings.memory_candidate_ttl_seconds)

    await _insert(owner, _proposal("el jazz", "jazz"), now=later)

    assert stale.candidate_id is not None
    expired = await candidates.get_candidate(stale.candidate_id)
    assert expired is not None
    assert expired.status is CandidateStatus.EXPIRED
    assert (expired.value_text, expired.value_key) == (None, None)
    assert expired.resolved_at == iso_utc(later)


@pytest.mark.usefixtures("store")
async def test_an_offer_moves_a_proposed_candidate_once() -> None:
    owner = await _person()
    stored = await _insert(owner)
    assert stored.candidate_id is not None
    offer = uuid4()

    first = await candidates.mark_offered(
        stored.candidate_id, owner, correlation_id=offer, now=_T0 + timedelta(seconds=5)
    )
    second = await candidates.mark_offered(
        stored.candidate_id, owner, correlation_id=uuid4(), now=_T0 + timedelta(seconds=6)
    )

    assert (first, second) == (True, False)
    candidate = await candidates.get_candidate(stored.candidate_id)
    assert candidate is not None
    assert candidate.status is CandidateStatus.OFFERED
    assert candidate.offer_count == 1
    assert candidate.offer_correlation_id == str(offer)
    assert candidate.offered_at == iso_utc(_T0 + timedelta(seconds=5))


@pytest.mark.usefixtures("store")
async def test_an_unanswered_offer_returns_to_proposed_on_the_next_access() -> None:
    owner = await _person()
    stored = await _insert(owner)
    assert stored.candidate_id is not None
    await candidates.mark_offered(stored.candidate_id, owner, correlation_id=uuid4(), now=_T0)
    after_window = _T0 + timedelta(seconds=settings.memory_candidate_answer_seconds)

    await _insert(owner, _proposal("el jazz", "jazz"), now=after_window)

    candidate = await candidates.get_candidate(stored.candidate_id)
    assert candidate is not None
    assert candidate.status is CandidateStatus.PROPOSED
    assert candidate.offered_at is None
    assert candidate.offer_correlation_id is None
    assert candidate.offer_count == 1


@pytest.mark.usefixtures("store")
async def test_a_candidate_is_offered_at_most_the_configured_times_and_then_lapses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "memory_candidate_max_offers", 2)
    owner = await _person()
    stored = await _insert(owner)
    assert stored.candidate_id is not None
    window = timedelta(seconds=settings.memory_candidate_answer_seconds)
    moment = _T0
    for _ in range(2):
        assert await candidates.mark_offered(
            stored.candidate_id, owner, correlation_id=uuid4(), now=moment
        )
        moment += window

    third = await candidates.mark_offered(
        stored.candidate_id, owner, correlation_id=uuid4(), now=moment
    )

    assert third is False
    candidate = await candidates.get_candidate(stored.candidate_id)
    assert candidate is not None
    assert candidate.status is CandidateStatus.EXPIRED
    assert candidate.value_text is None


@pytest.mark.usefixtures("store")
@pytest.mark.parametrize("outcome", [CandidateStatus.CONFIRMED, CandidateStatus.REJECTED])
async def test_resolving_an_offered_candidate_erases_its_value(outcome: CandidateStatus) -> None:
    owner = await _person()
    stored = await _insert(owner)
    assert stored.candidate_id is not None
    await candidates.mark_offered(stored.candidate_id, owner, correlation_id=uuid4(), now=_T0)
    answer = uuid4()
    moment = _T0 + timedelta(seconds=10)

    resolved = await candidates.resolve_candidate(
        stored.candidate_id, owner, to=outcome, correlation_id=answer, now=moment
    )
    again = await candidates.resolve_candidate(
        stored.candidate_id, owner, to=outcome, correlation_id=uuid4(), now=moment
    )

    assert (resolved, again) == (True, False)
    candidate = await candidates.get_candidate(stored.candidate_id)
    assert candidate is not None
    assert candidate.status is outcome
    assert (candidate.value_text, candidate.value_key) == (None, None)
    assert candidate.resolution_correlation_id == str(answer)
    assert candidate.resolved_at == iso_utc(moment)


@pytest.mark.usefixtures("store")
async def test_only_an_offered_candidate_can_be_resolved() -> None:
    owner = await _person()
    stored = await _insert(owner)
    assert stored.candidate_id is not None

    resolved = await candidates.resolve_candidate(
        stored.candidate_id, owner, to=CandidateStatus.CONFIRMED, correlation_id=uuid4(), now=_T0
    )

    assert resolved is False
    assert await _status(stored.candidate_id) is CandidateStatus.PROPOSED


@pytest.mark.usefixtures("store")
async def test_another_person_can_neither_offer_nor_resolve_a_candidate() -> None:
    owner = await _person("Canary Owner")
    visitor = await _person("Canary Visitor")
    stored = await _insert(owner)
    assert stored.candidate_id is not None

    stolen_offer = await candidates.mark_offered(
        stored.candidate_id, visitor, correlation_id=uuid4(), now=_T0
    )
    await candidates.mark_offered(stored.candidate_id, owner, correlation_id=uuid4(), now=_T0)
    stolen_answer = await candidates.resolve_candidate(
        stored.candidate_id, visitor, to=CandidateStatus.REJECTED, correlation_id=uuid4(), now=_T0
    )

    assert (stolen_offer, stolen_answer) == (False, False)
    assert await _status(stored.candidate_id) is CandidateStatus.OFFERED


@pytest.mark.usefixtures("store")
async def test_a_resolution_must_name_confirmed_or_rejected() -> None:
    owner = await _person()
    stored = await _insert(owner)
    assert stored.candidate_id is not None

    with pytest.raises(ValueError, match="confirmed or rejected"):
        await candidates.resolve_candidate(
            stored.candidate_id, owner, to=CandidateStatus.EXPIRED, correlation_id=uuid4(), now=_T0
        )


@pytest.mark.usefixtures("store")
async def test_the_kill_switch_covers_every_store_path(monkeypatch: pytest.MonkeyPatch) -> None:
    owner = await _person()
    stored = await _insert(owner)
    assert stored.candidate_id is not None
    monkeypatch.setattr(settings, "memory_candidates_enabled", False)

    insert = await _insert(owner, _proposal("el jazz", "jazz"))
    offered = await candidates.mark_offered(
        stored.candidate_id, owner, correlation_id=uuid4(), now=_T0
    )
    resolved = await candidates.resolve_candidate(
        stored.candidate_id, owner, to=CandidateStatus.REJECTED, correlation_id=uuid4(), now=_T0
    )

    assert insert.status is InsertStatus.DISABLED
    assert (offered, resolved) == (False, False)
    cursor = await db.get_conn().execute("SELECT COUNT(*) FROM memory_candidates")
    assert await cursor.fetchone() == (1,)
    await cursor.close()


@pytest.mark.usefixtures("store")
async def test_start_up_with_the_kill_switch_on_returns_offers_to_proposed() -> None:
    owner = await _person()
    stored = await _insert(owner)
    assert stored.candidate_id is not None
    await candidates.mark_offered(stored.candidate_id, owner, correlation_id=uuid4(), now=_T0)

    await candidates.reset_for_startup(_T0 + timedelta(seconds=1), enabled=True)

    candidate = await candidates.get_candidate(stored.candidate_id)
    assert candidate is not None
    assert candidate.status is CandidateStatus.PROPOSED
    assert candidate.value_text == "el mate"
    assert candidate.offer_count == 1


@pytest.mark.usefixtures("store")
async def test_start_up_with_the_kill_switch_off_voids_every_live_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await _person()
    first = await _insert(owner, _proposal("el mate", "mate"))
    second = await _insert(owner, _proposal("el jazz", "jazz"))
    assert second.candidate_id is not None
    await candidates.mark_offered(second.candidate_id, owner, correlation_id=uuid4(), now=_T0)
    await candidates.reset_for_startup(_T0 + timedelta(seconds=1), enabled=False)

    assert first.candidate_id is not None
    for candidate_id in (first.candidate_id, second.candidate_id):
        candidate = await candidates.get_candidate(candidate_id)
        assert candidate is not None
        assert candidate.status is CandidateStatus.EXPIRED
        assert (candidate.value_text, candidate.value_key) == (None, None)


async def _retention_run_at(now: datetime, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the real retention job as if the clock read *now*."""
    monkeypatch.setattr(retention, "utc_now", lambda: now)
    await retention._run_once()


def _file_bytes(db_path: Path) -> bytes:
    """Concatenate the database file and its write-ahead log, as an attacker would read them."""
    pieces = [db_path.read_bytes()]
    wal = db_path.with_name(db_path.name + "-wal")
    if wal.exists():
        pieces.append(wal.read_bytes())
    return b"".join(pieces)


@pytest.mark.parametrize(
    "scrub",
    ["reject", "expire", "void"],
)
async def test_a_scrubbed_value_is_gone_from_the_file_and_the_log(
    store: Path, scrub: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The scrub is physical: the canary value is found while live and never after."""
    owner = await _person()
    stored = await _insert(owner, _proposal(_CANARY, "zumo de pomelo rosado"))
    assert stored.candidate_id is not None
    await db.get_conn().commit()
    assert _CANARY.encode() in _file_bytes(store)

    if scrub == "reject":
        await candidates.mark_offered(stored.candidate_id, owner, correlation_id=uuid4(), now=_T0)
        await candidates.resolve_candidate(
            stored.candidate_id, owner, to=CandidateStatus.REJECTED, correlation_id=uuid4(), now=_T0
        )
    elif scrub == "expire":
        later = _T0 + timedelta(seconds=settings.memory_candidate_ttl_seconds)
        await _retention_run_at(later, monkeypatch)
    else:
        await candidates.reset_for_startup(_T0, enabled=False)

    assert _CANARY.encode() not in _file_bytes(store)


@pytest.mark.usefixtures("store")
async def test_no_log_line_carries_a_value(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await _person()
    with caplog.at_level(logging.DEBUG, logger="server"):
        stored = await _insert(owner, _proposal(_CANARY, "zumo de pomelo rosado"))
        assert stored.candidate_id is not None
        await candidates.mark_offered(stored.candidate_id, owner, correlation_id=uuid4(), now=_T0)
        await candidates.resolve_candidate(
            stored.candidate_id, owner, to=CandidateStatus.REJECTED, correlation_id=uuid4(), now=_T0
        )
        await _retention_run_at(_T0, monkeypatch)
        await candidates.reset_for_startup(_T0, enabled=True)

    assert "pomelo" not in caplog.text


async def _reject_with_the_log_pinned(db_path: Path) -> None:
    """Reject an offered canary candidate while another reader pins the write-ahead log.

    The page is erased and the resolution commits, but SQLite postpones the checkpoint, so the
    frames that still hold the canary stay in the ``-wal`` file.
    """
    owner = await _person()
    stored = await _insert(owner, _proposal(_CANARY, "zumo de pomelo rosado"))
    assert stored.candidate_id is not None
    await candidates.mark_offered(stored.candidate_id, owner, correlation_id=uuid4(), now=_T0)
    reader = sqlite3.connect(db_path)
    reader.execute("BEGIN")
    reader.execute("SELECT COUNT(*) FROM memory_candidates").fetchall()
    try:
        resolved = await candidates.resolve_candidate(
            stored.candidate_id,
            owner,
            to=CandidateStatus.REJECTED,
            correlation_id=uuid4(),
            now=_T0,
        )
    finally:
        reader.close()
    assert resolved is True  # the resolution committed; the postponed checkpoint did not fail it


async def test_a_scrub_whose_checkpoint_was_blocked_is_finished_at_the_next_entry(
    store: Path,
) -> None:
    """A reader pinned the log: the page was erased, the old frames stay until a later retry."""
    await _reject_with_the_log_pinned(store)
    assert _CANARY.encode() in _file_bytes(store)  # precondition: the blocked scrub left bytes

    await candidates.checkpoint_after_scrub(0)

    assert _CANARY.encode() not in _file_bytes(store)


@pytest.mark.parametrize("enabled", [True, False])
async def test_a_checkpoint_owed_by_a_previous_process_is_finished_at_start_up(
    store: Path, monkeypatch: pytest.MonkeyPatch, enabled: bool
) -> None:
    """The owed-checkpoint flag lives in memory: a restart forgets it, so start-up truncates."""
    await _reject_with_the_log_pinned(store)
    assert _CANARY.encode() in _file_bytes(store)  # precondition: the old frames are in the log
    monkeypatch.setattr(candidates, "_checkpoint_pending", False)  # the new process

    await candidates.reset_for_startup(_T0 + timedelta(seconds=1), enabled=enabled)

    assert _CANARY.encode() not in _file_bytes(store)


async def test_start_up_with_the_switch_on_scrubs_a_candidate_that_lapsed_while_down(
    store: Path,
) -> None:
    owner = await _person()
    stored = await _insert(owner, _proposal(_CANARY, "zumo de pomelo rosado"))
    assert stored.candidate_id is not None
    assert _CANARY.encode() in _file_bytes(store)
    later = _T0 + timedelta(seconds=settings.memory_candidate_ttl_seconds)

    await candidates.reset_for_startup(later, enabled=True)

    assert await _status(stored.candidate_id) is CandidateStatus.EXPIRED
    assert _CANARY.encode() not in _file_bytes(store)


@pytest.mark.parametrize("failure", [BrainMemoryError, ValueError, asyncio.CancelledError])
async def test_a_checkpoint_that_raises_still_leaves_the_owed_checkpoint_recorded(
    store: Path, monkeypatch: pytest.MonkeyPatch, failure: type[BaseException]
) -> None:
    """Shutdown cancellation or a closed connection must not make the process forget the debt."""
    attempts: list[str] = []

    async def _raises() -> bool:
        attempts.append("raised")
        raise failure

    async def _finishes() -> bool:
        attempts.append("finished")
        return True

    monkeypatch.setattr(db, "checkpoint_wal", _raises)
    with pytest.raises(failure):
        await candidates.checkpoint_after_scrub(1)
    monkeypatch.setattr(db, "checkpoint_wal", _finishes)

    await candidates.checkpoint_after_scrub(0)  # scrubbed nothing, but the debt is still owed
    await candidates.checkpoint_after_scrub(0)  # paid: no further call

    assert attempts == ["raised", "finished"]


@pytest.mark.usefixtures("store")
async def test_the_insert_is_logged_before_a_failing_checkpoint_and_names_its_turn(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A checkpoint problem must not hide that a value was stored."""
    owner = await _person()
    await _insert(owner, _proposal("el mate", "mate"))
    caplog.clear()  # the seeding insert logs too; only the one below is under test
    later = _T0 + timedelta(seconds=settings.memory_candidate_ttl_seconds)
    turn = uuid4()

    async def _raises() -> bool:
        raise BrainMemoryError("not open")

    monkeypatch.setattr(db, "checkpoint_wal", _raises)
    with caplog.at_level(logging.INFO, logger="server"), pytest.raises(BrainMemoryError):
        await candidates.insert_candidate(
            _proposal("el jazz", "jazz"),
            subject_person_id=owner,
            asserted_by_person_id=owner,
            channel=CandidateChannel.VOICE_CLASSIC,
            correlation_id=turn,
            now=later,
        )

    events = [r for r in caplog.records if getattr(r, "event", "") == "candidate.insert"]
    assert len(events) == 1
    assert getattr(events[0], "correlation_id", None) == str(turn)
