"""Unit tests for the closed relational-memory v4 predicate registry."""

from __future__ import annotations

from server.memory.predicate_registry import (
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
    assert normalize_literal(definition, "2017-12-29") == "2017-12-29"
    assert normalize_literal(definition, "29 de diciembre de 2017") is None


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
