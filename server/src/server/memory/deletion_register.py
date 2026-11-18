"""The deletion register: a deletion for good survives a power cut, a restart and a restore.

ADR 0032 decision 6, ADR 0038 decision 4, ADR 0039 decision 1, Plan 0086 D-12. Every physical
deletion of a memory goes through ``forget``, in this order:

1. one line per deleted row is appended to ``deletions.jsonl`` beside the database and the file
   is ``fsync``-ed (its directory too, where the OS allows it): ``seq``, ``kind``, ``id``, ``at``,
   never a value;
2. the rows are deleted by their owner modules in one transaction committed under
   ``synchronous=FULL``, which also moves the replay marker (``meta.deletion_register_seq``);
3. the write-ahead log is checkpointed until SQLite reports it done.

``replay_register`` runs after ``open_db`` (the server's start and ``iroko-admin``): every line
after the marker is applied again, in order, then the marker moves. A cut between steps 1 and 2
is finished at the next start; a database restored from an older backup gets its later
deletions back; and because the marker lives in the database, a line is applied once per
lineage, so an id a restored database hands out again is never deleted by a second start.

The register is a file **outside** the database: restoring the database does not roll it back.
It keys on the table and the integer id (ADR 0039 decision 1).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
import logging
import os
import sqlite3
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from server import db
from server.exceptions import BrainMemoryError
from server.memory import (
    care_contacts,
    conversation_consent,
    conversation_episodes,
    conversation_record,
    declarative,
    meta,
    pending_store,
    recall_store,
    relational_v4,
)
from server.settings import settings
from server.timestamps import instant_text

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping, Sequence
    from datetime import datetime
    from pathlib import Path

    import aiosqlite

__all__ = [
    "MARKER_KEY",
    "REGISTER_FILENAME",
    "Deletion",
    "DeletionKind",
    "ForgetResult",
    "forget",
    "forget_record",
    "register_path",
    "replay_register",
    "withdraw_conversation_consent",
]

logger = logging.getLogger(__name__)

REGISTER_FILENAME: Final = "deletions.jsonl"
MARKER_KEY: Final = "deletion_register_seq"
_INSTANT_LENGTH: Final = 32
_LINE_KEYS: Final = frozenset({"seq", "kind", "id", "at"})


class DeletionKind(StrEnum):
    """What one register line deletes; each kind is deleted by its table's owner module."""

    LITERAL_FACT = "literal_fact"
    ENTITY_RELATION = "entity_relation"
    CARE_CONTACT = "care_contact"
    TURN = "turn"
    # The id is the record's: its episode and the episode's recall unit go, its turns stay.
    EPISODE = "episode"
    RECORD = "record"
    # The id is the person's: the conversation consent is withdrawn and every record deleted.
    OWNER_RECORDS = "owner_records"
    ENTITY = "entity"
    # Rows a person's deletion reaches that no turn or episode carries with it (a unit or a topic
    # older than the turn rows, or one already archived).
    RECALL_UNIT = "recall_unit"
    PENDING_TOPIC = "pending_topic"


@dataclass(frozen=True)
class Deletion:
    """One row to delete for good."""

    kind: DeletionKind
    row_id: int


@dataclass(frozen=True)
class ForgetResult:
    """What one ``forget`` did: rows deleted, and whether the checkpoint completed."""

    rows: int
    checkpointed: bool


@dataclass(frozen=True)
class _Line:
    seq: int
    deletion: Deletion
    at: str


def register_path() -> Path:
    """The register file: ``deletions.jsonl`` in the database's own directory."""
    return settings.brain_db_path.parent / REGISTER_FILENAME


def _parse(raw: str) -> _Line | None:
    """One register line, or ``None`` when it is not a well-formed line."""
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict) or set(value) != _LINE_KEYS:
        return None
    seq, kind, row_id, at = value["seq"], value["kind"], value["id"], value["at"]
    if not (type(seq) is int and type(row_id) is int and isinstance(at, str)):  # no bool
        return None
    if kind not in DeletionKind.__members__.values() or len(at) != _INSTANT_LENGTH:
        return None
    return _Line(seq=seq, deletion=Deletion(DeletionKind(kind), row_id), at=at)


