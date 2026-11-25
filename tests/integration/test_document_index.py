"""Fitting sections to the model's window and embedding them (Plan 0088 Task B2, D-10).

Ollama is a ``MockTransport`` double; canary rows only.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx
import pytest
from server.memory import document_store
from server.memory.declarative import upsert_entity
from server.memory.document_index import backfill_sections, embed_section, fit_sections
from server.memory.document_store import NewSection, NewSource
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
    from pathlib import Path

pytestmark = pytest.mark.integration

_NOW = "2026-11-23T10:00:00.000000+00:00"
_VECTOR = [1.0] + [0.0] * 767


@pytest.fixture
async def owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "docs.db")
    monkeypatch.setattr(settings, "embedding_model", "canary-embed")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        yield await upsert_entity(name="Canary Owner", type="person")
    finally:
        await db.close_db()
        db._conn = None


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _words_as_tokens(request: httpx.Request) -> httpx.Response:
    """A model whose tokens are words and whose window is 512 (counts capped there)."""
    payload = json.loads(request.content)
    words = len(str(payload["input"]).split())
    if payload.get("truncate") is False and words > 512:
        return httpx.Response(400, json={"error": "the input length exceeds the context length"})
    return httpx.Response(200, json={"embeddings": [_VECTOR], "prompt_eval_count": min(words, 512)})


async def _sections(owner: int, bodies: list[str]) -> list[int]:
    source = NewSource(
        owner_entity_id=owner,
        title="Manual canario",
        file_sha256="e" * 64,
        format="txt",
        level="normal",
        channel="admin_local",
        loaded_at=_NOW,
        loaded_by_entity_id=owner,
    )
    sections = [NewSection(position=i, heading="", body=b) for i, b in enumerate(bodies)]
    async with db.transaction() as conn:
        source_id = await document_store.insert_source(conn, source=source, sections=sections)
    cursor = await db.get_conn().execute(
        "SELECT id FROM document_sections WHERE source_id = ? ORDER BY position", (source_id,)
    )
    ids = [int(row[0]) for row in await cursor.fetchall()]
    await cursor.close()
    return ids


async def test_a_section_the_model_counts_over_the_window_is_cut_before_insert() -> None:
    long_body = " ".join(["zz"] * 700)
    sections = [NewSection(0, "H", "zzcorta"), NewSection(1, "H", long_body)]

    async with _client(_words_as_tokens) as client:
        fitted = await fit_sections(client, sections)

    assert [s.position for s in fitted] == list(range(len(fitted)))
    assert len(fitted) >= 3
    assert all(len(s.body.split()) < 512 for s in fitted)
    assert sum(len(s.body.split()) for s in fitted) == 701
    assert {s.heading for s in fitted} == {"H"}


async def test_with_ollama_down_the_sections_are_kept_as_given() -> None:
    def down(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    sections = [NewSection(0, "", "zzuno")]
    async with _client(down) as client:
        assert await fit_sections(client, sections) == sections


async def test_a_refused_embedding_leaves_the_section_lexical_and_counted(owner: int) -> None:
    (section,) = await _sections(owner, [" ".join(["z"] * 600)])

    async with _client(_words_as_tokens) as client:
        assert not await embed_section(client, section, " ".join(["z"] * 600))
        assert await backfill_sections(client) == 0

    async with db.transaction() as conn:
        health = await document_store.document_index_health(conn)
    assert health.sections_refused == 1
    hits = await document_store.section_lexical_hits(
        owner_entity_id=owner, terms=["z"], levels=frozenset({"normal"}), source_ids=None, limit=5
    )
    assert hits == [section]


async def test_the_backfill_embeds_the_sections_without_a_vector(owner: int) -> None:
    first, second = await _sections(owner, ["zzuno", "zzdos"])

    async with _client(_words_as_tokens) as client:
        assert await backfill_sections(client) == 2

    assert await document_store.sections_without_vector(10) == []
    assert set(
        await document_store.section_distances_of([first, second], _VECTOR, owner_entity_id=owner)
    ) == {first, second}


async def test_a_section_the_new_model_refuses_leaves_no_vector_of_the_old_one(
    owner: int,
) -> None:
    """Review: an old vector left behind keeps the model guard above zero, words only for ever."""
    (section,) = await _sections(owner, [" ".join(["z"] * 600)])
    assert await document_store.store_section_vector(section, _VECTOR, model="canary-old")

    async with _client(_words_as_tokens) as client:
        assert not await embed_section(client, section, " ".join(["z"] * 600))

    assert await document_store.count_sections_of_another_model(owner) == 0
    assert (
        await document_store.section_distances_of([section], _VECTOR, owner_entity_id=owner) == {}
    )
