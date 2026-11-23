"""Searching the recall units (Plan 0078 Task 7, ADR 0028 decision 6).

Canary rows only; the embedding model is a double.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
import logging
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from server.cognition.recall_cues import CueStrength, RecallCue, classify_recall_cue
from server.cognition.spoken_dates import DayWindow
from server.memory import recall_index, recall_search, recall_store
from server.memory.conversation_types import RecordedTurn, TurnVerdict
from server.memory.declarative import upsert_entity
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence
    from pathlib import Path

    from server.memory.retrieval import GateSignals

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
    owner: int, record_id: int, heard: str, *, at: datetime = _YESTERDAY, axis: int | None = 0
) -> int:
    """A verified turn's unit; near the question's axis-0 embedding unless *axis* says else."""
    turn = RecordedTurn(
        at=at, heard=heard, said="ok", voice=TurnVerdict.VERIFIED, correlation_id=uuid4()
    )
    async with db.transaction() as conn:
        unit_id = await recall_store.insert_turn_unit(
            conn, record_id=record_id, owner_entity_id=owner, turn=turn
        )
    if axis is not None:
        assert await recall_store.store_vector(unit_id, _axis(axis), model=settings.embedding_model)
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
    # Found by words, outside T_v (0.30 here) but under T_w (ADR 0040).
    by_words = await _unit_at(owner, record_id, "fuimos al cerro con Zeta", 0.35)
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
    unit_id = await _unit(owner, record_id, "el cerro con Zeta")

    found = await _search(owner, _named_cue("cerro zeta", "zeta"))

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
    first = await _unit(owner, record_id, "el cerro con Zeta")
    second = await _unit(owner, record_id, "otra vez el cerro con Zeta")
    original = recall_store.lexical_hits

    async def then_reclassify(**kwargs: object) -> Sequence[int]:
        ids = await original(**kwargs)  # type: ignore[arg-type]  # the store's own keywords
        await _run(_RECLASSIFY, unit=first)
        return ids

    monkeypatch.setattr(recall_search, "lexical_hits", then_reclassify)

    found = await _search(owner, _named_cue("cerro zeta", "zeta"))

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


async def test_a_model_change_leaves_recall_lexical_until_the_re_index(
    owners: tuple[int, int],
    embed: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """ADR 0031 C1: two models never meet; words keep finding; the re-index brings vectors back."""
    owner, _ = owners
    monkeypatch.setattr(settings, "embedding_model", "canary-model-a")
    record_id = await _record(owner)
    by_words = await _unit(owner, record_id, "fuimos al cerro con Zeta", axis=5)
    by_vector = await _unit(owner, record_id, "subimos la montaña", axis=0)
    spy = AsyncMock(wraps=recall_search.vector_hits)
    monkeypatch.setattr(recall_search, "vector_hits", spy)
    monkeypatch.setattr(settings, "embedding_model", "canary-model-b")

    with caplog.at_level(logging.WARNING):
        found = await _search(owner, _named_cue("que del cerro con zeta", "zeta"))

    spy.assert_not_awaited()
    assert _ids(found) == [by_words]
    assert found.lexical_only
    assert [r.getMessage() for r in caplog.records].count(
        "recall.vector off reason=model_changed remaining=2"
    ) == 1

    monkeypatch.setattr(recall_index, "ollama_embed", AsyncMock(return_value=_axis(0)))
    assert await recall_index.backfill_vectors(httpx.AsyncClient(), limit=5) == 2
    assert await recall_store.units_without_vector(5) == []

    found = await _search(owner, _cue("que del cerro"))

    spy.assert_awaited_once()
    assert not found.lexical_only
    assert set(_ids(found)) == {by_words, by_vector}


async def test_only_the_owners_units_of_another_model_turn_the_vector_off(
    owners: tuple[int, int], embed: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, other = owners
    monkeypatch.setattr(settings, "embedding_model", "canary-model-a")
    await _unit(other, await _record(other), "el cerro de otra persona", axis=5)
    monkeypatch.setattr(settings, "embedding_model", "canary-model-b")
    mine = await _unit(owner, await _record(owner), "subimos la montaña", axis=0)

    found = await _search(owner, _cue("que del cerro"))

    assert not found.lexical_only
    assert _ids(found) == [mine]


# The gate as one step of the search (Plan 0088 Task A2, D-5).


async def test_the_distance_of_a_word_hit_outside_the_knn_is_measured(
    owners: tuple[int, int], embed: AsyncMock
) -> None:
    owner, _ = owners
    record_id = await _record(owner)
    for _ in range(recall_search.RECALL_VECTOR_K):
        await _unit(owner, record_id, "subimos la montaña", axis=0)
    far = await _unit(owner, record_id, "fuimos al cerro", axis=5)
    seen: list[GateSignals] = []

    def spy(signals: GateSignals) -> bool:
        seen.append(signals)
        return True

    found = await recall_search.search_recall(
        owner, _cue("cerro"), client=httpx.AsyncClient(), now=_NOW, gate=spy
    )

    by_words = [signals for signals in seen if signals.by_words]
    assert len(by_words) == 1
    assert by_words[0].distance == pytest.approx(1.0, abs=0.001)
    assert far in _ids(found)


async def test_distances_of_never_reads_another_owner(owners: tuple[int, int]) -> None:
    owner, other = owners
    mine = await _unit(owner, await _record(owner), "el cerro", axis=0)
    theirs = await _unit(other, await _record(other), "el cerro", axis=0)
    unembedded = await _unit(owner, await _record(owner), "el cerro otra vez", axis=None)

    distances = await recall_store.distances_of(
        [mine, theirs, unembedded], _axis(0), owner_entity_id=owner
    )

    assert distances == {mine: pytest.approx(0.0, abs=0.001)}


async def test_a_gate_given_to_the_search_decides_alone(
    owners: tuple[int, int], embed: AsyncMock
) -> None:
    owner, _ = owners
    record_id = await _record(owner)
    await _unit(owner, record_id, "fuimos al cerro con Zeta", axis=5)
    await _unit(owner, record_id, "subimos la montaña", axis=0)

    found = await recall_search.search_recall(
        owner, _cue("que del cerro"), client=httpx.AsyncClient(), now=_NOW, gate=lambda _: False
    )

    assert found.hits == ()
    assert found.rejected == 2


# ADR 0040, the relevance gate in production (Plan 0088 Task A5). The fixture's T_v is 0.30; the
# tests that need the production thresholds set them.


def _at(distance: float) -> list[float]:
    """A vector at *distance* (cosine) from the question's axis-0 embedding."""
    similarity = 1.0 - distance
    values = [0.0] * _DIMENSIONS
    values[0], values[1] = similarity, (1.0 - similarity**2) ** 0.5
    return values