def _read(path: Path) -> tuple[list[_Line], int]:
    """Every complete line, and the byte length of the complete part of the file.

    A last line without its newline was cut during an append, before any deletion ran: it is not
    a line. Any other unreadable line refuses, with a count and never the line.

    Raises:
        BrainMemoryError: If a complete line is unreadable or the sequence does not grow.
    """
    if not path.is_file():
        return [], 0
    data = path.read_bytes()
    complete = data[: data.rfind(b"\n") + 1]
    lines: list[_Line] = []
    bad = 0
    for raw in complete.decode("utf-8", errors="replace").splitlines():
        line = _parse(raw)
        if line is None or (lines and line.seq <= lines[-1].seq):
            bad += 1
        else:
            lines.append(line)
    if bad:
        raise BrainMemoryError(f"deletion register: {bad} unreadable line(s)")
    return lines, len(complete)


def _fsync_directory(directory: Path) -> None:
    """Make a new file's directory entry durable; Windows cannot open a directory to sync it."""
    if os.name == "nt":
        return
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _append(deletions: Sequence[Deletion], at: str, *, marker: int = 0) -> list[_Line]:
    """Append one line per deletion and make it durable, before anything is deleted.

    The first new ``seq`` follows both the file's last line and the database's marker, so a
    register file that was lost or reset can never hand out a number a replay would skip.
    """
    path = register_path()
    existing, complete = _read(path)
    first = max(existing[-1].seq if existing else 0, marker) + 1
    lines = [
        _Line(seq=first + offset, deletion=deletion, at=at)
        for offset, deletion in enumerate(deletions)
    ]
    text = "".join(
        json.dumps(
            {
                "seq": line.seq,
                "kind": line.deletion.kind.value,
                "id": line.deletion.row_id,
                "at": line.at,
            },
            separators=(",", ":"),
        )
        + "\n"
        for line in lines
    )
    created = not path.exists()
    with path.open("ab") as handle:
        handle.truncate(complete)  # drop a half-written last line before appending after it
        handle.write(text.encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())
    if created:
        _fsync_directory(path.parent)
    return lines


type _RowDeleter = Callable[[aiosqlite.Connection, int], Awaitable[int]]

# Each kind is deleted by its table's owner module (the one with SQL on it).
_DELETERS: Final[Mapping[DeletionKind, _RowDeleter]] = MappingProxyType(
    {
        DeletionKind.LITERAL_FACT: relational_v4.delete_literal_fact_row,
        DeletionKind.ENTITY_RELATION: relational_v4.delete_entity_relation_row,
        DeletionKind.CARE_CONTACT: care_contacts.delete_contact_row,
        DeletionKind.TURN: conversation_record.delete_turn_row,
        DeletionKind.EPISODE: conversation_episodes.delete_episode_row,
        DeletionKind.RECORD: conversation_record.delete_record_row,
        DeletionKind.ENTITY: declarative.delete_entity_row,
        DeletionKind.RECALL_UNIT: recall_store.delete_unit_row,
        DeletionKind.PENDING_TOPIC: pending_store.delete_topic_row,
    }
)


async def _apply(conn: aiosqlite.Connection, deletion: Deletion, at: str) -> int:
    """Delete one row through its owner module, inside the caller's transaction."""
    if deletion.kind is DeletionKind.OWNER_RECORDS:
        return await conversation_consent.withdraw_in(conn, deletion.row_id, at=at)
    rows = await _DELETERS[deletion.kind](conn, deletion.row_id)
    if deletion.kind is DeletionKind.EPISODE:
        # Without its episode the record is ordinary raw text again: the purge may take it whole
        # (a record kept only for its episode would otherwise stay for ever, Plan 0086 D-11).
        await conversation_record.set_episode_status(
            deletion.row_id, conversation_record.EpisodeStatus.SKIPPED, conn=conn
        )
    return rows


async def _probe(deletions: Sequence[Deletion], at: str) -> None:
    """Try the deletions and roll them back, so a refused one never reaches the register.

    A row a ``RESTRICT`` key still holds (a revoked role, a consent, a profile) would refuse the
    deletion at every replay; it is refused here, before the append.

    Raises:
        BrainMemoryError: If a foreign key refuses one of them; nothing is written.
    """
    async with db.transaction() as conn:
        await conn.execute("SAVEPOINT forget_probe")
        try:
            for deletion in deletions:
                await _apply(conn, deletion, at)
        except sqlite3.IntegrityError as exc:
            raise BrainMemoryError(
                "deletion refused by a foreign key: nothing was deleted"
            ) from exc
        finally:
            await conn.execute("ROLLBACK TO forget_probe")
            await conn.execute("RELEASE forget_probe")


async def _marker() -> int:
    value = await meta.get_flag(MARKER_KEY)
    return int(value) if value is not None else 0


type Audit = Callable[[aiosqlite.Connection], Awaitable[object]]


