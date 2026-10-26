"""The seed file and its reader, text in and no disk (Plan 0071 Task 2, ADR 0024 decisions 6 and 11).

Every name, phone and value is an invented canary.
"""

from __future__ import annotations

from collections.abc import Callable
import traceback
from typing import Any

import pytest
from server.exceptions import SeedFileError
from server.memory.commissioning import Section, SectionStatus
from server.memory.declarative import Guardianship
from server.memory.seed_file import SeedFile, parse_seed_text, sections_with_items

from tests.unit.seed_data import Toml, full_seed, minimal_seed, to_toml

pytestmark = pytest.mark.unit

type Mutation = Callable[[Toml], None]

_LEAK = "Canaryleak"


def _owner(data: Toml) -> dict[str, object]:
    owner = data["owner"]
    assert isinstance(owner, dict)
    return owner


def _member(data: Toml, key: str, index: int = 0) -> dict[str, object]:
    members = data[key]
    assert isinstance(members, list)
    member = members[index]
    assert isinstance(member, dict)
    return member


def _problems(data: Toml) -> tuple[str, ...]:
    with pytest.raises(SeedFileError) as caught:
        parse_seed_text(to_toml(data))
    return caught.value.problems


def test_a_full_file_parses_with_every_field() -> None:
    seed = parse_seed_text(to_toml(full_seed()))

    assert seed.schema_version == 1
    assert seed.pool_version == 1
    owner = seed.owner
    assert owner.name == "Canary Owner"
    assert owner.preferred_name == "Canary"
    assert owner.address_form == "tu"
    assert owner.birth_date == "1950-05-17"
    assert owner.health_coverage == "Canary Plan"
    assert owner.conditions == ("Canary condition",)
    assert owner.allergies == ("Canary allergy",)
    assert owner.medications == ("Canary pill, 10 mg, 8:00 y 20:00, con comida",)
    assert owner.takes_anticoagulant == "no"
    assert owner.rescue_medication == ("Canary inhaler, en el velador",)
    assert owner.devices == ()
    assert owner.blood_type == "O+"
    assert (owner.mobility, owner.hearing, owner.vision) == ("solo", "normal", "lentes")
    assert owner.documents == ("el testamento está en el cajón del escritorio",)
    assert owner.emergency_facility == "Canary Clinic"
    assert owner.address == "Canary Street 100, Canary Town"
    assert (owner.dwelling_type, owner.floor, owner.has_lift) == ("departamento", 20, "si")
    assert owner.access_note == "conserje en recepción"
    assert owner.lives_alone == "si"
    assert owner.likes == ("té verde",)
    assert owner.secrets == ("la alarma la tiene Canary Friend",)
    assert seed.status.devices is SectionStatus.NONE
    assert seed.partner is not None
    assert seed.partner.name == "Canary Partner"
    child, grown = seed.children
    assert (child.guardianship, grown.guardianship) == (Guardianship.MINOR, Guardianship.ADULT)
    assert child.birth_date == "2015-03-02"
    assert child.likes == ("dibujar",)
    (pet,) = seed.pets
    assert (pet.name, pet.species, pet.stated_age) == ("Canary Pet", "gato", 3)
    assert [p.name for p in seed.parents] == ["Canary Parent"]
    assert [p.name for p in seed.grandparents] == ["Canary Grandparent"]
    assert [p.name for p in seed.siblings] == ["Canary Sibling"]
    assert [p.name for p in seed.grandchildren] == ["Canary Grandchild"]
    assert [p.name for p in seed.withhold] == ["Canary Parent", "Canary Stranger"]
    caregiver, doctor = seed.contacts
    assert caregiver.phone == "+56900000001"
    assert caregiver.phone_alt == "+56200000002"
    assert (caregiver.call_order, caregiver.has_key, caregiver.may_receive_health_info) == (
        1,
        True,
        True,
    )
    assert caregiver.relationship == "hija"
    assert caregiver.may_view_activity is False
    assert (doctor.call_order, doctor.has_key, doctor.phone_alt) == (2, False, None)


