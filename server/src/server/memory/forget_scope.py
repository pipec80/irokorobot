"""What «everything about one person» is today (Plan 0086 D-7 and D-13, ADR 0039 decision 6).

A person is either an entity linked to the owner (by a relation or a care contact: the alta, the
seed file, ``iroko-admin``) or only a name the owner said in conversation: a third party told by
voice lives only in the diary until learning from conversation exists (after CM-7, ADR 0026
decision 9). For either, the scope is the entity and what hangs from it (its relations, its facts,
its care contacts) and the turns, episodes, recall units and pending topics whose words name it.

Both paths read it: the voice archive sets the scope aside (``archive_rows``), and
``iroko-admin forget person`` deletes it for good (``person_deletions``). The module holds no SQL:
each table is read through its owner. Names are folded (case, accents, punctuation) and matched
as whole words; no name ever reaches a log.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from server.cognition.identity import HouseholdRole
from server.memory import (
    care_contacts,
    conversation_episodes,
    conversation_record,
    declarative,
    pending_store,
    recall_store,
    relational_v4,
)
from server.memory.biometric_consent import has_active_face_consent
from server.memory.conversation_consent import has_active_conversation_consent
from server.memory.deletion_register import Deletion, DeletionKind
from server.memory.household_authorization import get_active_role
from server.memory.voice_consent import has_active_voice_consent
from server.memory.write_types import ArchiveCounts
from server.text_keys import normalize_spanish

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    import aiosqlite

__all__ = [
    "PersonScope",
    "archive_rows",
    "mentions",
    "person_deletions",
    "person_scope",
    "restore_archived",
]

_NORMAL = "normal"


@dataclass(frozen=True)
class PersonScope:
    """What one person reaches; ids only, and its ``repr`` never shows a name."""

    entity_id: int | None
    enrolled: bool
    above_normal: bool
    contacts: tuple[int, ...]
    facts: tuple[int, ...]
    relations: tuple[int, ...]
    turns: tuple[int, ...]
    episodes: tuple[int, ...]  # the ids of the records whose episode goes
    units: tuple[int, ...]
    topics: tuple[int, ...]

    @property
    def archivable(self) -> int:
        """How many rows a voice archive would set aside (what the read-back counts)."""
        return len(self.facts) + len(self.relations) + len(self.units) + len(self.topics)

    @property
    def empty(self) -> bool:
        """Whether nothing at all names the person."""
        return self.entity_id is None and not (
            self.turns or self.episodes or self.units or self.topics
        )


def _folded(text: str) -> str:
    return f" {normalize_spanish(text)} "


def mentions(text: str, names: Iterable[str]) -> bool:
    """Whether *text* holds one of *names* as whole words, folded.

    Args:
        text: The words to search.
        names: The names, as said or stored.

    Returns:
        ``True`` when one of the names appears as whole words.
    """
    folded = _folded(text)
    return any(name.strip() and _folded(name) in folded for name in names)


async def _linked_entity(owner_entity_id: int, words: str) -> int | None:
    """The entity linked to the owner whose name or alias is *words*, or ``None``."""
    relations = await relational_v4.list_active_relations(owner_entity_id, include_archived=True)
    linked = {
        endpoint
        for relation in relations
        for endpoint in (relation.source_entity_id, relation.target_entity_id)
        if endpoint != owner_entity_id
    }
    linked |= {
        contact.contact_entity_id
        for contact in await care_contacts.list_active_contacts(owner_entity_id)
    }
    wanted = _folded(words)
    for entity_id in sorted(linked):
        if any(_folded(name) == wanted for name in await declarative.entity_names(entity_id)):
            return entity_id
    return None


async def _enrolled(entity_id: int, owner_entity_id: int) -> bool:
    """Whether a person is an enrolled member: the owner, a role, a consent of their own."""
    return (
        entity_id == owner_entity_id
        or await get_active_role(entity_id) is not HouseholdRole.UNKNOWN
        or await has_active_face_consent(entity_id)
        or await has_active_voice_consent(entity_id)
        or await has_active_conversation_consent(entity_id)
    )


async def person_scope(
    owner_entity_id: int, *, now: str, entity_id: int | None = None, words: str | None = None
) -> PersonScope:
    """Find what one person reaches, by entity id or by the words that name them.

    Args:
        owner_entity_id: The owner whose memory is searched.
        now: The current instant (an expired record's units are not readable).
        entity_id: The person's entity, when known (``iroko-admin forget person <id>``).
        words: The name as said; it resolves to a linked entity when one bears it, else it is
            a name only talked about.

    Returns:
        The scope; ``empty`` when nothing names the person.
    """
    if entity_id is None and words:
        entity_id = await _linked_entity(owner_entity_id, words)
    names: tuple[str, ...] = (
        await declarative.entity_names(entity_id) if entity_id is not None else ()
    ) or ((words,) if words else ())
    facts, relations = (
        await relational_v4.rows_about_entity(entity_id) if entity_id is not None else ([], [])
    )
    turns = [
        turn_id
        for turn_id, heard, said in await conversation_record.turn_texts()
        if mentions(heard, names) or mentions(said, names)
    ]
    units = sorted(
        {
            unit_id
            for name in names
            for unit_id in await recall_store.unit_ids_naming(
                owner_entity_id=owner_entity_id, phrase=name, now=now
            )
        }
    )
    return PersonScope(
        entity_id=entity_id,
        enrolled=entity_id is not None and await _enrolled(entity_id, owner_entity_id),
        above_normal=any(fact.sensitivity != _NORMAL for fact in facts)
        or any(relation.sensitivity != _NORMAL for relation in relations),
        contacts=await care_contacts.contact_ids_of(entity_id) if entity_id is not None else (),
        facts=tuple(fact.id for fact in facts),
        relations=tuple(relation.id for relation in relations),
        turns=tuple(turns),
        episodes=await _episodes(names, turns),
        units=tuple(units),
        topics=tuple(
            topic_id
            for topic_id, text in await pending_store.topic_texts(owner_entity_id)
            if mentions(text, names)
        ),
    )


async def _episodes(names: Sequence[str], turns: Sequence[int]) -> tuple[int, ...]:
    """The records whose episode names the person or holds one of the named turns.

    A summary cannot be partly unsaid: deleting a story deletes its segment's whole episode
    (ADR 0032 decision 2).
    """
    records = {
        record_id
        for record_id, summary in await conversation_episodes.episode_summaries()
        if mentions(summary, names)
    }
    for turn_id in turns:
        record_id = await conversation_record.turn_record_id(turn_id)
        if record_id is not None:
            records.add(record_id)
    return tuple(sorted(records))


def person_deletions(scope: PersonScope) -> list[Deletion]:
    """The register lines that delete a person for good, in the order the keys need.

    The care contacts first (they hold the entity's ``RESTRICT`` key), then the turns and the
    episodes that name the person, then the entity (its relations, facts and candidates go with
    it by ``CASCADE``).
    """
    deletions = [Deletion(DeletionKind.CARE_CONTACT, contact) for contact in scope.contacts]
    deletions += [Deletion(DeletionKind.TURN, turn) for turn in scope.turns]
    deletions += [Deletion(DeletionKind.EPISODE, record) for record in scope.episodes]
    if scope.entity_id is not None:
        deletions.append(Deletion(DeletionKind.ENTITY, scope.entity_id))
    return deletions


async def archive_rows(
    conn: aiosqlite.Connection,
    *,
    facts: Sequence[int] = (),
    relations: Sequence[int] = (),
    units: Sequence[int] = (),
    topics: Sequence[int] = (),
    at: str,
) -> ArchiveCounts:
    """Set rows aside, each through its owner, inside the caller's transaction.

    Args:
        conn: The connection of an open ``db.transaction()``.
        facts: Literal facts to set aside.
        relations: Relations to set aside.
        units: Recall units to set aside.
        topics: Pending topics to set aside.
        at: The one archive instant of this request.

    Returns:
        How many rows of each kind were set aside.
    """
    fact_count, relation_count = await relational_v4.archive_v4_rows(
        conn, facts=facts, relations=relations, at=at
    )
    return ArchiveCounts(
        facts=fact_count,
        relations=relation_count,
        units=await recall_store.archive_units(conn, units, at=at),
        topics=await pending_store.archive_topics(conn, topics, at=at),
    )


async def restore_archived(conn: aiosqlite.Connection, *, at: str) -> ArchiveCounts:
    """Bring back every row set aside at *at* (``iroko-admin archive restore``).

    Args:
        conn: The connection of an open ``db.transaction()``.
        at: The archive instant of the group.

    Returns:
        How many rows of each kind came back.
    """
    fact_count, relation_count = await relational_v4.restore_archived_v4(conn, at=at)
    return ArchiveCounts(
        facts=fact_count,
        relations=relation_count,
        units=await recall_store.restore_archived_units(conn, at=at),
        topics=await pending_store.restore_archived_topics(conn, at=at),
    )
