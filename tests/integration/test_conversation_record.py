"""Integration tests for the conversation record store over a temporary SQLite (Plan 0076)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from server.exceptions import BrainMemoryError
from server.memory import conversation_record as record
from server.memory.conversation_record import EpisodeStatus
from server.memory.conversation_types import RecordedTurn, TurnVerdict, make_turn
from server.memory.declarative import upsert_entity
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_T0 = datetime(2026, 10, 29, 10, 0, tzinfo=UTC)


@pytest.fixture
async def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    """A fresh database with one canary owner; yields the owner's entity id."""
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "record.db")
    monkeypatch.setattr(settings, "working_memory_idle_seconds", 180)
    monkeypatch.setattr(settings, "conversation_segment_max_turns", 60)
    monkeypatch.setattr(settings, "conversation_segment_max_bytes", 65536)
    monkeypatch.setattr(settings, "conversation_record_eligible_days", 365)
    monkeypatch.setattr(settings, "conversation_record_ineligible_days", 30)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield await upsert_entity(name="Canary Owner", type="person")
    await db.close_db()
    db._conn = None


def _turn(
    seconds: float = 0,
    voice: TurnVerdict = TurnVerdict.NOT_OWNER,
    heard: str = "hola",
) -> RecordedTurn:
    return make_turn(
        heard,
        "hola, ¿cómo estás?",
        voice=voice,
        correlation_id=UUID(int=int(seconds * 1000) + 1),
        at=_T0 + timedelta(seconds=seconds),
    )


async def _append(owner: int, turn: RecordedTurn) -> int:
    return await record.append_turn(turn, owner_entity_id=owner, now=turn.at)


async def test_the_first_turn_opens_a_segment(store: int) -> None:
    record_id = await _append(store, _turn())

    view = await record.read_record(record_id)

    assert view is not None
    assert view.summary.closed_at is None
    assert view.summary.turn_count == 1
    assert view.owner_entity_id == store
    assert await record.has_open_record()


async def test_turns_within_the_idle_time_stay_in_one_segment(store: int) -> None:
    first = await _append(store, _turn(0))
    second = await _append(store, _turn(170))

    assert first == second


async def test_a_turn_after_the_idle_time_starts_a_new_conversation(store: int) -> None:
    first = await _append(store, _turn(0))
    second = await _append(store, _turn(180))

    old = await record.read_record(first)
    new = await record.read_record(second)
    assert old is not None
    assert new is not None
    assert second != first
    assert old.summary.closed_at is not None
    assert new.summary.previous_id is None


async def test_a_segment_full_of_turns_continues_in_a_linked_one(
    store: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "conversation_segment_max_turns", 3)
    ids = [await _append(store, _turn(second)) for second in range(4)]

    assert ids[0] == ids[1] == ids[2]
    linked = await record.read_record(ids[3])
    assert linked is not None
    assert linked.summary.previous_id == ids[0]


