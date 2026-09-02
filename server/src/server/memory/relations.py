"""Reverse (relational) queries over declarative memory.

Forward lookup finds entities NAMED in the text; these helpers find entities
LINKED by a relation the text mentions: "¿cómo se llaman mis hijos?" contains
no child's name — the answer lives in facts with predicate ``hijo_de``.
"""

from __future__ import annotations

import logging

from server.db import get_conn
from server.memory.declarative import get_active_facts
from server.memory.lexicon import predicates_in
from server.schemas import EntityWithFacts

logger = logging.getLogger(__name__)


async def find_facts_by_predicate(
    predicate: str,
    *,
    object_value: str | None = None,
) -> list[tuple[int, str, str]]:
    """Return active facts matching *predicate*, joined with their entity name.

    Example: ``find_facts_by_predicate("hijo_de")`` returns one row per child
    known to the robot; ``object_value="Pipec"`` narrows to Pipec's children.

    Args:
        predicate: Canonical relation name (e.g. ``"hijo_de"``).
        object_value: Optional exact filter on the fact's object value.

    Returns:
        List of ``(entity_id, entity_name, object_value)`` tuples.
    """
    conn = get_conn()
    sql = (
        "SELECT f.entity_id, e.name, f.object_value "
        "FROM facts AS f JOIN entities AS e ON e.id = f.entity_id "
        "WHERE f.predicate = ? AND f.superseded_at IS NULL"
    )
    params: list[str] = [predicate]
    if object_value is not None:
        sql += " AND f.object_value = ?"
        params.append(object_value)
    cur = await conn.execute(sql, params)
    rows = await cur.fetchall()
    await cur.close()
    return [(int(r[0]), str(r[1]), str(r[2])) for r in rows]


async def load_entity_by_id(entity_id: int) -> EntityWithFacts | None:
    """Load one entity by row id together with its active facts.

    Args:
        entity_id: Database row id of the entity.

    Returns:
        ``EntityWithFacts`` if the row exists, ``None`` otherwise.
    """
    conn = get_conn()
    cur = await conn.execute("SELECT id, name, type FROM entities WHERE id = ?", (entity_id,))
    row = await cur.fetchone()
    await cur.close()
    if row is None:
        return None
    facts = await get_active_facts(int(row[0]))
    return EntityWithFacts(id=int(row[0]), name=str(row[1]), type=row[2], facts=facts)


async def entities_for_relations(text: str) -> list[EntityWithFacts]:
    """Resolve relation words in *text* to the entities that answer them.

    "mis hijos" triggers ``hijo_de`` → every entity holding an active
    ``hijo_de`` fact is returned with its facts. Single-user household:
    no owner filter is applied — all family relations belong to the owner.
    (Refined per-owner filtering arrives with alias normalization, doc 04 §4.)

    Args:
        text: Raw user input text.

    Returns:
        Entities linked by the triggered predicates, deduped by id.
    """
    predicates = predicates_in(text)
    if not predicates:
        return []

    entities: list[EntityWithFacts] = []
    seen_ids: set[int] = set()
    for predicate in sorted(predicates):
        for entity_id, _name, _obj in await find_facts_by_predicate(predicate):
            if entity_id in seen_ids:
                continue
            seen_ids.add(entity_id)
            ent = await load_entity_by_id(entity_id)
            if ent is not None:
                entities.append(ent)

    logger.info(
        "Relational lookup: predicates=%s entities=%d (%d chars in)",
        sorted(predicates),
        len(entities),
        len(text),
        extra={
            "event": "memory.relational_lookup",
            "predicates": sorted(predicates),
            "entities": len(entities),
            "chars": len(text),
        },
    )
    return entities
