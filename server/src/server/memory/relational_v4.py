"""Typed repositories for additive relational-memory v4 storage.

These repositories are intentionally isolated from legacy runtime retrieval,
outbox publication, prompt assembly, and authorization. A later policy-gated
plan owns any production reader or writer cutover.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from server import db
from server.db import get_conn
from server.memory.predicate_registry import (
    PredicateCardinality,
    PredicateDefinition,
    PredicateKind,
    normalize_literal,
)

if TYPE_CHECKING:
    import aiosqlite


class AssertionLifecycle(StrEnum):
    """Lifecycle states stored by relational-memory v4 records."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    DISPUTED = "disputed"
    REVOKED = "revoked"
    EXPIRED = "expired"


class LiteralFactV4(BaseModel):
    """Immutable row returned after a v4 literal-fact write or lookup."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int
    subject_entity_id: int
    predicate: str
    value_text: str
    confidence: float
    source_memory_id: int | None
    asserted_at: str
    valid_from: str | None
    valid_to: str | None
    lifecycle: AssertionLifecycle
    visibility: str
    sensitivity: str
    superseded_at: str | None
    superseded_by: int | None


class EntityRelationV4(BaseModel):
    """Immutable row returned after a v4 entity-relation write or lookup."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int
    source_entity_id: int
    predicate: str
    target_entity_id: int
    confidence: float
    source_memory_id: int | None
    asserted_at: str
    valid_from: str | None
    valid_to: str | None
    lifecycle: AssertionLifecycle
    visibility: str
    sensitivity: str
    superseded_at: str | None
    superseded_by: int | None


type SqlValue = int | float | str | None
type SqlRow = tuple[SqlValue, ...]


def _required_int(value: SqlValue) -> int:
    """Read an integer field guaranteed by the v4 schema."""
    if isinstance(value, int):
        return value
    raise TypeError(f"expected integer SQLite value, got {type(value).__name__}")


def _required_float(value: SqlValue) -> float:
    """Read a numeric field guaranteed by the v4 schema."""
    if isinstance(value, (int, float)):
        return float(value)
    raise TypeError(f"expected numeric SQLite value, got {type(value).__name__}")


def _required_text(value: SqlValue) -> str:
    """Read a text field guaranteed by the v4 schema."""
    if isinstance(value, str):
        return value
    raise TypeError(f"expected text SQLite value, got {type(value).__name__}")


def _optional_text(value: SqlValue) -> str | None:
    """Read a nullable text field guaranteed by the v4 schema."""
    return None if value is None else _required_text(value)


def _optional_int(value: SqlValue) -> int | None:
    """Read a nullable integer field guaranteed by the v4 schema."""
    return None if value is None else _required_int(value)


async def _entity_type(entity_id: int) -> str:
    """Return an entity's persisted type or reject a missing ID."""
    conn = get_conn()
    cursor = await conn.execute("SELECT type FROM entities WHERE id = ?", (entity_id,))
    row = await cursor.fetchone()
    await cursor.close()
    if row is None:
        raise ValueError(f"entity {entity_id} does not exist")
    return str(row[0])


async def _validate_literal_subject(
    subject_entity_id: int,
    definition: PredicateDefinition,
) -> None:
    """Ensure a literal definition is applied to an allowed entity type."""
    if definition.kind is not PredicateKind.LITERAL:
        raise ValueError(f"{definition.canonical_id} is not a literal predicate")
    subject_type = await _entity_type(subject_entity_id)
    if subject_type not in definition.subject_types:
        raise ValueError(f"{definition.canonical_id} does not allow subject type {subject_type}")


async def _validate_relation_endpoints(
    source_entity_id: int,
    target_entity_id: int,
    definition: PredicateDefinition,
) -> None:
    """Ensure a relation definition accepts the persisted endpoint types."""
    if definition.kind is not PredicateKind.RELATION:
        raise ValueError(f"{definition.canonical_id} is not a relation predicate")
    if source_entity_id == target_entity_id:
        raise ValueError("v4 entity relations reject a self-relation")
    source_type = await _entity_type(source_entity_id)
    target_type = await _entity_type(target_entity_id)
    if source_type not in definition.subject_types:
        raise ValueError(f"{definition.canonical_id} does not allow source type {source_type}")
    if target_type not in definition.target_types:
        raise ValueError(f"{definition.canonical_id} does not allow target type {target_type}")


