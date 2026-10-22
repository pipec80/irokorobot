"""Typed repositories for additive relational-memory v4 storage.

These repositories are intentionally isolated from legacy runtime retrieval,
outbox publication, prompt assembly, and authorization. A later policy-gated
plan owns any production reader or writer cutover.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
import re
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from server import db
from server.db import get_conn
from server.exceptions import SecurityStorageUndecidedError
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
    # Who confirmed the fact and when (ADR 0021): set by the one candidate writer, absent for
    # every fact that was never a candidate. Defaulted so older constructions keep working.
    confirmed_by_entity_id: int | None = None
    confirmed_at: str | None = None
    # Who asserted the fact and through which channel (migration 010, ADR 0022 decision 2):
    # NULL for every row written before it or by a writer that does not state them.
    asserted_by_entity_id: int | None = None
    channel: str | None = None


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
    asserted_by_entity_id: int | None = None
    channel: str | None = None
    # Who confirmed the relation and when (ADR 0022 decision 2); the columns exist since
    # migration 004 and a repeat of an active triple keeps whatever the first write stored.
    confirmed_by_entity_id: int | None = None
    confirmed_at: str | None = None


type SqlValue = int | float | str | None
type SqlRow = tuple[SqlValue, ...]

_SECURITY_SENSITIVITY = "security"
_MONTH_ONLY_LENGTH = len("YYYY-MM")


def refuse_security_value(definition: PredicateDefinition, sensitivity: str | None = None) -> None:
    """Refuse to store a ``security`` value (ADR 0022 decision 9).

    Storage at rest (plain SQLite, per-value encryption or reference only) is decided by the
    Step 0 ADR, so no writer may bypass this: it runs before any query, write or log, and the
    message names neither the value nor the subject. The predicate decides: a security
    predicate is refused whatever label the caller asks for, and a caller may not label
    another predicate ``security`` either.

    Args:
        definition: The resolved predicate whose default sensitivity applies.
        sensitivity: The caller's explicit sensitivity, if any.

    Raises:
        SecurityStorageUndecidedError: If the predicate defaults to ``security`` or the caller
            asks for it.
    """
    if _SECURITY_SENSITIVITY in {definition.default_sensitivity, sensitivity}:
        raise SecurityStorageUndecidedError(
            "a security value cannot be stored until storage at rest is decided"
        )


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
        confirmed_by_entity_id=_optional_int(row[14]),
        confirmed_at=_optional_text(row[15]),
        asserted_by_entity_id=_optional_int(row[16]),
        channel=_optional_text(row[17]),
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
        asserted_by_entity_id=_optional_int(row[14]),
        channel=_optional_text(row[15]),
        confirmed_by_entity_id=_optional_int(row[16]),
        confirmed_at=_optional_text(row[17]),
    )


_LITERAL_COLUMNS = """
    id, subject_entity_id, predicate, value_text, confidence, source_memory_id, asserted_at,
    valid_from, valid_to, lifecycle, visibility, sensitivity, superseded_at, superseded_by,
    confirmed_by_entity_id, confirmed_at, asserted_by_entity_id, channel
