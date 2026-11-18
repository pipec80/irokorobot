"""The conversation record: the only SQL on ``conversation_records`` (ADR 0027, Plan 0076).

A conversation is one or more consecutive **segments**. Exchanges are rows of ``conversation_turns``
appended to the single open segment; a silence of ``WORKING_MEMORY_IDLE_SECONDS`` ends the
conversation, and a segment that holds ``CONVERSATION_SEGMENT_MAX_TURNS`` exchanges or would pass
``CONVERSATION_SEGMENT_MAX_BYTES`` is closed and continued in a new segment linked to it. Both
byte limits (the segment's and the whole record's cap) weigh an exchange as the UTF-8 bytes of what
was heard plus what was said. A closed
segment expires after ``CONVERSATION_RECORD_ELIGIBLE_DAYS`` when at least one exchange was the
owner's verified voice, after ``CONVERSATION_RECORD_INELIGIBLE_DAYS`` otherwise.

Nothing here logs a text: only ids, counts and closed reasons. No route, prompt or voice answer
reads this module (an architecture guard).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
import logging
from typing import TYPE_CHECKING
from uuid import UUID

from server import db
from server.exceptions import BrainMemoryError
from server.memory.conversation_types import RecordedTurn, TurnVerdict
from server.settings import settings
from server.timestamps import instant_text, parse_instant

if TYPE_CHECKING:
    import aiosqlite

__all__ = [
    "STORED_TURN_CORRELATION_IDS_SQL",
    "EpisodeStatus",
    "RecordSummary",
    "RecordView",
    "TurnIndexer",
    "append_turn",
    "chain_indexers",
    "close_idle_records",
    "count_failed_attempt",
    "delete_all_records",
    "delete_record_row",
    "delete_turn_row",
    "find_turn_id",
    "has_open_record",
    "list_records",
    "next_pending_record",
    "purge_records",
    "read_record",
    "record_turn_count",
    "set_episode_status",
    "turn_record_id",
    "turn_texts",
]

logger = logging.getLogger(__name__)

#: The correlation ids of the stored turns, as a subquery. A store that counts the rows derived
#: from a turn (the health check, Plan 0085) puts it inside its own statement, so only this module
#: names the table.
STORED_TURN_CORRELATION_IDS_SQL = "SELECT correlation_id FROM conversation_turns"

#: Writes what an appended exchange adds elsewhere, inside the append's transaction (the recall
#: unit, Plan 0078; the pending topic, Plan 0084; the link of its candidates, Plan 0085). It
#: receives the connection, the segment's id, the new turn's id and the exchange. Its result is
#: not used.
type TurnIndexer = Callable[[aiosqlite.Connection, int, int, RecordedTurn], Awaitable[object]]

_BYTES_PER_MB = 1_000_000
# How many exchanges a record holds and how many bytes they weigh, counted from its rows (the
# record keeps neither). A turn weighs its generated column `conversation_turns.bytes`, the one
# definition; the record's rows are found by the index `conversation_turns_record_idx` (at most
# a segment's turn limit of them). The fragments are constant: nothing a person says reaches them.
_RECORD_TURNS = "FROM conversation_records r LEFT JOIN conversation_turns t ON t.record_id = r.id"
_SUMMARY_COLUMNS = (
    "r.id, r.previous_id, r.started_at, r.closed_at, COUNT(t.id), COALESCE(SUM(t.bytes), 0), "
    "r.eligible, r.expires_at, r.episode_status"
)
_OPEN_SEGMENT_SQL = (
    "SELECT r.id, r.last_turn_at, r.eligible, COUNT(t.id), COALESCE(SUM(t.bytes), 0) "
    f"{_RECORD_TURNS} WHERE r.closed_at IS NULL GROUP BY r.id"
)
_TURN_COLUMNS = "said_at, heard, said, verdict, correlation_id"


class EpisodeStatus(StrEnum):
    """Where a closed record stands with the diary job."""

    PENDING = "pending"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True)
class RecordSummary:
    """A record's metadata; it carries no text."""

    id: int
    previous_id: int | None
    started_at: str
    closed_at: str | None
    turn_count: int
    byte_count: int
    eligible: bool
    expires_at: str | None
    episode_status: EpisodeStatus


