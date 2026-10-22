"""A V4 relation carries a classification, a confirmer, a provenance and a validity (Plan 0065).

Mirrors what ``assert_literal_fact`` already accepts (ADR 0021 decision 8) and adds the validity
range ADR 0022 decision 6 asks for. Every date is a fixed ISO string: nothing compares against
the real clock.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from server.exceptions import SecurityStorageUndecidedError
from server.memory.declarative import upsert_entity
from server.memory.predicate_registry import (
    PredicateCardinality,
    PredicateDefinition,
    PredicateKind,
    resolve_predicate,
)
from server.memory.relational_v4 import (
    AssertionLifecycle,
    EntityRelationV4,
    assert_entity_relation,
    get_active_entity_relations,
    get_entity_relation,
)
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from pathlib import Path

_ASSERTED_AT = "2026-10-20T10:00:00.000000+00:00"
_CONFIRMED_AT = "2026-10-20T10:00:05.000000+00:00"


@pytest.fixture
async def relation_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[misc]
    """Open a fresh, fully migrated database."""
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "relation-classification.db")
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield
    await db.close_db()
    db._conn = None


def _predicate(alias: str) -> PredicateDefinition:
    definition = resolve_predicate(alias)
    assert definition is not None
    return definition


async def _people_and_places() -> tuple[int, int, int, int]:
    owner = await upsert_entity(name="Canary Owner", type="person")
    child = await upsert_entity(name="Canary Child", type="person")
    town = await upsert_entity(name="Canary Town", type="place")
    city = await upsert_entity(name="Canary City", type="place")
    return owner, child, town, city


@pytest.mark.integration
async def test_a_relation_stores_and_returns_what_it_is_given(relation_db: None) -> None:
    owner, child, _town, _city = await _people_and_places()

    relation = await assert_entity_relation(
        source_entity_id=child,
        target_entity_id=owner,
        definition=_predicate("child_of"),
        confidence=1.0,
        asserted_at=_ASSERTED_AT,
        visibility="adults",
        sensitivity="private",
        confirmed_by_entity_id=owner,
        confirmed_at=_CONFIRMED_AT,
        valid_from="2019-04-02",
        asserted_by_entity_id=owner,
        channel="import_file",
    )

    assert relation.visibility == "adults"
    assert relation.sensitivity == "private"
    assert relation.confirmed_by_entity_id == owner
    assert relation.confirmed_at == _CONFIRMED_AT
    assert relation.valid_from == "2019-04-02"
    assert relation.valid_to is None
    assert relation.asserted_by_entity_id == owner
    assert relation.channel == "import_file"
    assert await get_entity_relation(relation.id) == relation


@pytest.mark.integration
async def test_with_no_argument_the_stored_values_are_the_registry_defaults(
    relation_db: None,
) -> None:
    """Today's behaviour (the local setup, the legacy migration) must not move."""
    owner, child, _town, _city = await _people_and_places()
    child_of = _predicate("child_of")

    relation = await assert_entity_relation(
        source_entity_id=child, target_entity_id=owner, definition=child_of
    )

    assert (relation.visibility, relation.sensitivity) == (
        child_of.default_visibility,
        child_of.default_sensitivity,
    )
    assert relation.confirmed_by_entity_id is None
    assert relation.confirmed_at is None
    assert relation.asserted_by_entity_id is None
    assert relation.channel is None
    assert relation.valid_from is None
    assert relation.valid_to is None
    assert relation.lifecycle is AssertionLifecycle.ACTIVE


@pytest.mark.integration
@pytest.mark.parametrize("alias", ["lives_in", "works_at"])
async def test_a_temporal_relation_closes_the_previous_one_at_the_new_valid_from(
    relation_db: None, alias: str
) -> None:
    """The previous row ends where the new one begins, never at the moment of the write."""
    owner, _child, town, city = await _people_and_places()
    definition = _predicate(alias)

    previous = await assert_entity_relation(
        source_entity_id=owner,
        target_entity_id=town,
        definition=definition,
        asserted_at=_ASSERTED_AT,
        valid_from="2018-03-01",
    )
    current = await assert_entity_relation(
        source_entity_id=owner,
        target_entity_id=city,
        definition=definition,
        asserted_at=_ASSERTED_AT,
        valid_from="2024-06-15",
    )

    closed = await get_entity_relation(previous.id)
    assert closed is not None
    assert closed.lifecycle is AssertionLifecycle.SUPERSEDED
    assert closed.valid_from == "2018-03-01"
    assert closed.valid_to == "2024-06-15" == current.valid_from
    assert closed.superseded_by == current.id
    active = await get_active_entity_relations(source_entity_id=owner, definition=definition)
    assert [row.id for row in active] == [current.id]


@pytest.mark.integration
async def test_without_a_spoken_date_a_temporal_relation_begins_at_its_assertion_date(
    relation_db: None,
) -> None:
    owner, _child, town, city = await _people_and_places()
    lives_in = _predicate("lives_in")

    previous = await assert_entity_relation(
        source_entity_id=owner,
        target_entity_id=town,
        definition=lives_in,
        asserted_at="2020-01-05T08:00:00.000000+00:00",
    )
    current = await assert_entity_relation(
        source_entity_id=owner,
        target_entity_id=city,
        definition=lives_in,
        asserted_at=_ASSERTED_AT,
    )

    assert previous.valid_from == "2020-01-05T08:00:00.000000+00:00"
    assert current.valid_from == _ASSERTED_AT
    closed = await get_entity_relation(previous.id)
    assert closed is not None
    assert closed.valid_to == _ASSERTED_AT


