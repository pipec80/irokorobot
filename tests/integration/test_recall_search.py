"""Searching the recall units (Plan 0078 Task 7, ADR 0028 decision 6).

Canary rows only; the embedding model is a double.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from server.cognition.recall_cues import CueStrength, RecallCue
from server.cognition.spoken_dates import DayWindow
from server.memory import recall_search, recall_store
from server.memory.conversation_types import RecordedTurn, TurnVerdict
from server.memory.declarative import upsert_entity
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence
    from pathlib import Path

pytestmark = pytest.mark.integration

_DIMENSIONS = 768
_NOW = datetime(2026, 11, 4, 15, tzinfo=UTC)
_YESTERDAY = datetime(2026, 11, 3, 15, tzinfo=UTC)
_LAST_WEEK = datetime(2026, 10, 27, 15, tzinfo=UTC)
_FUTURE = "2027-11-03T10:00:00.000000+00:00"


@pytest.fixture
async def owners(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[int, int]]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "recall-search.db")
    monkeypatch.setattr(settings, "household_timezone", "America/Santiago")
    monkeypatch.setattr(settings, "recall_max_distance", 0.30)
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        yield (
            await upsert_entity(name="Canary Owner", type="person"),
            await upsert_entity(name="Canary Other", type="person"),
        )
    finally:
        await db.close_db()
        db._conn = None


def _axis(axis: int) -> list[float]:
    values = [0.0] * _DIMENSIONS
    values[axis] = 1.0
    return values


@pytest.fixture
def embed(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    double = AsyncMock(return_value=_axis(0))
    monkeypatch.setattr(recall_search, "ollama_embed", double)
    return double


async def _record(owner: int) -> int:
    async with db.transaction() as conn:
        cursor = await conn.execute(
            "INSERT INTO conversation_records (owner_entity_id, started_at, last_turn_at, "
            "closed_at, expires_at) VALUES (?, 't', 't', 't', ?)",
            (owner, _FUTURE),
        )
        record_id = int(cursor.lastrowid or 0)
        await cursor.close()
    return record_id


async def _unit(
    owner: int, record_id: int, heard: str, *, at: datetime = _YESTERDAY, axis: int | None = None
) -> int:
    turn = RecordedTurn(
        at=at, heard=heard, said="ok", voice=TurnVerdict.VERIFIED, correlation_id=uuid4()
    )
    async with db.transaction() as conn:
        unit_id = await recall_store.insert_turn_unit(
            conn, record_id=record_id, owner_entity_id=owner, turn=turn
        )
    if axis is not None:
        assert await recall_store.store_vector(unit_id, _axis(axis), model="canary")
    return unit_id


def _cue(query: str, window: DayWindow | None = None) -> RecallCue:
    return RecallCue(strength=CueStrength.STRONG, query=query, window=window)


async def _search(owner: int, cue: RecallCue) -> recall_search.RecallSearch:
    return await recall_search.search_recall(owner, cue, client=httpx.AsyncClient(), now=_NOW)


def _ids(found: recall_search.RecallSearch) -> list[int]:
    return [hit.unit.id for hit in found.hits]


async def test_words_and_a_near_vector_both_find(owners: tuple[int, int], embed: AsyncMock) -> None:
    owner, _ = owners
    record_id = await _record(owner)
    by_words = await _unit(owner, record_id, "fuimos al cerro con Zeta", axis=5)
    by_vector = await _unit(owner, record_id, "subimos la montaña", axis=0)

    found = await _search(owner, _cue("que del cerro"))

    assert set(_ids(found)) == {by_words, by_vector}
    assert found.best_distance == pytest.approx(0.0, abs=0.001)
    assert not found.lexical_only
    embed.assert_awaited_once()


async def test_at_most_three_and_two_per_record(owners: tuple[int, int], embed: AsyncMock) -> None:
    owner, _ = owners
    first, second = await _record(owner), await _record(owner)
    for record_id in (first, first, first, second, second):
        await _unit(owner, record_id, "el cerro")

    found = await _search(owner, _cue("cerro"))

    records = [hit.unit.record_id for hit in found.hits]
    assert len(records) == 3
    assert max(records.count(first), records.count(second)) == 2
    assert set(records) == {first, second}


async def test_date_only_returns_recent_units(owners: tuple[int, int], embed: AsyncMock) -> None:
    owner, _ = owners
    record_id = await _record(owner)
    yesterday = await _unit(owner, record_id, "tomamos mate")
    await _unit(owner, record_id, "fuimos al cerro", at=_LAST_WEEK)

    found = await _search(
        owner, _cue("que", DayWindow(start=date(2026, 11, 3), end=date(2026, 11, 3)))
    )

    assert _ids(found) == [yesterday]
    assert all(hit.distance is None for hit in found.hits)
    embed.assert_not_awaited()


async def test_a_window_filters_the_word_search(owners: tuple[int, int], embed: AsyncMock) -> None:
    owner, _ = owners
    record_id = await _record(owner)
    await _unit(owner, record_id, "el cerro", at=_LAST_WEEK)
    yesterday = await _unit(owner, record_id, "otra vez el cerro")

    found = await _search(
        owner, _cue("cerro", DayWindow(start=date(2026, 11, 3), end=date(2026, 11, 3)))
    )

    assert _ids(found) == [yesterday]


async def test_an_embedding_failure_searches_by_words(
    owners: tuple[int, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, _ = owners
    monkeypatch.setattr(
        recall_search, "ollama_embed", AsyncMock(side_effect=httpx.ConnectError("offline"))
    )
    record_id = await _record(owner)
    unit_id = await _unit(owner, record_id, "el cerro")

    found = await _search(owner, _cue("cerro"))

    assert _ids(found) == [unit_id]
    assert found.lexical_only
    assert found.best_distance is None


async def test_nothing_qualifying_is_an_empty_result(
    owners: tuple[int, int], embed: AsyncMock
) -> None:
    owner, _ = owners
    record_id = await _record(owner)
    await _unit(owner, record_id, "tomamos mate", axis=1)

    found = await _search(owner, _cue("cerro"))

    assert found.hits == ()
    assert found.best_distance == pytest.approx(1.0, abs=0.001)


async def test_a_record_deleted_mid_search_drops_its_units(
    owners: tuple[int, int], embed: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review focus 3: never a unit of a deleted record, never a crash."""
    owner, _ = owners
    gone, kept = await _record(owner), await _record(owner)
    await _unit(owner, gone, "el cerro")
    kept_unit = await _unit(owner, kept, "el cerro otra vez")
    original = recall_store.lexical_hits

    async def then_delete(**kwargs: object) -> Sequence[int]:
        ids = await original(**kwargs)  # type: ignore[arg-type]  # the store's own keywords
        async with db.transaction() as conn:
            await conn.execute("DELETE FROM conversation_records WHERE id = ?", (gone,))
        return ids

    monkeypatch.setattr(recall_search, "lexical_hits", then_delete)

    found = await _search(owner, _cue("cerro"))

    assert _ids(found) == [kept_unit]


