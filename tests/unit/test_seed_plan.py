"""The plan of operations of a seed load, pure (Plan 0071 Task 3, ADR 0025 decision 11).

Every name, phone and value is an invented canary.
"""

from __future__ import annotations

import pytest
from server.memory.commissioning import Section, SectionStatus
from server.memory.seed_file import parse_seed_text
from server.memory.seed_plan import (
    OperationKind,
    SeedOperation,
    SeedPlan,
    SeedRef,
    SeedRole,
    build_plan,
)

from tests.unit.seed_data import Toml, full_seed, minimal_seed, to_toml

pytestmark = pytest.mark.unit

_OWNER = SeedRef(SeedRole.OWNER, "")

# D-4 is the oracle: the file's key and the predicate it is stored under.
_LITERAL_KEYS = {
    "preferred_name": "preferred_name",
    "address_form": "address_form",
    "birth_date": "birth_date",
    "health_coverage": "health_coverage",
    "conditions": "health_condition",
    "allergies": "allergic_to",
    "medications": "medication",
    "takes_anticoagulant": "takes_anticoagulant",
    "rescue_medication": "rescue_medication",
    "devices": "implanted_device",
    "blood_type": "blood_type",
    "mobility": "mobility",
    "hearing": "hearing",
    "vision": "vision",
    "documents": "document_location",
    "emergency_facility": "preferred_emergency_facility",
    "address": "home_address",
    "dwelling_type": "dwelling_type",
    "floor": "floor",
    "has_lift": "has_lift",
    "access_note": "home_access_note",
    "lives_alone": "lives_alone",
    "likes": "likes",
    "dislikes": "dislikes",
    "prefers": "prefers",
    "private_topics": "private_topic",
    "secrets": "secret_holder",
    "species": "species",
    "stated_age": "stated_age",
}
_RELATION_KEYS = {
    "children": "child_of",
    "partner": "partner_of",
    "pets": "pet_of",
    "parents": "has_parent",
    "grandparents": "has_grandparent",
    "siblings": "has_sibling",
    "grandchildren": "has_grandchild",
    "withhold": "withhold_from",
}


def _plan(data: Toml) -> SeedPlan:
    return build_plan(parse_seed_text(to_toml(data)))


def _of(plan: SeedPlan, kind: OperationKind) -> list[SeedOperation]:
    return [operation for operation in plan.operations if operation.kind is kind]


def test_the_operations_come_in_the_stated_order() -> None:
    plan = _plan(full_seed())

    kinds = [operation.kind for operation in plan.operations]
    relations = [op.predicate for op in _of(plan, OperationKind.WRITE_RELATION)]

    assert kinds == sorted(kinds, key=list(OperationKind).index)
    assert relations == [
        "child_of",
        "child_of",
        "partner_of",
        "pet_of",
        "has_parent",
        "has_grandparent",
        "has_sibling",
        "has_grandchild",
        "withhold_from",
        "withhold_from",
    ]
    subjects = [op.subject.role for op in _of(plan, OperationKind.WRITE_LITERAL) if op.subject]
    assert subjects == sorted(subjects, key=[SeedRole.OWNER, SeedRole.CHILD, SeedRole.PET].index)


def test_one_entity_per_distinct_name_and_none_for_the_owner() -> None:
    created = _of(_plan(full_seed()), OperationKind.CREATE_ENTITY)

    assert sorted(op.import_key or "" for op in created) == [
        "seed-v1:child:canary child",
        "seed-v1:child:canary grown",
        "seed-v1:grandchild:canary grandchild",
        "seed-v1:grandparent:canary grandparent",
        "seed-v1:parent:canary parent",
        "seed-v1:partner:canary partner",
        "seed-v1:pet:canary pet",
        "seed-v1:sibling:canary sibling",
        "seed-v1:third_party:canary doctor",
        "seed-v1:third_party:canary stranger",
    ]
    types = {op.import_key: op.entity_type for op in created}
    assert types["seed-v1:pet:canary pet"] == "other"
    assert {t for k, t in types.items() if k != "seed-v1:pet:canary pet"} == {"person"}
    assert all(op.subject != _OWNER for op in created)


def test_the_import_keys_do_not_depend_on_the_order_of_other_members() -> None:
    data = full_seed()
    reordered = full_seed()
    reordered["children"] = list(reversed(reordered["children"]))

    first = {op.import_key for op in _of(_plan(data), OperationKind.CREATE_ENTITY)}
    again = {op.import_key for op in _of(_plan(data), OperationKind.CREATE_ENTITY)}
    other = {op.import_key for op in _of(_plan(reordered), OperationKind.CREATE_ENTITY)}

    assert first == again == other


def test_a_child_carries_its_guardianship() -> None:
    created = {op.import_key: op for op in _of(_plan(full_seed()), OperationKind.CREATE_ENTITY)}

    assert created["seed-v1:child:canary child"].attributes == {"guardianship": "minor"}
    assert created["seed-v1:child:canary grown"].attributes == {"guardianship": "adult"}
    assert created["seed-v1:partner:canary partner"].attributes == {}


