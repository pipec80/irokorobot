"""The database health check (Plan 0085 D-11, ADR 0032 decision 1): counts only, never a value.

``check_health`` reads a database the server is not using (``iroko-admin health``, server
stopped) and counts what is wrong: SQLite's own integrity and foreign-key checks, the full-text
index, the rows that point at nothing, and the times outside the one format (ADR 0038 decision 5,
written in ``docs/architecture/data-dictionary.md``). Two further counts are pending work, not
faults: units that still wait for a vector and units whose vector another model computed (the
background re-index brings both to zero, ADR 0031 decision 8). Nothing here writes a row or
returns a text read from the database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from server import db
from server.memory.candidates import count_unlinked_candidates
from server.memory.conversation_record import STORED_TURN_CORRELATION_IDS_SQL
from server.memory.document_store import document_index_health
from server.memory.pending_store import count_unlinked_topics
from server.memory.recall_store import count_rows, count_unlinked_units, index_health
from server.timestamps import INSTANT_LENGTH

if TYPE_CHECKING:
    import aiosqlite

__all__ = ["HealthReport", "check_health", "health_failed", "render_health", "time_columns"]

# The exact instant: 32 characters, every digit position explicit, the literal ``+00:00``, and a
# real calendar moment (``strftime`` returns NULL for 02-31, so ``IS`` fails it).
_DIGITS_INSTANT: Final = (
    "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]"
    ".[0-9][0-9][0-9][0-9][0-9][0-9]+00:00"
)
_BAD_INSTANT: Final = (
    f"{{col}} IS NOT NULL AND NOT (length({{col}}) = {INSTANT_LENGTH} AND {{col}} GLOB '"
    + _DIGITS_INSTANT
    + "' "
    "AND strftime('%Y-%m-%dT%H:%M:%S', substr({col}, 1, 19)) IS substr({col}, 1, 19))"
)
# A validity bound is a day (YYYY-MM-DD) or a month (YYYY-MM), both real.
_BAD_BOUND: Final = (
    "{col} IS NOT NULL AND NOT ("
    "({col} GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' "
    "AND strftime('%Y-%m-%d', {col}) IS {col}) "
    "OR ({col} GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]' "
    "AND strftime('%Y-%m-%d', {col} || '-01') IS {col} || '-01'))"
)
# The TEXT columns of the live ordinary tables, derived from the schema (virtual tables and their
# shadow tables have none of these names), so a new `*_at` column is checked without a list.
_TIME_COLUMNS: Final = (
    "SELECT m.name, p.name FROM sqlite_master m, pragma_table_info(m.name) p "
    "WHERE m.type = 'table' AND substr(m.name, 1, 7) <> 'sqlite_' "
    "AND m.sql NOT LIKE 'CREATE VIRTUAL%' AND p.type = 'TEXT' AND {names}"
)
_INSTANT_NAMES: Final = "p.name LIKE '%!_at' ESCAPE '!'"
_BOUND_NAMES: Final = "p.name IN ('valid_from', 'valid_to')"


@dataclass(frozen=True)
class HealthReport:
    """What the health check counted: ints only, never a value read from the database.

    The first ten counts are faults; the last five are pending work (not a fault).
    """

    sqlite_version: tuple[int, int, int]
    vec_version: tuple[int, int, int]
    integrity_errors: int
    foreign_key_violations: int
    fts_errors: int
    vectors_without_unit: int
    units_without_fts_row: int
    face_vectors_without_profile: int
    times_outside_format: int
    rows_unlinked_from_their_turn: int
    document_vectors_without_section: int
    sections_without_fts_row: int
    units_without_vector: int
    units_of_another_model: int
    sections_without_vector: int
    sections_of_another_model: int
    sections_refused: int


# Every count of the report, in print order: (HealthReport field, label in Spanish, is a fault).
# The faults decide the exit code; the others are pending work. A new count touches the dataclass
# and this tuple only.
_MEASURES: Final = (
    ("integrity_errors", "errores de integridad", True),
    ("foreign_key_violations", "violaciones de claves foráneas", True),
    ("fts_errors", "errores del índice de texto", True),
    ("vectors_without_unit", "vectores sin unidad", True),
    ("units_without_fts_row", "unidades sin fila en el índice de texto", True),
    ("face_vectors_without_profile", "vectores de caras sin perfil", True),
    ("times_outside_format", "filas fuera del formato de hora", True),
    ("rows_unlinked_from_their_turn", "filas sin vínculo con su turno", True),
    ("document_vectors_without_section", "vectores de documentos sin sección", True),
    ("sections_without_fts_row", "secciones sin fila en el índice de texto", True),
    ("units_without_vector", "unidades sin vector (pendientes)", False),
    ("units_of_another_model", "unidades de otro modelo (pendientes)", False),
    ("sections_without_vector", "secciones sin vector (pendientes)", False),
    ("sections_of_another_model", "secciones de otro modelo (pendientes)", False),
    ("sections_refused", "secciones que el modelo no aceptó (solo por palabras)", False),
)


async def _rows(conn: aiosqlite.Connection, sql: str) -> list[tuple[str, ...]]:
    """Run a statement and return its rows as tuples of text."""
    cursor = await conn.execute(sql)
    rows = [tuple(str(value) for value in row) for row in await cursor.fetchall()]
    await cursor.close()
    return rows


async def _integrity_errors(conn: aiosqlite.Connection) -> int:
    """``PRAGMA integrity_check``: 0 when it answers ``ok``, else the number of problems."""
    rows = await _rows(conn, "PRAGMA integrity_check")
    return 0 if rows == [("ok",)] else len(rows)


async def time_columns(
    conn: aiosqlite.Connection, *, bounds: bool = False
) -> list[tuple[str, str]]:
    """Return ``(table, column)`` of every TEXT time column the schema has, derived from it.

    Args:
        conn: An open connection.
        bounds: ``False`` for the instant columns (``*_at``), ``True`` for the validity bounds.
    """
    names = _BOUND_NAMES if bounds else _INSTANT_NAMES
    rows = await _rows(conn, _TIME_COLUMNS.format(names=names) + " ORDER BY 1, p.cid")
    return [(row[0], row[1]) for row in rows]


async def _times_outside_format(conn: aiosqlite.Connection) -> int:
    """Count the non-NULL times that are not an exact instant (or a day or month, for a bound)."""
    total = 0
    for bounds, bad in ((False, _BAD_INSTANT), (True, _BAD_BOUND)):
        for table, column in await time_columns(conn, bounds=bounds):
            predicate = bad.format(col=f'"{column}"')
            total += await count_rows(conn, f'SELECT COUNT(*) FROM "{table}" WHERE {predicate}')  # noqa: S608
    return total


async def _rows_unlinked_from_their_turn(conn: aiosqlite.Connection) -> int:
    """Count the units, candidates and topics that miss the link to a turn that exists.

    Each store counts its own table; the record store names which turns are stored. A row like
    that would survive the deletion of its turn.
    """
    stored = STORED_TURN_CORRELATION_IDS_SQL
    return (
        await count_unlinked_units(conn, stored)
        + await count_unlinked_candidates(conn, stored)
        + await count_unlinked_topics(conn, stored)
    )


def _version(text: str) -> tuple[int, int, int]:
    """Read ``v0.1.9`` or ``3.50.4`` as three ints."""
    major, minor, patch = (int(part) for part in text.lstrip("v").split(".")[:3])
    return major, minor, patch


async def check_health(conn: aiosqlite.Connection) -> HealthReport:
    """Count what is wrong in the database; it changes no row and leaves no transaction open.

    Args:
        conn: An open connection with the schema at the latest version (``iroko-admin`` checks
            that first). "Another model" is the configured ``settings.embedding_model``.

    Returns:
        The counts.

    Raises:
        BrainMemoryError: If the SQLite runtime is not supported (``db.check_runtime``).
    """
    runtime = await db.check_runtime(conn)
    index = await index_health(conn)
    documents = await document_index_health(conn)
    return HealthReport(
        sqlite_version=runtime.sqlite_version,
        vec_version=_version(runtime.vec_version),
        integrity_errors=await _integrity_errors(conn),
        foreign_key_violations=len(await _rows(conn, "PRAGMA foreign_key_check")),
        fts_errors=index.fts_errors + documents.fts_errors,
        vectors_without_unit=index.vectors_without_unit,
        units_without_fts_row=index.units_without_fts_row,
        face_vectors_without_profile=await count_rows(
            conn, "SELECT COUNT(*) FROM vec_faces WHERE rowid NOT IN (SELECT id FROM face_profiles)"
        ),
        times_outside_format=await _times_outside_format(conn),
        rows_unlinked_from_their_turn=await _rows_unlinked_from_their_turn(conn),
        document_vectors_without_section=documents.vectors_without_section,
        sections_without_fts_row=documents.sections_without_fts_row,
        units_without_vector=index.units_without_vector,
        units_of_another_model=index.units_of_another_model,
        sections_without_vector=documents.sections_without_vector,
        sections_of_another_model=documents.sections_of_another_model,
        sections_refused=documents.sections_refused,
    )


def health_failed(report: HealthReport) -> bool:
    """Whether any fault was counted; pending embedding work is not a fault."""
    return any(getattr(report, name) for name, _label, is_fault in _MEASURES if is_fault)


def render_health(report: HealthReport) -> list[str]:
    """The report as lines in Spanish for the person at the terminal: names and counts only."""
    sqlite = ".".join(str(part) for part in report.sqlite_version)
    vec = ".".join(str(part) for part in report.vec_version)
    return [
        f"SQLite {sqlite}, sqlite-vec v{vec}",
        *(f"{label}: {getattr(report, name)}" for name, label, _is_fault in _MEASURES),
        "Resultado: con fallos." if health_failed(report) else "Resultado: sana.",
    ]
