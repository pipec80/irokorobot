"""Text embeddings via Ollama with SQLite-backed cache.

Cache key: ``sha256(text)[:16]`` + model name.
Vector encoding: ``struct.pack`` of ``N`` IEEE-754 float32 values.
"""

from __future__ import annotations

import hashlib
import logging
import struct
from typing import Final

import httpx

from server import db
from server.db import get_conn
from server.exceptions import BrainMemoryError
from server.settings import settings

logger = logging.getLogger(__name__)

# Fixed by design, NOT an environment setting (see docs/c-audit/
# auditoria-forense-codigo-2026-07-21.md F-04). server/src/server/memory/
# schema.sql hard-codes `vec_memories.embedding float[768]`, so changing
# this value requires a deliberate migration of `vec_memories` and
# invalidation of `embeddings_cache` — never a hot env-var change.
EMBEDDING_DIM: Final[int] = 768


def _hash(text: str) -> str:
    """Return a 16-char hex prefix of the SHA-256 hash of *text*.

    Args:
        text: Input string to hash.

    Returns:
        16-character lowercase hex string.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _pack(vec: list[float]) -> bytes:
    """Pack a float list into IEEE-754 float32 bytes (little-endian).

    Args:
        vec: List of floats to pack.

    Returns:
        Packed bytes suitable for storage in SQLite BLOB column.
    """
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack(blob: bytes, dim: int) -> list[float]:
    """Unpack IEEE-754 float32 bytes back to a float list.

    Args:
        blob: Packed bytes from SQLite BLOB column.
        dim: Expected number of dimensions (used for format string).

    Returns:
        List of *dim* floats.
    """
    return list(struct.unpack(f"{dim}f", blob))


async def embed(text: str) -> list[float]:
    """Return an embedding vector for *text*, hitting SQLite cache first.

    Caches new embeddings to the ``embeddings_cache`` table to avoid
    redundant Ollama round-trips across restarts.

    Args:
        text: Non-empty string to embed.

    Returns:
        List of ``EMBEDDING_DIM`` floats (768 for nomic-embed-text).

    Raises:
        ValueError: If *text* is empty.
        BrainMemoryError: If Ollama returns an unexpected payload or the HTTP
            call fails.
    """
    if not text:
        raise ValueError("Cannot embed empty text")

    conn = get_conn()
    h = _hash(text)

    cur = await conn.execute(
        "SELECT vector FROM embeddings_cache WHERE text_hash = ? AND model = ?",
        (h, settings.embedding_model),
    )
    row = await cur.fetchone()
    await cur.close()

    if row is not None:
        logger.debug("Embedding cache hit for hash %s", h)
        return _unpack(row[0], EMBEDDING_DIM)

    # /api/embed is Ollama's current endpoint (/api/embeddings is legacy).
    # It takes "input" and returns a list of embeddings (batched API).
    url = f"{settings.ollama_url}/api/embed"
    payload = {"model": settings.embedding_model, "input": text}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        embeddings = data.get("embeddings")
        vec: list[float] | None = (
            embeddings[0] if isinstance(embeddings, list) and embeddings else None
        )
        if not isinstance(vec, list) or len(vec) != EMBEDDING_DIM:
            got = len(vec) if isinstance(vec, list) else "invalid"
            raise BrainMemoryError(
                f"Ollama embedding has unexpected shape: expected {EMBEDDING_DIM}, got {got}"
            )
    except BrainMemoryError:
        raise
    except Exception as exc:
        raise BrainMemoryError("Ollama embeddings call failed") from exc

    # The write lock is acquired only around the INSERT itself, not the
    # Ollama round-trip above: holding it across a network call would
    # serialize every other write in the app behind one embedding request.
    # A concurrent cache miss for the same text can still race here — the
    # `OR REPLACE` makes that race harmless (idempotent), just occasionally
    # redundant.
    async with db.transaction() as write_conn:
        await write_conn.execute(
            "INSERT OR REPLACE INTO embeddings_cache (text_hash, model, vector) VALUES (?, ?, ?)",
            (h, settings.embedding_model, _pack(vec)),
        )
    logger.debug("Embedded and cached text (hash=%s, dim=%d)", h, len(vec))
    return vec
