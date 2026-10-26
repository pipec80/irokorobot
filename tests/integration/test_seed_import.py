"""The applier: the ready owner, the writes, idempotence and conflicts (Plan 0071 Task 4a).

ADR 0024 decisions 6, 7, 8 and 11: the importer writes through the canonical writers with the
channel ``import_assisted`` and the refuse policy, the owner asserts, and nothing it reports or
logs holds a name, a value or a phone. Every name, phone and value is an invented canary.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import SecretStr
import pytest
from server.exceptions import SeedOwnerError
from server.memory.care_contacts import ContactRole, count_active_contacts, write_contact
from server.memory.declarative import count_entities, create_third_party, upsert_entity
from server.memory.household_authorization import bootstrap_initial_owner
from server.memory.relational_v4 import count_v4_rows
from server.memory.seed_import import (
    OperationOutcome,
    OperationStatus,
    resolve_ready_owner,
    run_operations,
)
from server.memory.seed_plan import OperationKind
from server.memory.write_types import WriteChannel
from server.personal_setup import PersonalSetupInput, apply_personal_setup

from server import db
from tests.integration.seed_household import NOW, OWNER_NAME, owner, plan_of, scalar, seed_db
from tests.unit.seed_data import Toml, full_seed

if TYPE_CHECKING:
    from pathlib import Path

    from server.memory.seed_plan import SeedPlan

__all__ = ["owner", "seed_db"]

pytestmark = pytest.mark.integration

_SECRETS = (
    "Canary",
    "canary",
    "+5690",
    "+5620",
    "té verde",
    "hija",
    "1950-05-17",
    "gato",
    "testamento",
    "alarma",
)


async def _apply(
    plan: SeedPlan, owner_id: int, *, confirmed: bool = True
) -> list[OperationOutcome]:
    async with db.transaction():
        outcomes = await run_operations(
            plan, owner_entity_id=owner_id, now=NOW, confirmed_by_owner=confirmed
        )
    return list(outcomes)


def _problems(outcomes: list[OperationOutcome]) -> list[tuple[str, str | None]]:
    return [
        (outcome.operation.label, outcome.reason)
        for outcome in outcomes
        if outcome.status in {OperationStatus.REFUSED, OperationStatus.SKIPPED}
    ]


async def _snapshot() -> tuple[object, ...]:
    return (await count_v4_rows(), await count_entities(), await count_active_contacts())


# --- the owner --------------------------------------------------------------------------------


async def test_a_ready_owner_is_resolved_by_a_folded_name(owner: int) -> None:
    assert await resolve_ready_owner(OWNER_NAME) == owner
    assert await resolve_ready_owner("CANARY ówner") == owner


async def test_a_database_without_an_owner_is_refused_and_nothing_is_created(seed_db: Path) -> None:
    del seed_db
    with pytest.raises(SeedOwnerError) as caught:
        await resolve_ready_owner(OWNER_NAME)

    assert caught.value.reason == "owner_not_ready"
    assert await count_entities() == 0


async def test_an_owner_without_a_pin_is_not_ready(seed_db: Path) -> None:
    del seed_db
    owner_id = await upsert_entity(name=OWNER_NAME, type="person")
    await bootstrap_initial_owner(person_entity_id=owner_id, confirmed_person_entity_id=owner_id)

    with pytest.raises(SeedOwnerError) as caught:
        await resolve_ready_owner(OWNER_NAME)

    assert caught.value.reason == "owner_not_ready"
    assert await count_entities() == 1


async def test_an_owner_with_another_name_is_refused(owner: int) -> None:
    del owner
    before = await _snapshot()

    with pytest.raises(SeedOwnerError) as caught:
        await resolve_ready_owner("Canary Somebody")

    assert caught.value.reason == "owner_name_mismatch"
    assert "Canary" not in str(caught.value)
    assert await _snapshot() == before


# --- the writes -------------------------------------------------------------------------------


async def test_the_full_plan_writes_everything_through_the_writers(owner: int) -> None:
    plan = plan_of(full_seed())

    outcomes = await _apply(plan, owner)

    assert {outcome.status for outcome in outcomes} == {OperationStatus.WRITTEN}
    assert await count_entities() == 1 + plan.counts()[OperationKind.CREATE_ENTITY]
    assert await count_active_contacts() == 2
    channels = await scalar(
        "SELECT GROUP_CONCAT(DISTINCT channel) FROM "
        "(SELECT channel FROM literal_facts_v4 UNION ALL SELECT channel FROM entity_relations_v4)"
    )
    assert channels == WriteChannel.IMPORT_ASSISTED.value
    assert (
        await scalar(
            "SELECT COUNT(*) FROM literal_facts_v4 WHERE asserted_by_entity_id != ? "
            "OR confirmed_by_entity_id != ? OR asserted_at != ?",
            owner,
            owner,
            NOW,
        )
        == 0
    )
    assert (
        await scalar(
            "SELECT COUNT(*) FROM care_contacts WHERE channel != ? OR asserted_by_entity_id != ?",
            WriteChannel.IMPORT_ASSISTED.value,
            owner,
        )
        == 0
    )


async def test_the_writer_assigns_each_classification(owner: int) -> None:
    await _apply(plan_of(full_seed()), owner)

    async def label(subject: str, predicate: str) -> tuple[object, object]:
        cursor = await db.get_conn().execute(
            "SELECT f.visibility, f.sensitivity FROM literal_facts_v4 f "
            "JOIN entities e ON e.id = f.subject_entity_id WHERE e.name = ? AND f.predicate = ?",
            (subject, predicate),
        )
        row = await cursor.fetchone()
        await cursor.close()
        assert row is not None
        return row[0], row[1]

    assert await label("Canary Owner", "likes") == ("personal", "normal")
    assert await label("Canary Owner", "birth_date") == ("personal", "private")
    assert await label("Canary Owner", "secret_holder") == ("personal", "security")
    assert await label("Canary Child", "likes") == ("household", "normal")
    assert await label("Canary Pet", "species") == ("household", "normal")
    assert (
        await scalar("SELECT visibility FROM entity_relations_v4 WHERE predicate = 'has_parent'")
        == "personal"
    )


async def test_a_representative_review_stores_no_confirmer(owner: int) -> None:
    await _apply(plan_of(full_seed()), owner, confirmed=False)

    assert (
        await scalar(
            "SELECT COUNT(*) FROM literal_facts_v4 WHERE confirmed_by_entity_id IS NOT NULL"
        )
        == 0
    )
    assert (
        await scalar("SELECT COUNT(*) FROM care_contacts WHERE confirmed_by_entity_id IS NOT NULL")
        == 0
    )


async def test_the_same_plan_twice_changes_nothing(owner: int) -> None:
    plan = plan_of(full_seed())
    await _apply(plan, owner)
    after_first = await _snapshot()

    outcomes = await _apply(plan, owner)

    assert await _snapshot() == after_first
    assert {outcome.status for outcome in outcomes} == {OperationStatus.UNCHANGED}
    (caregiver,) = [o for o in outcomes if o.operation.kind is OperationKind.WRITE_CONTACT][:1]
    assert caregiver.status is OperationStatus.UNCHANGED


# --- conflicts --------------------------------------------------------------------------------


def _changed(change: dict[str, object], *, section: str = "owner") -> Toml:
    data = full_seed()
    target = data[section]
    assert isinstance(target, dict)
    target.update(change)
    return data


async def test_a_different_birth_date_is_a_conflict(owner: int) -> None:
    await _apply(plan_of(full_seed()), owner)

    outcomes = await _apply(plan_of(_changed({"birth_date": "1951-05-17"})), owner)

    assert _problems(outcomes) == [("owner.birth_date", "value_conflict")]


async def test_a_different_partner_is_a_conflict(owner: int) -> None:
    await _apply(plan_of(full_seed()), owner)

    outcomes = await _apply(plan_of(_changed({"name": "Canary Other"}, section="partner")), owner)

    assert _problems(outcomes) == [("partner", "value_conflict")]


async def test_a_changed_guardianship_is_a_conflict_and_its_dependents_are_skipped(
    owner: int,
) -> None:
    await _apply(plan_of(full_seed()), owner)
    data = full_seed()
    data["children"] = [
        {"name": "Canary Child", "guardianship": "adult"},
        {"name": "Canary Grown", "guardianship": "adult"},
    ]

    outcomes = await _apply(plan_of(data), owner)

    assert _problems(outcomes) == [
        ("create.child", "guardianship_conflict"),
        ("children", "dependency_failed"),
    ]


async def test_an_existing_entity_with_a_childs_name_is_a_conflict(owner: int) -> None:
    await create_third_party(name="canary child", type="person")

    outcomes = await _apply(plan_of(full_seed()), owner)

    problems = _problems(outcomes)
    assert problems[0] == ("create.child", "entity_exists")
    assert ("children", "dependency_failed") in problems
    assert ("child.likes", "dependency_failed") in problems
    assert ("child.birth_date", "dependency_failed") in problems


async def test_a_child_made_by_the_local_setup_is_a_conflict(seed_db: Path) -> None:
    del seed_db
    result = await apply_personal_setup(
        PersonalSetupInput(
            owner_name=OWNER_NAME, child_names=("Canary Child",), pin=SecretStr("482173")
        )
    )

    outcomes = await _apply(plan_of(full_seed()), result.owner_entity_id)

    assert _problems(outcomes)[0] == ("create.child", "entity_exists")


async def test_a_taken_call_order_is_refused(owner: int) -> None:
    friend = await create_third_party(name="Canary Neighbor", type="person")
    await write_contact(
        owner_entity_id=owner,
        contact_entity_id=friend,
        role=ContactRole.NEIGHBOR,
        phone="+56900000077",
        channel=WriteChannel.IMPORT_ASSISTED,
        confirmed_at=NOW,
        call_order=1,
    )

    outcomes = await _apply(plan_of(full_seed()), owner)

    assert _problems(outcomes) == [("contact", "order_taken")]


@pytest.mark.parametrize(
    "field, value",
    [
        ("phone", "+56900000099"),
        ("phone_alt", "+56200000099"),
        ("call_order", 5),
        ("has_key", False),
    ],
)
async def test_a_known_contact_with_other_terms_is_a_conflict(
    owner: int, field: str, value: object
) -> None:
    await _apply(plan_of(full_seed()), owner)
    data = full_seed()
    contacts = data["contacts"]
    assert isinstance(contacts, list)
    contacts[0][field] = value

    outcomes = await _apply(plan_of(data), owner)

    assert _problems(outcomes) == [("contact", "value_conflict")]


async def test_every_problem_is_reported(owner: int) -> None:
    await _apply(plan_of(full_seed()), owner)
    data = _changed({"birth_date": "1951-05-17", "blood_type": "A+"})
    data["partner"] = {"name": "Canary Other"}

    outcomes = await _apply(plan_of(data), owner)

    assert sorted(_problems(outcomes)) == [
        ("owner.birth_date", "value_conflict"),
        ("owner.blood_type", "value_conflict"),
        ("partner", "value_conflict"),
    ]


# --- nothing leaks ----------------------------------------------------------------------------


async def test_no_outcome_or_log_holds_a_name_a_value_or_a_phone(
    owner: int, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    await _apply(plan_of(full_seed()), owner)
    outcomes = await _apply(plan_of(_changed({"birth_date": "1951-05-17"})), owner)

    rendered = repr(outcomes) + "".join(
        f"{record.getMessage()} {record.__dict__!r}" for record in caplog.records
    )

    for secret in _SECRETS:
        assert secret not in rendered, secret
