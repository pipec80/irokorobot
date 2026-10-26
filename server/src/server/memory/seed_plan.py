"""The plan of operations of a seed load: pure, with no database and no clock (Plan 0071).

The plan is the one contract for entering data (ADR 0025 decision 11): the file, a later local
CRUD, a form or an inbox of changes all produce ``SeedOperation``s and one applier writes them. The
operations come in a fixed order: the entities, the membership relations, the relatives and the
people to keep out, the literals and the contacts; the section statuses travel beside them. Each
person is one entity, keyed by role and folded name, so a contact or a ``[[withhold]]`` entry that
repeats a person's name is that person. Nothing here holds a value in its ``repr``.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING

from server.memory.commissioning import Section, SectionStatus
from server.memory.declarative import SEED_IMPORT_KEY_PREFIX
from server.memory.seed_file import sections_with_items
from server.memory.seed_members import OWNER_PREDICATES
from server.text_keys import fold_name

if TYPE_CHECKING:
    from collections.abc import Mapping

    from server.memory.seed_file import SeedFile
    from server.memory.seed_members import SeedChild, SeedOwner, SeedPet

__all__ = [
    "OperationKind",
    "SeedOperation",
    "SeedPlan",
    "SeedRef",
    "SeedRole",
    "build_plan",
]

_PERSON = "person"
_PET = "other"
# The literal keys of a child and a pet: their own predicate names.
_CHILD_KEYS = ("birth_date", "stated_age", "likes", "dislikes", "prefers")
_PET_KEYS = ("species", "stated_age", "likes", "dislikes", "prefers")


class OperationKind(StrEnum):
    """What one operation does, in the order the plan lists them."""

    CREATE_ENTITY = "create_entity"
    WRITE_RELATION = "write_relation"
    WRITE_LITERAL = "write_literal"
    WRITE_CONTACT = "write_contact"


class SeedRole(StrEnum):
    """The role a person or a pet has in the file; part of its import key."""

    OWNER = "owner"
    PARTNER = "partner"
    CHILD = "child"
    PET = "pet"
    PARENT = "parent"
    GRANDPARENT = "grandparent"
    SIBLING = "sibling"
    GRANDCHILD = "grandchild"
    THIRD_PARTY = "third_party"


# The relative lists of the file: their role and the relation from the owner to them (D-4).
_RELATIVES = (
    ("parents", SeedRole.PARENT, "has_parent"),
    ("grandparents", SeedRole.GRANDPARENT, "has_grandparent"),
    ("siblings", SeedRole.SIBLING, "has_sibling"),
    ("grandchildren", SeedRole.GRANDCHILD, "has_grandchild"),
)


@dataclass(frozen=True)
class SeedRef:
    """A person or a pet of the file: its role and its folded name (hidden from the ``repr``)."""

    role: SeedRole
    key: str = field(repr=False)


OWNER_REF = SeedRef(SeedRole.OWNER, "")


@dataclass(frozen=True)
class SeedOperation:
    """One write of the plan; ``label`` is safe to show (``child.likes``), the rest is not."""

    kind: OperationKind
    label: str
    subject: SeedRef | None = None
    predicate: str | None = None
    target: SeedRef | None = None
    value: str | None = field(default=None, repr=False)
    entity_name: str | None = field(default=None, repr=False)
    entity_type: str | None = None
    import_key: str | None = field(default=None, repr=False)
    attributes: Mapping[str, object] = field(
        default_factory=lambda: MappingProxyType({}), repr=False
    )


@dataclass(frozen=True)
class SeedPlan:
    """The operations of one load and the status of every section."""

    operations: tuple[SeedOperation, ...]
    section_statuses: Mapping[Section, SectionStatus]

    def counts(self) -> Mapping[OperationKind, int]:
        """Return how many operations of each kind the plan holds."""
        return MappingProxyType(Counter(operation.kind for operation in self.operations))


class _People:
    """The entities of the file, one per folded name, in the order they are first named."""

    def __init__(self) -> None:
        self.refs: dict[str, SeedRef] = {}
        self.creations: list[SeedOperation] = []

    def add(
        self, name: str, role: SeedRole, *, kind: str = _PERSON, guardianship: str | None = None
    ) -> SeedRef:
        folded = fold_name(name)
        if folded in self.refs:
            return self.refs[folded]
        ref = SeedRef(role, folded)
        self.refs[folded] = ref
        self.creations.append(
            SeedOperation(
                kind=OperationKind.CREATE_ENTITY,
                label=f"create.{role.value}",
                subject=ref,
                entity_name=name,
                entity_type=kind,
                import_key=f"{SEED_IMPORT_KEY_PREFIX}{role.value}:{folded}",
                attributes=MappingProxyType(
                    {} if guardianship is None else {"guardianship": guardianship}
                ),
            )
        )
        return ref


def _relation(label: str, source: SeedRef, predicate: str, target: SeedRef) -> SeedOperation:
    return SeedOperation(
        kind=OperationKind.WRITE_RELATION,
        label=label,
        subject=source,
        predicate=predicate,
        target=target,
    )


def _literals(
    prefix: str, ref: SeedRef, member: SeedOwner | SeedChild | SeedPet, keys: Mapping[str, str]
) -> list[SeedOperation]:
    """One literal per value: a list gives one each, a number is written as text."""
    operations: list[SeedOperation] = []
    for key, predicate in keys.items():
        raw = getattr(member, key)
        values = raw if isinstance(raw, tuple) else () if raw is None else (raw,)
        operations.extend(
            SeedOperation(
                kind=OperationKind.WRITE_LITERAL,
                label=f"{prefix}.{key}",
                subject=ref,
                predicate=predicate,
                value=str(value),
            )
            for value in values
        )
    return operations


def _statuses(seed: SeedFile) -> Mapping[Section, SectionStatus]:
    """A section with items is ``provided``; one without takes its entry, or ``not_asked`` (D-5)."""
    items = sections_with_items(seed)
    return MappingProxyType(
        {
            section: SectionStatus.PROVIDED
            if section in items
            else getattr(seed.status, section.value) or SectionStatus.NOT_ASKED
            for section in Section
        }
    )


def build_plan(seed: SeedFile) -> SeedPlan:
    """Turn a validated seed file into the ordered operations of its load.

    Args:
        seed: A validated seed file.

    Returns:
        The plan: entities, membership relations, relatives and people to keep out, literals,
        contacts; and the status of every section.
    """
    people = _People()
    partner = None if seed.partner is None else people.add(seed.partner.name, SeedRole.PARTNER)
    children = [
        (people.add(child.name, SeedRole.CHILD, guardianship=child.guardianship.value), child)
        for child in seed.children
    ]
    relatives = [
        (key, predicate, people.add(member.name, role))
        for key, role, predicate in _RELATIVES
        for member in getattr(seed, key)
    ]
    pets = [(people.add(pet.name, SeedRole.PET, kind=_PET), pet) for pet in seed.pets]
    withheld = [people.add(member.name, SeedRole.THIRD_PARTY) for member in seed.withhold]
    contacts = [
        (people.add(contact.name, SeedRole.THIRD_PARTY), contact) for contact in seed.contacts
    ]

    relations = [_relation("children", ref, "child_of", OWNER_REF) for ref, _ in children]
    if partner is not None:
        relations.append(_relation("partner", partner, "partner_of", OWNER_REF))
    relations += [_relation("pets", ref, "pet_of", OWNER_REF) for ref, _ in pets]
    relations += [_relation(key, OWNER_REF, predicate, ref) for key, predicate, ref in relatives]
    relations += [_relation("withhold", OWNER_REF, "withhold_from", ref) for ref in withheld]

    literals = _literals("owner", OWNER_REF, seed.owner, OWNER_PREDICATES)
    for ref, child in children:
        literals += _literals("child", ref, child, {key: key for key in _CHILD_KEYS})
    for ref, pet in pets:
        literals += _literals("pet", ref, pet, {key: key for key in _PET_KEYS})

    writes = [
        SeedOperation(
            kind=OperationKind.WRITE_CONTACT,
            label="contact",
            subject=ref,
            attributes=MappingProxyType(contact.model_dump(exclude={"name"}, mode="json")),
        )
        for ref, contact in contacts
    ]
    operations = (*people.creations, *relations, *literals, *writes)
    return SeedPlan(operations=operations, section_statuses=_statuses(seed))
