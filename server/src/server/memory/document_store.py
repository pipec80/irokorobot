"""The document store: the only SQL on the documents' tables (Plan 0088 D-8, ADR 0034 decision 4).

A source is one loaded file of one owner; its sections are its text cut under the embedding
window. Every read filters by owner and level **inside the query**, and by the sources a search
scoped, before any ranking; ``sections_by_id`` applies them again where the text is returned.
Nothing here logs a title or a text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import sqlite3
from typing import TYPE_CHECKING, Final, Literal

import sqlite_vec

from server import db
from server.exceptions import BrainMemoryError
from server.memory.embeddings import EMBEDDING_DIM
from server.memory.recall_store import count_rows
from server.memory.retrieval import match_expression
from server.settings import settings

if TYPE_CHECKING:
    from collections.abc import Sequence

    import aiosqlite

__all__ = [
    "DocumentExistsError",
    "DocumentFormat",
    "DocumentIndexHealth",
    "DocumentLevel",
    "DocumentSection",
    "DocumentSource",
    "NewSection",
    "NewSource",
    "count_sections_of_another_model",
    "delete_source_row",
    "document_index_health",
    "insert_source",
    "mark_section_refused",
    "readable_titles",
    "section_distances_of",
    "section_lexical_hits",
    "section_vector_hits",
    "sections_by_id",
    "sections_without_vector",
    "sources_of",
    "store_section_vector",
]

type DocumentLevel = Literal["normal", "sensitive"]
type DocumentFormat = Literal["md", "txt", "pdf", "camera"]
# The write channel of a source: `admin_local`, `voice_camera`, or the alta's import channel, which
# only the import vocabulary names (an architecture guard); migration 023 checks the closed set.
type DocumentChannel = str

_PRIMARY_CODE_MASK: Final = 0xFF
_SOURCE_COLUMNS: Final = "id, title, format, level, loaded_at, sections, characters"
# The sections to (re-)embed, oldest first: no vector, or a vector of another model; a section the
# configured model refused as too long (D-10) is not offered to it again.
_SECTIONS_TO_EMBED_SQL: Final = (
    "SELECT id, body FROM document_sections WHERE id IN ("
    "SELECT id FROM document_sections WHERE embedding_model IS NULL "
    "UNION ALL SELECT id FROM document_sections WHERE embedding_model < ?1 "
    "UNION ALL SELECT id FROM document_sections WHERE embedding_model > ?1) "
    "AND (vector_refused_by IS NULL OR vector_refused_by <> ?1) ORDER BY id LIMIT ?2"
)


class DocumentExistsError(BrainMemoryError):
    """The owner already has a document with the same file hash."""


@dataclass(frozen=True)
class NewSource:
    """One source to insert; its ``repr`` never shows the title."""

    owner_entity_id: int
    title: str = field(repr=False)
    file_sha256: str
    format: DocumentFormat
    level: DocumentLevel
    channel: DocumentChannel
    loaded_at: str
    loaded_by_entity_id: int | None


@dataclass(frozen=True)
class NewSection:
    """One section to insert, at its position; its ``repr`` never shows the text."""

    position: int
    heading: str = field(repr=False)
    body: str = field(repr=False)


@dataclass(frozen=True)
class DocumentSource:
    """One stored source, as ``docs list`` shows it; its ``repr`` never shows the title."""

    id: int
    title: str = field(repr=False)
    format: str
    level: str
    loaded_at: str
    sections: int
    characters: int


@dataclass(frozen=True)
class DocumentSection:
    """One readable section with its source's title; its ``repr`` shows ids only."""

    id: int
    source_id: int
    position: int
    title: str = field(repr=False)
    heading: str = field(repr=False)
    body: str = field(repr=False)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _marks(prefix: str, values: Sequence[object]) -> tuple[str, dict[str, object]]:
    """Named placeholders for an ``IN (…)`` list and their parameters."""
    names = [f"{prefix}{index}" for index in range(len(values))]
    return ", ".join(f":{name}" for name in names), dict(zip(names, values, strict=True))


