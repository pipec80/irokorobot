"""The title step, then the section search (Plan 0088 Task B6, D-12, Review focus 3).

Ollama is a double that embeds every question on one axis; each section's stored vector sets its
distance to the question, so the gate is tested with fixed distances. Canary rows only.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import math
from typing import TYPE_CHECKING

import httpx
import pytest
from server.cognition.document_cues import DocumentCue, classify_document_cue
from server.cognition.recall_cues import CueStrength
from server.memory import document_store
from server.memory.declarative import upsert_entity
from server.memory.document_search import search_documents
from server.memory.document_store import DocumentLevel, NewSection, NewSource
from server.memory.retrieval import gate_near_or_named
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
    from pathlib import Path

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 11, 23, 12, tzinfo=UTC)
_NOW_ISO = "2026-11-23T12:00:00.000000+00:00"
_DIM = 768
_BOTH: frozenset[DocumentLevel] = frozenset({"normal", "sensitive"})
_NORMAL: frozenset[DocumentLevel] = frozenset({"normal"})
_GATE = gate_near_or_named(vector=0.30, words=0.40)


def _at(distance: float) -> list[float]:
    """A unit vector at cosine *distance* from the first axis."""
    angle = math.acos(1.0 - distance)
    values = [0.0] * _DIM
    values[0], values[1] = math.cos(angle), math.sin(angle)
    return values


def _client(up: bool = True) -> httpx.AsyncClient:
    def handler(_request: httpx.Request) -> httpx.Response:
        if not up:
            raise httpx.ConnectError("down")
        return httpx.Response(200, json={"embeddings": [_at(0.0)], "prompt_eval_count": 3})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture
async def owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "search.db")
    monkeypatch.setattr(settings, "embedding_model", "canary-embed")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        yield await upsert_entity(name="Canary Owner", type="person")
    finally:
        await db.close_db()
        db._conn = None


async def _document(
    owner: int,
    title: str,
    bodies: list[tuple[str, float | None]],
    *,
    level: DocumentLevel = "normal",
) -> list[int]:
    source = NewSource(
        owner_entity_id=owner,
        title=title,
        file_sha256=hashlib.sha256(title.encode()).hexdigest(),
        format="md",
        level=level,
        channel="admin_local",
        loaded_at=_NOW_ISO,
        loaded_by_entity_id=owner,
    )
    sections = [NewSection(i, "", body) for i, (body, _) in enumerate(bodies)]
    async with db.transaction() as conn:
        source_id = await document_store.insert_source(conn, source=source, sections=sections)
    cursor = await db.get_conn().execute(
        "SELECT id FROM document_sections WHERE source_id = ? ORDER BY position", (source_id,)
    )
    ids = [int(row[0]) for row in await cursor.fetchall()]
    await cursor.close()
    for section_id, (_, distance) in zip(ids, bodies, strict=True):
        if distance is not None:
            assert await document_store.store_section_vector(
                section_id, _at(distance), model="canary-embed"
            )
    return ids


def _cue(message: str) -> DocumentCue:
    cue = classify_document_cue(message)
    assert cue is not None
    return cue


async def _search(
    owner: int,
    message: str,
    *,
    levels: frozenset[DocumentLevel] = _BOTH,
    up: bool = True,
    title_step: bool = True,
    client: Callable[[bool], httpx.AsyncClient] = _client,
) -> document_store.DocumentSearch:
    async with client(up) as http:
        return await search_documents(
            owner,
            _cue(message),
            levels=levels,
            client=http,
            now=_NOW,
            gate=_GATE,
            title_step=title_step,
        )


async def test_the_title_step_picks_the_named_document(owner: int) -> None:
    (manual,) = await _document(owner, "Manual de la lavadora", [("zzfiltro: gírelo", 0.10)])
    await _document(owner, "Receta del pan", [("zzfiltro de la harina", 0.10)])

    found = await _search(owner, "¿Qué dice el manual de la lavadora sobre el zzfiltro?")

    assert found.scope_found
    assert [hit.section.id for hit in found.hits] == [manual]


async def test_without_the_title_step_both_documents_are_searched(owner: int) -> None:
    await _document(owner, "Manual de la lavadora", [("zzfiltro: gírelo", 0.10)])
    await _document(owner, "Receta del pan", [("zzfiltro de la harina", 0.10)])

    found = await _search(
        owner, "¿Qué dice el manual de la lavadora sobre el zzfiltro?", title_step=False
    )

    assert len(found.hits) == 2


async def test_a_named_document_with_no_title_match_finds_no_scope(owner: int) -> None:
    await _document(owner, "Manual de la lavadora", [("zzmetro", 0.10)])

    found = await _search(owner, "¿Qué dice la guía de Santiago sobre el zzmetro?")

    assert not found.scope_found
    assert found.hits == ()


async def test_a_cue_naming_none_searches_every_readable_source(owner: int) -> None:
    (manual,) = await _document(owner, "Manual de la lavadora", [("zzgarantia dos años", 0.10)])
    (recipe,) = await _document(owner, "Receta del pan", [("zzgarantia del horno", 0.20)])

    found = await _search(owner, "Según mis documentos, ¿qué dice la zzgarantia?")

    assert found.scope_found
    assert [hit.section.id for hit in found.hits] == [manual, recipe]


async def test_a_common_word_inside_the_scope_does_not_pass_the_gate(owner: int) -> None:
    near, *far = await _document(
        owner,
        "Manual de la lavadora",
        [
            ("La lavadora se limpia con vinagre", 0.20),
            ("La lavadora tiene ocho programas", 0.55),
            ("La lavadora pide un piso firme", 0.60),
            ("La lavadora muestra errores", 0.65),
        ],
    )

    found = await _search(
        owner, "¿Qué dice el manual de la lavadora sobre el color de la lavadora?"
    )

    assert [hit.section.id for hit in found.hits] == [near]
    assert found.rejected == len(far)


async def test_the_sensitive_sources_are_not_searched_without_their_level(owner: int) -> None:
    await _document(
        owner, "Guía de cuidados", [("zzparche cada dos días", 0.10)], level="sensitive"
    )

    with_level = await _search(owner, "¿Qué dice la guía de cuidados sobre el zzparche?")
    without = await _search(
        owner, "¿Qué dice la guía de cuidados sobre el zzparche?", levels=_NORMAL
    )

    assert len(with_level.hits) == 1
    assert (without.scope_found, without.hits) == (False, ())


async def test_at_most_three_sections(owner: int) -> None:
    await _document(owner, "Manual de la lavadora", [(f"zzfiltro {i}", 0.05 * i) for i in range(5)])

    found = await _search(owner, "¿Qué dice el manual de la lavadora sobre el zzfiltro?")

    assert len(found.hits) == 3


async def test_with_the_model_down_an_exact_code_still_qualifies(owner: int) -> None:
    await _document(
        owner, "Manual de la lavadora", [("El error E21 indica agua", None), ("zzotro", None)]
    )

    found = await _search(owner, "¿Qué dice el manual de la lavadora sobre el error E21?", up=False)

    assert len(found.hits) == 1


async def test_the_delivery_filter_holds_when_a_source_goes_between_search_and_read(
    owner: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _document(owner, "Manual de la lavadora", [("zzfiltro", 0.10)])
    real = document_store.sections_by_id

    async def removed_first(
        *args: object, **kwargs: object
    ) -> list[document_store.DocumentSection]:
        async with db.transaction() as conn:
            await conn.execute("DELETE FROM document_sources")
        return await real(*args, **kwargs)  # type: ignore[arg-type]  # the same call, forwarded

    monkeypatch.setattr("server.memory.document_search.sections_by_id", removed_first)

    found = await _search(owner, "¿Qué dice el manual de la lavadora sobre el zzfiltro?")

    assert found.hits == ()


def test_the_cue_strength_is_carried() -> None:
    assert (
        _cue("¿Qué dice mi manual de la lavadora sobre el filtro?").strength is CueStrength.STRONG
    )


def test_the_production_gate_reads_the_two_document_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from server.memory.document_search import production_document_gate  # noqa: PLC0415
    from server.memory.retrieval import GateSignals  # noqa: PLC0415

    monkeypatch.setattr(settings, "document_max_distance", 0.22)
    monkeypatch.setattr(settings, "document_word_max_distance", 0.61)
    gate = production_document_gate()

    def signals(distance: float, *, words: bool) -> GateSignals:
        return GateSignals(
            distance=distance, by_words=words, covers_specific=True, has_specific=False
        )

    assert gate(signals(0.21, words=False))
    assert not gate(signals(0.23, words=False))
    assert gate(signals(0.60, words=True))
    assert not gate(signals(0.62, words=True))
