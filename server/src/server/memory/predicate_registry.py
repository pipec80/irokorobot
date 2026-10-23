"""Closed predicate semantics for additive relational-memory v4."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
import re
from typing import Literal
import unicodedata

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
    # A pointer to where something is or who knows it, never the thing itself (ADR 0024 decision 4).
    REFERENCE = "reference"
    # One code of a closed set, written the way a person says it (ADR 0024 decision 2).
    CHOICE = "choice"


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
    # ``False`` for a value that must never be written, whoever asks and whatever label it
    # carries (ADR 0024 decision 4).
    storable: bool = True
    # The canonical codes a ``CHOICE`` literal accepts; ``None`` for every other format.
    choices: frozenset[str] | None = None


_PERSON: frozenset[EntityTypeName] = frozenset[EntityTypeName](("person",))
_PLACE: frozenset[EntityTypeName] = frozenset[EntityTypeName](("place",))
_PET: frozenset[EntityTypeName] = frozenset[EntityTypeName](("other",))

# A whole number as people say it: ASCII digits only (never `str.isdigit`, which accepts
# superscripts and other scripts' digits), no leading zero except "0", at most this age.
_INTEGER_PATTERN = re.compile(r"(0|[1-9][0-9]{0,2})")
_MAX_STATED_AGE = 130
# A reference is a short sentence; four digits anywhere would be a code, so it is refused.
_REFERENCE_LENGTH = range(2, 121)
_MAX_REFERENCE_DIGITS = 3


def _pool_literal(
    canonical_id: str,
    alias: str,
    literal_format: LiteralFormat,
    sensitivity: str,
    *,
    multi: bool = False,
    choices: str | None = None,
) -> PredicateDefinition:
    """Build a literal of the commissioning data pool: personal, about a person (Plan 0070).

    ``choices`` is the space-separated canonical codes of a ``CHOICE`` literal.
    """
    return PredicateDefinition(
        canonical_id=canonical_id,
        aliases=frozenset({canonical_id, alias}),
        kind=PredicateKind.LITERAL,
        cardinality=(
            PredicateCardinality.MULTI_VALUE if multi else PredicateCardinality.SINGLE_CURRENT
        ),
        subject_types=_PERSON,
        literal_format=literal_format,
        default_visibility="personal",
        default_sensitivity=sensitivity,
        choices=frozenset(choices.split()) if choices is not None else None,
    )


def _pool_relation(
    canonical_id: str, alias: str, *, sensitivity: str = "normal", symmetric: bool = False
) -> PredicateDefinition:
    """Build a relation between two people of the owner's circle: personal (Plan 0070)."""
    return PredicateDefinition(
        canonical_id=canonical_id,
        aliases=frozenset({canonical_id, alias}),
        kind=PredicateKind.RELATION,
        cardinality=PredicateCardinality.RELATION,
        subject_types=_PERSON,
        target_types=_PERSON,
        symmetric=symmetric,
        default_visibility="personal",
        default_sensitivity=sensitivity,
    )


_T, _C, _I, _R = (
    LiteralFormat.TEXT,
    LiteralFormat.CHOICE,
    LiteralFormat.INTEGER,
    LiteralFormat.REFERENCE,
)

