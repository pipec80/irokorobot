"""Entities and facts CRUD — the declarative (structured) memory layer.

Entities are identified by ``(name, type)`` and support alias union-merge
and attribute shallow-merge on upsert. Facts are versioned: asserting a new
fact supersedes (but does not delete) prior active facts for the same
``(entity_id, predicate)``.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager, nullcontext
from enum import StrEnum
import json
import logging
from typing import TYPE_CHECKING, Any

from server import db
from server.db import get_conn
from server.exceptions import AmbiguousEntityError
from server.schemas import EntityType, FactRecord
from server.text_keys import fold_name

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    import aiosqlite

logger = logging.getLogger(__name__)

# Key of ``entities.attributes`` that records which import created a third party.
_IMPORT_KEY_ATTRIBUTE = "import_key"
#: The prefix of every import key a seed file of schema version 1 gives (Plan 0071).
SEED_IMPORT_KEY_PREFIX = "seed-v1:"
# Key of ``entities.attributes`` that marks whether a child is a minor or an adult (ADR 0024
# decision 9). The canonical writer reads it, so the rule holds on every channel.
_GUARDIANSHIP_ATTRIBUTE = "guardianship"


def _transaction(manage_transaction: bool) -> AbstractAsyncContextManager[object]:
    """Own a transaction, or join the one the caller owns (``db.transaction`` is not reentrant)."""
    return db.transaction() if manage_transaction else nullcontext()


class Guardianship(StrEnum):
    """Whether a child of the owner is still a minor; an adult child gets the partner's rule."""

    MINOR = "minor"
    ADULT = "adult"


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
    target = fold_name(name)
    for r in rows:
        if fold_name(str(r[1])) == target:
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
    attrs_json = json.dumps(attributes or {})
    aliases_json = json.dumps(aliases or [])

    # The lookup runs inside the same transaction as the write that follows
    # it: two concurrent upserts for the same folded name must not both see
    # "not found" and both insert a duplicate entity.
    async with db.transaction() as conn:
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
            merged_attrs = attributes or {}
            merged_aliases = aliases or []
            inserted = True
        else:
            entity_id, existing_name, existing_attrs, existing_aliases = existing
            merged_attrs = {**json.loads(existing_attrs), **(attributes or {})}
            # A differently-accented incoming name ("Joaquin" vs "Joaquín")
            # becomes an alias so literal lookups on either spelling keep working.
            name_variants = {name} if name != existing_name else set()
            merged_aliases = sorted(
                set(json.loads(existing_aliases)) | set(aliases or []) | name_variants
            )
            await conn.execute(
                "UPDATE entities SET attributes = ?, aliases = ?, updated_at = datetime('now') "
                "WHERE id = ?",
                (json.dumps(merged_attrs), json.dumps(merged_aliases), entity_id),
            )
            inserted = False

    if inserted:
        logger.info(
            "Entity inserted: type=%s id=%d",
            type,
            entity_id,
            extra={"event": "entity.inserted", "entity_type": type, "entity_id": entity_id},
        )
    else:
        logger.info(
            "Entity merged: type=%s id=%d",
            type,
            entity_id,
            extra={"event": "entity.merged", "entity_type": type, "entity_id": entity_id},
        )
    return entity_id


def _stored_import_key(attributes_json: str) -> object:
    """Read the import key out of an entity's stored attributes, tolerating any other shape.

    Entities made by ``upsert_entity`` or by older code may hold attributes that are not an
    object (or not JSON at all); they simply carry no key.
    """
    try:
        attributes = json.loads(attributes_json)
    except json.JSONDecodeError:
        return None
    return attributes.get(_IMPORT_KEY_ATTRIBUTE) if isinstance(attributes, dict) else None