@pytest.mark.integration
async def test_a_past_relation_is_stored_as_history_and_never_closes_the_current_one(
    relation_db: None,
) -> None:
    """An explicit ``valid_to`` inserts an expired row: no supersede, no ``valid_from`` needed."""
    owner, _child, town, city = await _people_and_places()
    lives_in = _predicate("lives_in")
    current = await assert_entity_relation(
        source_entity_id=owner,
        target_entity_id=city,
        definition=lives_in,
        asserted_at=_ASSERTED_AT,
        valid_from="2024-06-15",
    )

    past = await assert_entity_relation(
        source_entity_id=owner,
        target_entity_id=town,
        definition=lives_in,
        asserted_at=_ASSERTED_AT,
        valid_to="2019-12-31",
    )
    # The same place the owner lives in now, in an earlier stretch: no clash with the active
    # triple, because the history row is not active.
    earlier_same_place = await assert_entity_relation(
        source_entity_id=owner,
        target_entity_id=city,
        definition=lives_in,
        asserted_at=_ASSERTED_AT,
        valid_from="2010-01-01",
        valid_to="2012-12-31",
    )

    assert past.lifecycle is AssertionLifecycle.EXPIRED
    assert past.valid_from is None
    assert past.valid_to == "2019-12-31"
    assert earlier_same_place.lifecycle is AssertionLifecycle.EXPIRED
    assert (earlier_same_place.valid_from, earlier_same_place.valid_to) == (
        "2010-01-01",
        "2012-12-31",
    )
    still_current = await get_entity_relation(current.id)
    assert still_current == current
    active = await get_active_entity_relations(source_entity_id=owner, definition=lives_in)
    assert [row.id for row in active] == [current.id]


@pytest.mark.integration
async def test_repeating_a_history_row_returns_the_one_already_stored(relation_db: None) -> None:
    owner, _child, town, _city = await _people_and_places()

    async def history() -> EntityRelationV4:
        return await assert_entity_relation(
            source_entity_id=owner,
            target_entity_id=town,
            definition=_predicate("lives_in"),
            asserted_at=_ASSERTED_AT,
            valid_from="2015-02-01",
            valid_to="2019-12-31",
        )

    first = await history()
    again = await history()

    assert again.id == first.id
    cursor = await db.get_conn().execute("SELECT COUNT(*) FROM entity_relations_v4")
    assert await cursor.fetchone() == (1,)
    await cursor.close()


@pytest.mark.integration
async def test_an_exact_repeat_keeps_the_row_it_finds_untouched(relation_db: None) -> None:
    """Documented: a ``child_of`` made by the local setup keeps no confirmer when repeated."""
    owner, child, _town, _city = await _people_and_places()
    child_of = _predicate("child_of")
    first = await assert_entity_relation(
        source_entity_id=child, target_entity_id=owner, definition=child_of
    )

    again = await assert_entity_relation(
        source_entity_id=child,
        target_entity_id=owner,
        definition=child_of,
        visibility="private",
        confirmed_by_entity_id=owner,
        confirmed_at=_CONFIRMED_AT,
        asserted_by_entity_id=owner,
        channel="voice_stream",
    )

    assert again == first
    assert again.confirmed_by_entity_id is None
    assert (again.visibility, again.channel) == (first.visibility, None)


@pytest.mark.integration
@pytest.mark.parametrize(
    "valid_from, valid_to",
    [
        ("14 de octubre", None),
        ("2024-13-01", None),
        ("2024-02-30", None),
        (None, "ayer"),
        ("2024-06-15", "2020-01-01"),
    ],
)
async def test_validity_dates_must_be_iso_and_ordered(
    relation_db: None, valid_from: str | None, valid_to: str | None
) -> None:
    owner, _child, town, _city = await _people_and_places()

    with pytest.raises(ValueError, match="valid_"):
        await assert_entity_relation(
            source_entity_id=owner,
            target_entity_id=town,
            definition=_predicate("lives_in"),
            valid_from=valid_from,
            valid_to=valid_to,
        )

    assert (
        await get_active_entity_relations(source_entity_id=owner, definition=_predicate("lives_in"))
        == []
    )


@pytest.mark.integration
async def test_a_month_alone_is_a_valid_date(relation_db: None) -> None:
    owner, _child, town, _city = await _people_and_places()

    relation = await assert_entity_relation(
        source_entity_id=owner,
        target_entity_id=town,
        definition=_predicate("lives_in"),
        valid_from="2022-09",
        valid_to="2023-03",
    )

    assert (relation.valid_from, relation.valid_to) == ("2022-09", "2023-03")


@pytest.mark.integration
async def test_a_relation_chosen_as_security_is_refused_without_a_trace(
    relation_db: None,
) -> None:
    owner, child, _town, _city = await _people_and_places()

    with pytest.raises(SecurityStorageUndecidedError):
        await assert_entity_relation(
            source_entity_id=child,
            target_entity_id=owner,
            definition=_predicate("child_of"),
            sensitivity="security",
        )

    cursor = await db.get_conn().execute("SELECT COUNT(*) FROM entity_relations_v4")
    assert await cursor.fetchone() == (0,)
    await cursor.close()


@pytest.mark.unit
def test_no_relation_predicate_is_single_current() -> None:
    """The plan relies on it: only ``temporal`` relations ever close a previous row."""
    for alias in ("child_of", "partner_of", "pet_of", "lives_in", "works_at"):
        definition = _predicate(alias)
        assert definition.kind is PredicateKind.RELATION
        assert definition.cardinality is not PredicateCardinality.SINGLE_CURRENT
