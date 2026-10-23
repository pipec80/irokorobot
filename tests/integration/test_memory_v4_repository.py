"""Integration coverage for v4 literal and entity-relation repositories."""

from __future__ import annotations

import logging
import sqlite3
from typing import TYPE_CHECKING

import pytest
from server.exceptions import UnstorableValueError
from server.memory.declarative import upsert_entity
from server.memory.predicate_registry import (
    PredicateCardinality,
    PredicateDefinition,
    PredicateKind,
    resolve_predicate,
)
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
    try:
        await db.open_db()
        await db.run_migrations()
        yield
    finally:
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
    maximo_id = await upsert_entity(name="Joaquin", type="person")
    birth_date = _predicate("fecha_nacimiento")

    previous = await assert_literal_fact(
        subject_entity_id=maximo_id,
        definition=birth_date,
        value="2016-10-14",
    )
    current = await assert_literal_fact(
        subject_entity_id=maximo_id,
        definition=birth_date,
        value="2017-10-14",
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
    maximo_id = await upsert_entity(name="Joaquin", type="person")
    sofia_id = await upsert_entity(name="Paula", type="person")
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


@pytest.mark.integration
async def test_a_literal_carries_who_confirmed_it_and_when(household_db: None) -> None:
    """ADR 0021 decision 8: the writer states the confirmation, the repository stores it."""
    owner_id = await upsert_entity(name="Felipe", type="person")
    likes = _predicate("likes")

    fact = await assert_literal_fact(
        subject_entity_id=owner_id,
        definition=likes,
        value="el mate",
        confirmed_by_entity_id=owner_id,
        confirmed_at="2026-10-14T10:00:00.000000+00:00",
    )

    assert fact.confirmed_by_entity_id == owner_id
    assert fact.confirmed_at == "2026-10-14T10:00:00.000000+00:00"
    stored = await get_literal_fact(fact.id)
    assert stored == fact


@pytest.mark.integration
async def test_an_unconfirmed_literal_has_no_confirmation(household_db: None) -> None:
    owner_id = await upsert_entity(name="Felipe", type="person")

    fact = await assert_literal_fact(
        subject_entity_id=owner_id, definition=_predicate("likes"), value="cafe"
    )

    assert fact.confirmed_by_entity_id is None
    assert fact.confirmed_at is None


@pytest.mark.integration
async def test_the_caller_chooses_visibility_and_sensitivity_without_changing_the_registry(
    household_db: None,
) -> None:
    """The registry default is the household reader's read contract and does not move."""
    owner_id = await upsert_entity(name="Felipe", type="person")
    likes = _predicate("likes")
    default_visibility = likes.default_visibility

    explicit = await assert_literal_fact(
        subject_entity_id=owner_id,
        definition=likes,
        value="el mate",
        visibility="personal",
        sensitivity="private",
    )
    implicit = await assert_literal_fact(
        subject_entity_id=owner_id, definition=likes, value="el cafe"
    )

    assert (explicit.visibility, explicit.sensitivity) == ("personal", "private")
    assert (implicit.visibility, implicit.sensitivity) == (default_visibility, "normal")
    assert _predicate("likes").default_visibility == default_visibility == "household"


@pytest.mark.integration
async def test_an_unknown_visibility_is_refused_by_the_schema(household_db: None) -> None:
    owner_id = await upsert_entity(name="Felipe", type="person")

    with pytest.raises(sqlite3.IntegrityError):
        await assert_literal_fact(
            subject_entity_id=owner_id,
            definition=_predicate("likes"),
            value="el mate",
            visibility="everyone",
        )


async def _write_inside_a_failing_transaction(owner_id: int, likes: PredicateDefinition) -> None:
    """Write a literal into a caller-owned transaction, then fail the caller."""
    async with db.transaction():
        await assert_literal_fact(
            subject_entity_id=owner_id,
            definition=likes,
            value="el mate",
            manage_transaction=False,
        )
        raise RuntimeError("caller rolled back")


@pytest.mark.integration
async def test_a_caller_owned_transaction_neither_opens_nor_commits_its_own(
    household_db: None,
) -> None:
    """`manage_transaction=False` joins the caller's `db.transaction()` (and is not reentrant)."""
    owner_id = await upsert_entity(name="Felipe", type="person")
    likes = _predicate("likes")

    with pytest.raises(RuntimeError, match="caller rolled back"):
        await _write_inside_a_failing_transaction(owner_id, likes)

    assert await get_active_literal_facts(subject_entity_id=owner_id, definition=likes) == []


# --- Plan 0065 (ADR 0022 decision 9): the repository stores no SECURITY value yet --------------

_CODE_CANARY = "canary-gate-code-5150"


async def _row_counts() -> tuple[int, int]:
    """Count every literal and relation row, whatever its lifecycle."""
    conn = db.get_conn()
    counts: list[int] = []
    for table in ("literal_facts_v4", "entity_relations_v4"):
        cursor = await conn.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
        row = await cursor.fetchone()
        await cursor.close()
        assert row is not None
        counts.append(int(row[0]))
    return counts[0], counts[1]


@pytest.mark.integration
async def test_a_security_literal_is_refused_and_leaves_no_trace(
    household_db: None, caplog: pytest.LogCaptureFixture
) -> None:
    """Storage at rest is undecided (Step 0): refuse before any write, any log, any message."""
    owner_id = await upsert_entity(name="Canary Owner", type="person")

    with caplog.at_level(logging.DEBUG):
        logging.getLogger("server.memory.relational_v4").debug("control record")
        with pytest.raises(UnstorableValueError) as refusal:
            await assert_literal_fact(
                subject_entity_id=owner_id,
                definition=_predicate("access_code"),
                value=_CODE_CANARY,
            )

    assert any(record.getMessage() == "control record" for record in caplog.records)
    assert await _row_counts() == (0, 0)
    assert _CODE_CANARY not in str(refusal.value)
    assert _CODE_CANARY not in repr(refusal.value)
    assert _CODE_CANARY not in repr(refusal.value.args)
    assert all(
        _CODE_CANARY not in record.getMessage() and _CODE_CANARY not in repr(vars(record))
        for record in caplog.records
    )


@pytest.mark.integration
async def test_a_security_sensitivity_chosen_by_the_caller_is_refused_too(
    household_db: None,
) -> None:
    """The refusal covers the effective sensitivity, not only the registry default."""
    owner_id = await upsert_entity(name="Canary Owner", type="person")

    with pytest.raises(UnstorableValueError):
        await assert_literal_fact(
            subject_entity_id=owner_id,
            definition=_predicate("likes"),
            value=_CODE_CANARY,
            sensitivity="security",
        )

    assert await _row_counts() == (0, 0)


@pytest.mark.integration
async def test_a_relation_whose_predicate_defaults_to_security_is_refused(
    household_db: None,
) -> None:
    """No relation predicate is SECURITY today; the repository still refuses the shape."""
    owner_id = await upsert_entity(name="Canary Owner", type="person")
    other_id = await upsert_entity(name="Canary Neighbour", type="person")
    security_relation = PredicateDefinition(
        canonical_id="shares_code_with",
        aliases=frozenset({"shares_code_with"}),
        kind=PredicateKind.RELATION,
        cardinality=PredicateCardinality.RELATION,
        subject_types=frozenset({"person"}),
        target_types=frozenset({"person"}),
        default_sensitivity="security",
    )

    with pytest.raises(UnstorableValueError):
        await assert_entity_relation(
            source_entity_id=owner_id, target_entity_id=other_id, definition=security_relation
        )

    assert await _row_counts() == (0, 0)


@pytest.mark.integration
async def test_the_new_household_literals_store_with_their_registry_classification(
    household_db: None,
) -> None:
    owner_id = await upsert_entity(name="Canary Owner", type="person")
    pet_id = await upsert_entity(name="Canary Pet", type="other")

    species = await assert_literal_fact(
        subject_entity_id=pet_id, definition=_predicate("species"), value="gato"
    )
    pet_age = await assert_literal_fact(
        subject_entity_id=pet_id, definition=_predicate("stated_age"), value="3"
    )
    owner_age = await assert_literal_fact(
        subject_entity_id=owner_id, definition=_predicate("stated_age"), value="41"
    )
    topic = await assert_literal_fact(
        subject_entity_id=owner_id, definition=_predicate("private_topic"), value="salud"
    )

    assert (species.visibility, species.sensitivity) == ("household", "normal")
    assert (pet_age.visibility, pet_age.sensitivity, pet_age.value_text) == (
        "household",
        "child_data",
        "3",
    )
    assert (owner_age.visibility, owner_age.sensitivity) == ("household", "child_data")
    assert (topic.visibility, topic.sensitivity) == ("personal", "normal")
    with pytest.raises(ValueError, match="subject type"):
        await assert_literal_fact(
            subject_entity_id=owner_id, definition=_predicate("species"), value="gato"
        )
    with pytest.raises(ValueError, match="subject type"):
        await assert_literal_fact(
            subject_entity_id=pet_id, definition=_predicate("private_topic"), value="salud"
        )
    with pytest.raises(ValueError, match="canonical literal"):
        await assert_literal_fact(
            subject_entity_id=pet_id, definition=_predicate("stated_age"), value="ocho"
        )


@pytest.mark.integration
async def test_a_stated_age_supersedes_the_previous_one(household_db: None) -> None:
    """Single current: «tiene 7» then «tiene 8» keeps one active age (as-of = asserted_at)."""
    child_id = await upsert_entity(name="Canary Child", type="person")
    stated_age = _predicate("stated_age")

    first = await assert_literal_fact(
        subject_entity_id=child_id,
        definition=stated_age,
        value="7",
        asserted_at="2026-01-10T09:00:00.000000+00:00",
    )
    second = await assert_literal_fact(
        subject_entity_id=child_id,
        definition=stated_age,
        value="8",
        asserted_at="2027-02-11T09:00:00.000000+00:00",
    )

    active = await get_active_literal_facts(subject_entity_id=child_id, definition=stated_age)
    assert [fact.value_text for fact in active] == ["8"]
    assert active[0].asserted_at == second.asserted_at == "2027-02-11T09:00:00.000000+00:00"
    superseded = await get_literal_fact(first.id)
    assert superseded is not None
    assert superseded.lifecycle is AssertionLifecycle.SUPERSEDED
