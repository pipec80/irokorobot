"""Integration coverage for v4 literal and entity-relation repositories."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pytest
from server.memory.declarative import upsert_entity
from server.memory.predicate_registry import PredicateDefinition, resolve_predicate
from server.memory.relational_v4 import (
    AssertionLifecycle,
    assert_entity_relation,
    assert_literal_fact,
    get_active_entity_relations,
    get_active_literal_facts,
    get_entity_relation,
    get_literal_fact,
)
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
async def household_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[misc]
    """Seed a fresh v4 database with people and places for repository tests."""
    db_path = tmp_path / "memory-v4-repository.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield
    await db.close_db()
    db._conn = None


def _predicate(alias: str) -> PredicateDefinition:
    """Resolve a registry predicate required by a test fixture."""
    definition = resolve_predicate(alias)
    assert definition is not None
    return definition


@pytest.mark.integration
async def test_multi_value_literals_remain_active(household_db: None) -> None:
    """A second preference does not supersede its multi-value sibling."""
    felipe_id = await upsert_entity(name="Felipe", type="person")
    likes = _predicate("le_gusta")

    await assert_literal_fact(subject_entity_id=felipe_id, definition=likes, value="cafe")
    await assert_literal_fact(subject_entity_id=felipe_id, definition=likes, value="robotica")

    active = await get_active_literal_facts(subject_entity_id=felipe_id, definition=likes)
    assert {fact.value_text for fact in active} == {"cafe", "robotica"}


@pytest.mark.integration
async def test_failed_duplicate_literal_rolls_back_transaction(household_db: None) -> None:
    """A duplicate active literal leaves the first record as the sole active row."""
    felipe_id = await upsert_entity(name="Felipe", type="person")
    likes = _predicate("le_gusta")
    await assert_literal_fact(subject_entity_id=felipe_id, definition=likes, value="cafe")

    with pytest.raises(sqlite3.IntegrityError):
        await assert_literal_fact(subject_entity_id=felipe_id, definition=likes, value="cafe")

    active = await get_active_literal_facts(subject_entity_id=felipe_id, definition=likes)
    assert [fact.value_text for fact in active] == ["cafe"]


@pytest.mark.integration
async def test_single_current_birth_date_supersedes_prior_value(household_db: None) -> None:
    """Birth date keeps history while exposing one active canonical value."""
    maximo_id = await upsert_entity(name="Maximo", type="person")
    birth_date = _predicate("fecha_nacimiento")

    previous = await assert_literal_fact(
        subject_entity_id=maximo_id,
        definition=birth_date,
        value="2017-12-29",
    )
    current = await assert_literal_fact(
        subject_entity_id=maximo_id,
        definition=birth_date,
        value="2018-12-29",
    )

    active = await get_active_literal_facts(subject_entity_id=maximo_id, definition=birth_date)
    assert [fact.id for fact in active] == [current.id]
    historical = await get_literal_fact(previous.id)
    assert historical is not None
    assert historical.lifecycle is AssertionLifecycle.SUPERSEDED
    assert historical.superseded_at is not None


@pytest.mark.integration
async def test_temporal_relation_closes_prior_validity(household_db: None) -> None:
    """A new location retains the prior relation with a closed interval."""
    felipe_id = await upsert_entity(name="Felipe", type="person")
    santiago_id = await upsert_entity(name="Santiago", type="place")
    valparaiso_id = await upsert_entity(name="Valparaiso", type="place")
    lives_in = _predicate("vive_en")

    previous = await assert_entity_relation(
        source_entity_id=felipe_id,
        target_entity_id=santiago_id,
        definition=lives_in,
    )
    current = await assert_entity_relation(
        source_entity_id=felipe_id,
        target_entity_id=valparaiso_id,
        definition=lives_in,
    )

    active = await get_active_entity_relations(
        source_entity_id=felipe_id,
        definition=lives_in,
    )
    assert [fact.id for fact in active] == [current.id]
    historical = await get_entity_relation(previous.id)
    assert historical is not None
    assert historical.lifecycle is AssertionLifecycle.SUPERSEDED
    assert historical.valid_to is not None


@pytest.mark.integration
async def test_self_relation_is_rejected(household_db: None) -> None:
    """Entity relations reject self-links before anything is persisted."""
    felipe_id = await upsert_entity(name="Felipe", type="person")

    with pytest.raises(ValueError, match="self-relation"):
        await assert_entity_relation(
            source_entity_id=felipe_id,
            target_entity_id=felipe_id,
            definition=_predicate("hijo_de"),
        )


@pytest.mark.integration
async def test_symmetric_partner_pair_has_one_canonical_active_record(household_db: None) -> None:
    """Mirrored partner assertions resolve to one lower-ID-first relation."""
    felipe_id = await upsert_entity(name="Felipe", type="person")
    ana_id = await upsert_entity(name="Ana", type="person")
    partner_of = _predicate("pareja_de")

    first = await assert_entity_relation(
        source_entity_id=felipe_id,
        target_entity_id=ana_id,
        definition=partner_of,
    )
    mirrored = await assert_entity_relation(
        source_entity_id=ana_id,
        target_entity_id=felipe_id,
        definition=partner_of,
    )

    active = await get_active_entity_relations(definition=partner_of)
    assert len(active) == 1
    assert first.id == mirrored.id == active[0].id
    assert (active[0].source_entity_id, active[0].target_entity_id) == tuple(
        sorted((felipe_id, ana_id))
    )


@pytest.mark.integration
async def test_relation_target_filter_returns_only_active_inverse_matches(
    household_db: None,
) -> None:
    """Filter inverse child relationships by the requested parent ID."""
    felipe_id = await upsert_entity(name="Felipe", type="person")
    maximo_id = await upsert_entity(name="Maximo", type="person")
    sofia_id = await upsert_entity(name="Sofia", type="person")
    ana_id = await upsert_entity(name="Ana", type="person")
    child_of = _predicate("hijo_de")
    for child_id, parent_id in (
        (maximo_id, felipe_id),
        (sofia_id, felipe_id),
        (ana_id, sofia_id),
    ):
        await assert_entity_relation(
            source_entity_id=child_id,
            target_entity_id=parent_id,
            definition=child_of,
        )

    relations = await get_active_entity_relations(
        definition=child_of,
        target_entity_id=felipe_id,
    )

    assert {relation.source_entity_id for relation in relations} == {maximo_id, sofia_id}
    assert {relation.target_entity_id for relation in relations} == {felipe_id}