async def insert_source(
    conn: aiosqlite.Connection, *, source: NewSource, sections: Sequence[NewSection]
) -> int:
    """Insert a source and its sections inside the caller's transaction.

    Args:
        conn: The connection of an open write transaction.
        source: The source.
        sections: Its sections, in order.

    Returns:
        The new source id.

    Raises:
        DocumentExistsError: If the owner already has a document with the same file hash.
    """
    try:
        cursor = await conn.execute(
            "INSERT INTO document_sources (owner_entity_id, title, file_sha256, format, level, "
            "channel, loaded_at, loaded_by_entity_id, sections, characters) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                source.owner_entity_id,
                source.title,
                source.file_sha256,
                source.format,
                source.level,
                source.channel,
                source.loaded_at,
                source.loaded_by_entity_id,
                len(sections),
                sum(len(section.body) for section in sections),
            ),
        )
    except sqlite3.IntegrityError as exc:
        if "file_sha256" in str(exc):
            raise DocumentExistsError("The owner already has this document") from exc
        raise
    source_id = int(cursor.lastrowid or 0)
    await cursor.close()
    await conn.executemany(
        "INSERT INTO document_sections (source_id, position, heading, body, body_sha256) "
        "VALUES (?, ?, ?, ?, ?)",
        [(source_id, s.position, s.heading, s.body, _sha256(s.body)) for s in sections],
    )
    return source_id


async def sources_of(*, owner_entity_id: int) -> list[DocumentSource]:
    """Return the owner's sources, oldest first (``iroko-admin docs list``)."""
    cursor = await db.get_conn().execute(
        f"SELECT {_SOURCE_COLUMNS} FROM document_sources "  # noqa: S608
        "WHERE owner_entity_id = ? ORDER BY id",
        (owner_entity_id,),
    )
    rows = await cursor.fetchall()
    await cursor.close()
    return [
        DocumentSource(
            id=int(r[0]),
            title=str(r[1]),
            format=str(r[2]),
            level=str(r[3]),
            loaded_at=str(r[4]),
            sections=int(r[5]),
            characters=int(r[6]),
        )
        for r in rows
    ]


async def readable_titles(
    *, owner_entity_id: int, levels: frozenset[DocumentLevel]
) -> list[tuple[int, str]]:
    """Return ``(source id, title)`` of the owner's sources at *levels* (the title step, D-12)."""
    if not levels:
        return []
    level_marks, level_params = _marks("level", sorted(levels))
    cursor = await db.get_conn().execute(
        "SELECT id, title FROM document_sources "  # noqa: S608
        f"WHERE owner_entity_id = :owner AND level IN ({level_marks}) ORDER BY id",
        {"owner": owner_entity_id, **level_params},
    )
    rows = await cursor.fetchall()
    await cursor.close()
    return [(int(row[0]), str(row[1])) for row in rows]


def _scope(
    levels: frozenset[DocumentLevel], source_ids: Sequence[int] | None, *, level: str, source: str
) -> tuple[str, dict[str, object]]:
    """The level and source filter of a read, on the columns *level* and *source*."""
    level_marks, params = _marks("level", sorted(levels))
    clause = f"{level} IN ({level_marks})"
    if source_ids is not None:
        source_marks, source_params = _marks("source", list(source_ids))
        clause += f" AND {source} IN ({source_marks})"
        params |= source_params
    return clause, params


async def section_lexical_hits(
    *,
    owner_entity_id: int,
    terms: Sequence[str],
    levels: frozenset[DocumentLevel],
    source_ids: Sequence[int] | None,
    limit: int,
) -> list[int]:
    """Return the readable sections whose words match any term, best ``bm25`` first.

    Args:
        owner_entity_id: The owner whose sections are searched.
        terms: Content words; each is quoted, so none is read as FTS syntax.
        levels: The levels the reader may hear.
        source_ids: The scope of the title step, or ``None`` for every readable source.
        limit: How many ids at most.

    Returns:
        The section ids.
    """
    expression = match_expression(terms)
    if not expression or not levels or source_ids == []:
        return []
    scope, params = _scope(levels, source_ids, level="s.level", source="c.source_id")
    cursor = await db.get_conn().execute(
        "SELECT c.id FROM document_sections_fts f "  # noqa: S608
        "JOIN document_sections c ON c.id = f.rowid "
        "JOIN document_sources s ON s.id = c.source_id "
        f"WHERE document_sections_fts MATCH :match AND s.owner_entity_id = :owner AND {scope} "
        "ORDER BY bm25(document_sections_fts), c.id LIMIT :limit",
        {"match": expression, "owner": owner_entity_id, "limit": limit, **params},
    )
    rows = await cursor.fetchall()
    await cursor.close()
    return [int(row[0]) for row in rows]


