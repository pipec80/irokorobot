"""Conservative local migration from active legacy facts into v4 storage.

The module intentionally does not create entities, infer target names, call a
model, or modify legacy rows. Every active legacy fact receives either a
deterministic v4 counterpart or a stable local ledger outcome.
"""

from __future__ import annotations

from enum import StrEnum
import json
import unicodedata

from pydantic import BaseModel, ConfigDict

from server.db import get_conn
from server.memory.predicate_registry import (
    PredicateDefinition,
    PredicateKind,
    normalize_literal,
    resolve_predicate,
)
from server.memory.relational_v4 import assert_entity_relation, assert_literal_fact


class MigrationOutcome(StrEnum):
    """Persisted decision for one active legacy fact."""

    MIGRATED = "migrated"
    DEFERRED = "deferred"
    REJECTED = "rejected"


class MigrationCounts(BaseModel):
    """Aggregate result of one dry run or idempotent apply operation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scanned: int = 0
    migrated: int = 0
    deferred: int = 0
    rejected: int = 0
    ledger_rows_written: int = 0


class _LegacyFact(BaseModel):
    """Immutable subset of a legacy fact required for deterministic migration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int
    entity_id: int
    predicate: str
    object_value: str
    confidence: float
    source_memory_id: int | None
    asserted_at: str