async def _apply_line(conn: aiosqlite.Connection, line: _Line) -> tuple[int, bool]:
    """Apply one replayed line in its own savepoint; a line a key refuses is skipped."""
    await conn.execute("SAVEPOINT replay_line")
    try:
        rows = await _apply(conn, line.deletion, line.at)
    except sqlite3.IntegrityError:
        await conn.execute("ROLLBACK TO replay_line")
        await conn.execute("RELEASE replay_line")
        return 0, False
    await conn.execute("RELEASE replay_line")
    return rows, True


async def _apply_lines(
    lines: Sequence[_Line], *, replay: bool = False, audit: Audit | None = None
) -> int:
    """Apply *lines* in one durable transaction that also moves the marker; returns the rows.

    On a replay each line has its own savepoint: a restored backup may hold a row that a later
    revocation freed (a role, a consent), so a line its key refuses is logged by count and
    skipped instead of stopping every start. A live deletion was probed before its append.
    """
    if not lines:
        return 0
    rows = 0
    refused = 0
    async with db.transaction(durable=True) as conn:
        for line in lines:
            if replay:
                done, applied = await _apply_line(conn, line)
                rows += done
                refused += 0 if applied else 1
            else:
                rows += await _apply(conn, line.deletion, line.at)
        await meta.set_flag_in(conn, MARKER_KEY, str(lines[-1].seq))
        if audit is not None:
            await audit(conn)
    if refused:
        logger.warning("deletion.replay refused lines=%d", refused)
    return rows


async def forget(
    deletions: Sequence[Deletion], *, now: datetime, audit: Audit | None = None
) -> ForgetResult:
    """Delete rows for good under the protocol (probe, register, durable delete, checkpoint).

    Args:
        deletions: The rows, in the order the foreign keys need (a care contact before its
            entity, a turn before its record).
        now: The deletion instant written on every line.
        audit: Writes the operation's audit row inside the deletion's own transaction, so a
            deletion is never left unaudited (``iroko-admin``).

    Returns:
        How many rows went, and whether the write-ahead log was checkpointed.

    Raises:
        BrainMemoryError: If a foreign key refuses a deletion, the register is unreadable or the
            database is not open; nothing is deleted then.
    """
    if not deletions:
        return ForgetResult(rows=0, checkpointed=True)
    at = instant_text(now)
    await _probe(deletions, at)
    # Lines a cut left unapplied (appended, never deleted) go first, so the marker never skips one.
    marker = await _marker()
    pending = [line for line in _read(register_path())[0] if line.seq > marker]
    lines = _append(deletions, at, marker=marker)
    rows = await _apply_lines([*pending, *lines], audit=audit)
    checkpointed = await db.checkpoint_wal_until_done()
    logger.info(
        "Deleted for good: %d line(s), %d row(s)",
        len(lines),
        rows,
        extra={"event": "memory.deleted", "lines": len(lines), "rows": rows},
    )
    return ForgetResult(rows=rows, checkpointed=checkpointed)


async def replay_register() -> int:
    """Apply every register line after the marker, in order; call right after ``open_db``.

    Returns:
        How many lines were applied (0 on a database that already holds them all).

    Raises:
        BrainMemoryError: If a line is unreadable; the start must not go on.
    """
    lines, _ = _read(register_path())
    marker = await _marker()
    pending = [line for line in lines if line.seq > marker]
    if not pending:
        return 0
    rows = await _apply_lines(pending, replay=True)
    await db.checkpoint_wal_until_done()
    logger.info("Deletion register replayed: %d line(s), %d row(s)", len(pending), rows)
    return len(pending)


async def forget_record(record_id: int, *, now: datetime) -> bool:
    """Delete one conversation segment for good (``iroko-admin conversations delete``).

    Its turns, episode, recall units, candidates and pending topics go with it; the next segment
    is unlinked.

    Returns:
        Whether a segment was deleted; a number that names no segment writes no register line.
    """
    if await conversation_record.read_record(record_id) is None:
        return False
    result = await forget([Deletion(DeletionKind.RECORD, record_id)], now=now)
    return result.rows > 0


async def withdraw_conversation_consent(person_entity_id: int, *, now: datetime) -> int:
    """Withdraw the conversation consent and delete every record and episode, for good.

    Idempotent: with no active grant it still deletes whatever record exists and succeeds.

    Args:
        person_entity_id: The owner withdrawing the consent.
        now: When the consent was withdrawn (timezone-aware).

    Returns:
        How many record segments were deleted.
    """
    result = await forget([Deletion(DeletionKind.OWNER_RECORDS, person_entity_id)], now=now)
    logger.info(
        "Conversation consent revoked: person=%s, %d segment(s) deleted",
        person_entity_id,
        result.rows,
    )
    return result.rows