async def section_vector_hits(
    *,
    owner_entity_id: int,
    vector: list[float],
    levels: frozenset[DocumentLevel],
    source_ids: Sequence[int] | None,
    k: int,
) -> list[tuple[int, float]]:
    """Return the nearest readable sections as ``(section id, cosine distance)``, nearest first.

    The KNN query itself filters by owner (the partition key), level and source.
    """
    if not levels or source_ids == []:
        return []
    scope, params = _scope(levels, source_ids, level="level", source="source_id")
    cursor = await db.get_conn().execute(
        "WITH knn AS (SELECT rowid AS id, distance FROM document_sections_vec "  # noqa: S608
        f"WHERE embedding MATCH :vector AND k = :k AND owner_entity_id = :owner AND {scope}) "
        "SELECT c.id, knn.distance FROM knn JOIN document_sections c ON c.id = knn.id "
        "ORDER BY knn.distance, c.id",
        {
            "vector": sqlite_vec.serialize_float32(vector),
            "k": k,
            "owner": owner_entity_id,
            **params,
        },
    )
    rows = await cursor.fetchall()
    await cursor.close()
    return [(int(row[0]), float(row[1])) for row in rows]


async def section_distances_of(
    ids: Sequence[int], vector: list[float], *, owner_entity_id: int
) -> dict[int, float]:
    """Return the cosine distance of each named section's vector (Plan 0088 D-5).

    Returns:
        ``{section id: distance}``; a section without a vector, or another owner's, is absent.
    """
    if not ids:
        return {}
    marks = ", ".join("?" for _ in ids)
    cursor = await db.get_conn().execute(
        "SELECT rowid, vec_distance_cosine(embedding, ?) FROM document_sections_vec "  # noqa: S608
        f"WHERE owner_entity_id = ? AND rowid IN ({marks})",
        (sqlite_vec.serialize_float32(vector), owner_entity_id, *ids),
    )
    rows = await cursor.fetchall()
    await cursor.close()
    return {int(row[0]): float(row[1]) for row in rows}


async def sections_by_id(
    ids: Sequence[int], *, owner_entity_id: int, levels: frozenset[DocumentLevel]
) -> list[DocumentSection]:
    """Return the sections still readable among *ids*, in the order given.

    The statement that returns the text applies the owner and level filters again, so a section
    whose source was removed after its id was found is not delivered (ADR 0031 decision 2).
    """
    if not ids or not levels:
        return []
    id_marks, id_params = _marks("id", list(ids))
    level_marks, level_params = _marks("level", sorted(levels))
    cursor = await db.get_conn().execute(
        "SELECT c.id, c.source_id, c.position, s.title, c.heading, c.body "  # noqa: S608
        "FROM document_sections c JOIN document_sources s ON s.id = c.source_id "
        f"WHERE c.id IN ({id_marks}) AND s.owner_entity_id = :owner "
        f"AND s.level IN ({level_marks})",
        {"owner": owner_entity_id, **id_params, **level_params},
    )
    rows = await cursor.fetchall()
    await cursor.close()
    found = {
        int(r[0]): DocumentSection(
            id=int(r[0]),
            source_id=int(r[1]),
            position=int(r[2]),
            title=str(r[3]),
            heading=str(r[4]),
            body=str(r[5]),
        )
        for r in rows
    }
    return [found[section_id] for section_id in ids if section_id in found]


async def delete_source_row(conn: aiosqlite.Connection, source_id: int) -> int:
    """Delete one source; its sections, word rows and vectors go with it (CASCADE, triggers).

    Returns:
        How many sources were deleted (0 when it was already gone).
    """
    cursor = await conn.execute("DELETE FROM document_sources WHERE id = ?", (source_id,))
    deleted = max(cursor.rowcount, 0)
    await cursor.close()
    return deleted