def test_a_file_with_only_the_owners_name_parses() -> None:
    seed = parse_seed_text(to_toml(minimal_seed()))

    assert seed.owner.name == "Canary Owner"
    assert seed.children == ()
    assert seed.partner is None


def test_values_are_normalized_by_the_registry() -> None:
    data = minimal_seed()
    _owner(data).update(
        {"takes_anticoagulant": "No sé", "has_lift": "Sí", "documents": ["en   el  cajón"]}
    )

    owner = parse_seed_text(to_toml(data)).owner

    assert (owner.takes_anticoagulant, owner.has_lift) == ("no_se", "si")
    assert owner.documents == ("en el cajón",)


def test_a_phone_is_stored_in_its_canonical_form() -> None:
    data = full_seed()
    _member(data, "contacts")["phone"] = "+56 9 0000 0001"

    assert parse_seed_text(to_toml(data)).contacts[0].phone == "+56900000001"


def test_a_contact_or_a_withheld_person_may_repeat_a_persons_name() -> None:
    data = full_seed()
    data["withhold"] = [{"name": "canary child"}, {"name": "Canary Doctor"}]

    seed = parse_seed_text(to_toml(data))

    assert [p.name for p in seed.withhold] == ["canary child", "Canary Doctor"]


def test_the_sections_with_items_follow_the_catalogue() -> None:
    seed = parse_seed_text(to_toml(full_seed()))

    assert sections_with_items(seed) == frozenset(Section) - {Section.DEVICES}
    assert sections_with_items(parse_seed_text(to_toml(minimal_seed()))) == frozenset()


def _set(path: tuple[str | int, ...], value: object) -> Mutation:
    def mutate(data: Toml) -> None:
        target: Any = data
        for step in path[:-1]:
            target = target[step]
        target[path[-1]] = value

    return mutate


def _drop(path: tuple[str | int, ...]) -> Mutation:
    def mutate(data: Toml) -> None:
        target: Any = data
        for step in path[:-1]:
            target = target[step]
        del target[path[-1]]

    return mutate


def _all(*mutations: Mutation) -> Mutation:
    def mutate(data: Toml) -> None:
        for mutation in mutations:
            mutation(data)

    return mutate