"""
_RELATION_COLUMNS = """
    id, source_entity_id, predicate, target_entity_id, confidence, source_memory_id, asserted_at,
    valid_from, valid_to, lifecycle, visibility, sensitivity, superseded_at, superseded_by,
    asserted_by_entity_id, channel, confirmed_by_entity_id, confirmed_at
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
    visibility: str | None = None,
    sensitivity: str | None = None,
    confirmed_by_entity_id: int | None = None,
    confirmed_at: str | None = None,
    asserted_by_entity_id: int | None = None,
    channel: str | None = None,
    manage_transaction: bool = True,
) -> LiteralFactV4:
    """Persist a typed literal while applying its registry lifecycle rule.

    The function has no runtime authorization semantics. It is limited to v4
    foundation and receives a previously resolved closed-registry definition.

    ``visibility`` and ``sensitivity`` default to the registry's values, which are the
    household reader's read contract; a caller that stores something else (the candidate
    writer stores the owner's own ``personal`` data) states it explicitly and the registry
    does not move. ``confirmed_by_entity_id`` and ``confirmed_at`` record who confirmed the
    fact and when; ``asserted_by_entity_id`` and ``channel`` record who said it and through
    which channel (the canonical writer states both; older writers leave them ``None``).

    ``manage_transaction=False`` joins a transaction the caller already owns (the legacy
    migration, which commits a record with its ledger entry, and the candidate writer, which
    commits a fact with its candidate's resolution). The call then neither opens, commits
    nor rolls back, and ``db.transaction()`` is not reentrant, so the caller must not nest.

    Args:
        subject_entity_id: The entity the literal describes.
        definition: The previously resolved closed-registry predicate definition.
        value: The raw literal; normalized by the registry rule.
        confidence: Confidence in the fact, between 0 and 1.
        source_memory_id: The episodic memory it came from, if any.
        asserted_at: Assertion timestamp; SQLite's now when ``None``.
        visibility: Overrides the registry's default visibility.
        sensitivity: Overrides the registry's default sensitivity.
        confirmed_by_entity_id: The entity that confirmed the fact, if any.
        confirmed_at: When it was confirmed, if it was.
        asserted_by_entity_id: The entity that asserted the fact, if stated.
        channel: The channel the assertion arrived through, if stated.
        manage_transaction: ``False`` joins the caller's open transaction.

    Returns:
        The stored literal fact.

    Raises:
        SecurityStorageUndecidedError: If the effective sensitivity is ``security``; nothing
            is written or logged.
        ValueError: If the value is not a valid canonical literal or the confidence is out
            of range.
        RuntimeError: If the stored row cannot be read back.
    """
    refuse_security_value(definition, sensitivity)
    await _validate_literal_subject(subject_entity_id, definition)
    normalized_value = normalize_literal(definition, value)
    if normalized_value is None:
        raise ValueError(f"{definition.canonical_id} requires a valid canonical literal")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")

    stamp = _LiteralStamp(
        visibility=visibility or definition.default_visibility,
        sensitivity=sensitivity or definition.default_sensitivity,
        confirmed_by_entity_id=confirmed_by_entity_id,
        confirmed_at=confirmed_at,
        asserted_by_entity_id=asserted_by_entity_id,
        channel=channel,
    )
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
                stamp=stamp,
            )
    else:
        # The caller owns one transaction (a legacy-migration record with its ledger entry, or
        # a candidate promotion): this call must not open, commit or roll back one of its own.
        literal_fact_id = await _insert_literal_fact(
            get_conn(),
            subject_entity_id=subject_entity_id,
            definition=definition,
            normalized_value=normalized_value,
            confidence=confidence,
            source_memory_id=source_memory_id,
            asserted_at=asserted_at,
            stamp=stamp,
        )
    result = await get_literal_fact(literal_fact_id)
    if result is None:
        raise RuntimeError("new literal fact was not readable after commit")
    return result


@dataclass(frozen=True)
class _LiteralStamp:
    """The classification, confirmation and provenance one literal is stored with."""

    visibility: str
    sensitivity: str
    confirmed_by_entity_id: int | None
    confirmed_at: str | None
    asserted_by_entity_id: int | None
    channel: str | None


