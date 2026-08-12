"""Closed predicate semantics for additive relational-memory v4."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

type EntityTypeName = Literal[
    "person",
    "place",
    "object",
    "event",
    "preference",
    "schedule",
    "concept",
    "other",
]


class PredicateKind(StrEnum):
    """Storage shape for a supported v4 predicate."""

    LITERAL = "literal"
    RELATION = "relation"


class PredicateCardinality(StrEnum):
    """Lifecycle rule applied to values of one predicate."""

    SINGLE_CURRENT = "single_current"
    MULTI_VALUE = "multi_value"
    RELATION = "relation"
    TEMPORAL = "temporal"


class LiteralFormat(StrEnum):
    """Canonical representation required for a literal value."""

    TEXT = "text"
    ISO_DATE = "iso_date"


class PredicateDefinition(BaseModel):
    """Immutable semantics for one supported relational-memory predicate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    canonical_id: str
    aliases: frozenset[str]
    kind: PredicateKind
    cardinality: PredicateCardinality
    subject_types: frozenset[EntityTypeName]
    target_types: frozenset[EntityTypeName] = frozenset()
    inverse_query_id: str | None = None
    symmetric: bool = False
    temporal: bool = False
    literal_format: LiteralFormat | None = None
    default_visibility: str = "household"
    default_sensitivity: str = "normal"


_PERSON = frozenset({"person"})
_PLACE = frozenset({"place"})
_PET = frozenset({"other"})

_PREDICATES: tuple[PredicateDefinition, ...] = (
    PredicateDefinition(
        canonical_id="birth_date",
        aliases=frozenset({"birth_date", "fecha_nacimiento"}),
        kind=PredicateKind.LITERAL,
        cardinality=PredicateCardinality.SINGLE_CURRENT,
        subject_types=_PERSON,
        literal_format=LiteralFormat.ISO_DATE,
        default_sensitivity="child_data",
    ),
    PredicateDefinition(
        canonical_id="likes",
        aliases=frozenset({"likes", "le_gusta"}),
        kind=PredicateKind.LITERAL,
        cardinality=PredicateCardinality.MULTI_VALUE,
        subject_types=_PERSON | _PET,
        literal_format=LiteralFormat.TEXT,
    ),
    PredicateDefinition(
        canonical_id="dislikes",
        aliases=frozenset({"dislikes", "odia"}),
        kind=PredicateKind.LITERAL,
        cardinality=PredicateCardinality.MULTI_VALUE,
        subject_types=_PERSON | _PET,
        literal_format=LiteralFormat.TEXT,
    ),
    PredicateDefinition(
        canonical_id="prefers",
        aliases=frozenset({"prefers", "prefiere"}),
        kind=PredicateKind.LITERAL,
        cardinality=PredicateCardinality.MULTI_VALUE,
        subject_types=_PERSON | _PET,
        literal_format=LiteralFormat.TEXT,
    ),
    PredicateDefinition(
        canonical_id="allergic_to",
        aliases=frozenset({"allergic_to", "alergico_a"}),
        kind=PredicateKind.LITERAL,
        cardinality=PredicateCardinality.MULTI_VALUE,
        subject_types=_PERSON | _PET,
        literal_format=LiteralFormat.TEXT,
        default_sensitivity="medical",
    ),
    PredicateDefinition(
        canonical_id="child_of",
        aliases=frozenset({"child_of", "hijo_de"}),
        kind=PredicateKind.RELATION,
        cardinality=PredicateCardinality.RELATION,
        subject_types=_PERSON,
        target_types=_PERSON,
        inverse_query_id="parent_of",
        default_sensitivity="child_data",
    ),
    PredicateDefinition(
        canonical_id="partner_of",
        aliases=frozenset({"partner_of", "pareja_de"}),
        kind=PredicateKind.RELATION,
        cardinality=PredicateCardinality.RELATION,
        subject_types=_PERSON,
        target_types=_PERSON,
        inverse_query_id="partner_of",
        symmetric=True,
    ),
    PredicateDefinition(
        canonical_id="pet_of",
        aliases=frozenset({"pet_of", "mascota_de"}),
        kind=PredicateKind.RELATION,
        cardinality=PredicateCardinality.RELATION,
        subject_types=_PET,
        target_types=_PERSON,
        inverse_query_id="caretaker_of",
    ),
    PredicateDefinition(
        canonical_id="lives_in",
        aliases=frozenset({"lives_in", "vive_en"}),
        kind=PredicateKind.RELATION,
        cardinality=PredicateCardinality.TEMPORAL,
        subject_types=_PERSON | _PET,
        target_types=_PLACE,
        temporal=True,
        default_sensitivity="location",
    ),
    PredicateDefinition(
        canonical_id="works_at",
        aliases=frozenset({"works_at", "trabaja_en"}),
        kind=PredicateKind.RELATION,
        cardinality=PredicateCardinality.TEMPORAL,
        subject_types=_PERSON,
        target_types=_PLACE,
        temporal=True,
    ),
)

_BY_ALIAS = {
    alias.casefold(): definition for definition in _PREDICATES for alias in definition.aliases
}


def resolve_predicate(alias: str) -> PredicateDefinition | None:
    """Resolve a closed canonical predicate definition from an alias.

    Args:
        alias: Candidate v4 canonical ID or explicit legacy alias.

    Returns:
        The immutable definition, or ``None`` for unsupported predicates.
    """
    return _BY_ALIAS.get(alias.strip().casefold())


def normalize_literal(definition: PredicateDefinition, value: str) -> str | None:
    """Validate and canonicalize a literal without database or model access.

    Args:
        definition: Resolved literal predicate semantics.
        value: Candidate value from a deterministic source or migration row.

    Returns:
        Canonical literal text, or ``None`` when the value is invalid.
    """
    if definition.kind is not PredicateKind.LITERAL:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if definition.literal_format is LiteralFormat.TEXT:
        return cleaned
    if definition.literal_format is LiteralFormat.ISO_DATE:
        try:
            parsed = date.fromisoformat(cleaned)
        except ValueError:
            return None
        return cleaned if parsed.isoformat() == cleaned else None
    return None
