"""Unit tests for server.memory.embeddings: embed() shape validation.

EMBEDDING_DIM is frozen at 768 by design (see docs/c-audit/
auditoria-forense-codigo-2026-07-21.md F-04) — a mismatched vector from
Ollama must fail loudly with a clear message, not a cryptic
struct.unpack error further down the line.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from server.exceptions import BrainMemoryError
from server.memory import embeddings
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path


class _FakeCursor:
    """Minimal stand-in for aiosqlite.Cursor — always a cache miss."""

    async def fetchone(self) -> None:
        return None

    async def close(self) -> None:
        pass


class _FakeConn:
    """Minimal stand-in for aiosqlite.Connection — no real DB needed."""

    async def execute(self, _query: str, _params: tuple[object, ...] = ()) -> _FakeCursor:
        return _FakeCursor()

    async def commit(self) -> None:
        pass


class _FakeResponse:
    """Minimal stand-in for httpx.Response returning a fixed embeddings payload."""

    def __init__(self, vec: list[float]) -> None:
        self._vec = vec

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, object]:
        return {"embeddings": [self._vec]}


class _FakeAsyncClient:
    """Minimal stand-in for httpx.AsyncClient — returns a canned response."""

    vec: list[float] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    # `json` must keep this exact name — embed() calls .post(url, json=payload)
    # as a keyword arg, and the payload itself is irrelevant to this fake.
    async def post(self, _url: str, json: dict[str, object]) -> _FakeResponse:  # noqa: ARG002
        return _FakeResponse(_FakeAsyncClient.vec)


@pytest.mark.unit
async def test_embed_rejects_wrong_dimension_vector(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 512-d vector from Ollama (instead of the frozen 768) must fail clearly."""
    monkeypatch.setattr(embeddings, "get_conn", _FakeConn)
    _FakeAsyncClient.vec = [0.1] * 512
    monkeypatch.setattr(embeddings.httpx, "AsyncClient", _FakeAsyncClient)

    with pytest.raises(BrainMemoryError, match=r"expected 768, got 512"):
        await embeddings.embed("hola")


@pytest.fixture
async def _real_memory_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Open a real temporary DB — `embed()`'s cache write now uses `db.transaction()`."""
    db_path = tmp_path / "embeddings-test.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield
    await db.close_db()
    db._conn = None


@pytest.mark.integration
@pytest.mark.usefixtures("_real_memory_db")
async def test_embed_accepts_correct_dimension_vector(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 768-d vector (the frozen EMBEDDING_DIM) must pass through untouched.

    Reclassified from `unit` to `integration` (Plan 0036): `embed()`'s cache
    write now goes through `db.transaction()`, which needs a real open
    connection — a bare `get_conn()` mock no longer reaches far enough.
    """
    _FakeAsyncClient.vec = [0.1] * 768
    monkeypatch.setattr(embeddings.httpx, "AsyncClient", _FakeAsyncClient)

    result = await embeddings.embed("hola")

    assert len(result) == 768