def _literal_from_row(row: SqlRow) -> LiteralFactV4:
    """Convert one selected literal row to its immutable domain model."""
    return LiteralFactV4(
        id=_required_int(row[0]),
        subject_entity_id=_required_int(row[1]),
        predicate=_required_text(row[2]),
        value_text=_required_text(row[3]),
        confidence=_required_float(row[4]),
        source_memory_id=_optional_int(row[5]),
        asserted_at=_required_text(row[6]),
        valid_from=_optional_text(row[7]),
        valid_to=_optional_text(row[8]),
        lifecycle=AssertionLifecycle(_required_text(row[9])),
        visibility=_required_text(row[10]),
        sensitivity=_required_text(row[11]),
        superseded_at=_optional_text(row[12]),
        superseded_by=_optional_int(row[13]),
    )


def _relation_from_row(row: SqlRow) -> EntityRelationV4:
    """Convert one selected relation row to its immutable domain model."""
    return EntityRelationV4(
        id=_required_int(row[0]),
        source_entity_id=_required_int(row[1]),
        predicate=_required_text(row[2]),
        target_entity_id=_required_int(row[3]),
        confidence=_required_float(row[4]),
        source_memory_id=_optional_int(row[5]),
        asserted_at=_required_text(row[6]),
        valid_from=_optional_text(row[7]),
        valid_to=_optional_text(row[8]),
        lifecycle=AssertionLifecycle(_required_text(row[9])),
        visibility=_required_text(row[10]),
        sensitivity=_required_text(row[11]),
        superseded_at=_optional_text(row[12]),
        superseded_by=_optional_int(row[13]),
    )


_LITERAL_COLUMNS = """
    id, subject_entity_id, predicate, value_text, confidence, source_memory_id, asserted_at,
    valid_from, valid_to, lifecycle, visibility, sensitivity, superseded_at, superseded_by
"""
_RELATION_COLUMNS = """
    id, source_entity_id, predicate, target_entity_id, confidence, source_memory_id, asserted_at,
    valid_from, valid_to, lifecycle, visibility, sensitivity, superseded_at, superseded_by
"""


async def get_literal_fact(literal_fact_id: int) -> LiteralFactV4 | None:
    """Return one v4 literal fact without applying runtime authorization."""
    conn = get_conn()
    cursor = await conn.execute(
        f"SELECT {_LITERAL_COLUMNS} FROM literal_facts_v4 WHERE id = ?",  # noqa: S608
        (literal_fact_id,),
    )
    row = await cursor.fetchone()
    await cursor.close()
    return _literal_from_row(tuple(row)) if row is not None else None


async def get_entity_relation(relation_id: int) -> EntityRelationV4 | None:
    """Return one v4 relation without applying runtime authorization."""
    conn = get_conn()
    cursor = await conn.execute(
        f"SELECT {_RELATION_COLUMNS} FROM entity_relations_v4 WHERE id = ?",  # noqa: S608
        (relation_id,),
    )
    row = await cursor.fetchone()
    await cursor.close()
    return _relation_from_row(tuple(row)) if row is not None else None


async def get_active_literal_facts(
    *,
    subject_entity_id: int,
    definition: PredicateDefinition,
) -> list[LiteralFactV4]:
    """Return active facts for repository tests and future policy-gated callers."""
    if definition.kind is not PredicateKind.LITERAL:
        raise ValueError(f"{definition.canonical_id} is not a literal predicate")
    conn = get_conn()
    cursor = await conn.execute(
        f"SELECT {_LITERAL_COLUMNS} FROM literal_facts_v4 "  # noqa: S608
        "WHERE subject_entity_id = ? AND predicate = ? AND lifecycle = 'active' ORDER BY id",
        (subject_entity_id, definition.canonical_id),
    )
    rows = await cursor.fetchall()
    await cursor.close()
    return [_literal_from_row(tuple(row)) for row in rows]