class _Decision(BaseModel):
    """Classification result before any v4 write occurs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: MigrationOutcome
    reason: str
    definition: PredicateDefinition | None = None
    normalized_literal: str | None = None
    target_entity_id: int | None = None


def _fold_name(value: str) -> str:
    """Fold accents and case for conservative canonical-name/alias matching."""
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()


def _aliases(raw_aliases: object) -> tuple[str, ...]:
    """Decode legacy aliases without treating malformed JSON as a match."""
    if not isinstance(raw_aliases, str):
        return ()
    try:
        parsed = json.loads(raw_aliases)
    except json.JSONDecodeError:
        return ()
    if not isinstance(parsed, list) or not all(isinstance(alias, str) for alias in parsed):
        return ()
    return tuple(parsed)


def _is_empty_target(value: str) -> bool:
    """Recognize legacy sentinels that must never become entity targets."""
    return value.strip().casefold() in {"", "-", "n/a", "na", "ninguno", "ninguna", "none", "null"}


async def _load_active_legacy_facts() -> list[_LegacyFact]:
    """Load immutable candidates without modifying legacy rows."""
    cursor = await get_conn().execute(
        "SELECT id, entity_id, predicate, object_value, confidence, source_memory_id, asserted_at "
        "FROM facts WHERE superseded_at IS NULL ORDER BY id"
    )
    rows = await cursor.fetchall()
    await cursor.close()
    return [
        _LegacyFact(
            id=int(row[0]),
            entity_id=int(row[1]),
            predicate=str(row[2]),
            object_value=str(row[3]),
            confidence=float(row[4]),
            source_memory_id=int(row[5]) if row[5] is not None else None,
            asserted_at=str(row[6]),
        )
        for row in rows
    ]


async def _matching_target_ids(name: str, definition: PredicateDefinition) -> tuple[int, ...]:
    """Return all allowed entity IDs whose canonical name or alias exactly matches."""
    if not definition.target_types:
        return ()
    type_placeholders = ", ".join("?" for _ in definition.target_types)
    cursor = await get_conn().execute(
        f"SELECT id, name, aliases FROM entities WHERE type IN ({type_placeholders})",  # noqa: S608
        tuple(sorted(definition.target_types)),
    )
    rows = await cursor.fetchall()
    await cursor.close()
    folded_name = _fold_name(name.strip())
    matches: set[int] = set()
    for row in rows:
        entity_id = int(row[0])
        variants = (str(row[1]), *_aliases(row[2]))
        if any(_fold_name(variant) == folded_name for variant in variants):
            matches.add(entity_id)
    return tuple(sorted(matches))


async def _classify(fact: _LegacyFact) -> _Decision:
    """Classify one legacy fact without writing v4 storage or a ledger row."""
    definition = resolve_predicate(fact.predicate)
    if definition is None:
        if _fold_name(fact.predicate) in {"age", "edad"}:
            return _Decision(outcome=MigrationOutcome.REJECTED, reason="derived_predicate")
        return _Decision(outcome=MigrationOutcome.REJECTED, reason="unsupported_predicate")

    if definition.kind is PredicateKind.LITERAL:
        normalized = normalize_literal(definition, fact.object_value)
        if normalized is None:
            return _Decision(outcome=MigrationOutcome.DEFERRED, reason="invalid_literal")
        return _Decision(
            outcome=MigrationOutcome.MIGRATED,
            reason="deterministic_literal",
            definition=definition,
            normalized_literal=normalized,
        )

    target_decision = _Decision(outcome=MigrationOutcome.REJECTED, reason="empty_target_value")
    if not _is_empty_target(fact.object_value):
        matches = await _matching_target_ids(fact.object_value, definition)
        if not matches:
            target_decision = _Decision(
                outcome=MigrationOutcome.DEFERRED,
                reason="missing_target_entity",
            )
        elif len(matches) > 1:
            target_decision = _Decision(
                outcome=MigrationOutcome.DEFERRED,
                reason="ambiguous_target_entity",
            )
        else:
            target_decision = _Decision(
                outcome=MigrationOutcome.MIGRATED,
                reason="deterministic_entity_relation",
                definition=definition,
                target_entity_id=matches[0],
            )
    return target_decision


async def _existing_outcome(legacy_fact_id: int) -> MigrationOutcome | None:
    """Return an already-ledgered decision so repeated applies are idempotent."""
    cursor = await get_conn().execute(
        "SELECT outcome FROM legacy_fact_migration_v4 WHERE legacy_fact_id = ?",
        (legacy_fact_id,),
    )
    row = await cursor.fetchone()
    await cursor.close()
    return MigrationOutcome(str(row[0])) if row is not None else None


async def _write_decision(fact: _LegacyFact, decision: _Decision) -> MigrationOutcome:
    """Atomically persist one deterministic v4 result and its immutable ledger row."""
    conn = get_conn()
    literal_fact_id: int | None = None
    entity_relation_id: int | None = None
    try:
        await conn.execute("BEGIN IMMEDIATE")
        if decision.outcome is MigrationOutcome.MIGRATED:
            if decision.definition is None:
                raise RuntimeError("migrated decision requires a predicate definition")
            if decision.definition.kind is PredicateKind.LITERAL:
                if decision.normalized_literal is None:
                    raise RuntimeError("literal migration requires a normalized value")
                literal = await assert_literal_fact(
                    subject_entity_id=fact.entity_id,
                    definition=decision.definition,
                    value=decision.normalized_literal,
                    confidence=fact.confidence,
                    source_memory_id=fact.source_memory_id,
                    asserted_at=fact.asserted_at,
                    manage_transaction=False,
                )
                literal_fact_id = literal.id
            else:
                if decision.target_entity_id is None:
                    raise RuntimeError("relation migration requires one target entity")
                relation = await assert_entity_relation(
                    source_entity_id=fact.entity_id,
                    target_entity_id=decision.target_entity_id,
                    definition=decision.definition,
                    confidence=fact.confidence,
                    source_memory_id=fact.source_memory_id,
                    asserted_at=fact.asserted_at,
                    manage_transaction=False,
                )
                entity_relation_id = relation.id
        await conn.execute(
            "INSERT INTO legacy_fact_migration_v4 "
            "(legacy_fact_id, outcome, literal_fact_v4_id, entity_relation_v4_id, reason) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                fact.id,
                decision.outcome,
                literal_fact_id,
                entity_relation_id,
                decision.reason,
            ),
        )
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise
    return decision.outcome


async def _ledger_count() -> int:
    """Return the persisted ledger size without exposing household data."""
    cursor = await get_conn().execute("SELECT COUNT(*) FROM legacy_fact_migration_v4")
    row = await cursor.fetchone()
    await cursor.close()
    return int(row[0]) if row is not None else 0


def _counts_from_outcomes(
    outcomes: list[MigrationOutcome], *, ledger_rows_written: int
) -> MigrationCounts:
    """Build one immutable aggregate without retaining raw legacy values."""
    return MigrationCounts(
        scanned=len(outcomes),
        migrated=outcomes.count(MigrationOutcome.MIGRATED),
        deferred=outcomes.count(MigrationOutcome.DEFERRED),
        rejected=outcomes.count(MigrationOutcome.REJECTED),
        ledger_rows_written=ledger_rows_written,
    )


async def migrate_active_legacy_facts(*, apply: bool) -> MigrationCounts:
    """Classify or migrate active legacy facts with dry-run as the caller choice.

    Args:
        apply: When ``False``, perform no writes. When ``True``, persist exactly
            one ledger row for every active fact not already ledgered.

    Returns:
        Aggregate counts only; no raw household values leave this local process.
    """
    outcomes: list[MigrationOutcome] = []
    for fact in await _load_active_legacy_facts():
        existing = await _existing_outcome(fact.id)
        if existing is not None:
            outcomes.append(existing)
            continue
        decision = await _classify(fact)
        if apply:
            outcomes.append(await _write_decision(fact, decision))
        else:
            outcomes.append(decision.outcome)
    ledger_rows_written = await _ledger_count() if apply else 0
    return _counts_from_outcomes(outcomes, ledger_rows_written=ledger_rows_written)
