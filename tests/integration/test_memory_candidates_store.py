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


# --- the dialogue's readers (Plan 0063, ADR 0021 decision 9) ---------------------------------


@pytest.mark.usefixtures("store")
async def test_the_oldest_proposed_candidate_of_that_person_is_the_one_offered() -> None:
    owner = await _person()
    visitor = await _person("Canary Visitor")
    await _insert(visitor, _proposal("el rock", "rock"), now=_T0 - timedelta(minutes=5))
    first = await _insert(owner, _proposal("el mate", "mate"), now=_T0)
    await _insert(owner, _proposal("el jazz", "jazz"), now=_T0 + timedelta(minutes=1))

    chosen = await candidates.next_offerable(owner, now=_T0 + timedelta(minutes=2))

    assert chosen is not None
    assert chosen.id == first.candidate_id
    assert chosen.subject_person_id == owner


@pytest.mark.usefixtures("store")
async def test_nothing_is_offerable_when_lapsed_used_up_offered_or_switched_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await _person()
    stored = await _insert(owner)
    assert stored.candidate_id is not None
    later = _T0 + timedelta(seconds=settings.memory_candidate_ttl_seconds + 1)

    assert await candidates.next_offerable(owner, now=later) is None
    assert await candidates.mark_offered(
        stored.candidate_id, owner, correlation_id=uuid4(), now=_T0
    )
    assert await candidates.next_offerable(owner, now=_T0) is None
    monkeypatch.setattr(settings, "memory_candidates_enabled", False)
    assert await candidates.next_offerable(owner, now=_T0) is None


@pytest.mark.usefixtures("store")
async def test_a_candidate_offered_as_often_as_allowed_is_not_offered_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "memory_candidate_max_offers", 1)
    owner = await _person()
    stored = await _insert(owner)
    assert stored.candidate_id is not None
    assert await candidates.mark_offered(
        stored.candidate_id, owner, correlation_id=uuid4(), now=_T0
    )
    answer_window = timedelta(seconds=settings.memory_candidate_answer_seconds + 1)

    assert await candidates.next_offerable(owner, now=_T0 + answer_window) is None


@pytest.mark.usefixtures("store")
async def test_an_unanswered_offer_is_offerable_again_once_its_window_closed() -> None:
    owner = await _person()
    stored = await _insert(owner)
    assert stored.candidate_id is not None
    assert await candidates.mark_offered(
        stored.candidate_id, owner, correlation_id=uuid4(), now=_T0
    )
    after_window = _T0 + timedelta(seconds=settings.memory_candidate_answer_seconds + 1)

    again = await candidates.next_offerable(owner, now=after_window)

    assert again is not None
    assert again.id == stored.candidate_id
    assert await candidates.mark_offered(
        stored.candidate_id, owner, correlation_id=uuid4(), now=after_window
    )


@pytest.mark.usefixtures("store")
async def test_an_answer_finds_only_that_persons_open_offer_with_that_key() -> None:
    owner = await _person()
    visitor = await _person("Canary Visitor")
    mine = await _insert(owner, _proposal("el mate", "mate"))
    theirs = await _insert(visitor, _proposal("el mate", "mate"))
    assert mine.candidate_id is not None
    assert theirs.candidate_id is not None
    for candidate_id, person in ((mine.candidate_id, owner), (theirs.candidate_id, visitor)):
        assert await candidates.mark_offered(candidate_id, person, correlation_id=uuid4(), now=_T0)
    soon = _T0 + timedelta(seconds=10)

    found = await candidates.find_offered(owner, "mate", now=soon)

    assert found is not None
    assert found.id == mine.candidate_id
    assert await candidates.find_offered(owner, "jazz", now=soon) is None


@pytest.mark.usefixtures("store")
async def test_an_offer_past_its_answer_window_or_not_yet_made_is_not_answerable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await _person()
    stored = await _insert(owner)
    assert stored.candidate_id is not None

    assert await candidates.find_offered(owner, "mate", now=_T0) is None
    assert await candidates.mark_offered(
        stored.candidate_id, owner, correlation_id=uuid4(), now=_T0
    )
    late = _T0 + timedelta(seconds=settings.memory_candidate_answer_seconds + 1)
    assert await candidates.find_offered(owner, "mate", now=late) is None
    monkeypatch.setattr(settings, "memory_candidates_enabled", False)
    assert await candidates.find_offered(owner, "mate", now=_T0) is None


async def _offer(person: int, proposal: ProposedCandidate) -> int:
    """Store *proposal* for *person* and mark it offered at ``_T0``; return its id."""
    stored = await _insert(person, proposal)
    assert stored.candidate_id is not None
    assert await candidates.mark_offered(
        stored.candidate_id, person, correlation_id=uuid4(), now=_T0
    )
    return stored.candidate_id