def test_only_the_owner_a_minor_and_a_pet_have_literals() -> None:
    literals = _of(_plan(full_seed()), OperationKind.WRITE_LITERAL)

    assert {op.subject for op in literals} == {
        _OWNER,
        SeedRef(SeedRole.CHILD, "canary child"),
        SeedRef(SeedRole.PET, "canary pet"),
    }


def test_the_membership_and_relative_relations_point_the_stated_way() -> None:
    relations = {
        (op.predicate, op.subject, op.target)
        for op in _of(_plan(full_seed()), OperationKind.WRITE_RELATION)
    }

    assert ("child_of", SeedRef(SeedRole.CHILD, "canary child"), _OWNER) in relations
    assert ("partner_of", SeedRef(SeedRole.PARTNER, "canary partner"), _OWNER) in relations
    assert ("pet_of", SeedRef(SeedRole.PET, "canary pet"), _OWNER) in relations
    assert ("has_parent", _OWNER, SeedRef(SeedRole.PARENT, "canary parent")) in relations
    assert ("withhold_from", _OWNER, SeedRef(SeedRole.PARENT, "canary parent")) in relations
    assert ("withhold_from", _OWNER, SeedRef(SeedRole.THIRD_PARTY, "canary stranger")) in relations


def test_a_contact_named_like_a_child_is_that_child() -> None:
    contacts = _of(_plan(full_seed()), OperationKind.WRITE_CONTACT)

    assert [op.subject for op in contacts] == [
        SeedRef(SeedRole.CHILD, "canary grown"),
        SeedRef(SeedRole.THIRD_PARTY, "canary doctor"),
    ]
    caregiver = contacts[0].attributes
    assert caregiver["role"] == "caregiver"
    assert caregiver["phone"] == "+56900000001"
    assert caregiver["phone_alt"] == "+56200000002"
    assert (caregiver["call_order"], caregiver["has_key"]) == (1, True)
    assert caregiver["may_receive_health_info"] is True
    assert caregiver["may_view_activity"] is False
    assert caregiver["relationship"] == "hija"


def test_a_name_in_a_contact_and_in_withhold_is_one_entity() -> None:
    data = minimal_seed()
    data["contacts"] = [{"name": "Canary Friend", "role": "trusted", "phone": "+56900000009"}]
    data["withhold"] = [{"name": "canary friend"}]

    plan = _plan(data)

    (created,) = _of(plan, OperationKind.CREATE_ENTITY)
    assert created.import_key == "seed-v1:third_party:canary friend"
    (withhold,) = _of(plan, OperationKind.WRITE_RELATION)
    assert withhold.target == created.subject == _of(plan, OperationKind.WRITE_CONTACT)[0].subject


def test_every_file_key_maps_to_its_predicate() -> None:
    plan = _plan(full_seed())

    for operation in _of(plan, OperationKind.WRITE_LITERAL):
        _, key = operation.label.split(".")
        assert operation.predicate == _LITERAL_KEYS[key], operation.label
    for operation in _of(plan, OperationKind.WRITE_RELATION):
        assert operation.predicate == _RELATION_KEYS[operation.label], operation.label
    seen = {op.label.split(".")[-1] for op in _of(plan, OperationKind.WRITE_LITERAL)}
    assert seen == set(_LITERAL_KEYS) - {"devices", "dislikes", "prefers", "private_topics"}


def test_a_list_gives_one_literal_per_value_and_a_number_is_text() -> None:
    literals = _of(_plan(full_seed()), OperationKind.WRITE_LITERAL)
    by_label = {op.label: op.value for op in literals}

    assert by_label["owner.floor"] == "20"
    assert by_label["pet.stated_age"] == "3"
    assert by_label["child.birth_date"] == "2015-03-02"


def test_the_statuses_follow_the_sections() -> None:
    assert _plan(full_seed()).section_statuses == {
        **dict.fromkeys(Section, SectionStatus.PROVIDED),
        Section.DEVICES: SectionStatus.NONE,
    }
    assert _plan(minimal_seed()).section_statuses == dict.fromkeys(Section, SectionStatus.NOT_ASKED)


def test_one_key_of_a_section_makes_it_provided() -> None:
    data = minimal_seed()
    data["owner"]["takes_anticoagulant"] = "si"
    data["status"] = {"conditions": "declined"}

    statuses = _plan(data).section_statuses

    assert statuses[Section.MEDICATIONS] is SectionStatus.PROVIDED
    assert statuses[Section.CONDITIONS] is SectionStatus.DECLINED
    assert statuses[Section.HOME] is SectionStatus.NOT_ASKED


def test_the_counts_are_by_kind() -> None:
    counts = _plan(full_seed()).counts()

    assert counts[OperationKind.CREATE_ENTITY] == 10
    assert counts[OperationKind.WRITE_RELATION] == 10
    assert counts[OperationKind.WRITE_CONTACT] == 2


def test_an_operations_repr_holds_no_value_or_name() -> None:
    rendered = repr(_plan(full_seed()))

    for secret in ("Canary", "canary", "+5690", "té verde", "hija", "1950-05-17", "gato"):
        assert secret not in rendered
