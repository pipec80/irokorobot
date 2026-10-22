"""The canonical writer, relations and validity (Plan 0065 Task 6b, ADR 0022 decisions 2, 4, 6).

Membership relations (``child_of``, ``partner_of``, ``pet_of``) are household data with the
registry's sensitivity whatever the channel; a temporal relation closes the previous one at the
spoken date; the whole thing joins a transaction the caller owns, so an importer gets
all-or-nothing and a preview with no new API.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, cast

import pytest
from server.exceptions import WriteRefusedError
from server.memory.canonical_writer import WriteChannel, write_literal, write_relation
from server.memory.declarative import create_third_party, upsert_entity
from server.memory.household_authorization import bootstrap_initial_owner
from server.memory.predicate_registry import PredicateDefinition, resolve_predicate
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
    from collections.abc import AsyncIterator
    from pathlib import Path

_CONFIRMED_AT = "2026-10-22T12:00:00.000000+00:00"
_ASSERTED_AT = "2026-10-22T11:59:00.000000+00:00"
_VALUE_CANARY = "canary-value-for-the-log-check"


@dataclass(frozen=True)
class _Household:
    """The people, pets and places of one invented household."""

    owner: int
    child: int
    pet: int
    partner: int
    visitor: int
    town: int
    city: int


@pytest.fixture
async def household(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Household]:
    """A migrated database with an owner, a child, a pet, a partner, a stranger and two places."""
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "canonical-relations.db")
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    try:
        owner = await upsert_entity(name="Canary Owner", type="person")
        await bootstrap_initial_owner(person_entity_id=owner, confirmed_person_entity_id=owner)
        child = await upsert_entity(name="Canary Child", type="person")
        pet = await upsert_entity(name="Canary Pet", type="other")
        partner = await upsert_entity(name="Canary Partner", type="person")
        visitor = await upsert_entity(name="Canary Visitor", type="person")
        town = await upsert_entity(name="Canary Town", type="place")
        city = await upsert_entity(name="Canary City", type="place")
        for source, alias in ((child, "child_of"), (pet, "pet_of")):
            await assert_entity_relation(
                source_entity_id=source, target_entity_id=owner, definition=_definition(alias)
            )
        yield _Household(owner, child, pet, partner, visitor, town, city)
    finally:
        await db.close_db()
        db._conn = None


def _definition(alias: str) -> PredicateDefinition:
    definition = resolve_predicate(alias)
    assert definition is not None
    return definition


async def _counts() -> tuple[int, int, int]:
    """Rows in the literal, relation and entity tables."""
    conn = db.get_conn()
    counts: list[int] = []
    for table in ("literal_facts_v4", "entity_relations_v4", "entities"):
        cursor = await conn.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
        row = await cursor.fetchone()
        await cursor.close()
        assert row is not None
        counts.append(int(row[0]))
    return counts[0], counts[1], counts[2]


async def _relate(
    home: _Household,
    source: int,
    predicate: str,
    target: int,
    channel: WriteChannel = WriteChannel.IMPORT_FILE,
    *,
    valid_from: str | None = None,
    valid_to: str | None = None,
) -> EntityRelationV4:
    return await write_relation(
        owner_entity_id=home.owner,
        source_entity_id=source,
        predicate=predicate,
        target_entity_id=target,
        channel=channel,
        confirmed_at=_CONFIRMED_AT,
        asserted_at=_ASSERTED_AT,
        valid_from=valid_from,
        valid_to=valid_to,
    )


@pytest.mark.integration
@pytest.mark.parametrize("channel", list(WriteChannel))
async def test_membership_relations_are_household_data_from_every_channel(
    household: _Household, channel: WriteChannel
) -> None:
    """Whatever the channel, ``child_of``, ``partner_of`` and ``pet_of`` store alike."""
    second_child = await create_third_party(name=f"Canary Child {channel.value}", type="person")
    second_pet = await create_third_party(name=f"Canary Pet {channel.value}", type="other")

    child = await _relate(household, second_child, "child_of", household.owner, channel)
    pet = await _relate(household, second_pet, "pet_of", household.owner, channel)
    partner = await _relate(household, household.owner, "partner_of", household.partner, channel)

    for relation, alias in ((child, "child_of"), (pet, "pet_of"), (partner, "partner_of")):
        registry = _definition(alias)
        assert (relation.visibility, relation.sensitivity) == (
            "household",
            registry.default_sensitivity,
        )
        assert relation.asserted_by_entity_id == household.owner
        assert relation.confirmed_by_entity_id == household.owner
        assert relation.confirmed_at == _CONFIRMED_AT
        assert relation.channel == channel.value
        assert relation.lifecycle is AssertionLifecycle.ACTIVE


@pytest.mark.integration
async def test_partner_of_is_symmetric_so_the_order_of_the_ids_changes_nothing(
    household: _Household,
) -> None:
    forward = await _relate(household, household.owner, "partner_of", household.partner)
    backward = await _relate(
        household, household.partner, "partner_of", household.owner, WriteChannel.VOICE_STREAM
    )

    assert backward.id == forward.id
    assert (backward.visibility, backward.sensitivity) == ("household", "normal")
    active = await get_active_entity_relations(definition=_definition("partner_of"))
    assert len(active) == 1


@pytest.mark.integration
@pytest.mark.parametrize(
    "source, predicate, target",
    [
        ("owner", "child_of", "visitor"),
        ("visitor", "partner_of", "partner"),
        ("partner", "lives_in", "town"),
        ("visitor", "works_at", "city"),
    ],
)
async def test_relations_outside_the_owners_world_are_refused(
    household: _Household, source: str, predicate: str, target: str
) -> None:
    """Only the owner's children, partner and pets; the partner's own facts wait for `family`."""
    before = await _counts()

    with pytest.raises(WriteRefusedError) as refusal:
        await _relate(
            household,
            getattr(household, source),
            predicate,
            getattr(household, target),
        )

    assert refusal.value.reason == "not_household_member"
    assert await _counts() == before


@pytest.mark.integration
async def test_a_temporal_relation_with_a_spoken_date_closes_the_previous_row_at_that_date(
    household: _Household,
) -> None:
    previous = await _relate(
        household, household.owner, "lives_in", household.town, valid_from="2018-03-01"
    )
    current = await _relate(
        household, household.owner, "lives_in", household.city, valid_from="2024-06-15"
    )

    closed = await get_entity_relation(previous.id)
    assert closed is not None
    assert closed.lifecycle is AssertionLifecycle.SUPERSEDED
    assert closed.valid_to == "2024-06-15" == current.valid_from
    # The owner's own location is personal data with the registry's sensitivity.
    assert (current.visibility, current.sensitivity) == ("personal", "location")


@pytest.mark.integration
async def test_a_place_given_as_past_is_stored_as_history(household: _Household) -> None:
    current = await _relate(
        household, household.owner, "lives_in", household.city, valid_from="2024-06-15"
    )

    past = await _relate(
        household, household.owner, "lives_in", household.town, valid_to="2019-12-31"
    )

    assert past.lifecycle is AssertionLifecycle.EXPIRED
    assert (past.valid_from, past.valid_to) == (None, "2019-12-31")
    active = await get_active_entity_relations(
        source_entity_id=household.owner, definition=_definition("lives_in")
    )
    assert [row.id for row in active] == [current.id]


@pytest.mark.integration
async def test_a_child_or_a_pet_can_live_somewhere_as_household_data(
    household: _Household,
) -> None:
    child_home = await _relate(household, household.child, "lives_in", household.town)
    pet_home = await _relate(household, household.pet, "lives_in", household.city)

    assert (child_home.visibility, child_home.sensitivity) == ("household", "location")
    assert (pet_home.visibility, pet_home.sensitivity) == ("household", "location")


@pytest.mark.integration
async def test_a_relation_to_a_third_party_created_by_the_importer_is_accepted(
    household: _Household,
) -> None:
    """The initial import creates third parties apart and relates them through the writer."""
    cousin_town = await create_third_party(name="Canary Cousin Town", type="place", import_key="p1")

    relation = await _relate(household, household.child, "lives_in", cousin_town)

    assert relation.target_entity_id == cousin_town
    assert relation.channel == "import_file"


@pytest.mark.integration
@pytest.mark.parametrize(
    "predicate, channel",
    [("likes", WriteChannel.IMPORT_FILE), ("inventado", WriteChannel.IMPORT_FILE)],
)
async def test_a_literal_or_unknown_predicate_is_not_a_relation(
    household: _Household, predicate: str, channel: WriteChannel
) -> None:
    with pytest.raises(ValueError, match=r"."):
        await _relate(household, household.child, predicate, household.owner, channel)

    with pytest.raises(ValueError, match=r"."):
        await write_relation(
            owner_entity_id=household.owner,
            source_entity_id=household.child,
            predicate="lives_in",
            target_entity_id=household.town,
            channel=cast("WriteChannel", "telepathy"),
            confirmed_at=_CONFIRMED_AT,
        )


@pytest.mark.integration
async def test_a_batch_is_atomic_inside_a_transaction_the_caller_owns(
    household: _Household, caplog: pytest.LogCaptureFixture
) -> None:
    """An importer: several writes in one caller transaction, one refused, nothing remains.

    This is what all-or-nothing and a preview need, with no new API: the third party, the literal
    and the relation commit with the caller or vanish with it.
    """
    before = await _counts()

    async def importer() -> None:
        async with db.transaction():
            new_child = await create_third_party(
                name="Canary Grandchild",
                type="person",
                import_key="g1",
                manage_transaction=False,
            )
            await write_relation(
                owner_entity_id=household.owner,
                source_entity_id=new_child,
                predicate="child_of",
                target_entity_id=household.owner,
                channel=WriteChannel.IMPORT_FILE,
                confirmed_at=_CONFIRMED_AT,
                manage_transaction=False,
            )
            await write_literal(
                owner_entity_id=household.owner,
                subject_entity_id=new_child,
                predicate="likes",
                value="el tren",
                channel=WriteChannel.IMPORT_FILE,
                confirmed_at=_CONFIRMED_AT,
                manage_transaction=False,
            )
            # The third write is refused: a fact about an outsider.
            await write_literal(
                owner_entity_id=household.owner,
                subject_entity_id=household.visitor,
                predicate="likes",
                value=_VALUE_CANARY,
                channel=WriteChannel.IMPORT_FILE,
                confirmed_at=_CONFIRMED_AT,
                manage_transaction=False,
            )

    with caplog.at_level(logging.DEBUG), pytest.raises(WriteRefusedError) as refusal:
        await importer()

    assert refusal.value.reason == "not_household_member"
    assert await _counts() == before
    assert all(
        _VALUE_CANARY not in record.getMessage() and _VALUE_CANARY not in repr(vars(record))
        for record in caplog.records
    )


@pytest.mark.integration
async def test_the_same_batch_commits_when_nothing_is_refused(household: _Household) -> None:
    async with db.transaction():
        new_child = await create_third_party(
            name="Canary Grandchild", type="person", import_key="g1", manage_transaction=False
        )
        await write_relation(
            owner_entity_id=household.owner,
            source_entity_id=new_child,
            predicate="child_of",
            target_entity_id=household.owner,
            channel=WriteChannel.IMPORT_FILE,
            confirmed_at=_CONFIRMED_AT,
            manage_transaction=False,
        )
        fact = await write_literal(
            owner_entity_id=household.owner,
            subject_entity_id=new_child,
            predicate="stated_age",
            value="2",
            channel=WriteChannel.IMPORT_FILE,
            confirmed_at=_CONFIRMED_AT,
            manage_transaction=False,
        )

    assert (fact.visibility, fact.sensitivity) == ("household", "child_data")
    assert fact.subject_entity_id == new_child


@pytest.mark.integration
async def test_the_writer_cannot_tell_an_adult_child_from_a_minor(household: _Household) -> None:
    """«Child» is a child in the owner's guardianship (D-2); an adult child is a Step 0 decision.

    The writer has no age to consult: it classifies whoever the owner declares as their child
    alike, so nothing here pretends to solve the adult-child gap ADR 0022 names.
    """
    adult_child = await _relate(household, household.visitor, "child_of", household.owner)
    fact = await write_literal(
        owner_entity_id=household.owner,
        subject_entity_id=household.visitor,
        predicate="likes",
        value="el jazz",
        channel=WriteChannel.IMPORT_FILE,
        confirmed_at=_CONFIRMED_AT,
    )

    assert (adult_child.visibility, adult_child.sensitivity) == ("household", "child_data")
    assert (fact.visibility, fact.sensitivity) == ("household", "normal")
