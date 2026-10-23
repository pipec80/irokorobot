"""Unit tests for the closed relational-memory v4 predicate registry."""

from __future__ import annotations

import pytest
from server.memory.predicate_registry import (
    LiteralFormat,
    PredicateCardinality,
    PredicateKind,
    normalize_literal,
    resolve_predicate,
)


def test_birth_date_alias_resolves_to_strict_single_literal() -> None:
    """A legacy Spanish alias must resolve to the canonical v4 date predicate."""
    definition = resolve_predicate("fecha_nacimiento")

    assert definition is not None
    assert definition.canonical_id == "birth_date"
    assert definition.kind is PredicateKind.LITERAL
    assert definition.cardinality is PredicateCardinality.SINGLE_CURRENT
    assert definition.subject_types == frozenset({"person"})
    assert normalize_literal(definition, "2016-10-14") == "2016-10-14"
    assert normalize_literal(definition, "14 de octubre de 2016") is None


def test_multi_value_preference_alias_keeps_cardinality() -> None:
    """A preference alias must resolve to a coexistence-capable literal."""
    definition = resolve_predicate("le_gusta")

    assert definition is not None
    assert definition.canonical_id == "likes"
    assert definition.kind is PredicateKind.LITERAL
    assert definition.cardinality is PredicateCardinality.MULTI_VALUE
    assert normalize_literal(definition, "robótica") == "robótica"


def test_child_relation_declares_inverse_query_and_entity_types() -> None:
    """A child relation must use entity targets and expose its inverse query."""
    definition = resolve_predicate("hijo_de")

    assert definition is not None
    assert definition.canonical_id == "child_of"
    assert definition.kind is PredicateKind.RELATION
    assert definition.inverse_query_id == "parent_of"
    assert definition.subject_types == frozenset({"person"})
    assert definition.target_types == frozenset({"person"})


def test_partner_relation_is_symmetric() -> None:
    """A partner relation must be stored canonically and queried symmetrically."""
    definition = resolve_predicate("pareja_de")

    assert definition is not None
    assert definition.canonical_id == "partner_of"
    assert definition.symmetric is True


def test_derived_age_and_unknown_predicates_are_unsupported() -> None:
    """Derived or unknown legacy predicates must not gain a v4 write target."""
    assert resolve_predicate("edad") is None
    assert resolve_predicate("inventado_por_modelo") is None


# --- Plan 0065 (ADR 0022 decisions 6, 8 and 9): the household writer's predicates -------------


def test_species_is_a_single_current_text_literal_for_pets_only() -> None:
    """A pet's species is a literal of the pet type (typed ``other``), never of a person."""
    definition = resolve_predicate("especie")

    assert definition is not None
    assert definition.canonical_id == "species"
    assert resolve_predicate("species") is definition
    assert definition.kind is PredicateKind.LITERAL
    assert definition.cardinality is PredicateCardinality.SINGLE_CURRENT
    assert definition.literal_format is LiteralFormat.TEXT
    assert definition.subject_types == frozenset({"other"})
    assert (definition.default_visibility, definition.default_sensitivity) == (
        "household",
        "normal",
    )


def test_stated_age_is_a_single_current_integer_for_a_person_or_a_pet() -> None:
    """The age as stated is kept (its as-of date is the row's ``asserted_at``); child data."""
    definition = resolve_predicate("edad_dicha")

    assert definition is not None
    assert definition.canonical_id == "stated_age"
    assert resolve_predicate("stated_age") is definition
    assert definition.kind is PredicateKind.LITERAL
    assert definition.cardinality is PredicateCardinality.SINGLE_CURRENT
    assert definition.literal_format is LiteralFormat.INTEGER
    assert definition.subject_types == frozenset({"person", "other"})
    # The household reader requires the stored sensitivity to equal this default for any subject.
    assert (definition.default_visibility, definition.default_sensitivity) == (
        "household",
        "child_data",
    )


@pytest.mark.parametrize(
    "value, canonical", [("7", "7"), ("0", "0"), ("130", "130"), (" 42 ", "42")]
)
def test_stated_age_accepts_a_whole_number_from_zero_to_130(value: str, canonical: str) -> None:
    definition = resolve_predicate("stated_age")
    assert definition is not None

    assert normalize_literal(definition, value) == canonical