async def _insert_or_reuse_third_party(
    conn: aiosqlite.Connection,
    *,
    name: str,
    type: EntityType,
    import_key: str | None,
    attributes: Mapping[str, str] | None,
) -> tuple[int, bool]:
    """Insert a third party, or return the one this import key already created.

    Runs on *conn*, inside a transaction the caller owns. It only ever reads or inserts:
    an existing entity is never updated, aliased or merged.

    Args:
        conn: The open connection, mid-transaction.
        name: Name of the third party.
        type: Entity category.
        import_key: Idempotency key of the import, or ``None``.
        attributes: Attributes stored with a new entity; an existing one keeps its own.

    Returns:
        ``(entity_id, created)``; ``created`` is ``False`` for an idempotent re-run.

    Raises:
        AmbiguousEntityError: If an entity of that folded name and type exists and the key
            does not prove it is the same import.
        RuntimeError: If the INSERT returns no row id.
    """
    existing = await _find_entity_folded(name, type)
    if existing is not None:
        existing_id, _name, existing_attrs, _aliases = existing
        if import_key is not None and _stored_import_key(existing_attrs) == import_key:
            return existing_id, False
        logger.warning(
            "Third party refused, an entity of that name exists: type=%s id=%d",
            type,
            existing_id,
            extra={
                "event": "entity.third_party_ambiguous",
                "entity_type": type,
                "entity_id": existing_id,
            },
        )
        raise AmbiguousEntityError(f"A third party of type {type!r} with that name already exists")

    stored = dict(attributes or {})
    if import_key is not None:
        stored[_IMPORT_KEY_ATTRIBUTE] = import_key
    cur = await conn.execute(
        "INSERT INTO entities (name, type, attributes, aliases) VALUES (?, ?, ?, ?)",
        (name, type, json.dumps(stored), json.dumps([])),
    )
    if cur.lastrowid is None:
        raise RuntimeError("INSERT into entities returned no lastrowid for a third party")
    entity_id: int = cur.lastrowid
    await cur.close()
    return entity_id, True


async def create_third_party(
    *,
    name: str,
    type: EntityType,
    import_key: str | None = None,
    attributes: Mapping[str, str] | None = None,
    manage_transaction: bool = True,
) -> int:
    """Create a third party exactly once; never merge it by name (ADR 0022 decision 7).

    The folded ``(name, type)`` (accent and case insensitive, as ``upsert_entity`` folds it)
    is looked up before the INSERT. The same *import_key* on the same entity is an idempotent
    re-run and returns the existing id without touching the row. Any other collision, with
    another key or with none, raises ``AmbiguousEntityError``: two homonymous third parties
    are impossible until the Step 0 ADR decides a migration. The table's own
    ``UNIQUE(name, type)`` remains the last line of defence. A pet is typed ``other``.

    ``manage_transaction=False`` joins a transaction the caller already owns (an atomic
    batch): the call then neither opens, commits nor rolls back one, and ``db.transaction()``
    is not reentrant, so the caller must not nest. A refusal leaves the caller's
    transaction untouched.

    Args:
        name: Name of the third party, as it will be stored.
        type: Entity category (``"person"``, or ``"other"`` for a pet).
        import_key: Idempotency key of the import; stored in ``attributes["import_key"]``.
        attributes: Extra attributes of a new entity (the guardianship marker of a child). An
            entity found again keeps whatever it has: a correction is not a creation's job.
        manage_transaction: ``False`` joins the caller's open transaction.

    Returns:
        Row id of the new entity, or of the entity this key already created.

    Raises:
        AmbiguousEntityError: If an entity of that folded name and type exists and
            *import_key* does not identify it. The message never carries the name or the key.
        ValueError: If *attributes* names ``import_key``, which only *import_key* may set,
            or holds a ``guardianship`` that is neither ``minor`` nor ``adult`` (never echoed).
        RuntimeError: If the INSERT returns no row id.
    """
    if attributes is not None and _IMPORT_KEY_ATTRIBUTE in attributes:
        raise ValueError(f"{_IMPORT_KEY_ATTRIBUTE} is set by the import_key argument")
    if attributes is not None and attributes.get(
        _GUARDIANSHIP_ATTRIBUTE, Guardianship.MINOR
    ) not in set(Guardianship):
        # A typo must not fail open: an adult child would be stored as a minor.
        raise ValueError(f"{_GUARDIANSHIP_ATTRIBUTE} must be one of the Guardianship values")
    # The lookup shares a transaction with the INSERT that follows it: two concurrent
    # creations of one folded name must not both see "not found".
    if manage_transaction:
        async with db.transaction() as conn:
            entity_id, created = await _insert_or_reuse_third_party(
                conn, name=name, type=type, import_key=import_key, attributes=attributes
            )
    else:
        # The caller owns the transaction: no BEGIN, COMMIT or ROLLBACK from here.
        entity_id, created = await _insert_or_reuse_third_party(
            get_conn(), name=name, type=type, import_key=import_key, attributes=attributes
        )

    event = "entity.third_party_created" if created else "entity.third_party_reused"
    # A creation joined to the caller's transaction may still be rolled back by the caller, so it
    # is only staged (debug); one that owned its transaction is committed by now (info).
    logger.log(
        logging.INFO if manage_transaction else logging.DEBUG,
        "Third party %s: type=%s id=%d",
        ("created" if manage_transaction else "staged") if created else "reused",
        type,
        entity_id,
        extra={"event": event, "entity_type": type, "entity_id": entity_id},
    )
    return entity_id


