"""The document store: the only SQL on the documents' tables (Plan 0088 Task B1, D-8).

Canary rows only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from server.memory import document_store
from server.memory.declarative import upsert_entity
from server.memory.document_store import DocumentLevel, NewSection, NewSource
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_NOW = "2026-11-23T10:00:00.000000+00:00"
_DIM = 768
_BOTH: frozenset[DocumentLevel] = frozenset({"normal", "sensitive"})
_NORMAL: frozenset[DocumentLevel] = frozenset({"normal"})


@pytest.fixture
async def owners(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[int, int]]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "docs.db")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        owner = await upsert_entity(name="Canary Owner", type="person")
        other = await upsert_entity(name="Canary Other", type="person")
        yield owner, other
    finally:
        await db.close_db()
        db._conn = None


def _axis(axis: int) -> list[float]:
    values = [0.0] * _DIM
    values[axis] = 1.0
    return values


def _new(owner: int, title: str, *, level: DocumentLevel = "normal", sha: str = "a") -> NewSource:
    return NewSource(
        owner_entity_id=owner,
        title=title,
        file_sha256=sha * 64,
        format="md",
        level=level,
        channel="admin_local",
        loaded_at=_NOW,
        loaded_by_entity_id=owner,
    )


async def _load(
    owner: int, title: str, bodies: list[str], *, level: DocumentLevel = "normal", sha: str = "a"
) -> int:
    sections = [NewSection(position=i, heading="", body=b) for i, b in enumerate(bodies)]
    async with db.transaction() as conn:
        return await document_store.insert_source(
            conn, source=_new(owner, title, level=level, sha=sha), sections=sections
        )


async def _section_ids(source: int) -> list[int]:
    cursor = await db.get_conn().execute(
        "SELECT id FROM document_sections WHERE source_id = ? ORDER BY position", (source,)
    )
    rows = [int(row[0]) for row in await cursor.fetchall()]
    await cursor.close()
    return rows


async def test_insert_stores_the_counts_and_the_hashes(owners: tuple[int, int]) -> None:
    owner, _ = owners
    source = await _load(owner, "Manual canario", ["zzuno filtro", "zzdos tambor"])
    listed = await document_store.sources_of(owner_entity_id=owner)
    assert [(s.id, s.sections, s.characters) for s in listed] == [(source, 2, 24)]
    assert "Manual canario" not in repr(listed[0])


async def test_the_same_file_twice_is_refused(owners: tuple[int, int]) -> None:
    owner, _ = owners
    await _load(owner, "Manual canario", ["zzuno"])
    with pytest.raises(document_store.DocumentExistsError):
        await _load(owner, "Otro titulo", ["zzdos"])


async def test_readable_titles_follow_the_owner_and_the_levels(owners: tuple[int, int]) -> None:
    owner, other = owners
    normal = await _load(owner, "Manual canario", ["zzuno"], sha="a")
    sensitive = await _load(owner, "Guia canaria", ["zzdos"], level="sensitive", sha="b")
    await _load(other, "Ajeno canario", ["zztres"], sha="c")

    assert await document_store.readable_titles(owner_entity_id=owner, levels=_NORMAL) == [
        (normal, "Manual canario")
    ]
    both = await document_store.readable_titles(owner_entity_id=owner, levels=_BOTH)
    assert sorted(both) == sorted([(normal, "Manual canario"), (sensitive, "Guia canaria")])


async def test_word_hits_filter_by_owner_level_and_source(owners: tuple[int, int]) -> None:
    owner, other = owners
    first = await _load(owner, "Manual canario", ["zzfiltro uno", "zzotro"], sha="a")
    second = await _load(owner, "Guia canaria", ["zzfiltro dos"], level="sensitive", sha="b")
    await _load(other, "Ajeno", ["zzfiltro ajeno"], sha="c")
    (first_hit, _), (second_hit,) = await _section_ids(first), await _section_ids(second)

    async def hits(levels: frozenset[DocumentLevel], sources: list[int] | None) -> list[int]:
        return await document_store.section_lexical_hits(
            owner_entity_id=owner, terms=["zzfiltro"], levels=levels, source_ids=sources, limit=10
        )

    assert sorted(await hits(_BOTH, None)) == sorted([first_hit, second_hit])
    assert await hits(_NORMAL, None) == [first_hit]
    assert await hits(_BOTH, [second]) == [second_hit]


async def test_vector_hits_and_distances_stay_inside_the_scope(owners: tuple[int, int]) -> None:
    owner, other = owners
    first = await _load(owner, "Manual canario", ["zzuno", "zzdos"], sha="a")
    alien = await _load(other, "Ajeno", ["zzajeno"], sha="c")
    near, far = await _section_ids(first)
    (alien_section,) = await _section_ids(alien)
    assert await document_store.store_section_vector(near, _axis(0), model="m")
    assert await document_store.store_section_vector(far, _axis(1), model="m")
    assert await document_store.store_section_vector(alien_section, _axis(0), model="m")

    hits = await document_store.section_vector_hits(
        owner_entity_id=owner, vector=_axis(0), levels=_NORMAL, source_ids=[first], k=5
    )
    assert [section for section, _ in hits] == [near, far]
    distances = await document_store.section_distances_of(
        [near, far, alien_section], _axis(0), owner_entity_id=owner
    )
    assert set(distances) == {near, far}
    assert distances[near] == pytest.approx(0.0)


async def test_sections_by_id_applies_the_delivery_filter(owners: tuple[int, int]) -> None:
    owner, _ = owners
    kept = await _load(owner, "Manual canario", ["zzuno"], sha="a")
    gone = await _load(owner, "Receta canaria", ["zzdos"], sha="b")
    secret = await _load(owner, "Guia canaria", ["zztres"], level="sensitive", sha="c")
    ids = [*(await _section_ids(kept)), *(await _section_ids(gone)), *(await _section_ids(secret))]
    async with db.transaction() as conn:
        assert await document_store.delete_source_row(conn, gone) == 1

    found = await document_store.sections_by_id(ids, owner_entity_id=owner, levels=_NORMAL)

    assert [(s.source_id, s.title, s.body) for s in found] == [(kept, "Manual canario", "zzuno")]
    assert "zzuno" not in repr(found[0])


async def test_the_model_guard_and_the_refused_sections(
    owners: tuple[int, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, _ = owners
    monkeypatch.setattr(settings, "embedding_model", "model-b")
    source = await _load(owner, "Manual canario", ["zzuno", "zzdos", "zztres"])
    old, refused, pending = await _section_ids(source)
    await document_store.store_section_vector(old, _axis(0), model="model-a")
    assert await document_store.mark_section_refused(refused, model="model-b")

    assert await document_store.count_sections_of_another_model(owner) == 1
    assert [s for s, _ in await document_store.sections_without_vector(10)] == [old, pending]
    async with db.transaction() as conn:
        health = await document_store.document_index_health(conn)
    assert health.sections_refused == 1
    assert health.sections_without_vector == 1
    assert health.sections_of_another_model == 1
    assert health.vectors_without_section == 0
    assert health.sections_without_fts_row == 0
