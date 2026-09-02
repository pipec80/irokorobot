"""Entities and facts CRUD — the declarative (structured) memory layer.

Entities are identified by ``(name, type)`` and support alias union-merge
and attribute shallow-merge on upsert. Facts are versioned: asserting a new
fact supersedes (but does not delete) prior active facts for the same
``(entity_id, predicate)``.
"""

from __future__ import annotations

import json
import logging
from typing import Any
import unicodedata

from server.db import get_conn
from server.memory.outbox import write_outbox
from server.schemas import EntityType, EntityWithFacts, FactRecord

logger = logging.getLogger(__name__)


def _fold_name(name: str) -> str:
    """Return an accent- and case-insensitive form of *name* for dedup.

    Whisper drops accents unpredictably ("Máximo" → "Maximo"); without
    folding, each variant becomes a separate entity and the dynamic
    hotwords then reinforce the misspelled one.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


async def _find_entity_folded(name: str, type: EntityType) -> tuple[int, str, str, str] | None:
    """Find an entity of *type* whose folded name matches *name*.

    Scans the (small, single-household) entities table in Python — SQLite
    has no accent-insensitive collation without an extension.

    Args:
        name: Candidate entity name.
        type: Entity category to search within.

    Returns:
        ``(id, name, attributes_json, aliases_json)`` or ``None``.
    """
    conn = get_conn()
    cur = await conn.execute(
        "SELECT id, name, attributes, aliases FROM entities WHERE type = ?",
        (type,),
    )
    rows = await cur.fetchall()
    await cur.close()
    target = _fold_name(name)
    for r in rows:
        if _fold_name(str(r[1])) == target:
            return (int(r[0]), str(r[1]), str(r[2]), str(r[3]))
    return None


async def upsert_entity(
    *,
    name: str,
    type: EntityType,
    attributes: dict[str, Any] | None = None,
    aliases: list[str] | None = None,
) -> int:
    """Insert or merge an entity row.

    On conflict (same ``type`` + accent/case-insensitive ``name`` match):
    aliases are union-merged, attributes are shallow-merged (new keys win),
    and a differently-spelled incoming name is preserved as an alias.

    Args:
        name: Canonical entity name.
        type: Entity category (one of the ``EntityType`` literals).
        attributes: Optional key-value dict; merged into existing attrs.
        aliases: Optional alternate names; unioned with existing aliases.

    Returns:
        Database row id of the inserted or existing entity.
    """
    conn = get_conn()
    attrs_json = json.dumps(attributes or {})
    aliases_json = json.dumps(aliases or [])

    existing = await _find_entity_folded(name, type)

    if existing is None:
        cur = await conn.execute(
            "INSERT INTO entities (name, type, attributes, aliases) VALUES (?, ?, ?, ?)",
            (name, type, attrs_json, aliases_json),
        )
        if cur.lastrowid is None:
            raise RuntimeError(f"INSERT into entities returned no lastrowid for {name!r}")
        entity_id: int = cur.lastrowid
        await cur.close()
        await conn.commit()
        await write_outbox(
            "entity",
            entity_id,
            "insert",
            {
                "name": name,
                "type": type,
                "attributes": attributes,
                "aliases": aliases,
            },
        )
        logger.info(
            "Entity inserted: type=%s id=%d",
            type,
            entity_id,
            extra={"event": "entity.inserted", "entity_type": type, "entity_id": entity_id},
        )
        return entity_id

    entity_id, existing_name, existing_attrs, existing_aliases = existing
    merged_attrs = {**json.loads(existing_attrs), **(attributes or {})}
    # A differently-accented incoming name ("Maximo" vs "Máximo") becomes an
    # alias so literal lookups on either spelling keep working.
    name_variants = {name} if name != existing_name else set()
    merged_aliases = sorted(set(json.loads(existing_aliases)) | set(aliases or []) | name_variants)
    await conn.execute(
        "UPDATE entities SET attributes = ?, aliases = ?, updated_at = datetime('now') "
        "WHERE id = ?",
        (json.dumps(merged_attrs), json.dumps(merged_aliases), entity_id),
    )
    await conn.commit()
    await write_outbox(
        "entity",
        entity_id,
        "update",
        {
            "attributes": merged_attrs,
            "aliases": merged_aliases,
        },
    )
    logger.info(
        "Entity merged: type=%s id=%d",
        type,
        entity_id,
        extra={"event": "entity.merged", "entity_type": type, "entity_id": entity_id},
    )
    return entity_id


async def assert_fact(
    *,
    entity_id: int,
    predicate: str,
    object_value: str,
    confidence: float = 0.9,
    source_memory_id: int | None = None,
    supersede_existing: bool = True,
) -> int:
    """Insert a fact, optionally superseding prior active facts.

    Superseded facts are soft-deleted (``superseded_at`` is set) so history
    is preserved.

    Args:
        entity_id: Row id of the entity this fact belongs to.
        predicate: Relation name in snake_case (e.g. ``"vive_en"``).
        object_value: Value of the relation.
        confidence: Confidence score in ``[0, 1]``.
        source_memory_id: Optional memory row id that sourced this fact.
        supersede_existing: If ``True``, mark prior active facts for the
            same ``(entity_id, predicate)`` as superseded.

    Returns:
        Row id of the newly inserted fact.
    """
    conn = get_conn()
    cur = await conn.execute(
        "INSERT INTO facts "
        "(entity_id, predicate, object_value, confidence, source_memory_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (entity_id, predicate, object_value, confidence, source_memory_id),
    )
    if cur.lastrowid is None:
        raise RuntimeError("INSERT into facts returned no lastrowid")
    fact_id: int = cur.lastrowid
    await cur.close()
    if supersede_existing:
        # The new fact is inserted first so superseded rows can record WHO
        # replaced them (superseded_by) — full versioning, not just a tombstone.
        await conn.execute(
            "UPDATE facts SET superseded_at = datetime('now'), superseded_by = ? "
            "WHERE entity_id = ? AND predicate = ? AND superseded_at IS NULL AND id != ?",
            (fact_id, entity_id, predicate, fact_id),
        )
    await conn.commit()
    await write_outbox(
        "fact",
        fact_id,
        "insert",
        {
            "entity_id": entity_id,
            "predicate": predicate,
            "object_value": object_value,
            "confidence": confidence,
        },
    )
    logger.info(
        "Fact asserted: entity=%d predicate=%s (%d chars)",
        entity_id,
        predicate,
        len(str(object_value)),
        extra={
            "event": "fact.asserted",
            "entity_id": entity_id,
            "predicate": predicate,
            "chars": len(str(object_value)),
        },
    )
    return fact_id


async def find_entities_by_name(name: str, *, limit: int = 5) -> list[dict[str, Any]]:
    """Find entities by exact name or alias substring match.

    SQLite has no trigram index by default; uses exact match, LIKE, and
    JSON-encoded alias lookup. Sufficient for a single-user homelab.

    Args:
        name: Name fragment or full entity name to search.
        limit: Maximum number of results to return.

    Returns:
        List of entity dicts with keys ``id``, ``name``, ``type``,
        ``attributes`` (dict), ``aliases`` (list).
    """
    conn = get_conn()
    cur = await conn.execute(
        "SELECT id, name, type, attributes, aliases FROM entities "
        "WHERE name = ? OR name LIKE ? OR aliases LIKE ? "
        "LIMIT ?",
        (name, f"%{name}%", f'%"{name}"%', limit),
    )
    rows = await cur.fetchall()
    await cur.close()
    return [
        {
            "id": r[0],
            "name": r[1],
            "type": r[2],
            "attributes": json.loads(r[3]),
            "aliases": json.loads(r[4]),
        }
        for r in rows
    ]


async def list_entity_names(*, limit: int = 30) -> list[str]:
    """Return names of the most recently updated entities.

    Feeds Whisper's dynamic hotwords: proper nouns are exactly what the STT
    garbles ("Dominga" → "Dominguez"), and the names the robot already knows
    are the ones most likely to be spoken again.

    Args:
        limit: Maximum number of names to return.

    Returns:
        Entity names, most recently updated first.
    """
    conn = get_conn()
    cur = await conn.execute(
        "SELECT name FROM entities ORDER BY updated_at DESC LIMIT ?",
        (limit,),
    )
    rows = await cur.fetchall()
    await cur.close()
    return [str(r[0]) for r in rows]


async def get_active_facts(entity_id: int) -> list[FactRecord]:
    """Return all non-superseded facts for an entity.

    Args:
        entity_id: Row id of the entity.

    Returns:
        List of ``FactRecord`` ordered by assertion time descending.
    """
    conn = get_conn()
    cur = await conn.execute(
        "SELECT predicate, object_value, confidence FROM facts "
        "WHERE entity_id = ? AND superseded_at IS NULL "
        "ORDER BY asserted_at DESC",
        (entity_id,),
    )
    rows = await cur.fetchall()
    await cur.close()
    return [FactRecord(predicate=r[0], object_value=r[1], confidence=r[2]) for r in rows]


async def load_entity_with_facts(name: str) -> EntityWithFacts | None:
    """Load the first entity matching *name* together with its active facts.

    Args:
        name: Entity name or alias to search.

    Returns:
        ``EntityWithFacts`` if found, ``None`` otherwise.
    """
    matches = await find_entities_by_name(name, limit=1)
    if not matches:
        return None
    e = matches[0]
    facts = await get_active_facts(e["id"])
    return EntityWithFacts(id=e["id"], name=e["name"], type=e["type"], facts=facts)