@pytest.mark.usefixtures("store")
async def test_without_a_key_the_one_open_offer_of_the_person_is_found() -> None:
    owner = await _person()
    offered_id = await _offer(owner, _proposal("el mate", "mate"))
    await _insert(owner, _proposal("el jazz", "jazz"))  # merely proposed: not open
    soon = _T0 + timedelta(seconds=10)

    found = await candidates.find_offered(owner, None, now=soon)

    assert found is not None
    assert found.id == offered_id


@pytest.mark.usefixtures("store")
async def test_without_a_key_no_open_offer_finds_nothing() -> None:
    owner = await _person()
    await _insert(owner)  # proposed, never offered
    soon = _T0 + timedelta(seconds=10)

    assert await candidates.find_offered(owner, None, now=soon) is None


@pytest.mark.usefixtures("store")
async def test_without_a_key_two_open_offers_are_ambiguous_and_find_nothing() -> None:
    owner = await _person()
    await _offer(owner, _proposal("el mate", "mate"))
    await _offer(owner, _proposal("el jazz", "jazz"))
    soon = _T0 + timedelta(seconds=10)

    assert await candidates.find_offered(owner, None, now=soon) is None
    # A keyed call still names the one it means.
    assert await candidates.find_offered(owner, "mate", now=soon) is not None


@pytest.mark.usefixtures("store")
async def test_without_a_key_another_persons_open_offer_is_never_found() -> None:
    owner = await _person()
    visitor = await _person("Canary Visitor")
    await _offer(visitor, _proposal("el mate", "mate"))
    soon = _T0 + timedelta(seconds=10)

    assert await candidates.find_offered(owner, None, now=soon) is None


@pytest.mark.usefixtures("store")
async def test_without_a_key_an_offer_past_its_answer_window_is_not_found() -> None:
    owner = await _person()
    await _offer(owner, _proposal("el mate", "mate"))
    late = _T0 + timedelta(seconds=settings.memory_candidate_answer_seconds + 1)

    assert await candidates.find_offered(owner, None, now=late) is None


@pytest.mark.usefixtures("store")
async def test_without_a_key_the_kill_switch_off_finds_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await _person()
    await _offer(owner, _proposal("el mate", "mate"))
    monkeypatch.setattr(settings, "memory_candidates_enabled", False)
    soon = _T0 + timedelta(seconds=10)

    assert await candidates.find_offered(owner, None, now=soon) is None


@pytest.mark.usefixtures("store")
async def test_with_a_key_the_lookup_is_exactly_as_before() -> None:
    owner = await _person()
    offered_id = await _offer(owner, _proposal("el mate", "mate"))
    soon = _T0 + timedelta(seconds=10)

    found = await candidates.find_offered(owner, "mate", now=soon)

    assert found is not None
    assert found.id == offered_id
    assert await candidates.find_offered(owner, "jazz", now=soon) is None
    assert await candidates.find_offered(owner, "", now=soon) is None


@pytest.mark.usefixtures("store")
async def test_nothing_else_is_offered_while_an_offer_waits_for_its_answer() -> None:
    owner = await _person()
    first = await _insert(owner, _proposal("el mate", "mate"), now=_T0)
    await _insert(owner, _proposal("el jazz", "jazz"), now=_T0 + timedelta(seconds=1))
    assert first.candidate_id is not None
    assert await candidates.mark_offered(
        first.candidate_id, owner, correlation_id=uuid4(), now=_T0 + timedelta(seconds=2)
    )

    waiting = _T0 + timedelta(seconds=10)
    assert await candidates.next_offerable(owner, now=waiting) is None
    window_closed = _T0 + timedelta(seconds=settings.memory_candidate_answer_seconds + 3)
    again = await candidates.next_offerable(owner, now=window_closed)
    assert again is not None
    assert again.id == first.candidate_id


