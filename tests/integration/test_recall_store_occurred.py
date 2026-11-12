"""Recall windows by when a told event happened (Plan 0083 Task 4, D-9 and D-15).

ADR 0037 decision 3: a unit with an occurred interval matches a window by it, one without by
``said_at``; an episode follows its turns. Canary rows only.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from server.cognition.spoken_dates import DayWindow, window_utc_bounds
from server.memory import recall_store
from server.memory.conversation_types import RecordedTurn, TurnVerdict
from server.memory.declarative import upsert_entity
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_ZONE = ZoneInfo("America/Santiago")
_TODAY = date(2026, 11, 12)
_NOW = "2026-11-12T15:00:00.000000+00:00"
_LATER = "2027-11-12T10:00:00.000000+00:00"
_EARLIER = "2026-11-01T00:00:00.000000+00:00"
# Noon, household time, on a local day.
_NOON_UTC_HOUR = 15
_DIMENSIONS = 768
_CID = UUID("00000000-0000-0000-0000-0000000000cc")
_LAST_YEAR = DayWindow(start=date(2025, 1, 1), end=date(2025, 12, 31))
_SATURDAY = DayWindow(start=date(2026, 11, 7), end=date(2026, 11, 7))
_SUMMER = DayWindow(start=date(2025, 12, 1), end=date(2026, 2, 28))


@pytest.fixture
async def owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "occurred.db")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        yield await upsert_entity(name="Canary Owner", type="person")
    finally:
        await db.close_db()
        db._conn = None


def _noon(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, _NOON_UTC_HOUR, tzinfo=UTC)


async def _record(owner_id: int, *, expires_at: str = _LATER) -> int:
    cursor = await db.get_conn().execute(
        "INSERT INTO conversation_records (owner_entity_id, started_at, last_turn_at, closed_at, "
        "expires_at) VALUES (?, ?, ?, ?, ?)",
        (owner_id, _EARLIER, _EARLIER, _EARLIER, expires_at),
    )
    record_id = int(cursor.lastrowid or 0)
    await cursor.close()
    await db.get_conn().commit()
    return record_id


async def _turn(
    owner_id: int, record_id: int, heard: str, day: date, occurred: DayWindow | None = None
) -> int:
    turn = RecordedTurn(
        at=_noon(day),
        heard=heard,
        said="zzrobotzz",
        voice=TurnVerdict.VERIFIED,
        correlation_id=_CID,
    )
    async with db.transaction() as conn:
        return await recall_store.insert_turn_unit(
            conn, record_id=record_id, owner_entity_id=owner_id, turn=turn, occurred=occurred
        )


async def _episode(owner_id: int, record_id: int, summary: str, day: date) -> int:
    said_at = _noon(day).isoformat(timespec="microseconds")
    cursor = await db.get_conn().execute(
        "INSERT INTO conversation_episodes (owner_entity_id, source_record_id, visibility, "
        "sensitivity, summary, model, created_at, expires_at) "
        "VALUES (?, ?, 'personal', 'normal', ?, 'zzmodelzz', ?, ?)",
        (owner_id, record_id, summary, said_at, _LATER),
    )
    episode_id = int(cursor.lastrowid or 0)
    await cursor.close()
    await db.get_conn().commit()
    async with db.transaction() as conn:
        return await recall_store.insert_episode_unit(
            conn,
            record_id=record_id,
            episode_id=episode_id,
            owner_entity_id=owner_id,
            summary=summary,
            sensitivity="normal",
            said_at=said_at,
        )


def _days(window: DayWindow) -> dict[str, str]:
    since, until = window_utc_bounds(window, _ZONE)
    return {
        "since": since,
        "until": until,
        "first_day": window.start.isoformat(),
        "last_day": window.end.isoformat(),
    }


def _one(day: date) -> DayWindow:
    return DayWindow(start=day, end=day)


async def _recent(owner_id: int, window: DayWindow, *, occurred: bool) -> list[int]:
    units = await recall_store.recent_units(
        owner_entity_id=owner_id, now=_NOW, limit=3, occurred=occurred, **_days(window)
    )
    return [unit.id for unit in units]


async def _lexical(owner_id: int, term: str, window: DayWindow, *, occurred: bool) -> list[int]:
    return await recall_store.lexical_hits(
        owner_entity_id=owner_id,
        terms=[term],
        now=_NOW,
        limit=10,
        occurred=occurred,
        **_days(window),
    )


def _axis(axis: int) -> list[float]:
    values = [0.0] * _DIMENSIONS
    values[axis] = 1.0
    return values


async def test_with_the_flag_off_the_results_are_unchanged(owner: int) -> None:
    record_id = await _record(owner)
    unit = await _turn(owner, record_id, "el sabado fui a la playa", _TODAY, occurred=_SATURDAY)
    assert await _lexical(owner, "playa", _one(_TODAY), occurred=False) == [unit]
    assert await _lexical(owner, "playa", _SATURDAY, occurred=False) == []
    assert await _recent(owner, _one(_TODAY), occurred=False) == [unit]
    [read] = await recall_store.units_by_id([unit], owner_entity_id=owner, now=_NOW)
    assert read.occurred is None


async def test_a_unit_matches_by_its_interval(owner: int) -> None:
    record_id = await _record(owner)
    unit = await _turn(owner, record_id, "el sabado fui a la playa", _TODAY, occurred=_SATURDAY)
    assert await _lexical(owner, "playa", _SATURDAY, occurred=True) == [unit]
    assert await _lexical(owner, "playa", _one(_TODAY), occurred=True) == []
    assert await _recent(owner, _SATURDAY, occurred=True) == [unit]


async def test_a_unit_without_one_matches_by_said_at(owner: int) -> None:
    record_id = await _record(owner)
    unit = await _turn(owner, record_id, "fui al cine con mi hermana", _TODAY)
    assert await _lexical(owner, "cine", _one(_TODAY), occurred=True) == [unit]
    assert await _lexical(owner, "cine", _SATURDAY, occurred=True) == []


async def test_overlap_not_containment(owner: int) -> None:
    record_id = await _record(owner)
    summer = await _turn(owner, record_id, "el verano pasado fuimos al lago", _TODAY, _SUMMER)
    year = await _turn(owner, record_id, "el ano pasado fui a la nieve", _TODAY, _LAST_YEAR)
    assert await _lexical(owner, "lago", _one(date(2026, 1, 15)), occurred=True) == [summer]
    week = DayWindow(start=date(2025, 6, 2), end=date(2025, 6, 8))
    assert await _lexical(owner, "nieve", week, occurred=True) == [year]


async def test_the_vector_side_filters_by_the_interval(owner: int) -> None:
    record_id = await _record(owner)
    unit = await _turn(owner, record_id, "el sabado fui a la playa", _TODAY, occurred=_SATURDAY)
    assert await recall_store.store_vector(unit, _axis(0), model="zzmodelzz")
    hits = await recall_store.vector_hits(
        owner_entity_id=owner, vector=_axis(0), now=_NOW, k=5, occurred=True, **_days(_SATURDAY)
    )
    assert [unit_id for unit_id, _ in hits] == [unit]
    off_window = await recall_store.vector_hits(
        owner_entity_id=owner, vector=_axis(0), now=_NOW, k=5, occurred=True, **_days(_one(_TODAY))
    )
    assert off_window == []


async def test_an_episode_follows_its_turns(owner: int) -> None:
    yesterday = _TODAY - timedelta(days=1)
    about_last_year = await _record(owner)
    await _turn(owner, about_last_year, "el ano pasado fui a la nieve", yesterday, _LAST_YEAR)
    await _episode(owner, about_last_year, "hablamos de la nieve", yesterday)
    about_yesterday = await _record(owner)
    await _turn(owner, about_yesterday, "fui al cine con mi hermana", yesterday)
    kept = await _episode(owner, about_yesterday, "hablamos del cine", yesterday)
    no_turns = await _record(owner)
    alone = await _episode(owner, no_turns, "hablamos del tiempo", yesterday)

    assert sorted(await _recent(owner, _one(yesterday), occurred=True)) == sorted([kept, alone])


async def test_the_last_year_story_told_yesterday(owner: int) -> None:
    """D-15: found for «¿qué hice ayer?» with the switch off (before), not with it on (after)."""
    yesterday = _TODAY - timedelta(days=1)
    record_id = await _record(owner)
    turn = await _turn(owner, record_id, "el ano pasado fui a la nieve", yesterday, _LAST_YEAR)
    episode = await _episode(owner, record_id, "hablamos de la nieve", yesterday)

    assert await _recent(owner, _one(yesterday), occurred=False) == [episode]
    assert await _recent(owner, _one(yesterday), occurred=True) == []
    assert await _lexical(owner, "nieve", _one(yesterday), occurred=False) != []
    assert await _lexical(owner, "nieve", _one(yesterday), occurred=True) == []
    assert await _lexical(owner, "nieve", _LAST_YEAR, occurred=True) == [turn]


async def test_units_by_id_still_applies_every_filter(owner: int) -> None:
    other = await upsert_entity(name="Canary Other", type="person")
    mine = await _record(owner)
    expired = await _record(owner, expires_at=_EARLIER)
    theirs = await _record(other)
    kept = await _turn(owner, mine, "el sabado fui a la playa", _TODAY, occurred=_SATURDAY)
    gone = await _turn(owner, expired, "el sabado fui al lago", _TODAY, occurred=_SATURDAY)
    foreign = await _turn(other, theirs, "el sabado fui al cerro", _TODAY, occurred=_SATURDAY)
    medical = await _turn(owner, mine, "el sabado me dolio el corazon", _TODAY, _SATURDAY)
    await db.get_conn().execute(
        "UPDATE recall_units SET sensitivity = 'medical' WHERE id = ?", (medical,)
    )
    await db.get_conn().commit()

    units = await recall_store.units_by_id(
        [kept, gone, foreign, medical], owner_entity_id=owner, now=_NOW, occurred=True
    )
    assert [unit.id for unit in units] == [kept]
    assert units[0].occurred == _SATURDAY


async def test_a_window_needs_its_days_with_the_flag(owner: int) -> None:
    since, until = window_utc_bounds(_one(_TODAY), _ZONE)
    with pytest.raises(ValueError, match="days"):
        await recall_store.recent_units(
            owner_entity_id=owner, since=since, until=until, now=_NOW, limit=3, occurred=True
        )