_INVALID: list[tuple[str, Mutation, str]] = [
    ("no schema version", _drop(("schema_version",)), "schema_version: missing"),
    ("schema version 2", _set(("schema_version",), 2), "schema_version: literal_error"),
    ("pool version 2", _set(("pool_version",), 2), "pool_version: less_than_equal"),
    ("a photo", _set(("owner", "photo"), "x"), "owner.photo: extra_forbidden"),
    ("an audio", _set(("owner", "audio"), "x"), "owner.audio: extra_forbidden"),
    ("an access code", _set(("owner", "access_code"), "x"), "owner.access_code: extra_forbidden"),
    ("a rut", _set(("owner", "rut"), "x"), "owner.rut: extra_forbidden"),
    ("a language", _set(("owner", "language"), "es"), "owner.language: extra_forbidden"),
    ("a top-level photo", _set(("photo",), "x"), "photo: extra_forbidden"),
    ("a child's photo", _set(("children", 0, "photo"), "x"), "children.0.photo: extra_forbidden"),
    (
        "no guardianship",
        _drop(("children", 0, "guardianship")),
        "children.0.guardianship: missing",
    ),
    ("a teen", _set(("children", 0, "guardianship"), "teen"), "children.0.guardianship: enum"),
    (
        "an adult child's tastes",
        _set(("children", 1, "likes"), ["leer"]),
        "children.1: adult_child_facts",
    ),
    (
        "an adult child's birth date",
        _set(("children", 1, "birth_date"), "1980-01-01"),
        "children.1: adult_child_facts",
    ),
    (
        "a birth date and an age",
        _set(("children", 0, "stated_age"), 7),
        "children.0: birth_date_and_stated_age",
    ),
    ("a month 13", _set(("owner", "birth_date"), "1950-13-01"), "owner.birth_date: invalid_value"),
    ("a year alone", _set(("owner", "birth_date"), "1950"), "owner.birth_date: invalid_value"),
    ("an age of 131", _set(("pets", 0, "stated_age"), 131), "pets.0.stated_age: less_than_equal"),
    (
        "an option outside a choice",
        _set(("owner", "takes_anticoagulant"), "quizas"),
        "owner.takes_anticoagulant: invalid_value",
    ),
    ("a parent's taste", _set(("parents", 0, "likes"), ["x"]), "parents.0.likes: extra_forbidden"),
    (
        "a partner's birth date",
        _set(("partner", "birth_date"), "1950-01-01"),
        "partner.birth_date: extra_forbidden",
    ),
    (
        "a local phone",
        _set(("contacts", 0, "phone"), "900000001"),
        "contacts.0.phone: invalid_phone",
    ),
    (
        "a local second phone",
        _set(("contacts", 0, "phone_alt"), "22000002"),
        "contacts.0.phone_alt: invalid_phone",
    ),
    ("an unknown role", _set(("contacts", 0, "role"), "nurse"), "contacts.0.role: enum"),
    (
        "a call order of 0",
        _set(("contacts", 0, "call_order"), 0),
        "contacts.0.call_order: greater_than_equal",
    ),
    (
        "a repeated call order",
        _set(("contacts", 1, "call_order"), 1),
        "contacts.1.call_order: repeated_call_order",
    ),
    (
        "a 41-character relationship",
        _set(("contacts", 0, "relationship"), "x" * 41),
        "contacts.0.relationship: string_too_long",
    ),
    (
        "a contact named like the owner",
        _set(("contacts", 1, "name"), "canary owner"),
        "contacts.1.name: name_is_owner",
    ),
    (
        "a contact named like a pet",
        _set(("contacts", 1, "name"), "Canary Pet"),
        "contacts.1.name: name_is_pet",
    ),
    (
        "a withheld person named like the owner",
        _set(("withhold", 1, "name"), "Canary Owner"),
        "withhold.1.name: name_is_owner",
    ),
    (
        "a withheld person named like a pet",
        _set(("withhold", 1, "name"), "Canary Pet"),
        "withhold.1.name: name_is_pet",
    ),
    (
        "the same contact and role twice",
        _all(
            _set(("contacts", 1, "name"), "Canary Grown"),
            _set(("contacts", 1, "role"), "caregiver"),
        ),
        "contacts.1: repeated_contact",
    ),
    (
        "a child named like the partner",
        _set(("children", 0, "name"), "Canary Partner"),
        "children.0.name: duplicate_name",
    ),
    (
        "a parent named like a child",
        _set(("parents", 0, "name"), "CANARY CHÍLD"),
        "parents.0.name: duplicate_name",
    ),
    (
        "a partner named like the owner",
        _set(("partner", "name"), "Canary Owner"),
        "partner.name: duplicate_name",
    ),
    (
        "a pet named like a person",
        _set(("pets", 0, "name"), "Canary Sibling"),
        "pets.0.name: duplicate_name",
    ),
    ("an 81-character name", _set(("owner", "name"), "x" * 81), "owner.name: string_too_long"),
    ("an empty name", _set(("owner", "name"), "  "), "owner.name: blank"),
    (
        "a control character",
        _set(("children", 0, "name"), "Canary\u0007Child"),
        "children.0.name: control_character",
    ),
    (
        "21 children",
        _set(("children",), [{"name": f"Canary {i}", "guardianship": "minor"} for i in range(21)]),
        "children: too_long",
    ),
    (
        "51 values",
        _set(("owner", "likes"), [f"cosa {i}" for i in range(51)]),
        "owner.likes: too_long",
    ),
    (
        "a value of 201 characters",
        _set(("owner", "likes"), ["x" * 201]),
        "owner.likes.0: string_too_long",
    ),
    (
        "a code in a secret",
        _set(("owner", "secrets"), ["1234 la clave"]),
        "owner.secrets.0: invalid_value",
    ),
    (
        "a value liked and disliked",
        _set(("owner", "dislikes"), ["Té Verde"]),
        "owner.dislikes.0: liked_and_disliked",
    ),
    (
        "a status for a section with items",
        _set(("status", "conditions"), "none"),
        "status.conditions: status_with_items",
    ),
    (
        "provided for a section without items",
        _set(("status", "devices"), "provided"),
        "status.devices: status_without_items",
    ),
    ("a status outside the five", _set(("status", "devices"), "maybe"), "status.devices: enum"),
    ("an unknown section", _set(("status", "photos"), "none"), "status.photos: extra_forbidden"),
]