@pytest.mark.usefixtures("store")
async def test_still_offerable_says_whether_the_compare_and_set_can_win(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await _person()
    visitor = await _person("Canary Visitor")
    stored = await _insert(owner)
    assert stored.candidate_id is not None
    candidate_id = stored.candidate_id

    assert await candidates.still_offerable(candidate_id, owner, now=_T0)
    assert not await candidates.still_offerable(candidate_id, visitor, now=_T0)
    lapsed = _T0 + timedelta(seconds=settings.memory_candidate_ttl_seconds + 1)
    assert not await candidates.still_offerable(candidate_id, owner, now=lapsed)
    assert await candidates.mark_offered(candidate_id, owner, correlation_id=uuid4(), now=_T0)
    assert not await candidates.still_offerable(candidate_id, owner, now=_T0)
    monkeypatch.setattr(settings, "memory_candidates_enabled", False)
    window_closed = _T0 + timedelta(seconds=settings.memory_candidate_answer_seconds + 1)
    assert not await candidates.still_offerable(candidate_id, owner, now=window_closed)


# --- the readers' edges: person isolation, state filter, window and deadline boundaries ------


@pytest.mark.usefixtures("store")
async def test_another_persons_open_offer_does_not_block_this_persons_candidate() -> None:
    """The one-open-offer rule is per person: a visitor's waiting offer blocks nobody else."""
    owner = await _person()
    visitor = await _person("Canary Visitor")
    theirs = await _insert(visitor, _proposal("el rock", "rock"), now=_T0)
    mine = await _insert(owner, _proposal("el mate", "mate"), now=_T0)
    assert theirs.candidate_id is not None
    assert mine.candidate_id is not None
    assert await candidates.mark_offered(
        theirs.candidate_id, visitor, correlation_id=uuid4(), now=_T0
    )
    waiting = _T0 + timedelta(seconds=10)

    chosen = await candidates.next_offerable(owner, now=waiting)

    assert chosen is not None
    assert chosen.id == mine.candidate_id
    assert await candidates.still_offerable(mine.candidate_id, owner, now=waiting)


async def _resolved_candidate(owner: int, outcome: CandidateStatus) -> int:
    """Store an offered candidate and leave it in *outcome*, the way production does."""
    stored = await _insert(owner, _proposal(f"el {outcome.value}", outcome.value))
    assert stored.candidate_id is not None
    assert await candidates.mark_offered(
        stored.candidate_id, owner, correlation_id=uuid4(), now=_T0
    )
    if outcome is CandidateStatus.EXPIRED:
        later = _T0 + timedelta(seconds=settings.memory_candidate_ttl_seconds)
        async with db.transaction() as conn:
            assert await candidates.expire_lapsed_in_transaction(conn, later) == 1
    else:
        assert await candidates.resolve_candidate(
            stored.candidate_id, owner, to=outcome, correlation_id=uuid4(), now=_T0
        )
    assert await _status(stored.candidate_id) is outcome
    return stored.candidate_id


@pytest.mark.usefixtures("store")
@pytest.mark.parametrize(
    "outcome", [CandidateStatus.CONFIRMED, CandidateStatus.REJECTED, CandidateStatus.EXPIRED]
)
async def test_a_resolved_or_expired_candidate_is_never_offerable_again(
    outcome: CandidateStatus,
) -> None:
    owner = await _person()
    candidate_id = await _resolved_candidate(owner, outcome)
    window = settings.memory_candidate_answer_seconds

    # Inside the answer window and right after it closed (when an `offered_at` check alone
    # would let a row that kept its offer timestamp through); both well before any deadline.
    for seconds in (10, window + 1):
        moment = _T0 + timedelta(seconds=seconds)
        assert await candidates.next_offerable(owner, now=moment) is None
        assert not await candidates.still_offerable(candidate_id, owner, now=moment)


@pytest.mark.usefixtures("store")
async def test_the_answer_window_edge_belongs_to_the_offer_not_to_the_answer() -> None:
    """At exactly ``answer_seconds`` the offer is no longer answerable and is offerable again."""
    owner = await _person()
    stored = await _insert(owner)
    assert stored.candidate_id is not None
    assert await candidates.mark_offered(
        stored.candidate_id, owner, correlation_id=uuid4(), now=_T0
    )
    edge = _T0 + timedelta(seconds=settings.memory_candidate_answer_seconds)
    just_inside = edge - timedelta(microseconds=1)

    # One microsecond before the edge: answerable, and nothing is offered meanwhile.
    found = await candidates.find_offered(owner, "mate", now=just_inside)
    assert found is not None
    assert found.id == stored.candidate_id
    assert await candidates.next_offerable(owner, now=just_inside) is None
    assert not await candidates.still_offerable(stored.candidate_id, owner, now=just_inside)

    # On the edge: not answerable, and offerable. No instant is both, and none is neither.
    assert await candidates.find_offered(owner, "mate", now=edge) is None
    again = await candidates.next_offerable(owner, now=edge)
    assert again is not None
    assert again.id == stored.candidate_id
    assert await candidates.still_offerable(stored.candidate_id, owner, now=edge)


@pytest.mark.usefixtures("store")
async def test_an_offer_past_its_deadline_is_not_answerable_even_inside_its_window() -> None:
    """Reads run no housekeeping: the deadline is enforced by ``find_offered`` itself."""
    owner = await _person()
    stored = await _insert(owner)
    assert stored.candidate_id is not None
    deadline = _T0 + timedelta(seconds=settings.memory_candidate_ttl_seconds)
    offered_at = deadline - timedelta(seconds=10)
    assert await candidates.mark_offered(
        stored.candidate_id, owner, correlation_id=uuid4(), now=offered_at
    )

    assert await candidates.find_offered(owner, "mate", now=deadline - timedelta(seconds=1))
    assert await candidates.find_offered(owner, "mate", now=deadline) is None
    # Nothing expired the row (a read writes nothing); the filter alone refused it.
    assert await _status(stored.candidate_id) is CandidateStatus.OFFERED