@dataclass(frozen=True)
class RecordView:
    """A record with its exchanges, sorted by time; its ``repr`` omits them."""

    summary: RecordSummary
    owner_entity_id: int
    turns: tuple[RecordedTurn, ...] = field(repr=False)
    # The stored id of each turn, in the same order (`iroko-admin forget turn`, Plan 0086).
    turn_ids: tuple[int, ...] = field(default=(), repr=False)


def _summary(row: tuple[object, ...]) -> RecordSummary:
    """Build a summary from one ``_SUMMARY_COLUMNS`` row."""
    return RecordSummary(
        id=int(str(row[0])),
        previous_id=None if row[1] is None else int(str(row[1])),
        started_at=str(row[2]),
        closed_at=None if row[3] is None else str(row[3]),
        turn_count=int(str(row[4])),
        byte_count=int(str(row[5])),
        eligible=bool(row[6]),
        expires_at=None if row[7] is None else str(row[7]),
        episode_status=EpisodeStatus(str(row[8])),
    )


def _turn(row: tuple[object, ...]) -> RecordedTurn:
    """Build an exchange from one ``_TURN_COLUMNS`` row; a malformed one raises a closed error."""
    try:
        return RecordedTurn(
            at=parse_instant(str(row[0])),
            heard=str(row[1]),
            said=str(row[2]),
            voice=TurnVerdict(str(row[3])),
            correlation_id=UUID(str(row[4])),
        )
    except ValueError:
        raise BrainMemoryError("A conversation record holds a malformed exchange") from None


def _expiry(closed_at: datetime, *, eligible: bool) -> str:
    days = (
        settings.conversation_record_eligible_days
        if eligible
        else settings.conversation_record_ineligible_days
    )
    return instant_text(closed_at + timedelta(days=days))


async def _close(
    conn: aiosqlite.Connection, record_id: int, *, eligible: bool, now: datetime
) -> None:
    await conn.execute(
        "UPDATE conversation_records SET closed_at = ?, expires_at = ? WHERE id = ?",
        (instant_text(now), _expiry(now, eligible=eligible), record_id),
    )


def chain_indexers(*hooks: TurnIndexer | None) -> TurnIndexer | None:
    """Return one indexer that runs the given ones in order, or ``None`` when there is none.

    Args:
        hooks: The writers an append runs inside its transaction; ``None`` entries are skipped.
    """
    present = [hook for hook in hooks if hook is not None]
    if not present:
        return None

    async def run(
        conn: aiosqlite.Connection, record_id: int, turn_id: int, recorded: RecordedTurn
    ) -> None:
        for hook in present:
            await hook(conn, record_id, turn_id, recorded)

    return run


async def append_turn(
    turn: RecordedTurn,
    *,
    owner_entity_id: int,
    now: datetime,
    index: TurnIndexer | None = None,
) -> int:
    """Append one exchange to the open segment, closing and opening segments as needed.

    Args:
        turn: The exchange.
        owner_entity_id: The owner the record belongs to.
        now: The time a segment closed here is stamped with.
        index: Called inside the append's transaction with the segment id and the new turn's
            id, after the append; a failure rolls the append back with it (the recall unit,
            Plan 0078, the pending topic, Plan 0084, and the candidates' link, Plan 0085).

    Returns:
        The id of the segment that received the exchange.
    """
    # Must equal the generated column `conversation_turns.bytes` (a test pins it).
    size = len(turn.heard.encode("utf-8")) + len(turn.said.encode("utf-8"))
    at = instant_text(turn.at)
    async with db.transaction() as conn:
        cursor = await conn.execute(_OPEN_SEGMENT_SQL)
        row = await cursor.fetchone()
        await cursor.close()
        record_id: int | None = None
        previous_id: int | None = None
        if row is not None:
            open_id, last_turn_at = int(row[0]), datetime.fromisoformat(str(row[1]))
            eligible, count, total = bool(row[2]), int(row[3]), int(row[4])
            idle = (turn.at - last_turn_at).total_seconds() >= settings.working_memory_idle_seconds
            full = (
                count >= settings.conversation_segment_max_turns
                or total + size > settings.conversation_segment_max_bytes
            )
            if idle or full:
                await _close(conn, open_id, eligible=eligible, now=now)
                previous_id = None if idle else open_id
            else:
                record_id = open_id
        if record_id is None:
            cursor = await conn.execute(
                "INSERT INTO conversation_records "
                "(previous_id, owner_entity_id, started_at, last_turn_at) VALUES (?, ?, ?, ?)",
                (previous_id, owner_entity_id, at, at),
            )
            record_id = int(cursor.lastrowid or 0)
            await cursor.close()
        cursor = await conn.execute(
            "INSERT INTO conversation_turns "
            "(record_id, correlation_id, said_at, verdict, heard, said) VALUES (?, ?, ?, ?, ?, ?)",
            (record_id, str(turn.correlation_id), at, turn.voice.value, turn.heard, turn.said),
        )
        turn_id = int(cursor.lastrowid or 0)
        await cursor.close()
        await conn.execute(
            "UPDATE conversation_records SET last_turn_at = max(last_turn_at, ?), "
            "eligible = max(eligible, ?) WHERE id = ?",
            (at, int(turn.voice is TurnVerdict.VERIFIED), record_id),
        )
        if index is not None:
            await index(conn, record_id, turn_id, turn)
    return record_id