async def is_adult_dependent(entity_id: int) -> bool:
    """Return whether an entity carries the ``adult`` guardianship marker.

    Anything else is ``False``: no marker, ``minor``, attributes that are not a JSON object,
    and an entity that does not exist (fail-open for a child made by the local setup, which
    has no marker; ADR 0024 decision 9).

    Args:
        entity_id: Row id of the entity.

    Returns:
        ``True`` only for the marker ``adult``.
    """
    cursor = await get_conn().execute("SELECT attributes FROM entities WHERE id = ?", (entity_id,))
    row = await cursor.fetchone()
    await cursor.close()
    if row is None:
        return False
    try:
        attributes = json.loads(str(row[0]))
    except json.JSONDecodeError:
        return False
    return isinstance(attributes, dict) and attributes.get(_GUARDIANSHIP_ATTRIBUTE) == (
        Guardianship.ADULT
    )


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
    async with db.transaction() as conn:
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
    garbles ("Martina" → "Martinez"), and the names the robot already knows
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


async def count_entities() -> int:
    """Return how many entities exist, of any type (the seed applier's before-and-after count)."""
    cursor = await get_conn().execute("SELECT COUNT(*) FROM entities")
    row = await cursor.fetchone()
    await cursor.close()
    return 0 if row is None else int(row[0])


async def delete_orphan_import_entities(
    has_rows: Callable[[int], Awaitable[bool]],
    has_contacts: Callable[[int], Awaitable[bool]],
    *,
    manage_transaction: bool = True,
) -> int:
    """Delete every entity a seed import created that nothing refers to any more.

    An entity qualifies only when its ``import_key`` starts with ``seed-v1:`` and both callbacks
    say nothing refers to it; the decision never relies on ``ON DELETE CASCADE`` (a table that
    restricts the delete still fails loudly). The callbacks are the repositories' own checks.

    Args:
        has_rows: Whether a V4 row is about the entity or points at it.
        has_contacts: Whether a contact row names the entity.
        manage_transaction: ``False`` joins the caller's open transaction.

    Returns:
        How many entities were deleted.
    """
    deleted = 0
    async with _transaction(manage_transaction):
        cursor = await get_conn().execute("SELECT id, attributes FROM entities")
        rows = [(int(row[0]), str(row[1])) for row in await cursor.fetchall()]
        await cursor.close()
        for entity_id, attributes in rows:
            key = _stored_import_key(attributes)
            if not (isinstance(key, str) and key.startswith(SEED_IMPORT_KEY_PREFIX)):
                continue
            if await has_rows(entity_id) or await has_contacts(entity_id):
                continue
            await get_conn().execute("DELETE FROM entities WHERE id = ?", (entity_id,))
            deleted += 1
    logger.debug(
        "Orphan import entities deleted: %d",
        deleted,
        extra={"event": "entity.import_orphans_deleted", "count": deleted},
    )
    return deleted
