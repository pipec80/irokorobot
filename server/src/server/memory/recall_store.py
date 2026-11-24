"""The recall store: the only SQL on ``recall_units`` and its indexes (ADR 0028, Plan 0078).

A unit is the owner's words of one ``VERIFIED`` turn or the diary summary of a conversation. Every
read here filters by owner, visibility ``personal``, sensitivity ``normal``, the record's expiry
and the optional window **inside the query**, before any ranking. Times are UTC ISO 8601 strings
with microseconds, comparable as text. Nothing here logs a text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
import re
import sqlite3
from typing import TYPE_CHECKING, Final, Literal

import sqlite_vec

from server import db
from server.cognition.intent_resolution import resolve_information_need
from server.cognition.response_plan import InformationNeed
from server.cognition.spoken_dates import DayWindow
from server.exceptions import BrainMemoryError
from server.memory.conversation_types import TurnVerdict
from server.memory.embeddings import EMBEDDING_DIM
from server.memory.export_model import StoredRows, fetch_count, fetch_stored_rows
from server.memory.recall_sensitivity import (
    RecallSensitivity,
    classify_turn_text,
    most_protective,
)
from server.memory.retrieval import match_expression
from server.settings import settings
from server.timestamps import instant_text

if TYPE_CHECKING:
    from collections.abc import Sequence

    import aiosqlite

    from server.memory.conversation_types import RecordedTurn

__all__ = [
    "RecallIndexHealth",
    "RecallUnit",
    "archive_units",
    "archived_units",
    "count_rows",
    "count_units_of_another_model",
    "count_unlinked_units",
    "delete_unit_row",
    "distances_of",
    "index_health",
    "insert_episode_unit",
    "insert_turn_unit",
    "lexical_hits",
    "occurred_time_on",
    "projection_counts",
    "raise_record_sensitivity",
    "recent_units",
    "restore_archived_units",
    "store_vector",
    "tells_something",
    "unit_ids_naming",
    "unit_ids_naming_stored",
    "units_by_id",
    "units_for_export",
    "units_without_vector",
    "vector_hits",
]

type UnitKind = Literal["turn", "episode"]

_HAS_WORD: Final = re.compile(r"\w")

# An extended SQLite result code keeps its primary code in the low byte (267 is 11 | 1 << 8).
_PRIMARY_CODE_MASK: Final = 0xFF

# The filters every read applies to a unit `u` joined to its record `r`; a unit the owner set
# aside (`archived_at`, Plan 0086 D-8) is never read. An episode unit is read whatever its record's
# expiry: the diary outlives the raw text (Plan 0086 D-11, ADR 0032 decision 5).
_READABLE = (
    "u.owner_entity_id = :owner AND u.visibility = 'personal' AND u.sensitivity = 'normal' "
    "AND u.archived_at IS NULL "
    "AND (u.kind = 'episode' OR r.expires_at IS NULL OR r.expires_at > :now) "
    "AND (:since IS NULL OR u.said_at >= :since) AND (:until IS NULL OR u.said_at < :until)"
)
# The model guard (ADR 0031 decision 8). The configured model is a parameter; each half of
# "another model" is a range (`<` or `>`), which the index `recall_units_model_idx` serves where `<>`
# would scan. A NULL model is neither: such a unit has no vector yet. The count names the index
# because, left alone, the planner reads the owner's whole slice of `recall_units_owner_time_idx`.
_OTHER_MODEL_COUNT_SQL = (
    "SELECT COUNT(*) FROM recall_units INDEXED BY recall_units_model_idx "
    "WHERE owner_entity_id = ?1 AND (embedding_model < ?2 OR embedding_model > ?2)"
)
# The units to (re-)embed, oldest first: no vector (the partial index
# `recall_units_unembedded_idx`) or a vector of another model (`recall_units_model_idx`).
_UNITS_TO_EMBED_SQL = (
    "SELECT id, body FROM recall_units WHERE id IN ("
    "SELECT id FROM recall_units WHERE embedding_model IS NULL "
    "UNION ALL SELECT id FROM recall_units WHERE embedding_model < ?1 "
    "UNION ALL SELECT id FROM recall_units WHERE embedding_model > ?1) "
    "ORDER BY id LIMIT ?2"
)
_UNIT_COLUMNS = "u.id, u.source_record_id, u.kind, u.body, u.said_at"
# With the occurred time on (Plan 0083 D-9): a unit with an occurred interval matches a window by
# the overlap of its local days, one without by ``said_at``. An episode said in the window is
# left out when its record has a turn with an interval and no turn of the record matches the
# window, so yesterday's diary entry of a story about last year is not «what you did yesterday».
_IN_WINDOW = (
    "(({t}.occurred_start IS NOT NULL "
    "AND {t}.occurred_start <= :last_day AND {t}.occurred_end >= :first_day) "
    "OR ({t}.occurred_start IS NULL AND {t}.said_at >= :since AND {t}.said_at < :until))"
)
_RECORD_TURNS = (
    "SELECT 1 FROM recall_units t WHERE t.source_record_id = u.source_record_id "
    "AND t.kind = 'turn' AND "
)
_READABLE_OCCURRED = (
    "u.owner_entity_id = :owner AND u.visibility = 'personal' AND u.sensitivity = 'normal' "
    "AND u.archived_at IS NULL "
    "AND (u.kind = 'episode' OR r.expires_at IS NULL OR r.expires_at > :now) "
    f"AND (:since IS NULL OR ({_IN_WINDOW.format(t='u')} AND NOT (u.kind = 'episode' "
    f"AND EXISTS ({_RECORD_TURNS}t.occurred_start IS NOT NULL) "
    f"AND NOT EXISTS ({_RECORD_TURNS}{_IN_WINDOW.format(t='t')}))))"
)
_UNIT_COLUMNS_OCCURRED = f"{_UNIT_COLUMNS}, u.occurred_start, u.occurred_end"
# What a date-only question reads, group by group; the first group with units answers. Today:
# the window's episodes, else its turn units. With the occurred time on (hardware, 2026-11-12), a
# turn unit whose occurred interval falls in the window but that was told on another day is held
# by no episode of the window: it comes first, beside the episodes.
_KIND = "u.kind = :kind"
_TOLD_ELSEWHERE = (
    "u.occurred_start IS NOT NULL AND NOT (u.said_at >= :since AND u.said_at < :until)"
)
_RECENT_GROUPS: Final = (((_KIND, "episode"),), ((_KIND, "turn"),))
_RECENT_GROUPS_OCCURRED: Final = (
    ((f"{_KIND} AND {_TOLD_ELSEWHERE}", "turn"), (_KIND, "episode")),
    ((_KIND, "turn"),),
)
# The two occurred columns come right after ``_UNIT_COLUMNS`` in ``_UNIT_COLUMNS_OCCURRED``.
_OCCURRED_START: Final = len(_UNIT_COLUMNS.split(","))
_OCCURRED_END: Final = _OCCURRED_START + 1


@dataclass(frozen=True)
class RecallUnit:
    """One recallable unit; its ``repr`` never shows the body."""

    id: int
    record_id: int
    kind: UnitKind
    body: str = field(repr=False)
    said_at: datetime
    # When the told event happened (Plan 0083): filled only by a read with ``occurred=True``.
    occurred: DayWindow | None = field(default=None, repr=False)


def _unit(row: Sequence[object], *, occurred: bool) -> RecallUnit:
    """A unit from a row; with *occurred* the row holds the two occurred columns too."""
    kind: UnitKind = "episode" if str(row[2]) == "episode" else "turn"
    days = (
        DayWindow(
            start=date.fromisoformat(str(row[_OCCURRED_START])),
            end=date.fromisoformat(str(row[_OCCURRED_END])),
        )
        if occurred and row[_OCCURRED_START] is not None
        else None
    )
    return RecallUnit(
        id=int(str(row[0])),
        record_id=int(str(row[1])),
        kind=kind,
        body=str(row[3]),
        said_at=datetime.fromisoformat(str(row[4])),
        occurred=days,
    )


def _readable(*, occurred: bool) -> str:
    return _READABLE_OCCURRED if occurred else _READABLE


def _columns(*, occurred: bool) -> str:
    return _UNIT_COLUMNS_OCCURRED if occurred else _UNIT_COLUMNS


def _window(
    since: str | None,
    until: str | None,
    first_day: str | None,
    last_day: str | None,
    *,
    occurred: bool,
) -> dict[str, str | None]:
    """The window's parameters; with the occurred time on, a window carries its local days too.

    Raises:
        ValueError: If a window read by the occurred time lacks its local days.
    """
    window: dict[str, str | None] = {"since": since, "until": until}
    if not occurred:
        return window
    if since is not None and (first_day is None or last_day is None):
        raise ValueError("a window read by the occurred time needs its local days")
    return window | {"first_day": first_day, "last_day": last_day}


def occurred_time_on() -> bool:
    """Whether a turn unit keeps when its told event happened (Plan 0083 D-1).

    The one place the three switches meet: ``OCCURRED_TIME_ENABLED`` works only with
    ``MEMORY_ENABLED`` and ``RECALL_ENABLED``.
    """
    return settings.memory_enabled and settings.recall_enabled and settings.occurred_time_enabled


def tells_something(text: str) -> bool:
    """Whether the owner's words tell something to remember, rather than ask for something.

    A recall question, a relatives or children question, «¿qué sabes de mí?» or a protected
    request is answered by a closed rule and tells nothing; found on Pipec's hardware run
    (2026-11-03), such questions were later read back as «me contaste…». Only words that resolve
    to ordinary conversation become a unit. With the sensitive switch on, a sensitive question
    tells nothing too; with memory on, a stated or asked secret value tells nothing (Plan 0079),
    and neither does a spoken change of a memory: «no quiero saber más de X» became a unit after
    the archive it asked for, and recall read it back (Plan 0086, hardware 2026-11-18).

    Args:
        text: What the owner said.

    Returns:
        ``True`` for non-blank words of an ordinary turn.
    """
    if not text.strip():
        return False
    resolution = resolve_information_need(
        text,
        recall=True,
        sensitive=settings.sensitive_read_enabled,
        secrets=settings.memory_enabled,
        alta=settings.sensitive_read_enabled and settings.alta_read_enabled,
        occurred=occurred_time_on(),
        documents=settings.documents_enabled,
        changes=settings.memory_enabled,
    )
    return resolution.need is InformationNeed.GENERIC_CONVERSATION


async def _insert(
    conn: aiosqlite.Connection,
    *,
    owner_entity_id: int,
    record_id: int,
    episode_id: int | None,
    kind: UnitKind,
    body: str,
    said_at: str,
    sensitivity: RecallSensitivity,
    correlation_id: str | None,
    turn_id: int | None = None,
    occurred: DayWindow | None = None,
) -> int:
    """Insert one unit, or return the id of the unit its turn or episode already has.

    A turn has one unit and an episode has one (unique indexes), so a retried job that indexes
    the same turn or episode again changes nothing and does not fail the append. Only that
    conflict is absorbed: it is named in the statement, so a unique index added later on another
    column still fails the insert instead of being swallowed. The unit that stays is looked up by
    the same key and owner.

    Raises:
        RuntimeError: If the conflict was absorbed but no unit of this owner holds the key.
    """
    key_column, key = ("turn_id", turn_id) if kind == "turn" else ("episode_id", episode_id)
    start, end = (None, None) if occurred is None else (occurred.start, occurred.end)
    cursor = await conn.execute(
        "INSERT INTO recall_units (owner_entity_id, source_record_id, episode_id, turn_id, kind, "  # noqa: S608
        "body, said_at, visibility, sensitivity, correlation_id, occurred_start, occurred_end) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'personal', ?, ?, ?, ?) "
        f"ON CONFLICT ({key_column}) DO NOTHING RETURNING id",
        (
            owner_entity_id,
            record_id,
            episode_id,
            turn_id,
            kind,
            body,
            said_at,
            sensitivity,
            correlation_id,
            None if start is None else start.isoformat(),
            None if end is None else end.isoformat(),
        ),
    )
    row = await cursor.fetchone()
    await cursor.close()
    if row is not None:
        return int(row[0])
    cursor = await conn.execute(
        f"SELECT id FROM recall_units WHERE {key_column} = ? AND owner_entity_id = ?",  # noqa: S608
        (key, owner_entity_id),
    )
    existing = await cursor.fetchone()
    await cursor.close()
    if existing is None:
        raise RuntimeError("INSERT into recall_units was refused without a unit to return")
    return int(existing[0])


async def insert_turn_unit(
    conn: aiosqlite.Connection,
    *,
    record_id: int,
    owner_entity_id: int,
    turn: RecordedTurn,
    turn_id: int | None = None,
    occurred: DayWindow | None = None,
) -> int:
    """Write the unit of one verified turn, inside the caller's open transaction.

    Args:
        conn: The connection of an open ``db.transaction()``.
        record_id: The record the turn was appended to.
        owner_entity_id: The owner of the record.
        turn: The exchange; only its ``heard`` text becomes the unit, never ``said``.
        turn_id: The stored turn the unit comes from, so deleting the turn deletes the unit;
            ``None`` only for a unit whose turn is not stored.
        occurred: When the told event happened, as local days (Plan 0083), or ``None``.

    Returns:
        The new unit's id, or that of the unit the turn already has.

    Raises:
        ValueError: If the turn is not ``VERIFIED`` or its words are blank.
    """
    if turn.voice is not TurnVerdict.VERIFIED:
        raise ValueError("only a verified turn becomes a recall unit")
    if not turn.heard.strip():
        raise ValueError("a blank turn does not become a recall unit")
    return await _insert(
        conn,
        owner_entity_id=owner_entity_id,
        record_id=record_id,
        episode_id=None,
        kind="turn",
        body=turn.heard,
        said_at=instant_text(turn.at),
        sensitivity=classify_turn_text(turn.heard),
        correlation_id=str(turn.correlation_id),
        turn_id=turn_id,
        occurred=occurred,
    )


async def insert_episode_unit(
    conn: aiosqlite.Connection,
    *,
    record_id: int,
    episode_id: int,
    owner_entity_id: int,
    summary: str,
    sensitivity: RecallSensitivity,
    said_at: str,
) -> int:
    """Write the unit of one diary summary, inside the caller's open transaction.

    Returns:
        The new unit's id, or that of the unit the episode already has.
    """
    return await _insert(
        conn,
        owner_entity_id=owner_entity_id,
        record_id=record_id,
        episode_id=episode_id,
        kind="episode",
        body=summary,
        said_at=said_at,
        sensitivity=sensitivity,
        correlation_id=None,
    )


async def raise_record_sensitivity(
    conn: aiosqlite.Connection, *, record_id: int, sensitivity: RecallSensitivity
) -> int:
    """Raise each turn unit of a record to at least *sensitivity*; never lower one.

    Args:
        conn: The connection of an open ``db.transaction()``.
        record_id: The record whose turn units are raised.
        sensitivity: The episode's sensitivity.

    Returns:
        How many units changed.
    """
    cursor = await conn.execute(
        "SELECT id, sensitivity FROM recall_units WHERE source_record_id = ? AND kind = 'turn'",
        (record_id,),
    )
    rows = await cursor.fetchall()
    await cursor.close()
    changed = 0
    for row in rows:
        own: RecallSensitivity = row[1]
        raised = most_protective(own, sensitivity)
        if raised != own:
            await conn.execute(
                "UPDATE recall_units SET sensitivity = ? WHERE id = ?", (raised, int(row[0]))
            )
            changed += 1
    return changed


async def unit_ids_naming(*, owner_entity_id: int, phrase: str, now: str) -> list[int]:
    """The owner's readable units whose body holds *phrase* as one FTS5 phrase (Plan 0086 D-7).

    A phrase with no word character names nothing (FTS5 would refuse an empty phrase).

    The phrase is quoted, so no input is FTS syntax; accents and case are folded by the
    tokenizer. Only units every read may deliver are returned (``_READABLE``).
    """
    if not _HAS_WORD.search(phrase):
        return []
    cursor = await db.get_conn().execute(
        "SELECT u.id FROM recall_units_fts f JOIN recall_units u ON u.id = f.rowid "  # noqa: S608
        "JOIN conversation_records r ON r.id = u.source_record_id "
        f"WHERE recall_units_fts MATCH :match AND {_READABLE} ORDER BY u.id",
        {
            "match": '"' + phrase.replace('"', '""') + '"',
            "owner": owner_entity_id,
            "now": now,
            "since": None,
            "until": None,
        },
    )
    rows = [int(row[0]) for row in await cursor.fetchall()]
    await cursor.close()
    return rows


async def archived_units() -> list[tuple[int, str, str]]:
    """Every unit set aside as ``(id, archived_at, body)``, for ``iroko-admin archive list``."""
    cursor = await db.get_conn().execute(
        "SELECT id, archived_at, body FROM recall_units WHERE archived_at IS NOT NULL "
        "ORDER BY archived_at, id"
    )
    rows = [(int(row[0]), str(row[1]), str(row[2])) for row in await cursor.fetchall()]
    await cursor.close()
    return rows


async def delete_unit_row(conn: aiosqlite.Connection, row_id: int) -> int:
    """Delete one recall unit for good, inside the caller's transaction (Plan 0086 D-12).

    Only ``deletion_register`` calls it, under the deletion protocol. Its word-index row and its vector go with
    it (the unit's triggers).

    Returns:
        How many rows went (0 when it was already gone: a replay is idempotent).
    """
    cursor = await conn.execute("DELETE FROM recall_units WHERE id = ?", (row_id,))
    deleted = max(cursor.rowcount, 0)
    await cursor.close()
    return deleted


async def unit_ids_naming_stored(*, owner_entity_id: int, phrase: str) -> list[int]:
    """Every unit of the owner whose body holds *phrase*, archived or expired too (a deletion)."""
    if not _HAS_WORD.search(phrase):
        return []
    cursor = await db.get_conn().execute(
        "SELECT u.id FROM recall_units_fts f JOIN recall_units u ON u.id = f.rowid "
        "WHERE recall_units_fts MATCH ? AND u.owner_entity_id = ? ORDER BY u.id",
        ('"' + phrase.replace('"', '""') + '"', owner_entity_id),
    )
    rows = [int(row[0]) for row in await cursor.fetchall()]
    await cursor.close()
    return rows


async def archive_units(conn: aiosqlite.Connection, unit_ids: Sequence[int], *, at: str) -> int:
    """Set recall units aside, inside the caller's transaction (Plan 0086 D-7).

    The unit, its word-index row and its vector stay; every read leaves it out. A unit already
    archived keeps its first instant.

    Args:
        conn: The connection of an open ``db.transaction()``.
        unit_ids: The units to set aside.
        at: The archive instant (32-character UTC).

    Returns:
        How many units were set aside.
    """
    values = tuple(sorted({int(unit_id) for unit_id in unit_ids}))
    if not values:
        return 0
    marks = ", ".join("?" for _ in values)
    cursor = await conn.execute(
        f"UPDATE recall_units SET archived_at = ? "  # noqa: S608 - placeholders only
        f"WHERE id IN ({marks}) AND archived_at IS NULL AND sensitivity = 'normal'",
        (at, *values),
    )
    changed = max(cursor.rowcount, 0)
    await cursor.close()
    return changed


async def restore_archived_units(conn: aiosqlite.Connection, *, at: str) -> int:
    """Bring back every unit set aside at *at*, inside the caller's transaction.

    Args:
        conn: The connection of an open ``db.transaction()``.
        at: The archive instant of the group to restore.

    Returns:
        How many units came back.
    """
    cursor = await conn.execute(
        "UPDATE recall_units SET archived_at = NULL WHERE archived_at = ?", (at,)
    )
    changed = max(cursor.rowcount, 0)
    await cursor.close()
    return changed


async def store_vector(unit_id: int, vector: list[float], *, model: str) -> bool:
    """Index a unit's vector with its owner and **current** sensitivity, in one transaction.

    Args:
        unit_id: The unit.
        vector: Its embedding (``EMBEDDING_DIM`` values).
        model: The model that computed it.

    Returns:
        ``False`` when the unit is gone (its record was deleted meanwhile); ``True`` otherwise,
        also when it already had a vector (it is replaced).

    Raises:
        ValueError: If the vector has the wrong size.
    """
    if len(vector) != EMBEDDING_DIM:
        raise ValueError("a recall vector has the wrong size")
    async with db.transaction() as conn:
        cursor = await conn.execute(
            "SELECT owner_entity_id, sensitivity FROM recall_units WHERE id = ?", (unit_id,)
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row is None:
            return False
        await conn.execute("DELETE FROM recall_units_vec WHERE rowid = ?", (unit_id,))
        await conn.execute(
            "INSERT INTO recall_units_vec (rowid, owner_entity_id, sensitivity, embedding) "
            "VALUES (?, ?, ?, ?)",
            (unit_id, int(row[0]), str(row[1]), sqlite_vec.serialize_float32(vector)),
        )
        await conn.execute(
            "UPDATE recall_units SET embedding_model = ? WHERE id = ?", (model, unit_id)
        )
    return True


async def units_without_vector(limit: int) -> list[tuple[int, str]]:
    """Return ``(id, body)`` of the oldest units to (re-)embed: no vector, or one of another model.

    The model is the configured one (``settings.embedding_model``). Both halves read an index
    (``recall_units_unembedded_idx`` and ``recall_units_model_idx``), so a tick with nothing
    to embed does not scan the units.
    """
    cursor = await db.get_conn().execute(_UNITS_TO_EMBED_SQL, (settings.embedding_model, limit))
    rows = await cursor.fetchall()
    await cursor.close()
    return [(int(row[0]), str(row[1])) for row in rows]


async def count_units_of_another_model(owner_entity_id: int) -> int:
    """Count the owner's units whose vector was computed by a model other than the configured one.

    A unit without a vector does not count: it has nothing to compare. While the count is above
    zero a vector search would compare two embedding spaces, so recall searches by words only
    (ADR 0031 decision 8) until the re-index brings it to zero.
    """
    cursor = await db.get_conn().execute(
        _OTHER_MODEL_COUNT_SQL, (owner_entity_id, settings.embedding_model)
    )
    row = await cursor.fetchone()
    await cursor.close()
    return 0 if row is None else int(row[0])


@dataclass(frozen=True)
class RecallIndexHealth:
    """Counts about the word index and the vectors of the recall units: ints only, no value."""

    fts_errors: int
    vectors_without_unit: int
    units_without_fts_row: int
    units_without_vector: int
    units_of_another_model: int


async def count_rows(
    conn: aiosqlite.Connection, sql: str, parameters: tuple[object, ...] = ()
) -> int:
    """Run a ``SELECT COUNT(*)`` and return the number."""
    cursor = await conn.execute(sql, parameters)
    row = await cursor.fetchone()
    await cursor.close()
    return 0 if row is None else int(row[0])


async def count_unlinked_units(conn: aiosqlite.Connection, stored_turn_ids_sql: str) -> int:
    """Count the turn units with no link to a stored turn whose correlation id they carry.

    Such a unit would survive the deletion of its turn (Plan 0085 D-8). A unit whose turn was
    never stored (the record was off, or the turn purged) has nothing to link and is not counted.
    The recall store never names the record's tables, so the caller passes the subquery.

    Args:
        conn: An open connection.
        stored_turn_ids_sql: A ``SELECT`` of the correlation ids of the stored turn rows (the record
            store's ``STORED_TURN_CORRELATION_IDS_SQL``).
    """
    return await count_rows(
        conn,
        "SELECT COUNT(*) FROM recall_units WHERE kind = 'turn' AND turn_id IS NULL "  # noqa: S608
        f"AND correlation_id IN ({stored_turn_ids_sql})",
    )


async def _fts_errors(conn: aiosqlite.Connection) -> int:
    """FTS5 ``integrity-check``: 0 or 1. The command raises on a damaged index and writes no row.

    ``rank = 1`` also compares the index with the external content table (``recall_units``);
    an SQLite that does not know the option checks the index alone. Only the corruption error
    (``SQLITE_CORRUPT_VTAB``, a ``DatabaseError`` of the ``SQLITE_CORRUPT`` family) counts as a
    damaged index: a lock held by another process stops the check, which proves nothing.

    Raises:
        BrainMemoryError: If the check could not run (the database is busy or locked).
    """
    try:
        await conn.execute(
            "INSERT INTO recall_units_fts (recall_units_fts, rank) VALUES ('integrity-check', 1)"
        )
    except sqlite3.DatabaseError as exc:
        if exc.sqlite_errorcode & _PRIMARY_CODE_MASK != sqlite3.SQLITE_CORRUPT:
            raise BrainMemoryError("The text index check could not run") from exc
        return 1
    finally:
        await conn.rollback()
    return 0


async def index_health(conn: aiosqlite.Connection) -> RecallIndexHealth:
    """Count what is wrong, or still pending, in the recall index (``iroko-admin health``).

    Args:
        conn: An open connection; nothing is written and no transaction is left open.

    Returns:
        The counts. "Another model" is the configured ``settings.embedding_model``. The word
        index is read through its ``docsize`` shadow table, one row per indexed unit.
    """
    return RecallIndexHealth(
        fts_errors=await _fts_errors(conn),
        vectors_without_unit=await count_rows(
            conn,
            "SELECT COUNT(*) FROM recall_units_vec WHERE rowid NOT IN (SELECT id FROM recall_units)",
        ),
        units_without_fts_row=await count_rows(
            conn,
            "SELECT COUNT(*) FROM recall_units "
            "WHERE id NOT IN (SELECT id FROM recall_units_fts_docsize)",
        ),
        units_without_vector=await count_rows(
            conn,
            "SELECT COUNT(*) FROM recall_units WHERE id NOT IN (SELECT rowid FROM recall_units_vec)",
        ),
        units_of_another_model=await count_rows(
            conn,
            "SELECT COUNT(*) FROM recall_units "
            "WHERE embedding_model IS NOT NULL AND embedding_model <> ?",
            (settings.embedding_model,),
        ),
    )


async def distances_of(
    ids: Sequence[int], vector: list[float], *, owner_entity_id: int
) -> dict[int, float]:
    """Return the cosine distance of each named unit's vector to *vector* (Plan 0088 D-5).

    For the candidates the KNN did not rank (a word hit outside its *k* neighbours): one query on
    the named rows, inside the owner's partition. The caller passes only units it may read.

    Args:
        ids: The unit ids.
        vector: The question's embedding.
        owner_entity_id: The owner; another owner's row is never read.

    Returns:
        ``{unit id: distance}``; a unit without a vector is absent.
    """
    if not ids:
        return {}
    marks = ", ".join("?" for _ in ids)
    cursor = await db.get_conn().execute(
        "SELECT rowid, vec_distance_cosine(embedding, ?) FROM recall_units_vec "  # noqa: S608
        f"WHERE owner_entity_id = ? AND rowid IN ({marks})",
        (sqlite_vec.serialize_float32(vector), owner_entity_id, *ids),
    )
    rows = await cursor.fetchall()
    await cursor.close()
    return {int(row[0]): float(row[1]) for row in rows}


async def lexical_hits(
    *,
    owner_entity_id: int,
    terms: Sequence[str],
    since: str | None,
    until: str | None,
    now: str,
    limit: int,
    first_day: str | None = None,
    last_day: str | None = None,
    occurred: bool = False,
) -> list[int]:
    """Return the readable units whose words match any term, best ``bm25`` first.

    Args:
        owner_entity_id: The owner whose units are searched.
        terms: Content words; each is quoted, so none is read as FTS syntax.
        since: Inclusive lower bound of ``said_at``, or ``None``.
        until: Exclusive upper bound of ``said_at``, or ``None``.
        now: The current time; expired records are skipped.
        limit: How many ids at most.
        first_day: The window's first local day (ISO), needed with ``occurred``.
        last_day: The window's last local day (ISO), needed with ``occurred``.
        occurred: Whether the window matches by the occurred interval (Plan 0083 D-9).

    Returns:
        The unit ids.
    """
    expression = match_expression(terms)
    if not expression:
        return []
    cursor = await db.get_conn().execute(
        "SELECT u.id FROM recall_units_fts f JOIN recall_units u ON u.id = f.rowid "  # noqa: S608
        "JOIN conversation_records r ON r.id = u.source_record_id "
        f"WHERE recall_units_fts MATCH :match AND {_readable(occurred=occurred)} "
        "ORDER BY bm25(recall_units_fts), u.id DESC LIMIT :limit",
        {
            "match": expression,
            "owner": owner_entity_id,
            "now": now,
            "limit": limit,
            **_window(since, until, first_day, last_day, occurred=occurred),
        },
    )
    rows = await cursor.fetchall()
    await cursor.close()
    return [int(row[0]) for row in rows]


async def vector_hits(
    *,
    owner_entity_id: int,
    vector: list[float],
    since: str | None,
    until: str | None,
    now: str,
    k: int,
    first_day: str | None = None,
    last_day: str | None = None,
    occurred: bool = False,
) -> list[tuple[int, float]]:
    """Return the nearest readable units as ``(unit_id, cosine distance)``, nearest first.

    The KNN query itself filters by owner (the partition key) and sensitivity ``normal``; the
    window and the expiry are applied to its *k* neighbours, by the occurred interval when
    *occurred* (Plan 0083 D-9; *first_day* and *last_day* as in ``lexical_hits``).
    """
    cursor = await db.get_conn().execute(
        "WITH knn AS (SELECT rowid AS id, distance FROM recall_units_vec "  # noqa: S608
        "WHERE embedding MATCH :vector AND k = :k AND owner_entity_id = :owner "
        "AND sensitivity = 'normal') "
        "SELECT u.id, knn.distance FROM knn JOIN recall_units u ON u.id = knn.id "
        "JOIN conversation_records r ON r.id = u.source_record_id "
        f"WHERE {_readable(occurred=occurred)} ORDER BY knn.distance, u.id DESC",
        {
            "vector": sqlite_vec.serialize_float32(vector),
            "k": k,
            "owner": owner_entity_id,
            "now": now,
            **_window(since, until, first_day, last_day, occurred=occurred),
        },
    )
    rows = await cursor.fetchall()
    await cursor.close()
    return [(int(row[0]), float(row[1])) for row in rows]


async def units_by_id(
    ids: Sequence[int], *, owner_entity_id: int, now: str, occurred: bool = False
) -> list[RecallUnit]:
    """Return the units still readable among *ids*, in the order given.

    The statement that returns the text applies the same filters as every other read (owner,
    visibility ``personal``, sensitivity ``normal``, the record's expiry; no window), so a unit
    reclassified, expired or deleted after its id was found is not delivered (ADR 0031 decision 2,
    Plan 0080 D-10). Residual: text already read is not recalled while the model words the answer.

    Args:
        ids: Unit ids found by a search, in ranking order.
        owner_entity_id: The owner whose units may be read.
        now: The current time; expired records are skipped.
        occurred: Whether each unit carries its occurred interval (Plan 0083).

    Returns:
        The readable units among *ids*, in the order of *ids*.
    """
    if not ids:
        return []
    marks = ", ".join(f":id{index}" for index in range(len(ids)))
    cursor = await db.get_conn().execute(
        f"SELECT {_columns(occurred=occurred)} FROM recall_units u "  # noqa: S608
        "JOIN conversation_records r ON r.id = u.source_record_id "
        f"WHERE u.id IN ({marks}) AND {_readable(occurred=occurred)}",
        {
            **{f"id{index}": unit_id for index, unit_id in enumerate(ids)},
            "owner": owner_entity_id,
            "now": now,
            **_window(None, None, None, None, occurred=occurred),
        },
    )
    rows = await cursor.fetchall()
    await cursor.close()
    found = {unit.id: unit for unit in (_unit(tuple(row), occurred=occurred) for row in rows)}
    return [found[unit_id] for unit_id in ids if unit_id in found]


async def recent_units(
    *,
    owner_entity_id: int,
    since: str,
    until: str,
    now: str,
    limit: int,
    first_day: str | None = None,
    last_day: str | None = None,
    occurred: bool = False,
) -> list[RecallUnit]:
    """Return the episodes said in the window, newest first; its turn units when it has none.

    Args:
        owner_entity_id: The owner whose units are read.
        since: Inclusive lower bound of ``said_at``.
        until: Exclusive upper bound of ``said_at``.
        now: The current time; expired records are skipped.
        limit: How many units at most.
        first_day: The window's first local day (ISO), needed with ``occurred``.
        last_day: The window's last local day (ISO), needed with ``occurred``.
        occurred: Whether the window matches by the occurred interval and an episode follows the
            turn units of its record (Plan 0083 D-9).

    Returns:
        The readable units.
    """
    window = _window(since, until, first_day, last_day, occurred=occurred)
    for group in _RECENT_GROUPS_OCCURRED if occurred else _RECENT_GROUPS:
        units: list[RecallUnit] = []
        for kind_clause, kind in group:
            cursor = await db.get_conn().execute(
                f"SELECT {_columns(occurred=occurred)} FROM recall_units u "  # noqa: S608
                "JOIN conversation_records r ON r.id = u.source_record_id "
                f"WHERE {kind_clause} AND {_readable(occurred=occurred)} "
                "ORDER BY u.said_at DESC, u.id DESC LIMIT :limit",
                {"kind": kind, "owner": owner_entity_id, "now": now, "limit": limit, **window},
            )
            units += [_unit(tuple(row), occurred=occurred) for row in await cursor.fetchall()]
            await cursor.close()
        if units:
            return units[:limit]
    return []


_UNIT_EXPORT_COLUMNS = (
    "id",
    "owner_entity_id",
    "source_record_id",
    "turn_id",
    "kind",
    "body",
    "sensitivity",
    "said_at",
    # The occurred interval leaves under its own keys: only this module names its columns.
    "occurred_from",
    "occurred_to",
    "archived_at",
)


async def units_for_export() -> StoredRows:
    """Every recall unit, archived ones included; never a vector, for an export (Plan 0087 D-5)."""
    return await fetch_stored_rows(
        _UNIT_EXPORT_COLUMNS,
        "SELECT id, owner_entity_id, source_record_id, turn_id, kind, body, sensitivity, said_at, "
        "occurred_start, occurred_end, archived_at FROM recall_units ORDER BY id",
    )


async def projection_counts() -> tuple[int, int]:
    """How many full-text rows and vectors the units project, for an export (Plan 0087 D-5).

    Returns:
        The rows of ``recall_units_fts`` and of ``recall_units_vec``.
    """
    return (
        await fetch_count("SELECT count(*) FROM recall_units_fts"),
        await fetch_count("SELECT count(*) FROM recall_units_vec"),
    )