async def find_turn_id(conn: aiosqlite.Connection, correlation_id: UUID) -> int | None:
    """Return the id of the stored turn with this correlation id, or ``None`` when none exists.

    A turn is not stored when the record is off or after it was purged; what was derived from it
    (a memory candidate) then keeps no turn link.

    Args:
        conn: The connection of an open ``db.transaction()``.
        correlation_id: The turn's correlation id.
    """
    cursor = await conn.execute(
        "SELECT id FROM conversation_turns WHERE correlation_id = ?", (str(correlation_id),)
    )
    row = await cursor.fetchone()
    await cursor.close()
    return None if row is None else int(row[0])


async def close_idle_records(now: datetime) -> int:
    """Close the open segment when nothing was appended for the session's idle time.

    Args:
        now: The current time.

    Returns:
        How many segments were closed (0 or 1).
    """
    threshold = instant_text(now - timedelta(seconds=settings.working_memory_idle_seconds))
    async with db.transaction() as conn:
        cursor = await conn.execute(
            "SELECT id, eligible FROM conversation_records "
            "WHERE closed_at IS NULL AND last_turn_at <= ?",
            (threshold,),
        )
        rows = list(await cursor.fetchall())
        await cursor.close()
        for row in rows:
            await _close(conn, int(row[0]), eligible=bool(row[1]), now=now)
    if rows:
        logger.info("Conversation record: %d idle segment(s) closed", len(rows))
    return len(rows)


async def has_open_record() -> bool:
    """Return whether a segment is open (someone is in a conversation)."""
    cursor = await db.get_conn().execute(
        "SELECT 1 FROM conversation_records WHERE closed_at IS NULL LIMIT 1"
    )
    row = await cursor.fetchone()
    await cursor.close()
    return row is not None


async def list_records(limit: int = 50) -> tuple[RecordSummary, ...]:
    """Return the newest records' metadata, newest first; never a text.

    Args:
        limit: How many records at most.

    Returns:
        The summaries.
    """
    cursor = await db.get_conn().execute(
        f"SELECT {_SUMMARY_COLUMNS} {_RECORD_TURNS} GROUP BY r.id ORDER BY r.id DESC LIMIT ?",
        (limit,),
    )
    rows = await cursor.fetchall()
    await cursor.close()
    return tuple(_summary(tuple(row)) for row in rows)


async def _view(where: str, params: tuple[object, ...], order: str = "") -> RecordView | None:
    conn = db.get_conn()
    cursor = await conn.execute(
        f"SELECT {_SUMMARY_COLUMNS}, r.owner_entity_id {_RECORD_TURNS} "
        f"WHERE {where} GROUP BY r.id {order}",
        params,
    )
    row = await cursor.fetchone()
    await cursor.close()
    if row is None:
        return None
    values = tuple(row)
    summary = _summary(values[:9])
    cursor = await conn.execute(
        f"SELECT {_TURN_COLUMNS}, id FROM conversation_turns "  # noqa: S608
        "WHERE record_id = ? ORDER BY said_at, id",
        (summary.id,),
    )
    rows = [tuple(turn_row) for turn_row in await cursor.fetchall()]
    await cursor.close()
    return RecordView(
        summary=summary,
        owner_entity_id=int(str(values[9])),
        turns=tuple(_turn(turn_row) for turn_row in rows),
        turn_ids=tuple(int(str(turn_row[-1])) for turn_row in rows),
    )


