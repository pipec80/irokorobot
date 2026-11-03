"""Embedding the recall units (ADR 0028 decision 2, Plan 0078).

A unit is searchable by its words as soon as it is written; its vector follows. The live path
embeds a turn's unit right after the reply; when the model is unreachable the unit stays
lexical-only and the conversation job fills the vector later, while nobody is talking. A text
longer than the model's window is embedded on its first window (Ollama truncates by default);
the word index keeps the whole text. Nothing here raises to its caller or logs a text.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

from server.llm_transport import ollama_embed
from server.memory.recall_store import store_vector, units_without_vector
from server.settings import settings

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger(__name__)

__all__ = ["backfill_vectors", "embed_unit", "warm_up"]

# Embedded once at start-up so the first recall after a restart does not pay the cold load.
_WARM_UP_TEXT: Final = "hola"


async def embed_unit(client: httpx.AsyncClient, unit_id: int, body: str) -> bool:
    """Compute and store one unit's vector; never raises.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039).
        unit_id: The unit.
        body: Its text (never logged).

    Returns:
        Whether a vector was stored; ``False`` when the model failed or the unit is gone.
    """
    try:
        vector = await ollama_embed(
            client, body, model=settings.embedding_model, timeout=settings.ollama_timeout_s
        )
        return await store_vector(unit_id, vector, model=settings.embedding_model)
    except Exception as exc:  # background boundary: a unit without a vector is still found by words
        # Only the class is logged: the message of a failure could carry a text.
        logger.warning(
            "Recall unit not embedded (%s)",
            type(exc).__name__,
            extra={"event": "recall.embed_error", "unit_id": unit_id},
        )
        return False


async def backfill_vectors(client: httpx.AsyncClient, *, limit: int = 5) -> int:
    """Embed up to *limit* units that have no vector; stop at the first failure.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039).
        limit: How many units at most in this call.

    Returns:
        How many vectors were stored.
    """
    stored = 0
    for unit_id, body in await units_without_vector(limit):
        if not await embed_unit(client, unit_id, body):
            break
        stored += 1
    if stored:
        logger.info("Recall backfill: %d vector(s) stored", stored)
    return stored


async def warm_up(client: httpx.AsyncClient) -> None:
    """Load the embedding model with one fixed word; a failure only logs its class.

    Args:
        client: The lifespan's HTTP client.
    """
    try:
        await ollama_embed(
            client, _WARM_UP_TEXT, model=settings.embedding_model, timeout=settings.ollama_timeout_s
        )
    except Exception as exc:  # start-up boundary: recall degrades to words, the server starts
        logger.warning(
            "Embedding model warm-up failed; recall searches by words (%s)", type(exc).__name__
        )