@pytest.mark.parametrize(
    "mutation, problem",
    [pytest.param(m, p, id=name) for name, m, p in _INVALID],
)
def test_an_invalid_file_is_refused_with_its_field_and_reason(
    mutation: Mutation, problem: str
) -> None:
    data = full_seed()
    mutation(data)

    assert problem in _problems(data)


def test_invalid_toml_is_refused_with_its_line_only() -> None:
    with pytest.raises(SeedFileError) as caught:
        parse_seed_text(f'schema_version = 1\nowner = "{_LEAK}\n')

    assert caught.value.problems == ("file: invalid_toml (line 2)",)


def test_every_problem_is_reported_together() -> None:
    data = full_seed()
    _owner(data)["blood_type"] = "Z"
    _member(data, "contacts", 1)["phone"] = "123"

    problems = _problems(data)

    assert "owner.blood_type: invalid_value" in problems
    assert "contacts.1.phone: invalid_phone" in problems


_LEAKS: list[tuple[str, Mutation]] = [
    ("a choice", _set(("owner", "takes_anticoagulant"), _LEAK)),
    ("a phone", _set(("contacts", 0, "phone"), f"{_LEAK} 0001")),
    ("a long name", _set(("owner", "name"), _LEAK * 9)),
    ("a control character", _set(("partner", "name"), f"{_LEAK}\u0007")),
    ("a secret", _set(("owner", "secrets"), [f"{_LEAK} 1234"])),
    ("an unknown key", _set(("owner", "photo"), _LEAK)),
    ("a duplicate name", _set(("parents", 0, "name"), "Canary Child")),
    ("a liked dislike", _set(("owner", "dislikes"), ["té verde"])),
    ("a wrong type", _set(("owner", "floor"), _LEAK)),
    ("a long relationship", _set(("contacts", 0, "relationship"), _LEAK * 5)),
]


@pytest.mark.parametrize("mutation", [pytest.param(m, id=name) for name, m in _LEAKS])
def test_no_error_carries_the_offending_value(mutation: Mutation) -> None:
    data = full_seed()
    mutation(data)

    with pytest.raises(SeedFileError) as caught:
        parse_seed_text(to_toml(data))

    error = caught.value
    rendered = "".join(traceback.format_exception(error))
    for text in (str(error), repr(error), rendered):
        assert _LEAK not in text
        assert "Canary Child" not in text
        assert "té verde" not in text
    assert error.__cause__ is None
    assert error.__context__ is None


def test_the_models_repr_holds_no_value() -> None:
    seed = parse_seed_text(to_toml(full_seed()))

    rendered = repr(seed)

    for secret in ("Canary", "+5690", "té verde", "hija", "1950-05-17", "gato"):
        assert secret not in rendered


def test_the_schema_carries_its_versions() -> None:
    schema = SeedFile.model_json_schema()

    assert schema["properties"]["schema_version"]["const"] == 1
    assert schema["properties"]["pool_version"]["maximum"] == 1
    assert schema["required"] == ["schema_version", "pool_version", "owner"]
