"""Closed predicate semantics for additive relational-memory v4."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
import re
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
    INTEGER = "integer"


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


_PERSON: frozenset[EntityTypeName] = frozenset[EntityTypeName](("person",))
_PLACE: frozenset[EntityTypeName] = frozenset[EntityTypeName](("place",))
_PET: frozenset[EntityTypeName] = frozenset[EntityTypeName](("other",))

# A whole number as people say it: ASCII digits only (never `str.isdigit`, which accepts
# superscripts and other scripts' digits), no leading zero except "0", at most this age.
_INTEGER_PATTERN = re.compile(r"(0|[1-9][0-9]{0,2})")
_MAX_STATED_AGE = 130

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
    # Plan 0065 (ADR 0022): what the household writer stores beyond tastes and relations.
    PredicateDefinition(
        canonical_id="species",
        aliases=frozenset({"species", "especie"}),
        kind=PredicateKind.LITERAL,
        cardinality=PredicateCardinality.SINGLE_CURRENT,
        subject_types=_PET,
        literal_format=LiteralFormat.TEXT,
    ),
    # The age as stated; the row's `asserted_at` is its as-of date. Child data for any subject
    # because the household reader requires the stored sensitivity to equal this default.
    PredicateDefinition(
        canonical_id="stated_age",
        aliases=frozenset({"stated_age", "edad_dicha"}),
        kind=PredicateKind.LITERAL,
        cardinality=PredicateCardinality.SINGLE_CURRENT,
        subject_types=_PERSON | _PET,
        literal_format=LiteralFormat.INTEGER,
        default_sensitivity="child_data",
    ),
    # «No menciones X delante de visitas»: the predicate only; nothing consumes it before CM-5.
    PredicateDefinition(
        canonical_id="private_topic",
        aliases=frozenset({"private_topic", "tema_privado"}),
        kind=PredicateKind.LITERAL,
        cardinality=PredicateCardinality.MULTI_VALUE,
        subject_types=_PERSON,
        literal_format=LiteralFormat.TEXT,
        default_visibility="personal",
    ),
    # The first SECURITY datum. No Spanish alias, so the legacy migration cannot route a legacy
    # fact into it; the repository refuses to store it until Step 0 decides storage at rest.
    PredicateDefinition(
        canonical_id="access_code",
        aliases=frozenset({"access_code"}),
        kind=PredicateKind.LITERAL,
        cardinality=PredicateCardinality.SINGLE_CURRENT,
        subject_types=_PERSON,
        literal_format=LiteralFormat.TEXT,
        default_visibility="personal",
        default_sensitivity="security",
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
    match definition.literal_format:
        case LiteralFormat.TEXT:
            return cleaned
        case LiteralFormat.ISO_DATE:
            return _normalize_iso_date(cleaned)
        case LiteralFormat.INTEGER:
            return _normalize_integer(cleaned)
        case _:
            return None


def _normalize_iso_date(cleaned: str) -> str | None:
    """Return *cleaned* when it is a calendar date written exactly as ``YYYY-MM-DD``."""
    try:
        parsed = date.fromisoformat(cleaned)
    except ValueError:
        return None
    return cleaned if parsed.isoformat() == cleaned else None


def _normalize_integer(cleaned: str) -> str | None:
    """Return *cleaned* when it is a plain whole number from 0 to ``_MAX_STATED_AGE``."""
    if _INTEGER_PATTERN.fullmatch(cleaned) is None or int(cleaned) > _MAX_STATED_AGE:
        return None
    return cleaned
