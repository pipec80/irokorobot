"""Read the owner's own contacts by voice after the checks (Plan 0082, ADR 0037 decision 1).

``sensitive_reply`` runs the audience and level checks of every sensitive question; for a contact
question it then hands over to ``contact_reply``, which makes the one policy request of D-8
(visibility ``personal``, sensitivity ``private`` and ``location``, the two the table holds), writes
its audit row **before** the read, reads the active contacts through ``list_active_contacts``,
selects what the question named (``contact_questions``) and words it with ``contact_answers``.

It reads only: nothing here writes a contact, calls a phone or raises an alert. A question that
names no own contact is never read (``is_own_contact_question``, decided before any check). No
phone, name or relationship reaches a log line or an exception message.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from server.cognition.authorization import (
    AuthorizationRequest,
    DataSensitivity,
    DataVisibility,
)
from server.cognition.contact_answers import (
    CANNOT_CALL,
    MAX_SPOKEN_CONTACTS,
    SpokenContact,
    role_descriptor,
    word_contacts,
    word_key_holders,
)
from server.cognition.contact_questions import contact_selector, match_score
from server.cognition.models import AuthorizationAction, AuthorizationStatus
from server.cognition.response_plan import SensitiveOutcome, SensitiveReply
from server.cognition.sensitive_questions import SensitiveTopic
from server.memory.care_contacts import list_active_contacts
from server.memory.entity_labels import get_person_label

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from datetime import datetime
    from uuid import UUID

    from server.cognition.authorization import ConsentStatus
    from server.cognition.identity import ActivePersonContext
    from server.cognition.sensitive_questions import SensitiveQuery
    from server.memory.candidate_policy import AuditWriter, PolicyEvaluator
    from server.memory.care_contacts import CareContact

__all__ = [
    "ContactsReader",
    "NameReader",
    "contact_reply",
    "is_own_contact_question",
    "stored_name",
]

type ContactsReader = Callable[[int], Awaitable[tuple[CareContact, ...]]]
type NameReader = Callable[[int], Awaitable[str | None]]

#: The two sensitivities a contact row can hold (migration 011): one request names both (D-8).
_CONTACT_SENSITIVITIES: Final = frozenset({DataSensitivity.PRIVATE, DataSensitivity.LOCATION})


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
    actor: ActivePersonContext,
    query: SensitiveQuery,
    *,
    consent: ConsentStatus,
    correlation_id: UUID,
    now: datetime,
    policy: PolicyEvaluator,
    audit: AuditWriter,
    contacts: ContactsReader = list_active_contacts,
    names: NameReader = stored_name,
) -> tuple[SensitiveReply, int]:
    """Answer one contact question once the audience and level checks passed.

    Args:
        actor: The face-identified owner (the caller checked it).
        query: A question of ``CONTACT_PHONE``, ``CONTACT_CALL`` or ``KEY_HOLDERS``.
        consent: The consent of a ``location`` read (Plan 0079 D-9).
        correlation_id: The turn's id, so the audit row joins the rest of the turn.
        now: The caller's clock reading.
        policy: The pure evaluator.
        audit: The audit writer; a failure propagates, so nothing is read.
        contacts: The owner's active contacts, by call order; tests inject doubles.
        names: A contact's stored name; tests inject doubles.

    Returns:
        The reply and how many people it concerned (a count for the log).
    """
    person_id = actor.person_id
    if person_id is None:  # unreachable after the caller's pre-check; the type narrows here
        return SensitiveReply(SensitiveOutcome.DENIED), 0
    request = AuthorizationRequest(
        actor=actor,
        action=AuthorizationAction.READ_PERSONAL_CONVERSATION_MEMORY,
        target_person_id=person_id,
        visibility=frozenset({DataVisibility.PERSONAL}),
        sensitivity=_CONTACT_SENSITIVITIES,
        consent=consent,
        correlation_id=correlation_id,
        requested_at=now,
    )
    decision = policy(request)
    await audit(request, decision)
    if decision.decision is not AuthorizationStatus.ALLOWED:
        return SensitiveReply(SensitiveOutcome.DENIED), 0
    people = await _chosen(query, await contacts(person_id), names)
    return _worded(query.topic, people), len(people)


async def _chosen(
    query: SensitiveQuery, rows: tuple[CareContact, ...], names: NameReader
) -> tuple[SpokenContact, ...]:
    """Select the rows the question named, best match first, one per person and phone (D-7)."""
    if query.topic is SensitiveTopic.KEY_HOLDERS:
        picked = tuple(row for row in rows if row.has_key)
        return await _spoken(_one_per_person(picked, by_phone=False), names)
    selector = contact_selector(query.keywords)
    named = {row.contact_entity_id: await names(row.contact_entity_id) for row in rows}
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
    unique = _one_per_person(picked, by_phone=True)[:MAX_SPOKEN_CONTACTS]
    return await _spoken(unique, names)


def _one_per_person(rows: tuple[CareContact, ...], *, by_phone: bool) -> tuple[CareContact, ...]:
    """Keep the first row of each person (and, for a phone question, each pair of phones)."""
    seen: set[tuple[int, str, str | None] | int] = set()
    kept: list[CareContact] = []
    for row in rows:
        key = (
            (row.contact_entity_id, row.phone, row.phone_alt) if by_phone else row.contact_entity_id
        )
        if key not in seen:
            seen.add(key)
            kept.append(row)
    return tuple(kept)


async def _spoken(rows: tuple[CareContact, ...], names: NameReader) -> tuple[SpokenContact, ...]:
    return tuple(
        [
            SpokenContact(
                name=await names(row.contact_entity_id),
                descriptor=row.relationship or role_descriptor(row.role.value),
                phone=row.phone,
                phone_alt=row.phone_alt,
            )
            for row in rows
        ]
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
