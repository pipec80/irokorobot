"""Read and say the owner's own contacts by voice (Plan 0082, ADR 0037 decision 1).

``sensitive_reply`` runs the audience and level checks of every sensitive question and the one
policy request of D-8 (visibility ``personal``, sensitivity ``CONTACT_SENSITIVITIES``, the two the
table holds), with its audit row **before** the read. Only then it hands over to
``contact_reply``, which reads the active contacts through ``list_active_contacts``, selects what
the question named (``contact_questions``) and words it with ``contact_answers``.

It reads only: nothing here writes a contact, calls a phone or raises an alert. A question that
names no own contact is never read (``is_own_contact_question``, decided before any check). No
phone, name or relationship reaches a log line or an exception message.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from server.cognition.contact_answers import (
    CANNOT_CALL,
    MAX_SPOKEN_CONTACTS,
    SpokenContact,
    role_descriptor,
    word_contacts,
    word_key_holders,
)
from server.cognition.contact_questions import contact_selector, match_score
from server.cognition.response_plan import SensitiveOutcome, SensitiveReply
from server.cognition.sensitive_questions import SensitiveTopic
from server.memory.care_contacts import list_active_contacts
from server.memory.entity_labels import get_person_label

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Hashable, Mapping

    from server.cognition.sensitive_questions import SensitiveQuery
    from server.memory.care_contacts import CareContact

__all__ = [
    "CONTACT_SENSITIVITIES",
    "ContactsReader",
    "NameReader",
    "contact_reply",
    "is_own_contact_question",
    "stored_name",
]

type ContactsReader = Callable[[int], Awaitable[tuple[CareContact, ...]]]
type NameReader = Callable[[int], Awaitable[str | None]]

#: The two sensitivities a contact row can hold (migration 011): one request names both (D-8).
CONTACT_SENSITIVITIES: Final[frozenset[str]] = frozenset({"private", "location"})


def is_own_contact_question(query: SensitiveQuery) -> bool:
    """Tell whether a contact question is about the owner's own contacts (D-6).

    Args:
        query: A recognized question of one of the contact topics.

    Returns:
        ``True`` for «mi», «mis» or a call order, and always for the key holders; ``False`` for a
        name alone or someone else's phone («los bomberos»), which stay ordinary conversation.
    """
    if query.topic is SensitiveTopic.KEY_HOLDERS:
        return True
    return contact_selector(query.keywords).own


async def stored_name(entity_id: int) -> str | None:
    """Return a contact's stored name, or ``None`` when none is stored.

    Args:
        entity_id: The contact's entity.

    Returns:
        The display name of the person.
    """
    label = await get_person_label(entity_id=entity_id)
    return None if label is None else label.display_name


async def contact_reply(
    query: SensitiveQuery,
    *,
    owner_entity_id: int,
    contacts: ContactsReader = list_active_contacts,
    names: NameReader = stored_name,
) -> tuple[SensitiveReply, int]:
    """Answer one contact question; the caller already authorized and audited the read.

    Args:
        query: A question of ``CONTACT_PHONE``, ``CONTACT_CALL`` or ``KEY_HOLDERS``.
        owner_entity_id: The face-identified owner whose contacts are read.
        contacts: The owner's active contacts, by call order; tests inject doubles.
        names: A contact's stored name, read once per person; tests inject doubles.

    Returns:
        The reply and how many people it concerned (a count for the log).
    """
    rows = await contacts(owner_entity_id)
    named: dict[int, str | None] = {}
    for row in rows:
        if row.contact_entity_id not in named:
            named[row.contact_entity_id] = await names(row.contact_entity_id)
    people = _spoken(_chosen(query, rows, named), named)
    return _worded(query.topic, people), len(people)


def _chosen(
    query: SensitiveQuery, rows: tuple[CareContact, ...], named: Mapping[int, str | None]
) -> tuple[CareContact, ...]:
    """Select the rows the question named, best match first, one per person and phone (D-7)."""
    if query.topic is SensitiveTopic.KEY_HOLDERS:
        return _first_of_each(tuple(row for row in rows if row.has_key), _person)
    selector = contact_selector(query.keywords)
    scores = tuple(
        match_score(
            selector,
            call_order=row.call_order,
            role=row.role.value,
            relationship=row.relationship,
            name=named[row.contact_entity_id],
        )
        for row in rows
    )
    best = max(scores, default=0)
    picked = tuple(row for row, score in zip(rows, scores, strict=True) if best and score == best)
    return _first_of_each(picked, _person_and_phones)[:MAX_SPOKEN_CONTACTS]


def _person(row: CareContact) -> Hashable:
    return row.contact_entity_id


def _person_and_phones(row: CareContact) -> Hashable:
    return (row.contact_entity_id, row.phone, row.phone_alt)


def _first_of_each(
    rows: tuple[CareContact, ...], key: Callable[[CareContact], Hashable]
) -> tuple[CareContact, ...]:
    """Keep the first row of each key, in the given order (call order first)."""
    kept: dict[Hashable, CareContact] = {}
    for row in rows:
        kept.setdefault(key(row), row)
    return tuple(kept.values())


def _spoken(
    rows: tuple[CareContact, ...], named: Mapping[int, str | None]
) -> tuple[SpokenContact, ...]:
    """Turn the selected rows into what the templates say, the label or the role's words."""
    return tuple(
        SpokenContact(
            name=named[row.contact_entity_id],
            descriptor=row.relationship or role_descriptor(row.role.value),
            phone=row.phone,
            phone_alt=row.phone_alt,
        )
        for row in rows
    )


def _worded(topic: SensitiveTopic, people: tuple[SpokenContact, ...]) -> SensitiveReply:
    """Word the selection: an answer, or the fixed sentence of nothing found (D-10)."""
    outcome = SensitiveOutcome.ANSWERED if people else SensitiveOutcome.NOT_REGISTERED
    match topic:
        case SensitiveTopic.KEY_HOLDERS:
            return SensitiveReply(outcome, word_key_holders(people))
        case SensitiveTopic.CONTACT_CALL:
            return SensitiveReply(outcome, f"{CANNOT_CALL} {word_contacts(people)}")
        case _:
            return SensitiveReply(outcome, word_contacts(people))