async def store_section_vector(section_id: int, vector: list[float], *, model: str) -> bool:
    """Index a section's vector with its owner, level and source, in one transaction.

    Returns:
        ``False`` when the section is gone; ``True`` otherwise (an old vector is replaced).

    Raises:
        ValueError: If the vector has the wrong size.
    """
    if len(vector) != EMBEDDING_DIM:
        raise ValueError("a document vector has the wrong size")
    async with db.transaction() as conn:
        cursor = await conn.execute(
            "SELECT s.owner_entity_id, s.level, s.id FROM document_sections c "
            "JOIN document_sources s ON s.id = c.source_id WHERE c.id = ?",
            (section_id,),
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row is None:
            return False
        await conn.execute("DELETE FROM document_sections_vec WHERE rowid = ?", (section_id,))
        await conn.execute(
            "INSERT INTO document_sections_vec (rowid, owner_entity_id, level, source_id, "
            "embedding) VALUES (?, ?, ?, ?, ?)",
            (
                section_id,
                int(row[0]),
                str(row[1]),
                int(row[2]),
                sqlite_vec.serialize_float32(vector),
            ),
        )
        await conn.execute(
            "UPDATE document_sections SET embedding_model = ?, vector_refused_by = NULL "
            "WHERE id = ?",
            (model, section_id),
        )
    return True


async def mark_section_refused(section_id: int, *, model: str) -> bool:
    """Record that *model* refused a section as too long (D-10); it stays searchable by words.

    Returns:
        ``False`` when the section is gone.
    """
    async with db.transaction() as conn:
        cursor = await conn.execute(
            "UPDATE document_sections SET vector_refused_by = ? WHERE id = ?", (model, section_id)
        )
        changed = cursor.rowcount > 0
        await cursor.close()
    return changed


async def sections_without_vector(limit: int) -> list[tuple[int, str]]:
    """Return ``(id, body)`` of the oldest sections to (re-)embed with the configured model."""
    cursor = await db.get_conn().execute(_SECTIONS_TO_EMBED_SQL, (settings.embedding_model, limit))
    rows = await cursor.fetchall()
    await cursor.close()
    return [(int(row[0]), str(row[1])) for row in rows]


async def count_sections_of_another_model(owner_entity_id: int) -> int:
    """Count the owner's sections whose vector another model computed (the model guard).

    While it is above zero a vector search would compare two embedding spaces, so the document
    search goes by words only (ADR 0031 decision 8), as recall does.
    """
    return await count_rows(
        db.get_conn(),
        "SELECT COUNT(*) FROM document_sections c JOIN document_sources s ON s.id = c.source_id "
        "WHERE s.owner_entity_id = ? AND c.embedding_model IS NOT NULL "
        "AND c.embedding_model <> ?",
        (owner_entity_id, settings.embedding_model),
    )


@dataclass(frozen=True)
class DocumentIndexHealth:
    """Counts about the documents' word index and vectors: ints only, no value."""

    fts_errors: int
    vectors_without_section: int
    sections_without_fts_row: int
    sections_without_vector: int
    sections_of_another_model: int
    sections_refused: int


async def _fts_errors(conn: aiosqlite.Connection) -> int:
    """FTS5 ``integrity-check`` of the section index: 0 or 1 (as ``recall_store``)."""
    try:
        await conn.execute(
            "INSERT INTO document_sections_fts (document_sections_fts, rank) "
            "VALUES ('integrity-check', 1)"
        )
    except sqlite3.DatabaseError as exc:
        if exc.sqlite_errorcode & _PRIMARY_CODE_MASK != sqlite3.SQLITE_CORRUPT:
            raise BrainMemoryError("The document text index check could not run") from exc
        return 1
    finally:
        await conn.rollback()
    return 0


async def document_index_health(conn: aiosqlite.Connection) -> DocumentIndexHealth:
    """Count what is wrong, or still pending, in the document index (``iroko-admin health``)."""
    return DocumentIndexHealth(
        fts_errors=await _fts_errors(conn),
        vectors_without_section=await count_rows(
            conn,
            "SELECT COUNT(*) FROM document_sections_vec "
            "WHERE rowid NOT IN (SELECT id FROM document_sections)",
        ),
        sections_without_fts_row=await count_rows(
            conn,
            "SELECT COUNT(*) FROM document_sections "
            "WHERE id NOT IN (SELECT id FROM document_sections_fts_docsize)",
        ),
        sections_without_vector=await count_rows(
            conn,
            "SELECT COUNT(*) FROM document_sections WHERE vector_refused_by IS NULL "
            "AND id NOT IN (SELECT rowid FROM document_sections_vec)",
        ),
        sections_of_another_model=await count_rows(
            conn,
            "SELECT COUNT(*) FROM document_sections "
            "WHERE embedding_model IS NOT NULL AND embedding_model <> ?",
            (settings.embedding_model,),
        ),
        sections_refused=await count_rows(
            conn, "SELECT COUNT(*) FROM document_sections WHERE vector_refused_by IS NOT NULL"
        ),
    )