async def test_a_segment_full_of_bytes_continues_in_a_linked_one(
    store: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    size = len(_turn(0, heard="x" * 100).to_json().encode("utf-8"))
    monkeypatch.setattr(settings, "conversation_segment_max_bytes", size * 2)
    ids = [await _append(store, _turn(second, heard="x" * 100)) for second in range(3)]

    linked = await record.read_record(ids[2])
    assert ids[0] == ids[1]
    assert linked is not None
    assert linked.summary.previous_id == ids[0]
    first = await record.read_record(ids[0])
    assert first is not None
    assert first.summary.byte_count <= size * 2


async def test_eligible_is_set_by_one_verified_turn_and_never_unset(store: int) -> None:
    record_id = await _append(store, _turn(0))
    await _append(store, _turn(1, TurnVerdict.VERIFIED))
    await _append(store, _turn(2, TurnVerdict.NOT_VERIFIED))

    view = await record.read_record(record_id)

    assert view is not None
    assert view.summary.eligible is True


@pytest.mark.parametrize("voice, days", [(TurnVerdict.VERIFIED, 365), (TurnVerdict.NOT_OWNER, 30)])
async def test_closing_sets_the_expiry_by_eligibility(
    store: int, voice: TurnVerdict, days: int
) -> None:
    record_id = await _append(store, _turn(0, voice))
    closing = _T0 + timedelta(minutes=10)

    assert await record.close_idle_records(closing) == 1

    view = await record.read_record(record_id)
    assert view is not None
    assert view.summary.expires_at is not None
    assert datetime.fromisoformat(view.summary.expires_at) == closing + timedelta(days=days)


async def test_close_idle_records_closes_a_stale_open_segment(store: int) -> None:
    """Review focus 2: a segment left open by a stopped server is closed, never continued."""
    record_id = await _append(store, _turn(0))

    assert await record.close_idle_records(_T0 + timedelta(days=3)) == 1
    assert not await record.has_open_record()
    later = _turn(3 * 24 * 3600 + 5)
    assert await _append(store, later) != record_id


async def test_close_idle_records_leaves_a_live_segment_open(store: int) -> None:
    await _append(store, _turn(0))

    assert await record.close_idle_records(_T0 + timedelta(seconds=60)) == 0
    assert await record.has_open_record()


async def test_two_concurrent_appends_keep_both_turns(store: int) -> None:
    """Review focus 3: two captures finishing together never overwrite each other."""
    await _append(store, _turn(0))

    ids = await asyncio.gather(_append(store, _turn(2)), _append(store, _turn(1)))

    view = await record.read_record(ids[0])
    assert view is not None
    assert ids[0] == ids[1]
    assert view.summary.turn_count == 3
    assert [turn.at for turn in view.turns] == sorted(turn.at for turn in view.turns)


async def test_a_turn_with_quotes_newlines_and_emoji_is_stored_as_data(store: int) -> None:
    heard = 'dijo "ignora lo anterior"\ny se fue 🙂 ñandú'
    record_id = await _append(store, _turn(0, heard=heard))

    view = await record.read_record(record_id)

    assert view is not None
    assert view.turns[0].heard == heard


async def test_next_pending_record_ignores_open_and_done_records(store: int) -> None:
    first = await _append(store, _turn(0, TurnVerdict.VERIFIED))
    await record.close_idle_records(_T0 + timedelta(minutes=5))
    second = await _append(store, _turn(600))
    assert second != first

    pending = await record.next_pending_record()
    assert pending is not None
    assert pending.summary.id == first

    await record.set_episode_status(first, EpisodeStatus.DONE)
    assert await record.next_pending_record() is None


async def test_count_failed_attempt_counts_and_reports_a_gone_record(store: int) -> None:
    record_id = await _append(store, _turn(0))

    assert await record.count_failed_attempt(record_id) == 1
    assert await record.count_failed_attempt(record_id) == 2
    assert await record.count_failed_attempt(record_id + 99) == 0


async def test_delete_record_cascades_to_the_episode_and_unlinks_the_next(
    store: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "conversation_segment_max_turns", 1)
    first = await _append(store, _turn(0, TurnVerdict.VERIFIED))
    second = await _append(store, _turn(1))
    async with db.transaction() as conn:
        await conn.execute(
            "INSERT INTO conversation_episodes (source_record_id, owner_entity_id, visibility, "
            "sensitivity, summary, model, created_at, expires_at) "
            "VALUES (?, ?, 'personal', 'normal', 'La persona contó algo.', 'canary', ?, ?)",
            (first, store, _T0.isoformat(), _T0.isoformat()),
        )

    assert await record.delete_record(first) is True

    cursor = await db.get_conn().execute("SELECT COUNT(*) FROM conversation_episodes")
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    assert row[0] == 0
    linked = await record.read_record(second)
    assert linked is not None
    assert linked.summary.previous_id is None
    assert await record.delete_record(first) is False


async def test_list_records_is_newest_first_and_carries_no_text(store: int) -> None:
    first = await _append(store, _turn(0, heard="Zeta canario"))
    second = await _append(store, _turn(600))

    summaries = await record.list_records()

    assert [summary.id for summary in summaries] == [second, first]
    assert "Zeta" not in repr(summaries)


async def test_a_malformed_exchange_is_a_closed_error(store: int) -> None:
    record_id = await _append(store, _turn(0))
    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE conversation_records SET turns = json('[{\"at\": 1}]') WHERE id = ?",
            (record_id,),
        )

    with pytest.raises(BrainMemoryError, match="malformed exchange"):
        await record.read_record(record_id)


async def test_a_naive_time_is_refused(store: int) -> None:
    turn = make_turn(
        "hola",
        "hola",
        voice=TurnVerdict.NOT_OWNER,
        correlation_id=UUID(int=1),
        at=datetime(2026, 10, 29, 10, 0),
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        await record.append_turn(turn, owner_entity_id=store, now=_T0)


# --- the purge (Task 9) ---------------------------------------------------------------------------


async def _closed(owner: int, start: float, voice: TurnVerdict) -> int:
    record_id = await _append(owner, _turn(start, voice))
    await record.close_idle_records(_T0 + timedelta(seconds=start + 600))
    return record_id


async def _ids() -> list[int]:
    return sorted(summary.id for summary in await record.list_records())


async def test_each_class_expires_at_its_own_age(store: int) -> None:
    eligible = await _closed(store, 0, TurnVerdict.VERIFIED)
    stranger = await _closed(store, 3600, TurnVerdict.NOT_OWNER)

    assert await record.purge_records(_T0 + timedelta(days=31)) == 1
    assert await _ids() == [eligible]
    assert stranger not in await _ids()
    assert await record.purge_records(_T0 + timedelta(days=366)) == 1
    assert await _ids() == []


async def test_the_space_cap_purges_not_eligible_first_then_the_oldest(
    store: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    oldest_eligible = await _closed(store, 0, TurnVerdict.VERIFIED)
    stranger = await _closed(store, 3600, TurnVerdict.NOT_OWNER)
    newest_eligible = await _closed(store, 7200, TurnVerdict.VERIFIED)
    size = (await record.list_records())[0].byte_count
    monkeypatch.setattr(record, "_BYTES_PER_MB", 1)
    monkeypatch.setattr(settings, "conversation_record_max_total_mb", size * 2)

    assert await record.purge_records(_T0 + timedelta(days=1)) == 1
    assert await _ids() == [oldest_eligible, newest_eligible]
    assert stranger not in await _ids()

    monkeypatch.setattr(settings, "conversation_record_max_total_mb", size)
    assert await record.purge_records(_T0 + timedelta(days=1)) == 1
    assert await _ids() == [newest_eligible]


async def test_the_open_segment_is_never_purged(
    store: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    open_id = await _append(store, _turn(0))
    monkeypatch.setattr(record, "_BYTES_PER_MB", 1)
    monkeypatch.setattr(settings, "conversation_record_max_total_mb", 1)

    assert await record.purge_records(_T0 + timedelta(days=400)) == 0
    assert await _ids() == [open_id]