async def _run(statement: str, **values: object) -> None:
    async with db.transaction() as conn:
        await conn.execute(statement, values)


_RECLASSIFY = "UPDATE recall_units SET sensitivity = 'medical' WHERE id = :unit"
_EXPIRE = (
    "UPDATE conversation_records SET expires_at = '2026-11-01T00:00:00.000000+00:00' "
    "WHERE id = :record"
)


async def test_a_unit_reclassified_mid_search_is_not_delivered(
    owners: tuple[int, int], embed: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Decision 2: the read that returns the text re-applies the class (Plan 0080 D-10)."""
    owner, _ = owners
    record_id = await _record(owner)
    first = await _unit(owner, record_id, "el cerro")
    second = await _unit(owner, record_id, "otra vez el cerro")

    async def reclassify_while_embedding(*args: object, **kwargs: object) -> list[float]:
        await _run(_RECLASSIFY, unit=first)
        return _axis(0)

    monkeypatch.setattr(recall_search, "ollama_embed", reclassify_while_embedding)

    found = await _search(owner, _cue("cerro"))

    assert _ids(found) == [second]


async def test_a_unit_whose_record_expired_mid_search_is_not_delivered(
    owners: tuple[int, int], embed: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, _ = owners
    expiring, kept = await _record(owner), await _record(owner)
    await _unit(owner, expiring, "el cerro")
    kept_unit = await _unit(owner, kept, "otra vez el cerro")

    async def expire_while_embedding(*args: object, **kwargs: object) -> list[float]:
        await _run(_EXPIRE, record=expiring)
        return _axis(0)

    monkeypatch.setattr(recall_search, "ollama_embed", expire_while_embedding)

    found = await _search(owner, _cue("cerro"))

    assert _ids(found) == [kept_unit]


async def test_the_same_holds_when_only_the_words_found_it(
    owners: tuple[int, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, _ = owners
    monkeypatch.setattr(
        recall_search, "ollama_embed", AsyncMock(side_effect=httpx.ConnectError("offline"))
    )
    record_id = await _record(owner)
    first = await _unit(owner, record_id, "el cerro")
    second = await _unit(owner, record_id, "otra vez el cerro")
    original = recall_store.lexical_hits

    async def then_reclassify(**kwargs: object) -> Sequence[int]:
        ids = await original(**kwargs)  # type: ignore[arg-type]  # the store's own keywords
        await _run(_RECLASSIFY, unit=first)
        return ids

    monkeypatch.setattr(recall_search, "lexical_hits", then_reclassify)

    found = await _search(owner, _cue("cerro"))

    assert found.lexical_only
    assert _ids(found) == [second]


async def test_another_owners_unit_ids_are_never_returned(owners: tuple[int, int]) -> None:
    """The read has its own owner filter, whatever ids it is handed."""
    owner, other = owners
    mine = await _unit(owner, await _record(owner), "el cerro")
    theirs = await _unit(other, await _record(other), "el cerro")
    now = _NOW.isoformat(timespec="microseconds")

    for who, expected in ((owner, mine), (other, theirs)):
        units = await recall_store.units_by_id([mine, theirs], owner_entity_id=who, now=now)
        assert [unit.id for unit in units] == [expected]


async def test_another_owner_is_never_returned(owners: tuple[int, int], embed: AsyncMock) -> None:
    owner, other = owners
    await _unit(other, await _record(other), "el cerro", axis=0)

    found = await _search(owner, _cue("cerro"))

    assert found.hits == ()
    assert found.best_distance is None


async def test_the_query_terms_are_capped_and_quoted(
    owners: tuple[int, int], embed: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, _ = owners
    seen: list[tuple[str, ...]] = []
    original = recall_store.lexical_hits

    async def spy(**kwargs: object) -> Sequence[int]:
        seen.append(tuple(kwargs["terms"]))  # type: ignore[arg-type]  # a sequence of words
        return await original(**kwargs)  # type: ignore[arg-type]  # the store's own keywords

    monkeypatch.setattr(recall_search, "lexical_hits", spy)

    await _search(owner, _cue('uno dos tres cuatro cinco seis siete ocho nueve "NEAR( *'))

    assert seen == [("uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho")]