async def _insert_literal_fact(
    conn: aiosqlite.Connection,
    *,
    subject_entity_id: int,
    definition: PredicateDefinition,
    normalized_value: str,
    confidence: float,
    source_memory_id: int | None,
    asserted_at: str | None,
    stamp: _LiteralStamp,
) -> int:
    """Issue the INSERT (and same-predicate supersede) on an active connection."""
    cursor = await conn.execute(
        "INSERT INTO literal_facts_v4 "
        "(subject_entity_id, predicate, value_text, confidence, source_memory_id, asserted_at, "
        "visibility, sensitivity, valid_from, confirmed_by_entity_id, confirmed_at, "
        "asserted_by_entity_id, channel) "
        "VALUES (?, ?, ?, ?, ?, COALESCE(?, datetime('now')), ?, ?, "
        "CASE WHEN ? THEN COALESCE(?, datetime('now')) ELSE NULL END, ?, ?, ?, ?)",
        (
            subject_entity_id,
            definition.canonical_id,
            normalized_value,
            confidence,
            source_memory_id,
            asserted_at,
            stamp.visibility,
            stamp.sensitivity,
            definition.temporal,
            asserted_at,
            stamp.confirmed_by_entity_id,
            stamp.confirmed_at,
            stamp.asserted_by_entity_id,
            stamp.channel,
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
    visibility: str | None = None,
    sensitivity: str | None = None,
    confirmed_by_entity_id: int | None = None,
    confirmed_at: str | None = None,
    valid_from: str | None = None,
    valid_to: str | None = None,
    asserted_by_entity_id: int | None = None,
    channel: str | None = None,
    manage_transaction: bool = True,
) -> EntityRelationV4:
    """Persist a typed entity relation while applying cardinality semantics.

    Mirrors ``assert_literal_fact``: ``visibility`` and ``sensitivity`` default to the
    registry's values (the household reader's read contract), ``confirmed_by_entity_id`` and
    ``confirmed_at`` record who confirmed the relation and when, and ``asserted_by_entity_id``
    and ``channel`` who said it and through which channel.

    Validity (ADR 0022 decision 6): ``valid_from`` and ``valid_to`` are ``YYYY-MM-DD`` or
    ``YYYY-MM``. A ``temporal`` predicate that arrives without ``valid_from`` begins at its
    assertion date, and the previous active relation of the same source and predicate is
    closed **at the new row's ``valid_from``**, never at the moment of the write. A row given
    an explicit ``valid_to`` is history: it is stored with lifecycle ``expired``, never closes
    the current row, may have no ``valid_from`` and cannot clash with the active-triple index.

    An exact repeat of an active triple returns the row already there **without** updating its
    classification or confirmer (a ``child_of`` made by the local setup keeps no confirmer).

    ``manage_transaction=False`` joins a transaction the caller already owns (the legacy
    migration, which commits a record with its ledger entry, and the canonical writer, which
    can commit a batch). The call then neither opens, commits nor rolls back, and
    ``db.transaction()`` is not reentrant, so the caller must not nest.

    Args:
        source_entity_id: The entity the relation starts from.
        target_entity_id: The entity it points to.
        definition: The previously resolved closed-registry predicate definition.
        confidence: Confidence in the relation, between 0 and 1.
        source_memory_id: The episodic memory it came from, if any.
        asserted_at: Assertion timestamp; SQLite's now when ``None``.
        visibility: Overrides the registry's default visibility.
        sensitivity: Overrides the registry's default sensitivity.
        confirmed_by_entity_id: The entity that confirmed the relation, if any.
        confirmed_at: When it was confirmed, if it was.
        valid_from: When the relation began, as ``YYYY-MM-DD`` or ``YYYY-MM``.
        valid_to: When it ended; makes the row history.
        asserted_by_entity_id: The entity that asserted the relation, if stated.
        channel: The channel the assertion arrived through, if stated.
        manage_transaction: ``False`` joins the caller's open transaction.

    Returns:
        The stored relation, or the active one already stored for the same triple.

    Raises:
        SecurityStorageUndecidedError: If the effective sensitivity is ``security``.
        ValueError: If an endpoint or the confidence is invalid, or a validity date is not a
            real ``YYYY-MM-DD`` / ``YYYY-MM`` date or ``valid_to`` precedes ``valid_from``.
        RuntimeError: If the stored row cannot be read back.
    """
    refuse_security_value(definition, sensitivity)
    await _validate_relation_endpoints(source_entity_id, target_entity_id, definition)
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")
    _validate_validity(valid_from, valid_to)
    if definition.symmetric:
        source_entity_id, target_entity_id = sorted((source_entity_id, target_entity_id))

    stamp = _RelationStamp(
        visibility=visibility or definition.default_visibility,
        sensitivity=sensitivity or definition.default_sensitivity,
        confirmed_by_entity_id=confirmed_by_entity_id,
        confirmed_at=confirmed_at,
        valid_from=valid_from,
        valid_to=valid_to,
        asserted_by_entity_id=asserted_by_entity_id,
        channel=channel,
    )
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
                stamp=stamp,
            )
    else:
        # The caller owns one transaction (the legacy migration with its ledger entry, or a
        # canonical-writer batch): this call must not open, commit or roll back one of its own.
        outcome = await _upsert_entity_relation(
            get_conn(),
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            definition=definition,
            confidence=confidence,
            source_memory_id=source_memory_id,
            asserted_at=asserted_at,
            stamp=stamp,
        )
    if isinstance(outcome, EntityRelationV4):
        return outcome
    result = await get_entity_relation(outcome)
    if result is None:
        raise RuntimeError("new entity relation was not readable after commit")
    return result


