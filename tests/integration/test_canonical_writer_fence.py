"""The canonical writer's fence: the adult child and the owner's relatives (Plan 0070 Task 4a).

ADR 0024 decisions 9 and 10: an adult child and a relative of the owner get the partner's rule
(name and relationship only), a relative can never be relabeled a member to unlock facts, and
an exact repeat of a relation that is already active is accepted so a load run twice changes
nothing. Every name is an invented canary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from server.exceptions import WriteRefusedError
from server.memory.canonical_writer import write_literal, write_relation
from server.memory.care_contacts import ContactRole, write_contact
from server.memory.declarative import Guardianship, create_third_party, upsert_entity
from server.memory.household_authorization import bootstrap_initial_owner
from server.memory.predicate_registry import resolve_predicate
from server.memory.relational_v4 import (
    assert_entity_relation,
    get_active_entity_relations,
    revoke_entity_relation,
)
from server.memory.write_types import WriteChannel
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable
    from pathlib import Path

    from server.memory.predicate_registry import PredicateDefinition
    from server.memory.relational_v4 import EntityRelationV4

pytestmark = pytest.mark.integration

_CONFIRMED_AT = "2026-10-22T12:00:00.000000+00:00"
_PHONE = "+56900000001"
_RELATIVE_PREDICATES = (
    "has_parent",
    "has_mother",
    "has_father",
    "has_grandparent",
    "has_grandchild",
    "has_sibling",
)


@dataclass(frozen=True)
class _Home:
    """An invented household: members, an adult child, relatives and a stranger."""

    owner: int
    child: int
    adult_child: int
    pet: int
    partner: int
    relative: int
    stranger: int


@pytest.fixture
async def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Home]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "canonical-fence.db")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        owner = await upsert_entity(name="Canary Owner", type="person")
        await bootstrap_initial_owner(person_entity_id=owner, confirmed_person_entity_id=owner)
        child = await create_third_party(name="Canary Minor", type="person")
        adult_child = await create_third_party(
            name="Canary Adult Child",
            type="person",
            attributes={"guardianship": Guardianship.ADULT},
        )
        pet = await create_third_party(name="Canary Pet", type="other")
        partner = await create_third_party(name="Canary Partner", type="person")
        relative = await create_third_party(name="Canary Relative", type="person")
        stranger = await create_third_party(name="Canary Stranger", type="person")
        household = _Home(owner, child, adult_child, pet, partner, relative, stranger)
        for source, predicate, target in (
            (child, "child_of", owner),
            (adult_child, "child_of", owner),
            (pet, "pet_of", owner),
            (owner, "partner_of", partner),
        ):
            await _relate(household, source, predicate, target)
        yield household
    finally:
        await db.close_db()
        db._conn = None


async def _relate(
    home: _Home,
    source: int,
    predicate: str,
    target: int,
    channel: WriteChannel = WriteChannel.IMPORT_ASSISTED,
) -> EntityRelationV4:
    return await write_relation(
        owner_entity_id=home.owner,
        source_entity_id=source,
        predicate=predicate,
        target_entity_id=target,
        channel=channel,
        confirmed_at=_CONFIRMED_AT,
    )


async def _refusal_of(call: Awaitable[object]) -> str:
    """Await *call* and return the closed reason it was refused for."""
    with pytest.raises(WriteRefusedError) as refusal:
        await call
    return refusal.value.reason


# --- the adult child ----------------------------------------------------------------------------


@pytest.mark.parametrize("channel", list(WriteChannel))
@pytest.mark.parametrize(
    "predicate,value",
    [("likes", "el tren"), ("birth_date", "1990-01-02"), ("stated_age", "31")],
)
async def test_a_fact_about_an_adult_child_is_refused_on_every_channel(
    home: _Home, channel: WriteChannel, predicate: str, value: str
) -> None:
    reason = await _refusal_of(
        write_literal(
            owner_entity_id=home.owner,
            subject_entity_id=home.adult_child,
            predicate=predicate,
            value=value,
            channel=channel,
            confirmed_at=_CONFIRMED_AT,
        )
    )

    assert reason == "not_household_member"


async def test_a_minor_is_still_a_member_whose_facts_are_stored(home: _Home) -> None:
    fact = await write_literal(
        owner_entity_id=home.owner,
        subject_entity_id=home.child,
        predicate="likes",
        value="el tren",
        channel=WriteChannel.IMPORT_ASSISTED,
        confirmed_at=_CONFIRMED_AT,
    )

    assert (fact.visibility, fact.sensitivity) == ("household", "normal")


async def test_the_membership_row_of_an_adult_child_is_accepted_and_repeats_to_the_same_row(
    home: _Home,
) -> None:
    again = await _relate(home, home.adult_child, "child_of", home.owner)

    stored = await get_active_entity_relations(
        definition=_definition("child_of"), source_entity_id=home.adult_child
    )
    assert [row.id for row in stored] == [again.id]


async def test_an_adult_child_cannot_be_declared_the_partner(home: _Home) -> None:
    reason = await _refusal_of(_relate(home, home.owner, "partner_of", home.adult_child))

    assert reason == "not_household_member"


# --- the owner's relatives ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "predicate", ["has_parent", "has_mother", "has_father", "has_grandparent", "has_grandchild"]
)
async def test_a_relative_is_stored_as_the_owners_personal_normal_row_and_repeats(
    home: _Home, predicate: str
) -> None:
    first = await _relate(home, home.owner, predicate, home.relative)
    again = await _relate(home, home.owner, predicate, home.relative, WriteChannel.IMPORT_FILE)

    assert again.id == first.id
    assert (first.visibility, first.sensitivity) == ("personal", "normal")
    assert first.asserted_by_entity_id == first.confirmed_by_entity_id == home.owner
    assert first.channel == "import_assisted"


async def test_a_sibling_is_written_from_the_owners_end_and_stored_once(home: _Home) -> None:
    first = await _relate(home, home.owner, "has_sibling", home.relative)
    again = await _relate(home, home.owner, "has_sibling", home.relative)

    assert again.id == first.id
    reason = await _refusal_of(_relate(home, home.relative, "has_sibling", home.owner))
    assert reason == "not_household_member"


@pytest.mark.parametrize("target", ["child", "adult_child", "partner", "stranger", "relative"])
async def test_a_person_to_keep_out_may_be_anyone_and_is_private(home: _Home, target: str) -> None:
    row = await _relate(home, home.owner, "withhold_from", getattr(home, target))

    assert (row.visibility, row.sensitivity) == ("personal", "private")


async def test_a_fact_about_a_relative_is_refused(home: _Home) -> None:
    await _relate(home, home.owner, "has_parent", home.relative)

    reason = await _refusal_of(
        write_literal(
            owner_entity_id=home.owner,
            subject_entity_id=home.relative,
            predicate="likes",
            value="el mate",
            channel=WriteChannel.IMPORT_ASSISTED,
            confirmed_at=_CONFIRMED_AT,
        )
    )

    assert reason == "not_household_member"


@pytest.mark.parametrize("relation", _RELATIVE_PREDICATES)
@pytest.mark.parametrize(
    "membership,owner_is_source",
    [("child_of", False), ("pet_of", False), ("partner_of", True), ("partner_of", False)],
)
async def test_a_relative_cannot_be_relabeled_a_member(
    home: _Home, relation: str, membership: str, owner_is_source: bool
) -> None:
    await _relate(home, home.owner, relation, home.relative)
    source, target = (home.owner, home.relative) if owner_is_source else (home.relative, home.owner)

    reason = await _refusal_of(_relate(home, source, membership, target))

    assert reason == "role_conflict"


@pytest.mark.parametrize("relation", _RELATIVE_PREDICATES)
@pytest.mark.parametrize("target", ["child", "adult_child", "pet", "partner"])
async def test_a_member_cannot_be_declared_a_relative(
    home: _Home, relation: str, target: str
) -> None:
    reason = await _refusal_of(_relate(home, home.owner, relation, getattr(home, target)))

    assert reason == "role_conflict"


async def test_an_exact_repeat_of_a_membership_is_accepted_even_if_the_source_holds_another_role(
    home: _Home,
) -> None:
    """A second run of a load changes nothing: the order of a load is membership first."""
    before = await get_active_entity_relations(
        definition=_definition("child_of"), source_entity_id=home.child
    )
    await assert_entity_relation(
        source_entity_id=home.owner,
        target_entity_id=home.child,
        definition=_definition("has_sibling"),
        visibility="personal",
        confirmed_by_entity_id=home.owner,
        confirmed_at=_CONFIRMED_AT,
    )

    again = await _relate(home, home.child, "child_of", home.owner)

    assert [row.id for row in before] == [again.id]


async def test_a_new_membership_for_someone_who_holds_a_relative_role_is_refused(
    home: _Home,
) -> None:
    await assert_entity_relation(
        source_entity_id=home.owner,
        target_entity_id=home.stranger,
        definition=_definition("has_grandparent"),
        visibility="personal",
        confirmed_by_entity_id=home.owner,
        confirmed_at=_CONFIRMED_AT,
    )

    reason = await _refusal_of(_relate(home, home.stranger, "child_of", home.owner))

    assert reason == "role_conflict"


async def test_a_person_to_keep_out_can_still_become_a_member(home: _Home) -> None:
    """`withhold_from` is not a role: keeping a future member out is allowed."""
    await _relate(home, home.owner, "withhold_from", home.stranger)

    row = await _relate(home, home.stranger, "child_of", home.owner)

    assert row.source_entity_id == home.stranger


def _definition(alias: str) -> PredicateDefinition:
    definition = resolve_predicate(alias)
    assert definition is not None
    return definition


# --- the side of a child (Plan 0080 D-4, Review focus 6) ------------------------------------------


@pytest.mark.parametrize("marker", ["daughter_of", "son_of"])
@pytest.mark.parametrize("child", ["child", "adult_child"])
async def test_the_side_of_a_child_is_stored_for_a_minor_and_for_an_adult_and_repeats(
    home: _Home, marker: str, child: str
) -> None:
    """A marker is a relationship: an adult child may carry it, beside the one child_of row."""
    entity = getattr(home, child)

    first = await _relate(home, entity, marker, home.owner)
    again = await _relate(home, entity, marker, home.owner, WriteChannel.IMPORT_FILE)

    assert again.id == first.id
    assert (first.visibility, first.sensitivity) == ("household", "child_data")
    assert (first.source_entity_id, first.target_entity_id) == (entity, home.owner)
    kept = await get_active_entity_relations(
        definition=_definition("child_of"), source_entity_id=entity
    )
    assert len(kept) == 1


@pytest.mark.parametrize("marker", ["daughter_of", "son_of"])
async def test_the_side_is_refused_for_the_partner_as_child_of_is(home: _Home, marker: str) -> None:
    assert await _refusal_of(_relate(home, home.partner, marker, home.owner)) == (
        await _refusal_of(_relate(home, home.partner, "child_of", home.owner))
    )
    assert await _refusal_of(_relate(home, home.partner, marker, home.owner)) == (
        "not_household_member"
    )


@pytest.mark.parametrize("marker", ["daughter_of", "son_of"])
async def test_the_side_is_refused_for_a_relative_who_is_not_a_child(
    home: _Home, marker: str
) -> None:
    await _relate(home, home.owner, "has_parent", home.relative)

    reason = await _refusal_of(_relate(home, home.relative, marker, home.owner))

    assert reason == "not_household_member"


@pytest.mark.parametrize("marker", ["daughter_of", "son_of"])
async def test_the_side_must_point_to_the_owner(home: _Home, marker: str) -> None:
    reason = await _refusal_of(_relate(home, home.owner, marker, home.child))

    assert reason == "not_household_member"


@pytest.mark.parametrize("marker", ["daughter_of", "son_of"])
@pytest.mark.parametrize("child", ["child", "adult_child"])
async def test_the_side_of_a_child_who_is_also_a_care_contact_is_stored(
    home: _Home, marker: str, child: str
) -> None:
    """An adult daughter is often the emergency contact: the marker unlocks nothing for her."""
    entity = getattr(home, child)
    await write_contact(
        owner_entity_id=home.owner,
        contact_entity_id=entity,
        role=ContactRole.EMERGENCY,
        phone=_PHONE,
        channel=WriteChannel.IMPORT_ASSISTED,
        confirmed_at=_CONFIRMED_AT,
    )

    row = await _relate(home, entity, marker, home.owner)

    assert (row.visibility, row.sensitivity) == ("household", "child_data")
    assert (row.source_entity_id, row.target_entity_id) == (entity, home.owner)


@pytest.mark.parametrize("marker", ["daughter_of", "son_of"])
async def test_the_side_of_an_entity_with_no_child_row_is_refused(home: _Home, marker: str) -> None:
    reason = await _refusal_of(_relate(home, home.stranger, marker, home.owner))

    assert reason == "not_household_member"


@pytest.mark.parametrize("marker", ["daughter_of", "son_of"])
async def test_the_side_of_a_child_whose_child_row_ended_is_refused(
    home: _Home, marker: str
) -> None:
    (row,) = await get_active_entity_relations(
        definition=_definition("child_of"), source_entity_id=home.child
    )
    await revoke_entity_relation(row.id, revoked_at=_CONFIRMED_AT)

    reason = await _refusal_of(_relate(home, home.child, marker, home.owner))

    assert reason == "not_household_member"


async def test_a_fact_about_an_adult_child_is_still_refused_after_the_side_is_stored(
    home: _Home,
) -> None:
    await _relate(home, home.adult_child, "daughter_of", home.owner)

    reason = await _refusal_of(
        write_literal(
            owner_entity_id=home.owner,
            subject_entity_id=home.adult_child,
            predicate="likes",
            value="el mate",
            channel=WriteChannel.IMPORT_ASSISTED,
            confirmed_at=_CONFIRMED_AT,
        )
    )

    assert reason == "not_household_member"