async def read_record(record_id: int) -> RecordView | None:
    """Return one record with its exchanges, or ``None`` when it does not exist.

    Raises:
        BrainMemoryError: If the record holds a malformed exchange.
    """
    return await _view("r.id = ?", (record_id,))


async def next_pending_record() -> RecordView | None:
    """Return the oldest closed record still waiting for the diary job, or ``None``.

    Raises:
        BrainMemoryError: If the record holds a malformed exchange.
    """
    return await _view(
        "r.closed_at IS NOT NULL AND r.episode_status = 'pending'",
        (),
        "ORDER BY r.closed_at, r.id LIMIT 1",
    )


async def set_episode_status(
    record_id: int, status: EpisodeStatus, *, conn: aiosqlite.Connection | None = None
) -> None:
    """Set a record's diary status, inside the caller's transaction when *conn* is given."""
    sql = "UPDATE conversation_records SET episode_status = ? WHERE id = ?"
    if conn is not None:
        await conn.execute(sql, (status.value, record_id))
        return
    async with db.transaction() as own:
        await own.execute(sql, (status.value, record_id))


async def count_failed_attempt(record_id: int) -> int:
    """Add one failed diary attempt to a record and return the new count (0 if it is gone)."""
    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE conversation_records SET episode_attempts = episode_attempts + 1 WHERE id = ?",
            (record_id,),
        )
        cursor = await conn.execute(
            "SELECT episode_attempts FROM conversation_records WHERE id = ?", (record_id,)
        )
        row = await cursor.fetchone()
        await cursor.close()
    return 0 if row is None else int(row[0])


async def turn_texts(owner_entity_id: int) -> list[tuple[int, str, str]]:
    """The owner's stored turns as ``(id, heard, said)``, for ``forget_scope`` to find a name in.

    Read by the administration and the voice archive only; never logged.
    """
    cursor = await db.get_conn().execute(
        "SELECT t.id, t.heard, t.said FROM conversation_turns t "
        "JOIN conversation_records r ON r.id = t.record_id WHERE r.owner_entity_id = ?",
        (owner_entity_id,),
    )
    rows = [(int(row[0]), str(row[1]), str(row[2])) for row in await cursor.fetchall()]
    await cursor.close()
    return rows


async def record_turn_count(record_id: int) -> int:
    """How many turns a record still holds (0 for a record kept only for its episode)."""
    cursor = await db.get_conn().execute(
        "SELECT COUNT(*) FROM conversation_turns WHERE record_id = ?", (record_id,)
    )
    row = await cursor.fetchone()
    await cursor.close()
    return 0 if row is None else int(row[0])


async def turn_record_id(turn_id: int) -> int | None:
    """The record a stored turn belongs to, or ``None`` when there is no such turn."""
    cursor = await db.get_conn().execute(
        "SELECT record_id FROM conversation_turns WHERE id = ?", (turn_id,)
    )
    row = await cursor.fetchone()
    await cursor.close()
    return None if row is None else int(row[0])


async def delete_turn_row(conn: aiosqlite.Connection, row_id: int) -> int:
    """Delete one turn for good, inside the caller's transaction (Plan 0086 D-12).

    Only ``deletion_register`` calls it, under the deletion protocol. Its recall unit, candidate and pending topic
    go with it (CASCADE).

    Returns:
        How many rows went (0 when it was already gone: a replay is idempotent).
    """
    cursor = await conn.execute("DELETE FROM conversation_turns WHERE id = ?", (row_id,))
    deleted = max(cursor.rowcount, 0)
    await cursor.close()
    return deleted