@pytest.mark.parametrize(
    "value",
    ["ocho", "-1", "131", "07", "00", "7 años", "²", "٣", "1.5", "", "   "],
)
def test_stated_age_rejects_anything_that_is_not_a_plain_whole_number(value: str) -> None:
    """Digits only (ASCII, not ``str.isdigit``), no leading zero except ``0``, at most 130."""
    definition = resolve_predicate("stated_age")
    assert definition is not None

    assert normalize_literal(definition, value) is None


def test_private_topic_is_a_multi_value_personal_literal_for_people() -> None:
    """«No menciones X delante de visitas»: only the predicate is registered (ADR 0022 §8)."""
    definition = resolve_predicate("tema_privado")

    assert definition is not None
    assert definition.canonical_id == "private_topic"
    assert resolve_predicate("private_topic") is definition
    assert definition.kind is PredicateKind.LITERAL
    assert definition.cardinality is PredicateCardinality.MULTI_VALUE
    assert definition.literal_format is LiteralFormat.TEXT
    assert definition.subject_types == frozenset({"person"})
    assert (definition.default_visibility, definition.default_sensitivity) == (
        "personal",
        "normal",
    )


def test_access_code_is_the_first_security_predicate_and_has_no_spanish_alias() -> None:
    """No alias, so a legacy fact can never be routed into it by the legacy migration."""
    definition = resolve_predicate("access_code")

    assert definition is not None
    assert definition.canonical_id == "access_code"
    assert definition.aliases == frozenset({"access_code"})
    assert definition.kind is PredicateKind.LITERAL
    assert definition.cardinality is PredicateCardinality.SINGLE_CURRENT
    assert definition.subject_types == frozenset({"person"})
    assert (definition.default_visibility, definition.default_sensitivity) == (
        "personal",
        "security",
    )
    assert resolve_predicate("codigo_acceso") is None


def test_a_pet_is_not_a_subject_of_a_private_topic_or_an_access_code() -> None:
    for alias in ("private_topic", "access_code"):
        definition = resolve_predicate(alias)
        assert definition is not None
        assert "other" not in definition.subject_types


# --- Plan 0070 Task 2 (ADR 0024 decision 4): a secret is stored by reference --------------------

_STORABLE_IDS = (
    "birth_date",
    "likes",
    "dislikes",
    "prefers",
    "allergic_to",
    "child_of",
    "partner_of",
    "pet_of",
    "lives_in",
    "works_at",
    "species",
    "stated_age",
    "private_topic",
    "secret_holder",
)


def test_only_the_access_code_is_never_storable() -> None:
    definition = resolve_predicate("access_code")

    assert definition is not None
    assert definition.storable is False
    for canonical_id in _STORABLE_IDS:
        other = resolve_predicate(canonical_id)
        assert other is not None
        assert other.storable is True, canonical_id


def test_secret_holder_is_a_personal_security_reference_for_people() -> None:
    """Who knows a secret, never the secret: a multi-value reference on a person."""
    definition = resolve_predicate("quien_conoce_el_secreto")

    assert definition is not None
    assert definition.canonical_id == "secret_holder"
    assert resolve_predicate("secret_holder") is definition
    assert definition.kind is PredicateKind.LITERAL
    assert definition.cardinality is PredicateCardinality.MULTI_VALUE
    assert definition.literal_format is LiteralFormat.REFERENCE
    assert definition.subject_types == frozenset({"person"})
    assert (definition.default_visibility, definition.default_sensitivity) == (
        "personal",
        "security",
    )


@pytest.mark.parametrize(
    "raw,canonical",
    [
        ("  mi hija   Ana ", "mi hija Ana"),
        ("la vecina", "la vecina"),
        ("ab", "ab"),
        ("x" * 120, "x" * 120),
        ("clave 123", "clave 123"),
        ("depto 12", "depto 12"),
    ],
)
def test_a_reference_is_stripped_and_collapsed(raw: str, canonical: str) -> None:
    definition = resolve_predicate("secret_holder")
    assert definition is not None

    assert normalize_literal(definition, raw) == canonical


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "a",
        "x" * 121,
        "clave 1234",
        "1 2 3 4",
        "1-2-3-4",
        "١٢٣٤",
        "código ०१२३",
        "casa 12 y 34",
    ],
)
def test_a_reference_refuses_the_wrong_length_and_four_digits_in_any_script(raw: str) -> None:
    definition = resolve_predicate("secret_holder")
    assert definition is not None

    assert normalize_literal(definition, raw) is None
