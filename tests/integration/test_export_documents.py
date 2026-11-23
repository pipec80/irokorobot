"""The owner's documents in an export (Plan 0088 Task B4, D-19, ADR 0032 decision 8).

``export all`` and the owner's own export hold every document (title, level, format, loaded at)
and every section's text, with the same rows in Markdown and JSON and never a vector; another
person's export holds none. Canary rows only.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from server.memory import document_store
from server.memory.data_export import gather_export
from server.memory.declarative import upsert_entity
from server.memory.document_store import NewSection, NewSource
from server.memory.export_files import render_json, render_markdown
from server.memory.export_model import ExportDocument, ExportScope, ExportScopeKind
from server.settings import settings

from server import db
from tests.unit.test_export_files import _as_text, _markdown_tables

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_NOW = "2026-11-23T12:00:00.000000+00:00"
_VECTOR = [0.25] * 768


@pytest.fixture
async def people(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[int, int]]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "export.db")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        owner = await upsert_entity(name="Canario", type="person")
        other = await upsert_entity(name="Canaria Otra", type="person")
        source = NewSource(
            owner_entity_id=owner,
            title="Manual zzcanario",
            file_sha256="c" * 64,
            format="md",
            level="sensitive",
            channel="admin_local",
            loaded_at=_NOW,
            loaded_by_entity_id=owner,
        )
        sections = [
            NewSection(0, "Filtro", "zzfiltro | a la izquierda"),
            NewSection(1, "", "zztambor"),
        ]
        async with db.transaction() as conn:
            source_id = await document_store.insert_source(conn, source=source, sections=sections)
        cursor = await db.get_conn().execute(
            "SELECT id FROM document_sections WHERE source_id = ? ORDER BY position", (source_id,)
        )
        row = await cursor.fetchone()
        await cursor.close()
        assert row is not None
        first = int(row[0])
        assert await document_store.store_section_vector(first, _VECTOR, model="m")
        yield owner, other
    finally:
        await db.close_db()
        db._conn = None


def _rows(document: ExportDocument, key: str) -> list[tuple[object, ...]]:
    return next(list(s.rows) for s in document.sections if s.key == key)


async def test_all_holds_the_documents_and_their_sections(people: tuple[int, int]) -> None:
    owner, _ = people

    document = await gather_export(
        ExportScope(ExportScopeKind.ALL), owner_entity_id=owner, now=_NOW
    )

    (source,) = _rows(document, "documentos")
    assert "Manual zzcanario" in source
    assert "sensitive" in source
    bodies = list(_rows(document, "secciones_documentos"))
    assert [b for row in bodies for b in row if isinstance(b, str) and b.startswith("zz")] == [
        "zzfiltro | a la izquierda",
        "zztambor",
    ]


async def test_markdown_and_json_hold_the_same_rows_and_no_vector(people: tuple[int, int]) -> None:
    owner, _ = people
    document = await gather_export(
        ExportScope(ExportScopeKind.ALL), owner_entity_id=owner, now=_NOW
    )

    parsed = json.loads(render_json(document))
    markdown = _markdown_tables(render_markdown(document))
    for key in ("documentos", "secciones_documentos"):
        section = next(s for s in parsed["sections"] if s["key"] == key)
        keys = [column["key"] for column in section["columns"]]
        as_json = [[_as_text(row[key]) for key in keys] for row in section["rows"]]
        assert markdown[section["title"]] == as_json
    assert "0.25" not in render_json(document)
    no_sale = next(s for s in parsed["sections"] if s["key"] == "no_sale")
    assert any("documentos" in str(row["what"]) for row in no_sale["rows"])


async def test_the_owner_export_holds_them_and_another_person_s_does_not(
    people: tuple[int, int],
) -> None:
    owner, other = people

    mine = await gather_export(
        ExportScope(ExportScopeKind.PERSON, entity_id=owner), owner_entity_id=owner, now=_NOW
    )
    theirs = await gather_export(
        ExportScope(ExportScopeKind.PERSON, entity_id=other), owner_entity_id=owner, now=_NOW
    )

    assert len(_rows(mine, "documentos")) == 1
    assert len(_rows(mine, "secciones_documentos")) == 2
    assert _rows(theirs, "documentos") == []
    assert _rows(theirs, "secciones_documentos") == []
