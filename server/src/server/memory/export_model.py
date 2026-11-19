"""The content of an export, before it is written (Plan 0087 D-4, ADR 0032 decision 8).

Each table's owner module reads its rows for an export with its own SQL and returns them as
``StoredRows``: the column keys and one tuple of cells per row, ordered by id. A cell is text, an
integer or nothing; a vector, an embedding or a salt is bytes and can never become a cell, so
``fetch_stored_rows`` refuses one outright. This module holds no SQL of its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from server.db import get_conn

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

__all__ = [
    "Cell",
    "ExportColumn",
    "ExportDocument",
    "ExportScope",
    "ExportScopeKind",
    "ExportSection",
    "StoredRows",
    "fetch_count",
    "fetch_stored_rows",
    "stored_rows",
]

type Cell = str | int | None


class ExportScopeKind(StrEnum):
    """What one export holds: everything, or everything about one person (D-1)."""

    ALL = "all"
    PERSON = "person"


@dataclass(frozen=True)
class ExportScope:
    """The scope of one export; its ``repr`` never shows the words that name a person.

    Attributes:
        kind: ``all`` or ``person``.
        entity_id: The person's entity (an id of ``iroko-admin list``), or ``None``.
        words: The name of a person only talked about, or ``None``.
    """

    kind: ExportScopeKind
    entity_id: int | None = None
    words: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class ExportColumn:
    """One column of a section: its key (English, as stored) and its Spanish label."""

    key: str
    label: str


@dataclass(frozen=True)
class ExportSection:
    """One section of an export: a key, a Spanish title, its columns and its rows."""

    key: str
    title: str
    columns: tuple[ExportColumn, ...]
    rows: tuple[tuple[Cell, ...], ...]


@dataclass(frozen=True)
class ExportDocument:
    """One export, the one model both files are rendered from (D-4)."""

    scope: ExportScope
    generated_at: str
    schema_version: int
    sections: tuple[ExportSection, ...]


@dataclass(frozen=True)
class StoredRows:
    """The rows of one table as read for an export.

    Attributes:
        columns: The column keys (English, the stored names), in the order of each row.
        rows: One tuple of cells per row, ordered by id.
    """

    columns: tuple[str, ...]
    rows: tuple[tuple[Cell, ...], ...]


def _cell(value: object) -> Cell:
    """Return *value* as a cell, or raise for anything that is not text, an integer or nothing."""
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise TypeError(f"an export cell is text, an integer or nothing, not {type(value).__name__}")


def stored_rows(columns: Sequence[str], fetched: Iterable[Sequence[object]]) -> StoredRows:
    """Build ``StoredRows`` from fetched rows, refusing a value that is not a cell.

    Args:
        columns: The column keys, in the order of each fetched row.
        fetched: The rows as SQLite returned them.

    Returns:
        The rows, one tuple of cells each.

    Raises:
        TypeError: For bytes (a vector, a salt) or a float in a row.
        ValueError: For a row whose width is not the number of columns.
    """
    keys = tuple(columns)
    rows: list[tuple[Cell, ...]] = []
    for row in fetched:
        if len(row) != len(keys):
            raise ValueError("an export row must have one cell per column")
        rows.append(tuple(_cell(value) for value in row))
    return StoredRows(columns=keys, rows=tuple(rows))


async def fetch_stored_rows(columns: Sequence[str], sql: str, *params: object) -> StoredRows:
    """Run an owner module's ``SELECT`` of *columns* and return its rows as ``StoredRows``.

    Args:
        columns: The column keys the statement selects, in order.
        sql: The owner module's statement.
        *params: Its parameters.

    Returns:
        The rows, one tuple of cells each.
    """
    cursor = await get_conn().execute(sql, params)
    fetched = await cursor.fetchall()
    await cursor.close()
    return stored_rows(columns, (tuple(row) for row in fetched))


async def fetch_count(sql: str) -> int:
    """Run an owner module's ``SELECT count(*)`` and return the number.

    Args:
        sql: The owner module's statement.

    Returns:
        The count, 0 when the statement returns no row.
    """
    cursor = await get_conn().execute(sql)
    row = await cursor.fetchone()
    await cursor.close()
    return 0 if row is None else int(row[0])
