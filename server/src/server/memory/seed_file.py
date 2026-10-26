"""The seed file: read, validate and hash it, with no database access (Plan 0071, ADR 0024).

A household's data pool arrives as one local TOML file (schema version 1) that the interviewer
fills in with the owner. This module turns it into frozen models or refuses it with a
``SeedFileError`` that lists every ``field.path: reason`` pair and nothing else: no value, name
or phone reaches the message, the ``repr``, the cause or the context (the pydantic error that
holds the input is dropped before the refusal is raised). The models are the contract every front
end validates against (``SeedFile.model_json_schema()``, ADR 0025 decision 11).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
import tomllib
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from server.exceptions import SeedFileError
from server.memory.commissioning import POOL_VERSION, Section, SectionStatus
from server.memory.seed_members import (
    MAX_MEMBERS,
    SeedChild,
    SeedContact,
    SeedOwner,
    SeedPerson,
    SeedPet,
)
from server.text_keys import comparison_key, fold_name

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
    from pathlib import Path

__all__ = [
    "MAX_SEED_BYTES",
    "LoadedSeed",
    "SeedFile",
    "SeedStatus",
    "json_schema_text",
    "load_seed_file",
    "parse_seed_text",
    "sections_with_items",
]

MAX_SEED_BYTES = 262144
_TOML_LINE = re.compile(r"at line (\d+)")
_PLAIN_KEY = re.compile(r"[a-z_][a-z0-9_]{0,39}")
_MEMBER_LISTS = ("children", "parents", "grandparents", "siblings", "grandchildren")


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SeedStatus(_Frozen):
    """The explicit status of a section that has no items (D-5); a missing one is ``not_asked``."""

    conditions: SectionStatus | None = None
    allergies: SectionStatus | None = None
    medications: SectionStatus | None = None
    devices: SectionStatus | None = None
    contacts: SectionStatus | None = None
    withhold: SectionStatus | None = None
    secrets: SectionStatus | None = None  # pragma: allowlist secret (a section name)
    documents: SectionStatus | None = None
    household: SectionStatus | None = None
    home: SectionStatus | None = None
    function: SectionStatus | None = None


class SeedFile(_Frozen):
    """One seed file, schema version 1."""

    schema_version: Literal[1]
    pool_version: int = Field(ge=1, le=POOL_VERSION)
    owner: SeedOwner
    status: SeedStatus = SeedStatus()
    partner: SeedPerson | None = None
    children: tuple[SeedChild, ...] = Field(default=(), max_length=MAX_MEMBERS)
    pets: tuple[SeedPet, ...] = Field(default=(), max_length=MAX_MEMBERS)
    parents: tuple[SeedPerson, ...] = Field(default=(), max_length=MAX_MEMBERS)
    grandparents: tuple[SeedPerson, ...] = Field(default=(), max_length=MAX_MEMBERS)
    siblings: tuple[SeedPerson, ...] = Field(default=(), max_length=MAX_MEMBERS)
    grandchildren: tuple[SeedPerson, ...] = Field(default=(), max_length=MAX_MEMBERS)
    withhold: tuple[SeedPerson, ...] = Field(default=(), max_length=MAX_MEMBERS)
    contacts: tuple[SeedContact, ...] = Field(default=(), max_length=MAX_MEMBERS)


@dataclass(frozen=True)
class LoadedSeed:
    """A validated seed file and the SHA-256 of its bytes (64 lowercase hex digits)."""

    seed: SeedFile = field(repr=False)
    sha256: str


def json_schema_text() -> str:
    """Return the file's JSON Schema as the text committed in ``docs/examples``.

    Returns:
        The schema of ``SeedFile``, indented, with a final newline.
    """
    return json.dumps(SeedFile.model_json_schema(), indent=2, ensure_ascii=False) + "\n"


def sections_with_items(seed: SeedFile) -> frozenset[Section]:
    """Return the sections that have at least one item in the file (D-5).

    Args:
        seed: A validated seed file.

    Returns:
        The sections whose keys hold a value; every other section takes its explicit status.
    """
    owner = seed.owner
    filled = {
        Section.CONDITIONS: _filled(owner.conditions),
        Section.ALLERGIES: _filled(owner.allergies),
        Section.MEDICATIONS: _filled(
            owner.medications, owner.takes_anticoagulant, owner.rescue_medication
        ),
        Section.DEVICES: _filled(owner.devices),
        Section.CONTACTS: _filled(seed.contacts),
        Section.WITHHOLD: _filled(seed.withhold),
        Section.SECRETS: _filled(owner.secrets),
        Section.DOCUMENTS: _filled(owner.documents),
        Section.HOUSEHOLD: _filled(seed.partner, seed.children, seed.pets),
        Section.HOME: _filled(
            owner.address,
            owner.dwelling_type,
            owner.floor,
            owner.has_lift,
            owner.access_note,
            owner.lives_alone,
            owner.emergency_facility,
        ),
        Section.FUNCTION: _filled(owner.mobility, owner.hearing, owner.vision),
    }
    return frozenset(section for section, has_items in filled.items() if has_items)


def _filled(*values: object) -> bool:
    """Return whether any key holds a value: a list with an item, or anything but ``None``."""
    return any(bool(value) if isinstance(value, tuple) else value is not None for value in values)


def _people(seed: SeedFile) -> Iterator[tuple[str, str]]:
    """Every person of the owner's circle by path: the owner, the partner, children, relatives."""
    yield "owner.name", seed.owner.name
    if seed.partner is not None:
        yield "partner.name", seed.partner.name
    for key in _MEMBER_LISTS:
        for index, member in enumerate(getattr(seed, key)):
            yield f"{key}.{index}.name", member.name