async def get_active_entity_relations(
    *,
    definition: PredicateDefinition,
    source_entity_id: int | None = None,
    target_entity_id: int | None = None,
) -> list[EntityRelationV4]:
    """Return active relations for repository tests and future policy-gated callers.

    This raw repository does not apply runtime authorization. Callers in the
    cognitive path must authorize before requesting relation values.

    Args:
        definition: Closed relation predicate to retrieve.
        source_entity_id: Optional source entity filter.
        target_entity_id: Optional target entity filter.

    Returns:
        Active relation rows matching the supplied predicate and filters.
    """
    if definition.kind is not PredicateKind.RELATION:
        raise ValueError(f"{definition.canonical_id} is not a relation predicate")
    conn = get_conn()
    sql = (
        f"SELECT {_RELATION_COLUMNS} FROM entity_relations_v4 "  # noqa: S608
        "WHERE predicate = ? AND lifecycle = 'active'"
    )
    params: tuple[object, ...] = (definition.canonical_id,)
    if source_entity_id is not None:
        sql += " AND source_entity_id = ?"
        params += (source_entity_id,)
    if target_entity_id is not None:
        sql += " AND target_entity_id = ?"
        params += (target_entity_id,)
    sql += " ORDER BY id"
    cursor = await conn.execute(sql, params)
    rows = await cursor.fetchall()
    await cursor.close()
    return [_relation_from_row(tuple(row)) for row in rows]


async def assert_literal_fact(
    *,
    subject_entity_id: int,
    definition: PredicateDefinition,
    value: str,
    confidence: float = 0.9,
    source_memory_id: int | None = None,
    asserted_at: str | None = None,
    manage_transaction: bool = True,
) -> LiteralFactV4:
    """Persist a typed literal while applying its registry lifecycle rule.

    The function has no runtime authorization semantics. It is limited to v4
    foundation and receives a previously resolved closed-registry definition.
    ``manage_transaction=False`` is reserved for the local legacy migration,
    which owns one transaction for a record and its migration ledger entry.
    """
    await _validate_literal_subject(subject_entity_id, definition)
    normalized_value = normalize_literal(definition, value)
    if normalized_value is None:
        raise ValueError(f"{definition.canonical_id} requires a valid canonical literal")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")

    if manage_transaction:
        async with db.transaction() as conn:
            literal_fact_id = await _insert_literal_fact(
                conn,
                subject_entity_id=subject_entity_id,
                definition=definition,
                normalized_value=normalized_value,
                confidence=confidence,
                source_memory_id=source_memory_id,
                asserted_at=asserted_at,
            )
    else:
        # Reserved for the local legacy migration, which owns one transaction
        # for a record and its migration ledger entry — this call must not
        # open (or commit/roll back) a transaction of its own.
        literal_fact_id = await _insert_literal_fact(
            get_conn(),
            subject_entity_id=subject_entity_id,
            definition=definition,
            normalized_value=normalized_value,
            confidence=confidence,
            source_memory_id=source_memory_id,
            asserted_at=asserted_at,
        )
    result = await get_literal_fact(literal_fact_id)
    if result is None:
        raise RuntimeError("new literal fact was not readable after commit")
    return result


async def _insert_literal_fact(
    conn: aiosqlite.Connection,
    *,
    subject_entity_id: int,
    definition: PredicateDefinition,
    normalized_value: str,
    confidence: float,
    source_memory_id: int | None,
    asserted_at: str | None,
) -> int:
    """Issue the INSERT (and same-predicate supersede) on an active connection."""
    cursor = await conn.execute(
        "INSERT INTO literal_facts_v4 "
        "(subject_entity_id, predicate, value_text, confidence, source_memory_id, asserted_at, "
        "visibility, sensitivity, valid_from) "
        "VALUES (?, ?, ?, ?, ?, COALESCE(?, datetime('now')), ?, ?, "
        "CASE WHEN ? THEN COALESCE(?, datetime('now')) ELSE NULL END)",
        (
            subject_entity_id,
            definition.canonical_id,
            normalized_value,
            confidence,
            source_memory_id,
            asserted_at,
            definition.default_visibility,
            definition.default_sensitivity,
            definition.temporal,
            asserted_at,
        ),
    )
    if cursor.lastrowid is None:
        raise RuntimeError("INSERT into literal_facts_v4 returned no lastrowid")
    literal_fact_id = int(cursor.lastrowid)
    await cursor.close()
    if definition.cardinality in {
        PredicateCardinality.SINGLE_CURRENT,
        PredicateCardinality.TEMPORAL,
    }:
        await conn.execute(
            "UPDATE literal_facts_v4 "
            "SET lifecycle = 'superseded', superseded_at = datetime('now'), "
            "superseded_by = ?, valid_to = CASE WHEN ? THEN datetime('now') ELSE valid_to END "
            "WHERE subject_entity_id = ? AND predicate = ? AND lifecycle = 'active' AND id != ?",
            (
                literal_fact_id,
                definition.temporal,
                subject_entity_id,
                definition.canonical_id,
                literal_fact_id,
            ),
        )
    return literal_fact_id


