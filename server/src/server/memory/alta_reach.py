"""How each datum the alta loads is reached by voice (Plan 0082, ADR 0037 decision 5).

Pipec's rule: a datum loaded at the alta must be available to the owner's questions, never stored
and disconnected. This closed map gives every field the seed importer can write
(``seed_plan.ALTA_FIELDS``) and every field of a contact row its voice read, or the reason it is
not said aloud. It is data, read by a test that fails when a field has no entry and checks each
claimed read against the reader that makes it; nothing at runtime consults it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["ALTA_REACH", "CONTACT_FIELD_REACH", "Reach", "ReachEntry"]


class Reach(StrEnum):
    """How one field is reached by voice, or why it is not."""

    CARD = "card"  # the profile card and «¿qué sabes de mí?» (ADR 0026)
    RELATIVES = "relatives"  # the relatives and children templates (ADR 0028, Plan 0080)
    SENSITIVE = "sensitive"  # the sensitive read (ADR 0029, Plan 0079 and Plan 0082)
    CONTACTS = "contacts"  # a contact's phone and the key holders (Plan 0082)
    RULE = "rule"  # a rule the robot obeys, not an answer
    BOOKKEEPING = "bookkeeping"  # ids, labels, channel and dates of a row
    FAMILY_STAGE = "family_stage"  # a household member's own data, read in the family stage


_READS: Final = frozenset({Reach.CARD, Reach.RELATIVES, Reach.SENSITIVE, Reach.CONTACTS})


@dataclass(frozen=True)
class ReachEntry:
    """One field's reach; a field not said aloud carries its reason.

    Raises:
        ValueError: For a read with a reason, or a field not read without one.
    """

    reach: Reach
    reason: str | None = None

    def __post_init__(self) -> None:
        """Keep a reason exactly on the fields that are not read aloud."""
        if self.reach in _READS and self.reason is not None:
            raise ValueError("a field read by voice takes no reason")
        if self.reach not in _READS and not self.reason:
            raise ValueError("a field not read by voice needs a reason")


_CARD: Final = ReachEntry(Reach.CARD)
_RELATIVES: Final = ReachEntry(Reach.RELATIVES)
_SENSITIVE: Final = ReachEntry(Reach.SENSITIVE)
_CONTACTS: Final = ReachEntry(Reach.CONTACTS)
_FAMILY_STAGE: Final = ReachEntry(
    Reach.FAMILY_STAGE, "a household member's own data, read in the family stage (P3)"
)
_BOOKKEEPING: Final = ReachEntry(Reach.BOOKKEEPING, "how the row was stored, not a datum to say")
_WITHHOLD: Final = ReachEntry(
    Reach.RULE, "who must not hear the owner's data: obeyed, never said (ADR 0029 decision 6)"
)
_PRIVATE_TOPIC: Final = ReachEntry(
    Reach.RULE, "a topic not to touch: obeyed, never said (ADR 0029 decision 6)"
)
_AUDIENCE: Final = ReachEntry(
    Reach.RULE, "what a contact may be told or see: the audience rule of the family stage"
)

_OWNER, _CHILD, _PET, _PARTNER = "owner", "child", "pet", "partner"

#: Every ``(subject role, predicate)`` of ``seed_plan.ALTA_FIELDS`` and how it is reached.
ALTA_REACH: Final[Mapping[tuple[str, str], ReachEntry]] = MappingProxyType(
    {
        (_OWNER, "preferred_name"): _CARD,
        (_OWNER, "address_form"): _CARD,
        (_OWNER, "likes"): _CARD,
        (_OWNER, "dislikes"): _CARD,
        (_OWNER, "prefers"): _CARD,
        (_OWNER, "birth_date"): _SENSITIVE,
        (_OWNER, "health_coverage"): _SENSITIVE,
        (_OWNER, "health_condition"): _SENSITIVE,
        (_OWNER, "allergic_to"): _SENSITIVE,
        (_OWNER, "medication"): _SENSITIVE,
        (_OWNER, "takes_anticoagulant"): _SENSITIVE,
        (_OWNER, "rescue_medication"): _SENSITIVE,
        (_OWNER, "implanted_device"): _SENSITIVE,
        (_OWNER, "blood_type"): _SENSITIVE,
        (_OWNER, "mobility"): _SENSITIVE,
        (_OWNER, "hearing"): _SENSITIVE,
        (_OWNER, "vision"): _SENSITIVE,
        (_OWNER, "document_location"): _SENSITIVE,
        (_OWNER, "preferred_emergency_facility"): _SENSITIVE,
        (_OWNER, "home_address"): _SENSITIVE,
        (_OWNER, "dwelling_type"): _SENSITIVE,
        (_OWNER, "floor"): _SENSITIVE,
        (_OWNER, "has_lift"): _SENSITIVE,
        (_OWNER, "home_access_note"): _SENSITIVE,
        (_OWNER, "lives_alone"): _SENSITIVE,
        (_OWNER, "secret_holder"): _SENSITIVE,
        (_OWNER, "private_topic"): _PRIVATE_TOPIC,
        (_OWNER, "has_mother"): _RELATIVES,
        (_OWNER, "has_father"): _RELATIVES,
        (_OWNER, "has_parent"): _RELATIVES,
        (_OWNER, "has_grandparent"): _RELATIVES,
        (_OWNER, "has_sibling"): _RELATIVES,
        (_OWNER, "has_grandchild"): _RELATIVES,
        (_OWNER, "withhold_from"): _WITHHOLD,
        (_PARTNER, "partner_of"): _RELATIVES,
        (_CHILD, "child_of"): _RELATIVES,
        (_CHILD, "daughter_of"): _RELATIVES,
        (_CHILD, "son_of"): _RELATIVES,
        (_CHILD, "birth_date"): _SENSITIVE,
        (_CHILD, "stated_age"): _FAMILY_STAGE,
        (_CHILD, "likes"): _FAMILY_STAGE,
        (_CHILD, "dislikes"): _FAMILY_STAGE,
        (_CHILD, "prefers"): _FAMILY_STAGE,
        (_PET, "pet_of"): _RELATIVES,
        (_PET, "species"): _FAMILY_STAGE,
        (_PET, "stated_age"): _FAMILY_STAGE,
        (_PET, "likes"): _FAMILY_STAGE,
        (_PET, "dislikes"): _FAMILY_STAGE,
        (_PET, "prefers"): _FAMILY_STAGE,
    }
)

#: Every field of a ``care_contacts`` row and how it is reached.
CONTACT_FIELD_REACH: Final[Mapping[str, ReachEntry]] = MappingProxyType(
    {
        "contact_entity_id": _CONTACTS,  # the contact's stored name
        "role": _CONTACTS,
        "relationship": _CONTACTS,
        "phone": _CONTACTS,
        "phone_alt": _CONTACTS,
        "call_order": _CONTACTS,
        "has_key": _CONTACTS,
        "may_receive_health_info": _AUDIENCE,
        "may_view_activity": _AUDIENCE,
        "id": _BOOKKEEPING,
        "owner_entity_id": _BOOKKEEPING,
        "visibility": _BOOKKEEPING,
        "sensitivity": _BOOKKEEPING,
        "asserted_by_entity_id": _BOOKKEEPING,
        "channel": _BOOKKEEPING,
        "confirmed_by_entity_id": _BOOKKEEPING,
        "confirmed_at": _BOOKKEEPING,
        "created_at": _BOOKKEEPING,
        "revoked_at": _BOOKKEEPING,
    }
)