async def delete_record_row(conn: aiosqlite.Connection, row_id: int) -> int:
    """Delete one segment for good, inside the caller's transaction (Plan 0086 D-12).

    Only ``deletion_register`` calls it, under the deletion protocol. Its turns, episode and what hangs from them go
    with it (CASCADE).

    Returns:
        How many rows went (0 when it was already gone: a replay is idempotent).
    """
    cursor = await conn.execute("DELETE FROM conversation_records WHERE id = ?", (row_id,))
    deleted = max(cursor.rowcount, 0)
    await cursor.close()
    return deleted


async def delete_all_records(conn: aiosqlite.Connection) -> int:
    """Delete every segment (and every episode) inside the caller's open transaction.

    Args:
        conn: The connection of an open ``db.transaction()``.

    Returns:
        How many segments were deleted.
    """
    cursor = await conn.execute("DELETE FROM conversation_records")
    deleted = cursor.rowcount
    await cursor.close()
    return max(deleted, 0)


# A record whose episode is written keeps its row when its turns go (Plan 0086 D-11, ADR 0032
# decision 5): the diary outlives the raw text. It is purgeable only while it still holds a turn;
# a record with no written episode is purgeable whole.
_PURGEABLE = (
    "closed_at IS NOT NULL AND (episode_status <> 'done' OR EXISTS "
    "(SELECT 1 FROM conversation_turns t WHERE t.record_id = conversation_records.id))"
)


async def _purge_one(conn: aiosqlite.Connection, record_id: int, status: str) -> int:
    """Purge one closed segment: its turns when its episode is written, else the whole row.

    Returns:
        The bytes its exchanges weighed.
    """
    cursor = await conn.execute(
        "SELECT COALESCE(SUM(bytes), 0) FROM conversation_turns WHERE record_id = ?", (record_id,)
    )
    weighed = await cursor.fetchone()
    await cursor.close()
    if status == EpisodeStatus.DONE.value:
        await conn.execute("DELETE FROM conversation_turns WHERE record_id = ?", (record_id,))
    else:
        await conn.execute("DELETE FROM conversation_records WHERE id = ?", (record_id,))
    return 0 if weighed is None else int(weighed[0])


async def _delete_oldest_closed(conn: aiosqlite.Connection) -> int | None:
    """Purge the next closed segment to go (not eligible first, then the oldest).

    Returns:
        The bytes its exchanges weighed, or ``None`` when no purgeable segment is left.
    """
    cursor = await conn.execute(
        f"SELECT id, episode_status FROM conversation_records WHERE {_PURGEABLE} "  # noqa: S608
        "ORDER BY eligible, closed_at, id LIMIT 1"
    )
    victim = await cursor.fetchone()
    await cursor.close()
    if victim is None:
        return None
    return await _purge_one(conn, int(victim[0]), str(victim[1]))


async def purge_records(now: datetime) -> int:
    """Purge expired segments, then the oldest closed ones while the record is over its cap.

    Not-eligible segments go before eligible ones; the open segment is never purged. A segment
    whose episode is written loses its turns (and, by cascade, their recall units, candidates and
    pending topics) and keeps its row, its episode and the episode's recall unit (Plan 0086 D-11);
    any other segment goes whole, with whatever it holds.

    Args:
        now: The current time.

    Returns:
        How many segments were purged.
    """
    cap = settings.conversation_record_max_total_mb * _BYTES_PER_MB
    async with db.transaction() as conn:
        cursor = await conn.execute(
            f"SELECT id, episode_status FROM conversation_records WHERE {_PURGEABLE} "  # noqa: S608
            "AND expires_at < ? ORDER BY id",
            (instant_text(now),),
        )
        expired = [(int(row[0]), str(row[1])) for row in await cursor.fetchall()]
        await cursor.close()
        for record_id, status in expired:
            await _purge_one(conn, record_id, status)
        deleted = len(expired)
        cursor = await conn.execute("SELECT COALESCE(SUM(bytes), 0) FROM conversation_turns")
        row = await cursor.fetchone()
        await cursor.close()
        total = 0 if row is None else int(row[0])
        while total > cap:
            freed = await _delete_oldest_closed(conn)
            if freed is None:
                break
            total -= freed
            deleted += 1
    if deleted:
        logger.info("Conversation record: %d segment(s) purged", deleted)
        await db.checkpoint_wal()
    return deleted