# What a commissioning captures about the owner (ADR 0024 decision 2, seed-data-pool.md).
_POOL_PREDICATES: tuple[PredicateDefinition, ...] = (
    _pool_literal("preferred_name", "nombre_preferido", _T, "normal"),
    _pool_literal("address_form", "trato", _C, "normal", choices="tu usted"),
    _pool_literal("health_coverage", "prevision", _T, "private"),
    _pool_literal("health_condition", "condicion_de_salud", _T, "medical", multi=True),
    _pool_literal("medication", "medicamento", _T, "medical", multi=True),
    _pool_literal(
        "takes_anticoagulant", "toma_anticoagulante", _C, "medical", choices="si no no_se"
    ),
    _pool_literal("rescue_medication", "medicamento_de_rescate", _T, "medical", multi=True),
    _pool_literal("implanted_device", "dispositivo_implantado", _T, "medical", multi=True),
    _pool_literal(
        "blood_type",
        "grupo_sanguineo",
        _C,
        "medical",
        choices="A+ A- B+ B- AB+ AB- O+ O-",
    ),
    _pool_literal(
        "mobility", "movilidad", _C, "medical", choices="solo baston andador silla_de_ruedas"
    ),
    _pool_literal("hearing", "audicion", _C, "medical", choices="normal audifonos dificultad"),
    _pool_literal("vision", "vision", _C, "medical", choices="normal lentes dificultad"),
    _pool_literal("document_location", "ubicacion_de_documento", _R, "security", multi=True),
    _pool_literal("preferred_emergency_facility", "urgencia_preferida", _T, "location"),
    _pool_literal("home_address", "direccion", _T, "location"),
    _pool_literal("dwelling_type", "tipo_de_vivienda", _C, "location", choices="casa departamento"),
    _pool_literal("floor", "piso", _I, "location"),
    _pool_literal("has_lift", "tiene_ascensor", _C, "location", choices="si no"),
    _pool_literal("home_access_note", "acceso_a_la_casa", _R, "location"),
    _pool_literal("lives_alone", "vive_solo", _C, "location", choices="si no"),
    _pool_relation("has_parent", "tiene_padre_o_madre"),
    _pool_relation("has_grandparent", "tiene_abuelo_o_abuela"),
    _pool_relation("has_grandchild", "tiene_nieto_o_nieta"),
    _pool_relation("has_sibling", "tiene_hermano_o_hermana", symmetric=True),
    _pool_relation("withhold_from", "no_informar_a", sensitivity="private"),
    # Who knows a secret (ADR 0024 decision 4): free text written by the owner, never the secret.
    _pool_literal("secret_holder", "quien_conoce_el_secreto", _R, "security", multi=True),
)

# The legacy migration never writes these: the pool is loaded through the canonical writer only.
POOL_PREDICATE_IDS: frozenset[str] = frozenset(
    definition.canonical_id for definition in _POOL_PREDICATES
)

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
    # fact into it; its value is never stored (ADR 0024 decision 4), only who knows it below.
    PredicateDefinition(
        canonical_id="access_code",
        aliases=frozenset({"access_code"}),
        kind=PredicateKind.LITERAL,
        cardinality=PredicateCardinality.SINGLE_CURRENT,
        subject_types=_PERSON,
        literal_format=LiteralFormat.TEXT,
        default_visibility="personal",
        default_sensitivity="security",
        storable=False,
    ),
    *_POOL_PREDICATES,
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
    normalized: str | None
    match definition.literal_format:
        case LiteralFormat.TEXT:
            normalized = cleaned
        case LiteralFormat.ISO_DATE:
            normalized = _normalize_iso_date(cleaned)
        case LiteralFormat.INTEGER:
            normalized = _normalize_integer(cleaned)
        case LiteralFormat.REFERENCE:
            normalized = _normalize_reference(cleaned)
        case LiteralFormat.CHOICE:
            normalized = _normalize_choice(definition, cleaned)
        case _:
            normalized = None
    return normalized


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


def _normalize_reference(cleaned: str) -> str | None:
    """Return *cleaned* with its spaces collapsed when it is a short sentence without a code.

    ``str.isdigit`` is used on purpose: it also counts the digits of other scripts, which a code
    can be written in. It is a defence in depth, not a guarantee (a code spelled in words passes).
    """
    collapsed = " ".join(cleaned.split())
    if len(collapsed) not in _REFERENCE_LENGTH:
        return None
    if sum(character.isdigit() for character in collapsed) > _MAX_REFERENCE_DIGITS:
        return None
    return collapsed


def _fold_code(value: str) -> str:
    """Fold case and accents and join words with ``_``: ``"No sé"`` becomes ``"no_se"``."""
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    unaccented = "".join(c for c in decomposed if not unicodedata.combining(c))
    return "_".join(unaccented.split())


def _normalize_choice(definition: PredicateDefinition, cleaned: str) -> str | None:
    """Return the canonical code of *cleaned*, or ``None`` when it is outside the set."""
    folded = _fold_code(cleaned)
    return next((code for code in definition.choices or () if _fold_code(code) == folded), None)