def _name_problems(seed: SeedFile) -> list[str]:
    """Refuse a repeated name among the people and the pets, and a contact named like them."""
    problems: list[str] = []
    seen: set[str] = set()
    for path, name in _people(seed):
        if fold_name(name) in seen:
            problems.append(f"{path}: duplicate_name")
        seen.add(fold_name(name))
    pets: set[str] = set()
    for index, pet in enumerate(seed.pets):
        if fold_name(pet.name) in seen | pets:
            problems.append(f"pets.{index}.name: duplicate_name")
        pets.add(fold_name(pet.name))
    owner = fold_name(seed.owner.name)
    for key in ("contacts", "withhold"):
        for index, member in enumerate(getattr(seed, key)):
            folded = fold_name(member.name)
            if folded == owner:
                problems.append(f"{key}.{index}.name: name_is_owner")
            elif folded in pets:
                problems.append(f"{key}.{index}.name: name_is_pet")
    return problems


def _contact_problems(seed: SeedFile) -> list[str]:
    """Refuse a call order used twice and one person listed twice with the same role."""
    problems: list[str] = []
    orders: set[int] = set()
    pairs: set[tuple[str, str]] = set()
    for index, contact in enumerate(seed.contacts):
        if contact.call_order is not None and contact.call_order in orders:
            problems.append(f"contacts.{index}.call_order: repeated_call_order")
        if contact.call_order is not None:
            orders.add(contact.call_order)
        pair = (fold_name(contact.name), contact.role.value)
        if pair in pairs:
            problems.append(f"contacts.{index}: repeated_contact")
        pairs.add(pair)
    return problems


def _taste_problems(seed: SeedFile) -> list[str]:
    """Refuse a value that is both liked and disliked by the same subject (compared by key)."""
    subjects: list[tuple[str, SeedOwner | SeedChild | SeedPet]] = [("owner", seed.owner)]
    subjects += [(f"children.{i}", child) for i, child in enumerate(seed.children)]
    subjects += [(f"pets.{i}", pet) for i, pet in enumerate(seed.pets)]
    problems: list[str] = []
    for prefix, subject in subjects:
        liked = {comparison_key(value) or value for value in subject.likes}
        for index, value in enumerate(subject.dislikes):
            if (comparison_key(value) or value) in liked:
                problems.append(f"{prefix}.dislikes.{index}: liked_and_disliked")
    return problems


