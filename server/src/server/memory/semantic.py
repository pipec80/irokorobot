"""Semantic memory store and vector search via sqlite-vec.

Each memory has a parallel row in the ``vec_memories`` virtual table
(``rowid == memories.id``). Search uses sqlite-vec's KNN operator
``MATCH + k`` which internally runs a brute-force scan on the float[768]
column — fast enough for the expected row counts (<100K).
"""

from __future__ import annotations

import json
import logging
import struct
from typing import Any

from server.db import get_conn
from server.memory.embeddings import embed
from server.memory.outbox import write_outbox
from server.schemas import MemoryHit
from server.settings import settings

logger = logging.getLogger(__name__)


def _pack(vec: list[float]) -> bytes:
    """Pack floats to IEEE-754 bytes for sqlite-vec ``float[N]`` column.

    Args:
        vec: Float list to pack.

    Returns:
        Packed bytes.
    """
    return struct.pack(f"{len(vec)}f", *vec)


async def store_memory(
    *,
    kind: str,
    content: str,
    summary: str | None = None,
    importance: float = 0.5,
    metadata: dict[str, Any] | None = None,
    related_entities: list[int] | None = None,
) -> int:
    """Persist a memory and its embedding vector.

    The text embedded is *summary* when provided, otherwise *content*.
    Both the ``memories`` row and the ``vec_memories`` row are inserted
    atomically before the commit.

    Args:
        kind: Memory kind — ``"episodic"``, ``"semantic"``, or ``"reflection"``.
        content: Full content of the memory (stored verbatim).
        summary: Short summary used for embedding (optional).
        importance: Importance score in ``[0, 1]``.
        metadata: Arbitrary JSON-serializable metadata.
        related_entities: List of entity row ids linked to this memory.

    Returns:
        Row id of the newly inserted memory.

    Raises:
        BrainMemoryError: If embedding fails or the DB write fails.
    """
    conn = get_conn()
    vec = await embed(summary or content)

    cur = await conn.execute(
        "INSERT INTO memories "
        "(kind, content, summary, metadata, importance, related_entities) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            kind,
            content,
            summary,
            json.dumps(metadata or {}),
            importance,
            json.dumps(related_entities or []),
        ),
    )
    if cur.lastrowid is None:
        raise RuntimeError("INSERT into memories returned no lastrowid")
    memory_id: int = cur.lastrowid
    await cur.close()

    await conn.execute(
        "INSERT INTO vec_memories (rowid, embedding) VALUES (?, ?)",
        (memory_id, _pack(vec)),
    )
    await conn.commit()
    await write_outbox(
        "memory",
        memory_id,
        "insert",
        {
            "kind": kind,
            "summary": summary,
            "importance": importance,
        },
    )
    logger.debug("Memory stored: kind=%s id=%d importance=%.2f", kind, memory_id, importance)
    return memory_id


async def search_memories(
    query: str,
    *,
    top_k: int | None = None,
    kind: str | None = None,
) -> list[MemoryHit]:
    """KNN vector search over stored memories.

    Embeds *query* then runs sqlite-vec's ``MATCH + k`` operator. Results
    are ordered by distance ascending (most similar first). Accessing
    memories updates ``last_accessed_at`` and ``access_count``.

    Args:
        query: Free-text query to embed and search against.
        top_k: Number of results to return. Defaults to
            ``settings.semantic_top_k``.
        kind: Optional filter — ``"episodic"``, ``"semantic"``, or
            ``"reflection"``.

    Returns:
        List of ``MemoryHit`` ordered by similarity.

    Raises:
        BrainMemoryError: If embedding fails.
    """
    k = top_k or settings.semantic_top_k
    qvec = await embed(query)
    conn = get_conn()

    sql = (
        "SELECT m.id, m.kind, m.content, m.summary, m.importance, v.distance "
        "FROM vec_memories AS v "
        "JOIN memories AS m ON m.id = v.rowid "
        "WHERE v.embedding MATCH ? AND k = ? "
        "AND m.archived_at IS NULL"
    )
    # The archived_at filter runs AFTER the KNN selects its k neighbours, so
    # archived rows would shrink the result set. Over-fetch and trim below.
    params: list[Any] = [_pack(qvec), k * 2]
    if kind is not None:
        sql += " AND m.kind = ?"
        params.append(kind)
    sql += " ORDER BY v.distance"

    cur = await conn.execute(sql, params)
    rows = await cur.fetchall()
    await cur.close()

    hits = [
        MemoryHit(
            id=r[0],
            kind=r[1],
            content=r[2],
            summary=r[3],
            importance=r[4],
            distance=r[5],
        )
        for r in rows
    ][:k]

    if hits:
        placeholders = ",".join("?" * len(hits))
        await conn.execute(
            "UPDATE memories "  # nosec B608  # noqa: S608 — ? placeholders only
            "SET last_accessed_at = datetime('now'), access_count = access_count + 1 "
            f"WHERE id IN ({placeholders})",
            tuple(h.id for h in hits),
        )
        await conn.commit()

    logger.info("Memory search: query=%r top_k=%d hits=%d", query[:40], k, len(hits))
    return hits
