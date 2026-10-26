"""The candidate store: claims the owner made about their own taste, until they lapse or resolve.

A candidate is **not** canonical memory (ADR 0021 decision 6). This module is the only place
that issues SQL against ``memory_candidates`` (an architecture guard pins it) and it
guarantees, in code and in the schema:

* **The value is scrubbed on resolution.** ``value_text`` and ``value_key`` exist only while a
  candidate is ``proposed`` or ``offered``; a resolution that forgot to erase them is refused
  by the table's ``CHECK``. A scrub is followed by a write-ahead-log checkpoint, so the old
  bytes are not left in the log.
* **Transitions are compare-and-set** (``UPDATE ... WHERE status = ?`` and a row count) and
  always filtered by the subject, so another person can neither resolve nor lapse a candidate.
* **One clock.** Every timestamp is supplied by the caller as an aware datetime and stored as
  UTC ISO 8601; the store never uses SQLite's ``datetime('now')``.
* **Bounded and idempotent.** A repeated statement is a no-op insert; at the per-person cap a
  new candidate is refused and an old one is never evicted.
* **Housekeeping on every write entry.** Lapsed candidates are expired and unanswered offers
  return to ``proposed`` inside the entry's own transaction (insert, offer, resolve and the
  writer's promote), whatever the retention job did. Reads (``get_candidate``,
  ``get_candidate_in_transaction``, ``resolve_candidate_in_transaction``, ``void_live_candidates``,
  ``next_offerable``, ``still_offerable`` and ``find_offered``) run none of it. That is why an
  offer whose answer window has closed still counts as offerable to ``next_offerable`` and
  ``still_offerable``: ``mark_offered``, the write entry that follows, returns it to ``proposed``
  before its own compare-and-set.

Logs carry ids, the predicate, a status and a closed reason, never a value.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
import logging
from typing import TYPE_CHECKING

from server import db
from server.memory.candidate_types import CandidateChannel, CandidateStatus, ProposedCandidate
from server.settings import settings

if TYPE_CHECKING:
    from uuid import UUID

    import aiosqlite

logger = logging.getLogger(__name__)

__all__ = [
    "VOID_LIVE_SQL",
    "Candidate",
    "InsertResult",
    "InsertStatus",
    "checkpoint_after_scrub",
    "count_live_candidates",
    "expire_lapsed_in_transaction",
    "find_offered",
    "get_candidate",
    "insert_candidate",
    "iso_utc",
    "mark_offered",
    "next_offerable",
    "precheck_insert",
    "reset_for_startup",
    "resolve_candidate",
    "resolve_candidate_in_transaction",
    "run_housekeeping",
    "still_offerable",
    "void_live_candidates",
]

_LIVE = ("proposed", "offered")
_COLUMNS = (
    "id, subject_person_id, asserted_by_person_id, predicate, value_text, value_key, status, "
    "channel, source_correlation_id, offer_correlation_id, resolution_correlation_id, "
    "proposed_at, offered_at, resolved_at, expires_at, offer_count, promoted_fact_id"
)

#: Void every live candidate. Used by start-up with the kill-switch off, and by
#: ``scripts/scrub_candidates.py`` (stdlib ``sqlite3``) before ``just reset-db`` copies the
#: database to ``data/backups``. One parameter: the resolution timestamp.
VOID_LIVE_SQL = (
    "UPDATE memory_candidates SET status = 'expired', value_text = NULL, value_key = NULL, "
    "resolved_at = ? WHERE status IN ('proposed', 'offered')"
)


class InsertStatus(StrEnum):
    """Closed outcome of one insert attempt."""

    INSERTED = "inserted"
    DUPLICATE = "duplicate"
    CAPACITY = "capacity"
    DISABLED = "disabled"


@dataclass(frozen=True)
class InsertResult:
    """What ``insert_candidate`` did.

    Attributes:
        status: The closed outcome.
        candidate_id: The new row's id when ``status`` is ``INSERTED``.
    """

    status: InsertStatus
    candidate_id: int | None = None


@dataclass(frozen=True)
class Candidate:
    """One stored candidate. ``value_text`` and ``value_key`` are ``None`` once resolved."""

    id: int
    subject_person_id: int
    asserted_by_person_id: int
    predicate: str
    value_text: str | None
    value_key: str | None
    status: CandidateStatus
    channel: CandidateChannel
    source_correlation_id: str
    offer_correlation_id: str | None
    resolution_correlation_id: str | None
    proposed_at: str
    offered_at: str | None
    resolved_at: str | None
    expires_at: str
    offer_count: int
    promoted_fact_id: int | None


def iso_utc(moment: datetime) -> str:
    """Return *moment* as fixed-width UTC ISO 8601, the only timestamp format stored here.

    Args:
        moment: An aware datetime.

    Returns:
        ``YYYY-MM-DDTHH:MM:SS.ffffff+00:00``; fixed width, so strings sort like instants.

    Raises:
        ValueError: If *moment* is naive.
    """
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("candidate timestamps must be timezone-aware")
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


def _from_row(row: tuple[object, ...]) -> Candidate:
    """Build the immutable model from one ``_COLUMNS`` row."""
    return Candidate(
        id=int(str(row[0])),
        subject_person_id=int(str(row[1])),
        asserted_by_person_id=int(str(row[2])),
        predicate=str(row[3]),
        value_text=None if row[4] is None else str(row[4]),
        value_key=None if row[5] is None else str(row[5]),
        status=CandidateStatus(str(row[6])),
        channel=CandidateChannel(str(row[7])),
        source_correlation_id=str(row[8]),
        offer_correlation_id=None if row[9] is None else str(row[9]),
        resolution_correlation_id=None if row[10] is None else str(row[10]),
        proposed_at=str(row[11]),
        offered_at=None if row[12] is None else str(row[12]),
        resolved_at=None if row[13] is None else str(row[13]),
        expires_at=str(row[14]),
        offer_count=int(str(row[15])),
        promoted_fact_id=None if row[16] is None else int(str(row[16])),
    )


async def _rowcount(cursor: aiosqlite.Cursor) -> int:
    """Read and close a cursor, returning how many rows its statement changed."""
    changed = cursor.rowcount
    await cursor.close()
    return changed


async def expire_lapsed_in_transaction(conn: aiosqlite.Connection, now: datetime) -> int:
    """Expire (and scrub) every live candidate past its deadline or out of offers.

    Args:
        conn: The connection of an open ``db.transaction()``.
        now: The caller's clock reading.

    Returns:
        How many candidates were expired. The caller checkpoints the log when this is not 0.
    """
    stamp = iso_utc(now)
    cursor = await conn.execute(
        "UPDATE memory_candidates SET status = 'expired', value_text = NULL, value_key = NULL, "
        "resolved_at = ? WHERE status IN ('proposed', 'offered') AND expires_at <= ?",
        (stamp, stamp),
    )
    lapsed = await _rowcount(cursor)
    cursor = await conn.execute(
        "UPDATE memory_candidates SET status = 'expired', value_text = NULL, value_key = NULL, "
        "resolved_at = ? WHERE status = 'proposed' AND offer_count >= ?",
        (stamp, settings.memory_candidate_max_offers),
    )
    return lapsed + await _rowcount(cursor)


async def run_housekeeping(conn: aiosqlite.Connection, now: datetime) -> int:
    """Expire what lapsed and return unanswered offers to ``proposed``.

    Args:
        conn: The connection of an open ``db.transaction()``.
        now: The caller's clock reading.

    Returns:
        How many candidates were scrubbed (expired); the caller checkpoints when not 0.
    """
    waited_since = iso_utc(now - timedelta(seconds=settings.memory_candidate_answer_seconds))
    cursor = await conn.execute(
        "UPDATE memory_candidates SET status = 'proposed', offered_at = NULL, "
        "offer_correlation_id = NULL WHERE status = 'offered' AND offered_at <= ?",
        (waited_since,),
    )
    await cursor.close()
    return await expire_lapsed_in_transaction(conn, now)


# A checkpoint that SQLite postponed (a reader pinned the log) is owed to the next entry: the
# value was erased in the page but its old frames are still in the log until it is truncated.
_checkpoint_pending = False


async def checkpoint_after_scrub(scrubbed: int) -> None:
    """Truncate the write-ahead log after a transaction that erased a value, or retry one owed.

    Never raises for a busy log: the operation that erased the value has already committed. The
    debt is recorded before the checkpoint is attempted, so a checkpoint that raises (a
    cancellation at shutdown, a closed connection) still leaves it owed to the next entry.

    Args:
        scrubbed: How many values the transaction that just committed erased. ``0`` only
            retries a checkpoint a previous call could not complete.
    """
    global _checkpoint_pending  # noqa: PLW0603 — one owed checkpoint per process (single worker, ADR 0010)
    if not scrubbed and not _checkpoint_pending:
        return
    _checkpoint_pending = True
    _checkpoint_pending = not await db.checkpoint_wal()


async def insert_candidate(
    proposal: ProposedCandidate,
    *,
    subject_person_id: int,
    asserted_by_person_id: int,
    channel: CandidateChannel,
    correlation_id: UUID,
    now: datetime,
) -> InsertResult:
    """Store one accepted candidate, unless it repeats a live one or the person is at the cap.

    Args:
        proposal: The classifier's output.
        subject_person_id: Whose memory it would become.
        asserted_by_person_id: Who said it (the subject in CM-3a).
        channel: The voice route it came from.
        correlation_id: The turn's correlation id, so audit rows join to the candidate.
        now: The caller's clock reading.

    Returns:
        ``INSERTED`` with the id; ``DUPLICATE`` for a live candidate of that person with the
        same predicate and key; ``CAPACITY`` at the per-person cap (nothing is evicted);
        ``DISABLED`` with the kill-switch off.
    """
    if not settings.memory_candidates_enabled:
        return InsertResult(InsertStatus.DISABLED)
    async with db.transaction() as conn:
        scrubbed = await run_housekeeping(conn, now)
        result = await _insert_in_transaction(
            conn, proposal, subject_person_id, asserted_by_person_id, channel, correlation_id, now
        )
    # Logged before the checkpoint: a checkpoint problem must not hide that a value was stored.
    logger.info(
        "Candidate insert: %s",
        result.status.value,
        extra={
            "event": "candidate.insert",
            "outcome": result.status,
            "candidate_id": result.candidate_id,
            "predicate": proposal.predicate,
            "channel": channel,
            "correlation_id": str(correlation_id),
        },
    )
    await checkpoint_after_scrub(scrubbed)
    return result


async def _blocking_status(
    conn: aiosqlite.Connection, subject_person_id: int, predicate: str, value_key: str
) -> InsertStatus | None:
    """Return ``DUPLICATE`` or ``CAPACITY`` when the insert rules refuse, else ``None``."""
    cursor = await conn.execute(
        "SELECT 1 FROM memory_candidates WHERE subject_person_id = ? AND predicate = ? "
        "AND value_key = ? AND status IN ('proposed', 'offered')",
        (subject_person_id, predicate, value_key),
    )
    duplicate = await cursor.fetchone()
    await cursor.close()
    if duplicate is not None:
        return InsertStatus.DUPLICATE
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM memory_candidates WHERE subject_person_id = ? "
        "AND status IN ('proposed', 'offered')",
        (subject_person_id,),
    )
    live_row = await cursor.fetchone()
    await cursor.close()
    if live_row is not None and int(live_row[0]) >= settings.memory_candidate_max_live:
        return InsertStatus.CAPACITY
    return None


async def precheck_insert(
    proposal: ProposedCandidate, *, subject_person_id: int
) -> InsertStatus | None:
    """Say, without writing, why ``insert_candidate`` would refuse this proposal right now.

    The caller asks before it writes an audit row, so the audit log does not say "allowed" for a
    proposal the store was always going to refuse. It is advisory: ``insert_candidate`` decides
    again inside its own transaction.

    Args:
        proposal: The classifier's output.
        subject_person_id: Whose memory it would become.

    Returns:
        ``DISABLED`` with the kill-switch off, ``DUPLICATE`` for a live candidate with the same
        predicate and key, ``CAPACITY`` at the per-person cap, or ``None`` when it would insert.
    """
    if not settings.memory_candidates_enabled:
        return InsertStatus.DISABLED
    return await _blocking_status(
        db.get_conn(), subject_person_id, proposal.predicate, proposal.value_key
    )


async def _insert_in_transaction(
    conn: aiosqlite.Connection,
    proposal: ProposedCandidate,
    subject_person_id: int,
    asserted_by_person_id: int,
    channel: CandidateChannel,
    correlation_id: UUID,
    now: datetime,
) -> InsertResult:
    """Apply the duplicate and cap rules, then insert, inside an open transaction."""
    blocked = await _blocking_status(
        conn, subject_person_id, proposal.predicate, proposal.value_key
    )
    if blocked is not None:
        return InsertResult(blocked)
    cursor = await conn.execute(
        "INSERT INTO memory_candidates (subject_person_id, asserted_by_person_id, predicate, "
        "value_text, value_key, status, channel, source_correlation_id, proposed_at, expires_at) "
        "VALUES (?, ?, ?, ?, ?, 'proposed', ?, ?, ?, ?)",
        (
            subject_person_id,
            asserted_by_person_id,
            proposal.predicate,
            proposal.value_text,
            proposal.value_key,
            channel.value,
            str(correlation_id),
            iso_utc(now),
            iso_utc(now + timedelta(seconds=settings.memory_candidate_ttl_seconds)),
        ),
    )
    candidate_id = cursor.lastrowid
    await cursor.close()
    if candidate_id is None:
        raise RuntimeError("INSERT into memory_candidates returned no lastrowid")
    return InsertResult(InsertStatus.INSERTED, int(candidate_id))


async def get_candidate(candidate_id: int) -> Candidate | None:
    """Return one candidate by id, with no policy applied (callers filter by subject).

    Args:
        candidate_id: The row id.

    Returns:
        The candidate, or ``None`` when it does not exist.
    """
    cursor = await db.get_conn().execute(
        f"SELECT {_COLUMNS} FROM memory_candidates WHERE id = ?",  # noqa: S608
        (candidate_id,),
    )
    row = await cursor.fetchone()
    await cursor.close()
    return _from_row(tuple(row)) if row is not None else None


async def get_candidate_in_transaction(
    conn: aiosqlite.Connection, candidate_id: int
) -> Candidate | None:
    """Return one candidate as seen by an open transaction.

    Args:
        conn: The connection of an open ``db.transaction()``.
        candidate_id: The row id.

    Returns:
        The candidate, or ``None`` when it does not exist.
    """
    cursor = await conn.execute(
        f"SELECT {_COLUMNS} FROM memory_candidates WHERE id = ?",  # noqa: S608
        (candidate_id,),
    )
    row = await cursor.fetchone()
    await cursor.close()
    return _from_row(tuple(row)) if row is not None else None


_OFFERABLE_SQL = (
    "subject_person_id = ? "
    "AND (status = 'proposed' OR (status = 'offered' AND offered_at <= ?)) "
    "AND expires_at > ? AND offer_count < ? "
    # One open offer per person: while an answer to one may still come, nothing else is
    # offered, so an answer always names the offer it resolves.
    "AND NOT EXISTS (SELECT 1 FROM memory_candidates AS open WHERE "
    "open.subject_person_id = memory_candidates.subject_person_id "
    "AND open.status = 'offered' AND open.offered_at > ?)"
)


def _offerable_args(subject_person_id: int, now: datetime) -> tuple[object, ...]:
    """The parameters of ``_OFFERABLE_SQL`` for one person at *now*."""
    waited_since = iso_utc(now - timedelta(seconds=settings.memory_candidate_answer_seconds))
    return (
        subject_person_id,
        waited_since,
        iso_utc(now),
        settings.memory_candidate_max_offers,
        waited_since,
    )


async def next_offerable(subject_person_id: int, *, now: datetime) -> Candidate | None:
    """Return the subject's oldest candidate that may be offered now, without writing.

    Read-only, like every reader of this store: housekeeping runs on the write entry that
    follows (``mark_offered``), so an offer whose answer window has closed counts as offerable
    here and is returned to ``proposed`` there before the compare-and-set. While one offer of
    that person still waits for its answer, nothing is offerable.

    Args:
        subject_person_id: Whose candidate; another person's is never returned.
        now: The caller's clock reading.

    Returns:
        The oldest live candidate of that person that has not lapsed and has offers left, or
        ``None`` (also with the kill-switch off).
    """
    if not settings.memory_candidates_enabled:
        return None
    cursor = await db.get_conn().execute(
        f"SELECT {_COLUMNS} FROM memory_candidates WHERE {_OFFERABLE_SQL} "  # noqa: S608
        "ORDER BY proposed_at, id LIMIT 1",
        _offerable_args(subject_person_id, now),
    )
    row = await cursor.fetchone()
    await cursor.close()
    return _from_row(tuple(row)) if row is not None else None


async def still_offerable(candidate_id: int, subject_person_id: int, *, now: datetime) -> bool:
    """Say, without writing, whether one candidate may still be offered now.

    Asked right before the policy's read step is audited, so the audit log does not say
    "allowed" for an offer the compare-and-set was always going to lose (another turn offered
    it, it lapsed during generation). It is advisory: ``mark_offered`` decides again.

    Args:
        candidate_id: The candidate the offer was prepared for.
        subject_person_id: Whose it is.
        now: The caller's clock reading.

    Returns:
        ``True`` when it is still offerable for that person; ``False`` otherwise or with the
        kill-switch off.
    """
    if not settings.memory_candidates_enabled:
        return False
    cursor = await db.get_conn().execute(
        f"SELECT 1 FROM memory_candidates WHERE id = ? AND {_OFFERABLE_SQL}",  # noqa: S608
        (candidate_id, *_offerable_args(subject_person_id, now)),
    )
    row = await cursor.fetchone()
    await cursor.close()
    return row is not None


async def find_offered(
    subject_person_id: int, value_key: str | None, *, now: datetime
) -> Candidate | None:
    """Return the subject's open offer, the one an answer may resolve.

    With a *value_key* it is the offer with that key. With ``None`` it is the person's one open
    offer, whatever its value: it is returned only when exactly one is open, so zero or several
    cannot be told apart from each other by the caller.

    Args:
        subject_person_id: Whose offer; another person's is never returned.
        value_key: The comparison key of the value the answer repeated, or ``None`` when the
            answer named no value and means the person's one open offer.
        now: The caller's clock reading.

    Returns:
        The ``offered`` candidate of that person (with that key, when one was given), still
        inside its answer window and not lapsed, or ``None`` (also with the kill-switch off, and
        with no key when none or more than one offer is open).
    """
    if not settings.memory_candidates_enabled:
        return None
    stamp = iso_utc(now)
    waited_since = iso_utc(now - timedelta(seconds=settings.memory_candidate_answer_seconds))
    if value_key is None:
        cursor = await db.get_conn().execute(
            f"SELECT {_COLUMNS} FROM memory_candidates WHERE subject_person_id = ? "  # noqa: S608
            "AND status = 'offered' AND offered_at > ? AND expires_at > ? "
            "ORDER BY offered_at DESC, id LIMIT 2",
            (subject_person_id, waited_since, stamp),
        )
        rows = list(await cursor.fetchall())
        await cursor.close()
        return _from_row(tuple(rows[0])) if len(rows) == 1 else None
    cursor = await db.get_conn().execute(
        f"SELECT {_COLUMNS} FROM memory_candidates WHERE subject_person_id = ? "  # noqa: S608
        "AND status = 'offered' AND value_key = ? AND offered_at > ? AND expires_at > ? "
        "ORDER BY offered_at DESC, id LIMIT 1",
        (subject_person_id, value_key, waited_since, stamp),
    )
    row = await cursor.fetchone()
    await cursor.close()
    return _from_row(tuple(row)) if row is not None else None


async def mark_offered(
    candidate_id: int, subject_person_id: int, *, correlation_id: UUID, now: datetime
) -> bool:
    """Move one ``proposed`` candidate to ``offered`` (compare-and-set).

    It also receives a candidate that is still ``offered`` but whose answer window has closed:
    housekeeping, run first, returns it to ``proposed``, so the transition then succeeds.

    It repeats the "one open offer per person" rule of ``next_offerable`` inside the
    compare-and-set: while another ``offered`` row of the same person is inside its answer
    window and not lapsed, the transition is refused and nothing changes.

    Args:
        candidate_id: The candidate.
        subject_person_id: Whose it is; another person's id changes nothing.
        correlation_id: The turn that spoke the offer.
        now: The caller's clock reading.

    Returns:
        ``True`` when this call made the transition. ``False`` when the candidate is not
        ``proposed``, lapsed, belongs to someone else, has used every offer, the person already
        has another open offer, or the kill-switch is off.
    """
    if not settings.memory_candidates_enabled:
        return False
    stamp = iso_utc(now)
    waited_since = iso_utc(now - timedelta(seconds=settings.memory_candidate_answer_seconds))
    async with db.transaction() as conn:
        scrubbed = await run_housekeeping(conn, now)
        cursor = await conn.execute(
            "UPDATE memory_candidates SET status = 'offered', offered_at = ?, "
            "offer_correlation_id = ?, offer_count = offer_count + 1 "
            "WHERE id = ? AND subject_person_id = ? AND status = 'proposed' AND offer_count < ? "
            "AND NOT EXISTS (SELECT 1 FROM memory_candidates AS open WHERE "
            "open.subject_person_id = memory_candidates.subject_person_id "
            "AND open.status = 'offered' AND open.offered_at > ?)",
            (
                stamp,
                str(correlation_id),
                candidate_id,
                subject_person_id,
                settings.memory_candidate_max_offers,
                waited_since,
            ),
        )
        changed = await _rowcount(cursor)
    await checkpoint_after_scrub(scrubbed)
    return changed == 1


async def resolve_candidate_in_transaction(
    conn: aiosqlite.Connection,
    candidate_id: int,
    subject_person_id: int,
    *,
    to: CandidateStatus,
    correlation_id: UUID,
    now: datetime,
    promoted_fact_id: int | None = None,
) -> bool:
    """Resolve one ``offered`` candidate and erase its value, inside an open transaction.

    Args:
        conn: The connection of an open ``db.transaction()``.
        candidate_id: The candidate.
        subject_person_id: Whose it is; another person's id changes nothing.
        to: ``CONFIRMED`` or ``REJECTED``.
        correlation_id: The turn that resolved it.
        now: The caller's clock reading.
        promoted_fact_id: The canonical fact it became, for ``CONFIRMED``.

    Returns:
        ``True`` when this call resolved it; ``False`` when it was not ``offered`` for that
        subject (the compare-and-set lost, or someone else's candidate).

    Raises:
        ValueError: If *to* is not a resolution.
    """
    if to not in {CandidateStatus.CONFIRMED, CandidateStatus.REJECTED}:
        raise ValueError("a candidate resolves to confirmed or rejected only")
    cursor = await conn.execute(
        "UPDATE memory_candidates SET status = ?, value_text = NULL, value_key = NULL, "
        "resolved_at = ?, resolution_correlation_id = ?, promoted_fact_id = ? "
        "WHERE id = ? AND subject_person_id = ? AND status = 'offered'",
        (
            to.value,
            iso_utc(now),
            str(correlation_id),
            promoted_fact_id,
            candidate_id,
            subject_person_id,
        ),
    )
    return await _rowcount(cursor) == 1


async def resolve_candidate(
    candidate_id: int,
    subject_person_id: int,
    *,
    to: CandidateStatus,
    correlation_id: UUID,
    now: datetime,
) -> bool:
    """Resolve one ``offered`` candidate in its own transaction and checkpoint the log.

    Args:
        candidate_id: The candidate.
        subject_person_id: Whose it is.
        to: ``CONFIRMED`` or ``REJECTED``.
        correlation_id: The turn that resolved it.
        now: The caller's clock reading.

    Returns:
        ``True`` when this call resolved it; ``False`` otherwise or with the kill-switch off.
    """
    if not settings.memory_candidates_enabled:
        return False
    async with db.transaction() as conn:
        scrubbed = await run_housekeeping(conn, now)
        resolved = await resolve_candidate_in_transaction(
            conn, candidate_id, subject_person_id, to=to, correlation_id=correlation_id, now=now
        )
    await checkpoint_after_scrub(scrubbed + int(resolved))
    return resolved


async def _void_live_in_transaction(now: datetime) -> int:
    """Void every live candidate in one transaction, without checkpointing the log."""
    async with db.transaction() as conn:
        cursor = await conn.execute(VOID_LIVE_SQL, (iso_utc(now),))
        return await _rowcount(cursor)


async def void_live_candidates(now: datetime) -> int:
    """Void every live candidate (start-up with the kill-switch off).

    Args:
        now: The caller's clock reading.

    Returns:
        How many candidates were voided.
    """
    voided = await _void_live_in_transaction(now)
    await checkpoint_after_scrub(voided)
    return voided


async def reset_for_startup(now: datetime, *, enabled: bool) -> None:
    """Make the store consistent with a process that has just started (ADR 0021 decision 6).

    With the switch off every live candidate is voided. With it on, an ``offered``
    candidate returns to ``proposed`` (whatever was said in the previous process is gone and
    the answer window cannot be trusted) and lapsed candidates are expired. Either way the
    write-ahead log is then truncated once: a checkpoint a previous process still owed is
    forgotten with it, so start-up cannot assume nothing is owed. Runs before any request is
    served.

    Args:
        now: The caller's clock reading.
        enabled: ``MEMORY_CANDIDATES_ENABLED`` as the application was configured (the lifespan
            reads it from the app's own settings, not from the module global).
    """
    if not enabled:
        scrubbed = await _void_live_in_transaction(now)
        logger.info("Candidates voided at start-up: %d", scrubbed)
    else:
        async with db.transaction() as conn:
            cursor = await conn.execute(
                "UPDATE memory_candidates SET status = 'proposed', offered_at = NULL, "
                "offer_correlation_id = NULL WHERE status = 'offered'"
            )
            await cursor.close()
            scrubbed = await expire_lapsed_in_transaction(conn, now)
        logger.info("Candidates reconciled at start-up: %d expired", scrubbed)
    # `max(..., 1)`: truncate even when this start-up erased nothing (see the docstring).
    await checkpoint_after_scrub(max(scrubbed, 1))


async def count_live_candidates() -> int:
    """Return how many candidates still hold a value (``proposed`` or ``offered``).

    A resolved candidate has been erased (ADR 0021), so only a live one means the robot learned
    something by voice that a replacement could contradict (Plan 0071).
    """
    cursor = await db.get_conn().execute(
        "SELECT COUNT(*) FROM memory_candidates WHERE status IN ('proposed', 'offered')"
    )
    row = await cursor.fetchone()
    await cursor.close()
    return 0 if row is None else int(row[0])
