"""Integration tests for the diary: episodes and the background job (Plan 0076, ADR 0027)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest
from server.exceptions import LLMError
from server.memory import conversation_jobs, conversation_record as record
from server.memory.candidate_limits import limiter
from server.memory.conversation_episodes import EpisodeOutcome, get_episode, write_episode
from server.memory.conversation_record import EpisodeStatus
from server.memory.conversation_summary import NOTHING_TO_REMEMBER, EpisodeDraft
from server.memory.conversation_types import TurnVerdict, make_turn
from server.memory.declarative import upsert_entity
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from server.memory.conversation_record import RecordView

pytestmark = pytest.mark.integration

_T0 = datetime(2026, 10, 29, 10, 0, tzinfo=UTC)
_LATER = _T0 + timedelta(minutes=10)
_DRAFT = EpisodeDraft(summary="La persona contó que le gusta el mate.", sensitivity="normal")


@pytest.fixture
async def owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "diary.db")
    monkeypatch.setattr(settings, "working_memory_idle_seconds", 180)
    monkeypatch.setattr(settings, "conversation_record_enabled", True)
    monkeypatch.setattr(settings, "conversation_episodes_enabled", True)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield await upsert_entity(name="Canary Owner", type="person")
    await db.close_db()
    db._conn = None


async def _closed_record(owner: int, voice: TurnVerdict, *, start: float = 0) -> RecordView:
    turn = make_turn(
        "me gusta el mate",
        "Qué rico.",
        voice=voice,
        correlation_id=UUID(int=int(start) + 1),
        at=_T0 + timedelta(seconds=start),
    )
    record_id = await record.append_turn(turn, owner_entity_id=owner, now=turn.at)
    await record.close_idle_records(turn.at + timedelta(minutes=5))
    view = await record.read_record(record_id)
    assert view is not None
    return view


async def _status(record_id: int) -> EpisodeStatus:
    view = await record.read_record(record_id)
    assert view is not None
    return view.summary.episode_status


async def test_an_eligible_record_gets_one_personal_episode_with_its_expiry(owner: int) -> None:
    view = await _closed_record(owner, TurnVerdict.VERIFIED)

    outcome = await write_episode(
        view, client=httpx.AsyncClient(), now=_LATER, summarize=AsyncMock(return_value=_DRAFT)
    )

    episode = await get_episode(view.summary.id)
    assert outcome is EpisodeOutcome.WRITTEN
    assert episode is not None
    assert (episode.owner_entity_id, episode.sensitivity) == (owner, "normal")
    assert episode.summary == _DRAFT.summary
    assert episode.expires_at == view.summary.expires_at
    assert await _status(view.summary.id) is EpisodeStatus.DONE


async def test_a_not_eligible_record_is_skipped_without_a_model_call(owner: int) -> None:
    view = await _closed_record(owner, TurnVerdict.NOT_OWNER)
    summarize = AsyncMock()

    outcome = await write_episode(view, client=httpx.AsyncClient(), now=_LATER, summarize=summarize)

    assert outcome is EpisodeOutcome.SKIPPED
    summarize.assert_not_awaited()
    assert await _status(view.summary.id) is EpisodeStatus.SKIPPED


async def test_nothing_to_remember_is_skipped(owner: int) -> None:
    view = await _closed_record(owner, TurnVerdict.VERIFIED)
    nothing = EpisodeDraft(summary=NOTHING_TO_REMEMBER, sensitivity="normal")

    outcome = await write_episode(
        view, client=httpx.AsyncClient(), now=_LATER, summarize=AsyncMock(return_value=nothing)
    )

    assert outcome is EpisodeOutcome.SKIPPED
    assert await get_episode(view.summary.id) is None


async def test_a_busy_limiter_leaves_it_pending(owner: int) -> None:
    view = await _closed_record(owner, TurnVerdict.VERIFIED)
    assert limiter.try_acquire() is None
    try:
        outcome = await write_episode(
            view, client=httpx.AsyncClient(), now=_LATER, summarize=AsyncMock(return_value=_DRAFT)
        )
    finally:
        limiter.release()

    assert outcome is EpisodeOutcome.BUSY
    assert await _status(view.summary.id) is EpisodeStatus.PENDING


async def test_three_failures_mark_it_failed_and_the_limiter_is_released(owner: int) -> None:
    view = await _closed_record(owner, TurnVerdict.VERIFIED)
    summarize = AsyncMock(side_effect=LLMError("down"))

    outcomes = [
        await write_episode(view, client=httpx.AsyncClient(), now=_LATER, summarize=summarize)
        for _ in range(3)
    ]

    assert outcomes == [EpisodeOutcome.RETRY, EpisodeOutcome.RETRY, EpisodeOutcome.FAILED]
    assert await _status(view.summary.id) is EpisodeStatus.FAILED
    assert not limiter.busy


async def test_a_record_deleted_meanwhile_is_gone_and_no_episode_exists(owner: int) -> None:
    """Review focus 4."""
    view = await _closed_record(owner, TurnVerdict.VERIFIED)

    async def summarize_then_delete(_client: httpx.AsyncClient, _turns: object) -> EpisodeDraft:
        await record.delete_record(view.summary.id)
        return _DRAFT

    outcome = await write_episode(
        view, client=httpx.AsyncClient(), now=_LATER, summarize=summarize_then_delete
    )

    assert outcome is EpisodeOutcome.GONE
    assert await get_episode(view.summary.id) is None


async def test_run_once_closes_idle_segments_even_with_the_diary_off(
    owner: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "conversation_episodes_enabled", False)
    turn = make_turn("hola", "hola", voice=TurnVerdict.VERIFIED, correlation_id=UUID(int=9), at=_T0)
    await record.append_turn(turn, owner_entity_id=owner, now=_T0)
    write = AsyncMock()
    monkeypatch.setattr(conversation_jobs, "write_episode", write)

    await conversation_jobs.run_once(httpx.AsyncClient(), _LATER)

    assert not await record.has_open_record()
    write.assert_not_awaited()


async def test_no_episode_is_written_while_a_conversation_is_open(
    owner: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _closed_record(owner, TurnVerdict.VERIFIED)
    live = make_turn(
        "hola", "hola", voice=TurnVerdict.VERIFIED, correlation_id=UUID(int=8), at=_LATER
    )
    await record.append_turn(live, owner_entity_id=owner, now=_LATER)
    write = AsyncMock()
    monkeypatch.setattr(conversation_jobs, "write_episode", write)

    await conversation_jobs.run_once(httpx.AsyncClient(), _LATER + timedelta(seconds=30))

    write.assert_not_awaited()


async def test_at_most_one_episode_per_tick_and_not_eligible_ones_are_skipped(
    owner: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    stranger = await _closed_record(owner, TurnVerdict.NOT_OWNER, start=0)
    first = await _closed_record(owner, TurnVerdict.VERIFIED, start=600)
    second = await _closed_record(owner, TurnVerdict.VERIFIED, start=1200)
    write = AsyncMock(return_value=EpisodeOutcome.WRITTEN)
    monkeypatch.setattr(conversation_jobs, "write_episode", write)

    await conversation_jobs.run_once(httpx.AsyncClient(), _T0 + timedelta(hours=2))

    assert await _status(stranger.summary.id) is EpisodeStatus.SKIPPED
    assert [call.args[0].summary.id for call in write.await_args_list] == [first.summary.id]
    assert await _status(second.summary.id) is EpisodeStatus.PENDING


async def test_run_once_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        conversation_jobs, "close_idle_records", AsyncMock(side_effect=RuntimeError("db"))
    )

    await conversation_jobs.run_once(httpx.AsyncClient(), _LATER)