async def _unit_at(owner: int, record_id: int, heard: str, distance: float) -> int:
    unit_id = await _unit(owner, record_id, heard)
    assert await recall_store.store_vector(unit_id, _at(distance), model=settings.embedding_model)
    return unit_id


def _named_cue(query: str, *specific: str) -> RecallCue:
    return RecallCue(
        strength=CueStrength.STRONG, query=query, window=None, specific=frozenset(specific)
    )


@pytest.fixture
def production_thresholds(owners: tuple[int, int], monkeypatch: pytest.MonkeyPatch) -> None:
    """After ``owners``, which sets the fixture's own 0.30."""
    monkeypatch.setattr(settings, "recall_max_distance", 0.43)
    monkeypatch.setattr(settings, "recall_word_max_distance", 0.464)


@pytest.mark.usefixtures("production_thresholds")
async def test_a_named_person_never_told_finds_nothing_even_near(
    owners: tuple[int, int], embed: AsyncMock
) -> None:
    """The hardware defect of 2026-11-18: an unrelated story at 0.37 for a person never told."""
    owner, _ = owners
    record_id = await _record(owner)
    await _unit_at(owner, record_id, "vino una amiga a tomar once", 0.37)

    found = await _search(owner, _named_cue("de florencia", "florencia"))

    assert found.hits == ()
    assert found.rejected == 1


@pytest.mark.usefixtures("production_thresholds")
async def test_a_story_asked_by_its_meaning_still_qualifies(
    owners: tuple[int, int], embed: AsyncMock
) -> None:
    owner, _ = owners
    meaning = await _unit_at(owner, await _record(owner), "fuimos a la playa", 0.40)

    found = await _search(owner, _cue("del mar"))

    assert _ids(found) == [meaning]


async def test_an_exact_code_qualifies_with_the_vector_side_off(
    owners: tuple[int, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, _ = owners
    monkeypatch.setattr(
        recall_search, "ollama_embed", AsyncMock(side_effect=httpx.ConnectError("offline"))
    )
    code = await _unit(owner, await _record(owner), "pedí el repuesto ZX-41")

    found = await _search(owner, _named_cue("del repuesto zx 41", "zx", "41"))

    assert found.lexical_only
    assert _ids(found) == [code]


async def test_a_common_word_with_the_vector_side_off_does_not_qualify(
    owners: tuple[int, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review focus 2: with no distance, one common word is not enough."""
    owner, _ = owners
    monkeypatch.setattr(
        recall_search, "ollama_embed", AsyncMock(side_effect=httpx.ConnectError("offline"))
    )
    await _unit(owner, await _record(owner), "subimos el cerro")

    found = await _search(owner, _cue("del cerro"))

    assert found.lexical_only
    assert found.hits == ()
    assert found.rejected == 1


@pytest.mark.usefixtures("production_thresholds")
async def test_a_lower_case_name_falls_back_to_the_rule_without_specific_words(
    owners: tuple[int, int], embed: AsyncMock
) -> None:
    """Review focus 1: «zeta» in lower case is not specific; a near story still qualifies."""
    owner, _ = owners
    near = await _unit_at(owner, await _record(owner), "vino una amiga a tomar once", 0.20)
    cue = classify_recall_cue("¿qué te conté de zeta?", today=date(2026, 11, 4))
    assert cue is not None
    assert cue.specific == frozenset()

    found = await _search(owner, cue)

    assert _ids(found) == [near]


async def test_a_unit_without_a_vector_yet_follows_the_no_distance_rule(
    owners: tuple[int, int], embed: AsyncMock
) -> None:
    owner, _ = owners
    record_id = await _record(owner)
    named = await _unit(owner, record_id, "fuimos al cerro con Zeta", axis=None)

    assert (await _search(owner, _cue("del cerro"))).hits == ()
    assert _ids(await _search(owner, _named_cue("del cerro con zeta", "zeta"))) == [named]


async def test_a_question_with_a_spoken_date_in_digits_finds_its_story(
    owners: tuple[int, int], embed: AsyncMock
) -> None:
    """Final review of Plan 0088: «el 3 de noviembre» is the window, not a word the story holds."""
    owner, _ = owners
    story = await _unit(owner, await _record(owner), "subimos el cerro")
    cue = classify_recall_cue("¿Qué te conté del cerro el 3 de noviembre?", today=date(2026, 11, 4))
    assert cue is not None

    found = await _search(owner, cue)

    assert _ids(found) == [story]