def _status_problems(seed: SeedFile) -> list[str]:
    """Refuse a status that contradicts the items (D-5): absence and presence must not mix."""
    items = sections_with_items(seed)
    problems: list[str] = []
    for section in Section:
        status = getattr(seed.status, section.value)
        if status is None:
            continue
        if section in items and status is not SectionStatus.PROVIDED:
            problems.append(f"status.{section.value}: status_with_items")
        if section not in items and status is SectionStatus.PROVIDED:
            problems.append(f"status.{section.value}: status_without_items")
    return problems


def _safe_path(location: tuple[int | str, ...]) -> str:
    """Join a pydantic location; a key that is not a plain word is not echoed (it may be a value)."""
    parts = [
        str(part) if isinstance(part, int) or _PLAIN_KEY.fullmatch(part) else "?"
        for part in location
    ]
    return ".".join(parts) or "file"


def _reason(error: Mapping[str, object]) -> str:
    """The closed reason of one error: pydantic's type, or the closed word a validator raised."""
    context = error.get("ctx")
    raised = context.get("error") if isinstance(context, dict) else None
    if error["type"] == "value_error" and _PLAIN_KEY.fullmatch(str(raised)):
        return str(raised)
    return str(error["type"])


def _validated(data: dict[str, Any]) -> SeedFile | tuple[str, ...]:  # Any: parsed TOML
    """Validate the parsed document, or return the problems (never the pydantic error)."""
    try:
        seed = SeedFile.model_validate(data)
    except ValidationError as exc:
        return tuple(f"{_safe_path(error['loc'])}: {_reason(error)}" for error in exc.errors())
    problems = (
        _name_problems(seed)
        + _contact_problems(seed)
        + _taste_problems(seed)
        + _status_problems(seed)
    )
    return tuple(problems) if problems else seed


def _parsed(text: str) -> dict[str, Any] | str:  # Any: tomllib returns an untyped document
    """Parse TOML, or return the problem with the line number only (never the offending text)."""
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        line = _TOML_LINE.search(str(exc))
    return f"file: invalid_toml (line {line.group(1)})" if line else "file: invalid_toml"


def parse_seed_text(text: str) -> SeedFile:
    """Validate the text of a seed file.

    Args:
        text: The whole file, decoded.

    Returns:
        The validated, frozen file.

    Raises:
        SeedFileError: With every ``field.path: reason`` pair found; no value is ever echoed.
    """
    parsed = _parsed(text)
    if isinstance(parsed, str):
        raise SeedFileError((parsed,))
    result = _validated(parsed)
    if isinstance(result, tuple):
        raise SeedFileError(result)
    return result


def _decoded(raw: bytes) -> str | None:
    """Decode UTF-8 (a byte-order mark is accepted), or ``None`` for bytes that are not."""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


def load_seed_file(path: Path) -> LoadedSeed:
    """Read, validate and hash a seed file; its size is checked before it is read.

    Args:
        path: The file on this machine.

    Returns:
        The validated file and the SHA-256 of its bytes.

    Raises:
        SeedFileError: For a missing path, a directory, a file over ``MAX_SEED_BYTES``, bytes
            that are not UTF-8, invalid TOML or an invalid file.
    """
    if not path.exists():
        raise SeedFileError(("file: not_found",))
    if not path.is_file():
        raise SeedFileError(("file: not_a_file",))
    if path.stat().st_size > MAX_SEED_BYTES:
        raise SeedFileError(("file: too_large",))
    raw = path.read_bytes()
    text = _decoded(raw)
    if text is None:
        raise SeedFileError(("file: invalid_utf8",))
    return LoadedSeed(seed=parse_seed_text(text), sha256=hashlib.sha256(raw).hexdigest())
