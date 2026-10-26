"""The members of a seed file: the owner, the people around them and the contacts (Plan 0071).

Each model is frozen, refuses an unknown key and validates every value with the registry's own
normalizer, so the file accepts exactly what the canonical writer would store. A validator here
raises a ``ValueError`` whose message is a closed reason and never the value; every field that holds a name, a value or
a phone is left out of the ``repr``.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)

from server.memory.care_contacts import ContactRole, normalize_phone
from server.memory.declarative import Guardianship
from server.memory.predicate_registry import (
    PredicateDefinition,
    normalize_literal,
    resolve_predicate,
)

__all__ = [
    "MAX_MEMBERS",
    "OWNER_PREDICATES",
    "SeedChild",
    "SeedContact",
    "SeedOwner",
    "SeedPerson",
    "SeedPet",
]

MAX_MEMBERS = 20
_MAX_NAME = 80
_MAX_VALUE = 200
_MAX_VALUES = 50
_MAX_AGE = 130
_MAX_RELATIONSHIP = 40
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f-\x9f]")

# D-4: the file's key (English) and the predicate it is stored under. A key not listed here is
# the predicate's own name.
OWNER_PREDICATES = {
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
    "secrets": "secret_holder",  # pragma: allowlist secret (a predicate name)
}


def _definition(predicate: str) -> PredicateDefinition:
    """Resolve a predicate this closed module depends on."""
    definition = resolve_predicate(predicate)
    if definition is None:
        raise RuntimeError(f"required predicate {predicate!r} is not registered")
    return definition


def _normalized(predicate: str, value: str) -> str:
    """Return the registry's canonical form of one value, or a closed error without the value."""
    normalized = normalize_literal(_definition(predicate), value)
    if normalized is None:
        raise ValueError("invalid_value")
    return normalized


def _text(value: str) -> str:
    return _normalized("likes", value)


def _reference(value: str) -> str:
    return _normalized("document_location", value)


def _name(value: str) -> str:
    if _CONTROL_CHARACTERS.search(value):
        raise ValueError("control_character")
    stripped = " ".join(value.split())
    if not stripped:
        raise ValueError("blank")
    return stripped


def _phone(value: str) -> str:
    canonical = normalize_phone(value)
    if canonical is None:
        raise ValueError("invalid_phone")
    return canonical


Name = Annotated[str, StringConstraints(max_length=_MAX_NAME), AfterValidator(_name)]
Text = Annotated[str, StringConstraints(max_length=_MAX_VALUE), AfterValidator(_text)]
Reference = Annotated[str, StringConstraints(max_length=_MAX_VALUE), AfterValidator(_reference)]
Phone = Annotated[str, AfterValidator(_phone)]
Single = Annotated[str, StringConstraints(max_length=_MAX_VALUE)]
Relationship = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=_MAX_RELATIONSHIP)
]


# Any: pydantic's own `Field` returns Any so that a default fits whatever the annotation says.
def _values() -> Any:  # noqa: ANN401
    """A list of at most fifty values, hidden from the ``repr``."""
    return Field(default=(), max_length=_MAX_VALUES, repr=False)


def _hidden() -> Any:  # noqa: ANN401
    """An optional value hidden from the ``repr``."""
    return Field(default=None, repr=False)


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SeedPerson(_Frozen):
    """The partner, a relative or a person to keep out: the name and nothing else."""

    name: Name = Field(repr=False)


class _Tastes(_Frozen):
    likes: tuple[Text, ...] = _values()
    dislikes: tuple[Text, ...] = _values()
    prefers: tuple[Text, ...] = _values()


class SeedChild(_Tastes):
    """A child of the owner; an adult child is the name and the guardianship only."""

    name: Name = Field(repr=False)
    guardianship: Guardianship
    birth_date: Single | None = _hidden()
    stated_age: int | None = Field(default=None, ge=0, le=_MAX_AGE, repr=False)

    @field_validator("birth_date")
    @classmethod
    def _date(cls, value: str | None) -> str | None:
        return None if value is None else _normalized("birth_date", value)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.guardianship is Guardianship.ADULT and (
            self.likes or self.dislikes or self.prefers or self.birth_date or self.stated_age
        ):
            raise ValueError("adult_child_facts")
        if self.birth_date is not None and self.stated_age is not None:
            raise ValueError("birth_date_and_stated_age")
        return self


class SeedPet(_Tastes):
    """A pet of the owner."""

    name: Name = Field(repr=False)
    species: Text | None = _hidden()
    stated_age: int | None = Field(default=None, ge=0, le=_MAX_AGE, repr=False)


class SeedContact(_Frozen):
    """A person the owner wants called or told; repeating a person's name is that person."""

    name: Name = Field(repr=False)
    role: ContactRole
    relationship: Relationship | None = _hidden()
    phone: Phone = Field(repr=False)
    phone_alt: Phone | None = _hidden()
    call_order: int | None = Field(default=None, ge=1)
    has_key: bool = False
    may_receive_health_info: bool = False
    may_view_activity: bool = False


_SINGLE_KEYS = (
    "preferred_name",
    "address_form",
    "birth_date",
    "health_coverage",
    "takes_anticoagulant",
    "blood_type",
    "mobility",
    "hearing",
    "vision",
    "emergency_facility",
    "address",
    "dwelling_type",
    "has_lift",
    "access_note",
    "lives_alone",
)


class SeedOwner(_Tastes):
    """What the owner says about themselves; the name must equal the one already set up."""

    name: Name = Field(repr=False)
    preferred_name: Single | None = _hidden()
    address_form: Single | None = _hidden()
    birth_date: Single | None = _hidden()
    health_coverage: Single | None = _hidden()
    conditions: tuple[Text, ...] = _values()
    allergies: tuple[Text, ...] = _values()
    medications: tuple[Text, ...] = _values()
    takes_anticoagulant: Single | None = _hidden()
    rescue_medication: tuple[Text, ...] = _values()
    devices: tuple[Text, ...] = _values()
    blood_type: Single | None = _hidden()
    mobility: Single | None = _hidden()
    hearing: Single | None = _hidden()
    vision: Single | None = _hidden()
    documents: tuple[Reference, ...] = _values()
    emergency_facility: Single | None = _hidden()
    address: Single | None = _hidden()
    dwelling_type: Single | None = _hidden()
    floor: int | None = Field(default=None, ge=0, le=_MAX_AGE, repr=False)
    has_lift: Single | None = _hidden()
    access_note: Single | None = _hidden()
    lives_alone: Single | None = _hidden()
    private_topics: tuple[Text, ...] = _values()
    secrets: tuple[Reference, ...] = _values()  # pragma: allowlist secret (who knows, never what)

    @field_validator(*_SINGLE_KEYS)
    @classmethod
    def _single(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None or info.field_name is None:
            return value
        return _normalized(OWNER_PREDICATES[info.field_name], value)