async def assert_entity_relation(
    *,
    source_entity_id: int,
    target_entity_id: int,
    definition: PredicateDefinition,
    confidence: float = 0.9,
    source_memory_id: int | None = None,
    asserted_at: str | None = None,
    manage_transaction: bool = True,
) -> EntityRelationV4:
    """Persist a typed entity relation while applying cardinality semantics.

    ``manage_transaction=False`` is reserved for the local legacy migration,
    which owns one transaction for a record and its migration ledger entry.
    """
    await _validate_relation_endpoints(source_entity_id, target_entity_id, definition)
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")
    if definition.symmetric:
        source_entity_id, target_entity_id = sorted((source_entity_id, target_entity_id))

    if manage_transaction:
        async with db.transaction() as conn:
            outcome = await _upsert_entity_relation(
                conn,
                source_entity_id=source_entity_id,
                target_entity_id=target_entity_id,
                definition=definition,
                confidence=confidence,
                source_memory_id=source_memory_id,
                asserted_at=asserted_at,
            )
    else:
        # Reserved for the local legacy migration, which owns one transaction
        # for a record and its migration ledger entry — this call must not
        # open (or commit/roll back) a transaction of its own.
        outcome = await _upsert_entity_relation(
            get_conn(),
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            definition=definition,
            confidence=confidence,
            source_memory_id=source_memory_id,
            asserted_at=asserted_at,
        )
    if isinstance(outcome, EntityRelationV4):
        return outcome
    result = await get_entity_relation(outcome)
    if result is None:
        raise RuntimeError("new entity relation was not readable after commit")
    return result


async def _upsert_entity_relation(
    conn: aiosqlite.Connection,
    *,
    source_entity_id: int,
    target_entity_id: int,
    definition: PredicateDefinition,
    confidence: float,
    source_memory_id: int | None,
    asserted_at: str | None,
) -> EntityRelationV4 | int:
    """Return the existing active relation, or insert one and return its id."""
    existing_cursor = await conn.execute(
        f"SELECT {_RELATION_COLUMNS} FROM entity_relations_v4 "  # noqa: S608
        "WHERE source_entity_id = ? AND predicate = ? AND target_entity_id = ? AND lifecycle = 'active'",
        (source_entity_id, definition.canonical_id, target_entity_id),
    )
    existing_row = await existing_cursor.fetchone()
    await existing_cursor.close()
    if existing_row is not None:
        return _relation_from_row(tuple(existing_row))

    cursor = await conn.execute(
        "INSERT INTO entity_relations_v4 "
        "(source_entity_id, predicate, target_entity_id, confidence, source_memory_id, asserted_at, "
        "visibility, sensitivity, valid_from) "
        "VALUES (?, ?, ?, ?, ?, COALESCE(?, datetime('now')), ?, ?, "
        "CASE WHEN ? THEN COALESCE(?, datetime('now')) ELSE NULL END)",
        (
            source_entity_id,
            definition.canonical_id,
            target_entity_id,
            confidence,
            source_memory_id,
            asserted_at,
            definition.default_visibility,
            definition.default_sensitivity,
            definition.temporal,
            asserted_at,
        ),
    )
    if cursor.lastrowid is None:
        raise RuntimeError("INSERT into entity_relations_v4 returned no lastrowid")
    relation_id = int(cursor.lastrowid)
    await cursor.close()
    if definition.cardinality is PredicateCardinality.TEMPORAL:
        await conn.execute(
            "UPDATE entity_relations_v4 "
            "SET lifecycle = 'superseded', superseded_at = datetime('now'), "
            "superseded_by = ?, valid_to = datetime('now') "
            "WHERE source_entity_id = ? AND predicate = ? AND lifecycle = 'active' AND id != ?",
            (relation_id, source_entity_id, definition.canonical_id, relation_id),
        )
    return relation_id