@dataclass(frozen=True)
class _RelationStamp:
    """The classification, confirmation, provenance and validity one relation is stored with."""

    visibility: str
    sensitivity: str
    confirmed_by_entity_id: int | None
    confirmed_at: str | None
    valid_from: str | None
    valid_to: str | None
    asserted_by_entity_id: int | None
    channel: str | None


_VALIDITY_DATE = re.compile(r"[0-9]{4}-[0-9]{2}(-[0-9]{2})?")


def _validity_bound(name: str, value: str, *, end: bool) -> date:
    """Parse a ``YYYY-MM-DD`` or ``YYYY-MM`` date; a month alone is its first or last day."""
    if _VALIDITY_DATE.fullmatch(value) is None:
        raise ValueError(f"{name} must be YYYY-MM-DD or YYYY-MM")
    try:
        if len(value) == _MONTH_ONLY_LENGTH:
            first = date.fromisoformat(f"{value}-01")
            if not end:
                return first
            return first.replace(day=monthrange(first.year, first.month)[1])
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} is not a real calendar date") from exc


def _validate_validity(valid_from: str | None, valid_to: str | None) -> None:
    """Reject a validity date that is not a real ISO date, or a range that runs backwards."""
    start = _validity_bound("valid_from", valid_from, end=False) if valid_from is not None else None
    stop = _validity_bound("valid_to", valid_to, end=True) if valid_to is not None else None
    if start is not None and stop is not None and stop < start:
        raise ValueError("valid_to must not be before valid_from")


