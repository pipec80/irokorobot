"""Care contacts: a person with a phone the owner wants called or told (Plan 0070 Task 6).

ADR 0024 decision 5: a contact is operational data in a table of its own, written by one
function, classified by the writer; it opens no fact about the contact and never makes the
contact a household member. Phones are invented; no log, error or repr may hold one.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

import pytest
from server.exceptions import WriteRefusedError
from server.memory.canonical_writer import write_literal, write_relation
from server.memory.care_contacts import (
    CareContact,
    ContactRole,
    entity_has_contact_rows,
    has_active_contact,
    list_active_contacts,
    write_contact,
)
from server.memory.declarative import Guardianship, create_third_party, upsert_entity
from server.memory.household_authorization import bootstrap_initial_owner
from server.memory.write_types import ConflictPolicy, WriteChannel
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_CONFIRMED_AT = "2026-10-23T12:00:00.000000+00:00"
_PHONE = "+56900000001"
_PHONE_2 = "+56900000002"
_PHONE_ALT = "+56220000003"
_CHANNEL = WriteChannel.IMPORT_ASSISTED


@dataclass(frozen=True)
class _Home:
    owner: int
    adult_child: int
    partner: int
    relative: int
    neighbour: int
    pet: int
    town: int


@pytest.fixture
async def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Home]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "care-contacts.db")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        owner = await upsert_entity(name="Canary Owner", type="person")
        await bootstrap_initial_owner(person_entity_id=owner, confirmed_person_entity_id=owner)
        adult_child = await create_third_party(
            name="Canary Adult Child",
            type="person",
            attributes={"guardianship": Guardianship.ADULT},
        )
        partner = await create_third_party(name="Canary Partner", type="person")
        relative = await create_third_party(name="Canary Relative", type="person")
        neighbour = await create_third_party(name="Canary Neighbour", type="person")
        pet = await create_third_party(name="Canary Pet", type="other")
        town = await upsert_entity(name="Canary Town", type="place")
        for source, predicate, target in (
            (adult_child, "child_of", owner),
            (owner, "partner_of", partner),
            (owner, "has_parent", relative),
        ):
            await _relate(owner, source, predicate, target)
        yield _Home(owner, adult_child, partner, relative, neighbour, pet, town)
    finally:
        await db.close_db()
        db._conn = None


async def _relate(owner: int, source: int, predicate: str, target: int) -> None:
    await write_relation(
        owner_entity_id=owner,
        source_entity_id=source,
        predicate=predicate,
        target_entity_id=target,
        channel=_CHANNEL,
        confirmed_at=_CONFIRMED_AT,
    )


async def _contact(home: _Home, contact: int, **overrides: object) -> CareContact:
    arguments: dict[str, object] = {
        "owner_entity_id": home.owner,
        "contact_entity_id": contact,
        "role": ContactRole.CAREGIVER,
        "phone": _PHONE,
        "channel": _CHANNEL,
        "confirmed_at": _CONFIRMED_AT,
        **overrides,
    }
    return await write_contact(**arguments)  # type: ignore[arg-type]  # a test helper taking overrides


async def _count(sql: str = "SELECT COUNT(*) FROM care_contacts") -> int:
    cursor = await db.get_conn().execute(sql)
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    return int(row[0])


# --- who may be a contact -----------------------------------------------------------------------


@pytest.mark.parametrize("who", ["adult_child", "partner", "relative", "neighbour"])
async def test_an_adult_child_the_partner_a_relative_and_a_third_party_may_be_contacts(
    home: _Home, who: str
) -> None:
    row = await _contact(home, getattr(home, who))

    assert row.contact_entity_id == getattr(home, who)
    assert row.role is ContactRole.CAREGIVER
    assert (row.visibility, row.sensitivity) == ("personal", "private")
    assert row.asserted_by_entity_id == row.confirmed_by_entity_id == home.owner
    assert row.channel == "import_assisted"
    assert row.confirmed_at == _CONFIRMED_AT
    assert row.revoked_at is None


async def test_a_contact_who_holds_a_key_is_classified_location(home: _Home) -> None:
    row = await _contact(home, home.neighbour, role=ContactRole.KEY_HOLDER, has_key=True)

    assert (row.visibility, row.sensitivity) == ("personal", "location")
    assert row.has_key is True


async def test_an_unconfirmed_contact_stores_no_confirmer(home: _Home) -> None:
    row = await _contact(home, home.neighbour, confirmed_by_owner=False)

    assert row.confirmed_by_entity_id is None
    assert row.confirmed_at == _CONFIRMED_AT
    assert row.asserted_by_entity_id == home.owner


async def test_the_flags_the_phones_the_label_and_the_order_are_stored(home: _Home) -> None:
    row = await _contact(
        home,
        home.neighbour,
        phone_alt="+56 2 2000 0003",
        relationship="vecina",
        call_order=2,
        may_receive_health_info=True,
        may_view_activity=True,
    )

    assert (row.phone, row.phone_alt) == (_PHONE, _PHONE_ALT)
    assert (row.relationship, row.call_order) == ("vecina", 2)
    assert (row.may_receive_health_info, row.may_view_activity, row.has_key) == (True, True, False)


async def test_the_owner_cannot_be_their_own_contact(home: _Home) -> None:
    with pytest.raises(WriteRefusedError) as refusal:
        await _contact(home, home.owner)

    assert refusal.value.reason == "contact_is_owner"
    assert await _count() == 0


@pytest.mark.parametrize("who", ["pet", "town"])
async def test_a_pet_or_a_place_is_not_a_person(home: _Home, who: str) -> None:
    with pytest.raises(WriteRefusedError) as refusal:
        await _contact(home, getattr(home, who))

    assert refusal.value.reason == "not_a_person"
    assert await _count() == 0


async def test_a_missing_entity_is_a_value_error(home: _Home) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        await _contact(home, 9999)


# --- what is validated before anything is written -----------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"phone": "0900000001"},
        {"phone": "+5690"},
        {"phone": _PHONE, "phone_alt": "0900000001"},
        {"call_order": 0},
        {"relationship": ""},
        {"relationship": "x" * 41},
    ],
)
async def test_a_bad_phone_order_or_label_is_a_value_error_and_writes_nothing(
    home: _Home, overrides: dict[str, object]
) -> None:
    with pytest.raises(ValueError, match=r"^[^0-9]*$"):
        await _contact(home, home.neighbour, **overrides)

    assert await _count() == 0


async def test_two_active_contacts_cannot_share_a_call_order(home: _Home) -> None:
    await _contact(home, home.neighbour, call_order=1)

    with pytest.raises(WriteRefusedError) as refusal:
        await _contact(home, home.partner, call_order=1)

    assert refusal.value.reason == "order_taken"
    assert await _count() == 1


# --- one person, several roles; repeats; changes ------------------------------------------------


async def test_one_person_with_two_roles_has_two_rows_and_may_share_a_phone(home: _Home) -> None:
    first = await _contact(home, home.neighbour, role=ContactRole.CAREGIVER)
    second = await _contact(home, home.neighbour, role=ContactRole.KEY_HOLDER, has_key=True)

    assert first.id != second.id
    assert first.phone == second.phone
    assert await _count() == 2


async def test_an_identical_contact_returns_the_same_row(home: _Home) -> None:
    first = await _contact(home, home.neighbour, call_order=1, relationship="vecina")

    again = await _contact(home, home.neighbour, call_order=1, relationship="vecina")

    assert again.id == first.id
    assert await _count() == 1


@pytest.mark.parametrize(
    "change",
    [
        {"phone": _PHONE_2},
        {"phone_alt": _PHONE_ALT},
        {"call_order": 3},
        {"has_key": True},
        {"may_receive_health_info": True},
        {"may_view_activity": True},
        {"relationship": "amiga"},
    ],
)
async def test_a_changed_contact_supersedes_the_old_row_by_default(
    home: _Home, change: dict[str, object]
) -> None:
    first = await _contact(home, home.neighbour, call_order=1, relationship="vecina")

    second = await _contact(
        home, home.neighbour, **{"call_order": 1, "relationship": "vecina", **change}
    )

    assert second.id != first.id
    active = await list_active_contacts(home.owner)
    assert [row.id for row in active] == [second.id]
    assert await _count("SELECT COUNT(*) FROM care_contacts WHERE revoked_at IS NOT NULL") == 1


async def test_a_changed_contact_is_a_conflict_under_the_refusing_policy(home: _Home) -> None:
    first = await _contact(home, home.neighbour)

    with pytest.raises(WriteRefusedError) as refusal:
        await _contact(home, home.neighbour, phone=_PHONE_2, on_conflict=ConflictPolicy.REFUSE)

    assert refusal.value.reason == "value_conflict"
    assert [row.id for row in await list_active_contacts(home.owner)] == [first.id]
    assert (await list_active_contacts(home.owner))[0].phone == _PHONE


async def test_the_identical_contact_is_idempotent_under_the_refusing_policy(home: _Home) -> None:
    first = await _contact(home, home.neighbour)

    again = await _contact(home, home.neighbour, on_conflict=ConflictPolicy.REFUSE)

    assert again.id == first.id


async def test_a_refused_order_leaves_the_superseded_row_active(home: _Home) -> None:
    keep = await _contact(home, home.partner, call_order=1)
    await _contact(home, home.neighbour, call_order=2)

    with pytest.raises(WriteRefusedError):
        await _contact(home, home.neighbour, call_order=1, phone=_PHONE_2)

    assert [
        (row.contact_entity_id, row.call_order, row.phone)
        for row in (await list_active_contacts(home.owner))
    ] == [(home.partner, 1, _PHONE), (home.neighbour, 2, _PHONE)]
    assert (await list_active_contacts(home.owner))[0].id == keep.id


async def test_the_active_contacts_come_by_call_order_nulls_last_then_id(home: _Home) -> None:
    no_order = await _contact(home, home.relative)
    second = await _contact(home, home.partner, call_order=2)
    first = await _contact(home, home.neighbour, call_order=1)

    assert [row.id for row in await list_active_contacts(home.owner)] == [
        first.id,
        second.id,
        no_order.id,
    ]


async def test_the_two_presence_queries_tell_active_from_revoked(home: _Home) -> None:
    assert not await has_active_contact(home.neighbour)
    assert not await entity_has_contact_rows(home.neighbour)

    await _contact(home, home.neighbour)
    assert await has_active_contact(home.neighbour)
    assert await entity_has_contact_rows(home.neighbour)

    await db.get_conn().execute("UPDATE care_contacts SET revoked_at = ?", (_CONFIRMED_AT,))
    await db.get_conn().commit()
    assert not await has_active_contact(home.neighbour)
    assert await entity_has_contact_rows(home.neighbour)


# --- being a contact is not being a member ------------------------------------------------------


async def test_a_contact_cannot_be_relabeled_a_child_to_unlock_facts(home: _Home) -> None:
    await _contact(home, home.neighbour)

    with pytest.raises(WriteRefusedError) as refusal:
        await _relate_raw(home, home.neighbour, "child_of")

    assert refusal.value.reason == "role_conflict"


async def test_the_exact_repeat_of_a_caregiver_childs_membership_is_accepted(home: _Home) -> None:
    await _contact(home, home.adult_child)

    await _relate_raw(home, home.adult_child, "child_of")

    assert (
        await _count("SELECT COUNT(*) FROM entity_relations_v4 WHERE predicate = 'child_of'") == 1
    )


async def test_a_contact_opens_no_fact_about_them(home: _Home) -> None:
    await _contact(home, home.neighbour)

    with pytest.raises(WriteRefusedError) as refusal:
        await write_literal(
            owner_entity_id=home.owner,
            subject_entity_id=home.neighbour,
            predicate="likes",
            value="el mate",
            channel=_CHANNEL,
            confirmed_at=_CONFIRMED_AT,
        )

    assert refusal.value.reason == "not_household_member"


async def _relate_raw(home: _Home, source: int, predicate: str) -> None:
    await _relate(home.owner, source, predicate, home.owner)


# --- no phone leaves a trace --------------------------------------------------------------------


async def test_no_log_error_or_repr_holds_a_phone(
    home: _Home, caplog: pytest.LogCaptureFixture
) -> None:
    traces: list[str] = []
    with caplog.at_level(logging.DEBUG):
        row = await _contact(
            home, home.neighbour, phone_alt=_PHONE_ALT, relationship="vecina", call_order=1
        )
        await _contact(home, home.neighbour, phone=_PHONE_2, call_order=1)
        for failing in (
            _contact(home, home.owner, phone=_PHONE),
            _contact(home, home.pet, phone=_PHONE),
            _contact(home, home.partner, phone=_PHONE, call_order=1),
            _contact(home, home.relative, phone="0900000001"),
        ):
            with pytest.raises((WriteRefusedError, ValueError)) as failure:
                await failing
            traces.append(str(failure.value) + repr(failure.value) + repr(failure.value.args))
        traces.append(repr(row) + str(row))

    traces.extend(record.getMessage() + repr(vars(record)) for record in caplog.records)
    assert caplog.records
    for secret in ("56900000001", "56900000002", "56220000003", "vecina"):
        assert not any(secret in trace for trace in traces), secret
