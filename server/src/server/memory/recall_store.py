"""The recall store: the only SQL on ``recall_units`` and its indexes (ADR 0028, Plan 0078).

A unit is the owner's words of one ``VERIFIED`` turn or the diary summary of a conversation. Every
read here filters by owner, visibility ``personal``, sensitivity ``normal``, the record's expiry
and the optional window **inside the query**, before any ranking. Times are UTC ISO 8601 strings
with microseconds, comparable as text. Nothing here logs a text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Final, Literal

import sqlite_vec

from server import db
from server.cognition.intent_resolution import resolve_information_need
from server.cognition.response_plan import InformationNeed
from server.cognition.spoken_dates import DayWindow
from server.memory.conversation_types import TurnVerdict
from server.memory.embeddings import EMBEDDING_DIM
from server.memory.recall_sensitivity import (
    RecallSensitivity,
    classify_turn_text,
    most_protective,
)
from server.settings import settings

if TYPE_CHECKING:
    from collections.abc import Sequence

    import aiosqlite

    from server.memory.conversation_types import RecordedTurn

__all__ = [
    "RecallUnit",
    "insert_episode_unit",
    "insert_turn_unit",
    "lexical_hits",
    "occurred_time_on",
    "raise_record_sensitivity",
    "recent_units",
    "store_vector",
    "tells_something",
    "units_by_id",
    "units_without_vector",
    "vector_hits",
]

type UnitKind = Literal["turn", "episode"]

# The filters every read applies to a unit `u` joined to its record `r`.
_READABLE = (
    "u.owner_entity_id = :owner AND u.visibility = 'personal' AND u.sensitivity = 'normal' "
    "AND (r.expires_at IS NULL OR r.expires_at > :now) "
    "AND (:since IS NULL OR u.said_at >= :since) AND (:until IS NULL OR u.said_at < :until)"
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
    "AND (r.expires_at IS NULL OR r.expires_at > :now) "
    f"AND (:since IS NULL OR ({_IN_WINDOW.format(t='u')} AND NOT (u.kind = 'episode' "
    f"AND EXISTS ({_RECORD_TURNS}t.occurred_start IS NOT NULL) "
    f"AND NOT EXISTS ({_RECORD_TURNS}{_IN_WINDOW.format(t='t')}))))"
)
_UNIT_COLUMNS_OCCURRED = f"{_UNIT_COLUMNS}, u.occurred_start, u.occurred_end"
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
    tells nothing too; with memory on, a stated or asked secret value tells nothing (Plan 0079).

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
    occurred: DayWindow | None = None,
) -> int:
    start, end = (None, None) if occurred is None else (occurred.start, occurred.end)
    cursor = await conn.execute(
        "INSERT INTO recall_units (owner_entity_id, source_record_id, episode_id, kind, body, "
        "said_at, visibility, sensitivity, correlation_id, occurred_start, occurred_end) "
        "VALUES (?, ?, ?, ?, ?, ?, 'personal', ?, ?, ?, ?)",
        (
            owner_entity_id,
            record_id,
            episode_id,
            kind,
            body,
            said_at,
            sensitivity,
            correlation_id,
            None if start is None else start.isoformat(),
            None if end is None else end.isoformat(),
        ),
    )
    unit_id = int(cursor.lastrowid or 0)
    await cursor.close()
    return unit_id


async def insert_turn_unit(
    conn: aiosqlite.Connection,
    *,
    record_id: int,
    owner_entity_id: int,
    turn: RecordedTurn,
    occurred: DayWindow | None = None,
) -> int:
    """Write the unit of one verified turn, inside the caller's open transaction.

    Args:
        conn: The connection of an open ``db.transaction()``.
        record_id: The record the turn was appended to.
        owner_entity_id: The owner of the record.
        turn: The exchange; only its ``heard`` text becomes the unit, never ``said``.
        occurred: When the told event happened, as local days (Plan 0083), or ``None``.

    Returns:
        The new unit's id.

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
        said_at=_iso(turn.at),
        sensitivity=classify_turn_text(turn.heard),
        correlation_id=str(turn.correlation_id),
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
        The new unit's id.
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
    """Return ``(id, body)`` of the oldest units that have no vector yet."""
    cursor = await db.get_conn().execute(
        "SELECT id, body FROM recall_units WHERE embedding_model IS NULL ORDER BY id LIMIT ?",
        (limit,),
    )
    rows = await cursor.fetchall()
    await cursor.close()
    return [(int(row[0]), str(row[1])) for row in rows]


def _match_expression(terms: Sequence[str]) -> str:
    """Quote each term as an FTS5 string, so no input is FTS syntax, and join with ``OR``."""
    quoted = ['"' + term.replace('"', '""') + '"' for term in terms if term.strip()]
    return " OR ".join(quoted)


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
    expression = _match_expression(terms)
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
    for kind in ("episode", "turn"):
        cursor = await db.get_conn().execute(
            f"SELECT {_columns(occurred=occurred)} FROM recall_units u "  # noqa: S608
            "JOIN conversation_records r ON r.id = u.source_record_id "
            f"WHERE u.kind = :kind AND {_readable(occurred=occurred)} "
            "ORDER BY u.said_at DESC, u.id DESC LIMIT :limit",
            {"kind": kind, "owner": owner_entity_id, "now": now, "limit": limit, **window},
        )
        rows = list(await cursor.fetchall())
        await cursor.close()
        if rows:
            return [_unit(tuple(row), occurred=occurred) for row in rows]
    return []


def _iso(moment: datetime) -> str:
    """A fixed-width UTC ISO 8601 string, so strings sort like instants."""
    return moment.astimezone(UTC).isoformat(timespec="microseconds")
