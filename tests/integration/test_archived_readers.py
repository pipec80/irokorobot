"""Archived rows are never said, offered or searched, and come back (Plan 0086 Task 1, D-8 to D-10).

Canary rows only.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
import sqlite3
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from server.memory import pending_store, recall_store, relational_v4
from server.memory.conversation_types import RecordedTurn, TurnVerdict
from server.memory.declarative import upsert_entity
from server.memory.predicate_registry import PredicateDefinition, resolve_predicate
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_DIMENSIONS = 768
_SAID = datetime(2026, 11, 3, 15, tzinfo=UTC)
_SAID_ISO = "2026-11-03T15:00:00.000000+00:00"
_NOW = "2026-11-04T12:00:00.000000+00:00"
_FUTURE = "2027-11-03T10:00:00.000000+00:00"
_ARCHIVED = "2026-11-17T10:00:00.000000+00:00"
_CANARY = "quokka"


@pytest.fixture
async def owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "archive.db")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        yield await upsert_entity(name="Canary Owner", type="person")
    finally:
        await db.close_db()
        db._conn = None


def _definition(name: str) -> PredicateDefinition:
    definition = resolve_predicate(name)
    assert definition is not None
    return definition


async def _taste(owner: int, value: str = f"el {_CANARY}") -> int:
    fact = await relational_v4.assert_literal_fact(
        subject_entity_id=owner,
        definition=_definition("likes"),
        value=value,
        visibility="personal",
        sensitivity="normal",
    )
    return fact.id


async def _relation(owner: int) -> int:
    friend = await upsert_entity(name="Canaria", type="person")
    relation = await relational_v4.assert_entity_relation(
        source_entity_id=owner,
        definition=_definition("has_sibling"),
        target_entity_id=friend,
    )
    return relation.id


async def _record(owner: int) -> int:
    async with db.transaction() as conn:
        cursor = await conn.execute(
            "INSERT INTO conversation_records (owner_entity_id, started_at, last_turn_at, "
            "closed_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (owner, _SAID_ISO, _SAID_ISO, _SAID_ISO, _FUTURE),
        )
        record_id = int(cursor.lastrowid or 0)
        await cursor.close()
    return record_id


async def _unit(owner: int, record_id: int) -> int:
    turn = RecordedTurn(
        at=_SAID,
        heard=f"fuimos al cine con {_CANARY}",
        said="zzrobotzz",
        voice=TurnVerdict.VERIFIED,
        correlation_id=uuid4(),
    )
    async with db.transaction() as conn:
        unit_id = await recall_store.insert_turn_unit(
            conn, record_id=record_id, owner_entity_id=owner, turn=turn
        )
    vector = [0.0] * _DIMENSIONS
    vector[0] = 1.0
    assert await recall_store.store_vector(unit_id, vector, model="canary-model")
    return unit_id


async def _topic(owner: int, record_id: int) -> int:
    async with db.transaction() as conn:
        topic_id = await pending_store.insert_unnamed(
            conn,
            owner_entity_id=owner,
            record_id=record_id,
            correlation_id=UUID(int=7),
            said_day=date(2026, 11, 3),
            due_day=date(2026, 11, 4),
            heard="mañana veo a la canaria",
            sensitivity="normal",
            now=_SAID,
        )
    assert await pending_store.set_topic(topic_id, _CANARY)
    return topic_id


async def _archive(*, facts: tuple[int, ...] = (), relations: tuple[int, ...] = ()) -> None:
    async with db.transaction() as conn:
        await relational_v4.archive_v4_rows(conn, facts=facts, relations=relations, at=_ARCHIVED)


async def _archive_units(units: tuple[int, ...] = (), topics: tuple[int, ...] = ()) -> None:
    async with db.transaction() as conn:
        await recall_store.archive_units(conn, units, at=_ARCHIVED)
        await pending_store.archive_topics(conn, topics, at=_ARCHIVED)


async def _restore() -> tuple[int, int, int, int]:
    async with db.transaction() as conn:
        facts, relations = await relational_v4.restore_archived_v4(conn, at=_ARCHIVED)
        units = await recall_store.restore_archived_units(conn, at=_ARCHIVED)
        topics = await pending_store.restore_archived_topics(conn, at=_ARCHIVED)
    return facts, relations, units, topics


async def test_migration_021_adds_archived_at_and_refuses_a_malformed_instant(owner: int) -> None:
    cursor = await db.get_conn().execute("PRAGMA user_version")
    version = await cursor.fetchone()
    await cursor.close()
    assert version is not None
    assert int(version[0]) == db.latest_schema_version() == 21
    fact_id = await _taste(owner)
    for table in ("literal_facts_v4", "entity_relations_v4", "recall_units", "pending_topics"):
        cursor = await db.get_conn().execute(f"PRAGMA table_info({table})")
        columns = {str(row[1]) for row in await cursor.fetchall()}
        await cursor.close()
        assert "archived_at" in columns, table
    with pytest.raises(sqlite3.IntegrityError):
        async with db.transaction() as conn:
            await conn.execute(
                "UPDATE literal_facts_v4 SET archived_at = '2026-11-17 10:00:00' WHERE id = ?",
                (fact_id,),
            )


async def test_an_archived_taste_is_not_on_the_card_nor_read(owner: int) -> None:
    fact_id = await _taste(owner)

    await _archive(facts=(fact_id,))

    card = await relational_v4.list_card_literals(
        subject_entity_id=owner, predicates=frozenset({"likes"})
    )
    active = await relational_v4.get_active_literal_facts(
        subject_entity_id=owner, definition=_definition("likes")
    )
    assert card == []
    assert active == []
    assert await relational_v4.list_active_facts(owner) == []
    kept = await relational_v4.get_active_literal_facts(
        subject_entity_id=owner, definition=_definition("likes"), include_archived=True
    )
    assert [fact.archived_at for fact in kept] == [_ARCHIVED]


async def test_an_archived_relation_is_not_read(owner: int) -> None:
    relation_id = await _relation(owner)

    await _archive(relations=(relation_id,))

    assert (
        await relational_v4.get_active_entity_relations(
            definition=_definition("has_sibling"), source_entity_id=owner
        )
        == []
    )
    assert await relational_v4.list_active_relations(owner) == []
    assert [
        row.id for row in await relational_v4.list_active_relations(owner, include_archived=True)
    ] == [relation_id]


async def test_an_archived_unit_is_found_by_no_search(owner: int) -> None:
    record_id = await _record(owner)
    unit_id = await _unit(owner, record_id)
    vector = [0.0] * _DIMENSIONS
    vector[0] = 1.0

    await _archive_units((unit_id,))

    assert (
        await recall_store.lexical_hits(
            owner_entity_id=owner, terms=(_CANARY,), since=None, until=None, now=_NOW, limit=10
        )
        == []
    )
    assert (
        await recall_store.vector_hits(
            owner_entity_id=owner, vector=vector, since=None, until=None, now=_NOW, k=5
        )
        == []
    )
    assert await recall_store.units_by_id([unit_id], owner_entity_id=owner, now=_NOW) == []
    assert (
        await recall_store.recent_units(
            owner_entity_id=owner,
            since="2026-11-03T00:00:00.000000+00:00",
            until="2026-11-04T00:00:00.000000+00:00",
            now=_NOW,
            limit=5,
        )
        == []
    )


async def test_an_archived_topic_is_not_greeted(owner: int) -> None:
    record_id = await _record(owner)
    topic_id = await _topic(owner, record_id)
    assert await pending_store.due_topic(owner, today=date(2026, 11, 5)) is not None

    await _archive_units(topics=(topic_id,))

    assert await pending_store.due_topic(owner, today=date(2026, 11, 5)) is None


async def test_a_restore_brings_every_kind_back(owner: int) -> None:
    fact_id = await _taste(owner)
    relation_id = await _relation(owner)
    record_id = await _record(owner)
    unit_id = await _unit(owner, record_id)
    topic_id = await _topic(owner, record_id)
    await _archive(facts=(fact_id,), relations=(relation_id,))
    await _archive_units((unit_id,), (topic_id,))

    assert await _restore() == (1, 1, 1, 1)

    assert [fact.id for fact in await relational_v4.list_active_facts(owner)] == [fact_id]
    assert [row.id for row in await relational_v4.list_active_relations(owner)] == [relation_id]
    assert await recall_store.units_by_id([unit_id], owner_entity_id=owner, now=_NOW) != []
    assert await pending_store.due_topic(owner, today=date(2026, 11, 5)) is not None


async def test_archiving_twice_keeps_the_first_instant(owner: int) -> None:
    fact_id = await _taste(owner)
    await _archive(facts=(fact_id,))

    async with db.transaction() as conn:
        counts = await relational_v4.archive_v4_rows(
            conn, facts=(fact_id,), relations=(), at="2026-11-18T10:00:00.000000+00:00"
        )

    assert counts == (0, 0)
    fact = await relational_v4.get_literal_fact(fact_id)
    assert fact is not None
    assert fact.archived_at == _ARCHIVED