async def _upsert_entity_relation(
    conn: aiosqlite.Connection,
    *,
    source_entity_id: int,
    target_entity_id: int,
    definition: PredicateDefinition,
    confidence: float,
    source_memory_id: int | None,
    asserted_at: str | None,
    stamp: _RelationStamp,
) -> EntityRelationV4 | int:
    """Return the matching stored relation, or insert one and return its id.

    An active row (no ``valid_to``) is looked up among the active triples; a history row is
    looked up among the expired ones with the same range, so a repeat is idempotent either way.
    """
    if stamp.valid_to is None:
        lookup = "lifecycle = 'active'"
        params: tuple[object, ...] = (source_entity_id, definition.canonical_id, target_entity_id)
    else:
        lookup = "lifecycle = 'expired' AND valid_from IS ? AND valid_to = ?"
        params = (
            source_entity_id,
            definition.canonical_id,
            target_entity_id,
            stamp.valid_from,
            stamp.valid_to,
        )
    existing_cursor = await conn.execute(
        f"SELECT {_RELATION_COLUMNS} FROM entity_relations_v4 "  # noqa: S608
        f"WHERE source_entity_id = ? AND predicate = ? AND target_entity_id = ? AND {lookup}",
        params,
    )
    existing_row = await existing_cursor.fetchone()
    await existing_cursor.close()
    if existing_row is not None:
        return _relation_from_row(tuple(existing_row))

    cursor = await conn.execute(
        "INSERT INTO entity_relations_v4 "
        "(source_entity_id, predicate, target_entity_id, confidence, source_memory_id, "
        "asserted_at, visibility, sensitivity, valid_from, valid_to, lifecycle, "
        "confirmed_by_entity_id, confirmed_at, asserted_by_entity_id, channel) "
        "VALUES (?, ?, ?, ?, ?, COALESCE(?, datetime('now')), ?, ?, "
        "COALESCE(?, CASE WHEN ? AND ? IS NULL THEN COALESCE(?, datetime('now')) END), "
        "?, ?, ?, ?, ?, ?)",
        (
            source_entity_id,
            definition.canonical_id,
            target_entity_id,
            confidence,
            source_memory_id,
            asserted_at,
            stamp.visibility,
            stamp.sensitivity,
            stamp.valid_from,
            definition.temporal,
            stamp.valid_to,
            asserted_at,
            stamp.valid_to,
            AssertionLifecycle.ACTIVE if stamp.valid_to is None else AssertionLifecycle.EXPIRED,
            stamp.confirmed_by_entity_id,
            stamp.confirmed_at,
            stamp.asserted_by_entity_id,
            stamp.channel,
        ),
    )
    if cursor.lastrowid is None:
        raise RuntimeError("INSERT into entity_relations_v4 returned no lastrowid")
    relation_id = int(cursor.lastrowid)
    await cursor.close()
    if stamp.valid_to is None and definition.cardinality is PredicateCardinality.TEMPORAL:
        await _close_previous(
            conn,
            new_id=relation_id,
            source_entity_id=source_entity_id,
            predicate=definition.canonical_id,
        )
    return relation_id


_STORED_DAY = re.compile(r"([0-9]{4})-([0-9]{2})(?:-([0-9]{2}))?")


def _stored_day(value: str) -> date | None:
    """The calendar day of a stored validity value: a date, a month or a timestamp."""
    match = _STORED_DAY.match(value)
    if match is None:
        return None
    year, month, day = match.groups()
    try:
        return date(int(year), int(month), int(day) if day else 1)
    except ValueError:
        return None


def _closing_value(previous_from: str | None, new_from: str | None) -> str | None:
    """Where the previous relation ends: at the new ``valid_from``, never before its own start.

    A move dated before the relation it replaces cannot end that relation earlier than it began,
    so the older row is closed at its own start (a zero-length range) rather than inverted.
    """
    if previous_from is None or new_from is None:
        return new_from
    previous_day, new_day = _stored_day(previous_from), _stored_day(new_from)
    if previous_day is not None and new_day is not None and new_day < previous_day:
        return previous_from
    return new_from


async def _close_previous(
    conn: aiosqlite.Connection, *, new_id: int, source_entity_id: int, predicate: str
) -> None:
    """Supersede the active rows of one source and predicate, each at the new row's start."""
    cursor = await conn.execute(
        "SELECT id, valid_from FROM entity_relations_v4 "
        "WHERE source_entity_id = ? AND predicate = ? AND lifecycle = 'active' AND id != ?",
        (source_entity_id, predicate, new_id),
    )
    previous = [(int(row[0]), _optional_text(row[1])) for row in await cursor.fetchall()]
    await cursor.close()
    cursor = await conn.execute(
        "SELECT valid_from FROM entity_relations_v4 WHERE id = ?", (new_id,)
    )
    new_row = await cursor.fetchone()
    await cursor.close()
    new_from = _optional_text(new_row[0]) if new_row is not None else None
    for previous_id, previous_from in previous:
        await conn.execute(
            "UPDATE entity_relations_v4 "
            "SET lifecycle = 'superseded', superseded_at = datetime('now'), "
            "superseded_by = ?, valid_to = ? WHERE id = ?",
            (new_id, _closing_value(previous_from, new_from), previous_id),
        )
