"""Fitting the document sections to the model's window and embedding them (Plan 0088 D-10).

At load, when Ollama answers, each section's tokens are counted and a section at the window is
cut again **before** it is inserted; with Ollama down the character cap alone applies. Every
section is embedded with ``truncate=False``, so none is ever cut silently: one the model still
refuses is marked (``vector_refused_by``), logged with its id only and stays searchable by its
words. Nothing here raises to its caller or logs a text.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final, Literal

import httpx

from server.exceptions import LLMError
from server.llm_transport import ollama_embed, ollama_token_count
from server.memory.document_sections import split_body
from server.memory.document_store import (
    NewSection,
    mark_section_refused,
    sections_without_vector,
    store_section_vector,
)
from server.settings import settings

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

__all__ = ["EMBEDDING_WINDOW_TOKENS", "backfill_sections", "embed_section", "fit_sections"]

#: The window of ``granite-embedding:278m`` (``bert.context_length``, Plan 0088 audit item 6).
EMBEDDING_WINDOW_TOKENS: Final = 512
_HTTP_BAD_REQUEST: Final = 400


async def _fits(client: httpx.AsyncClient, body: str) -> bool:
    """Whether the model reads *body* whole (the count is capped at the window)."""
    count = await ollama_token_count(
        client, body, model=settings.embedding_model, timeout=settings.ollama_timeout_s
    )
    return count < EMBEDDING_WINDOW_TOKENS


async def _fitted_bodies(client: httpx.AsyncClient, body: str) -> list[str]:
    """*body*, or its halves cut again until each one fits the window."""
    if await _fits(client, body):
        return [body]
    pieces = split_body(body, max(1, len(body) // 2))
    if len(pieces) < 2:  # noqa: PLR2004 - a body that cannot be cut further is kept as it is
        return [body]
    bodies: list[str] = []
    for piece in pieces:
        bodies += await _fitted_bodies(client, piece)
    return bodies


async def fit_sections(
    client: httpx.AsyncClient, sections: Sequence[NewSection]
) -> list[NewSection]:
    """Cut again every section the model counts at its window, before it is inserted.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039).
        sections: The sections cut by characters.

    Returns:
        The sections, renumbered from 0; as given when Ollama does not answer.
    """
    fitted: list[NewSection] = []
    try:
        for section in sections:
            fitted += [
                NewSection(position=0, heading=section.heading, body=body)
                for body in await _fitted_bodies(client, section.body)
            ]
    except (httpx.HTTPError, LLMError) as exc:
        logger.info(
            "Document sections not counted (%s): the character cap alone applies",
            type(exc).__name__,
            extra={"event": "document.fit_skipped"},
        )
        return list(sections)
    return [NewSection(position=i, heading=s.heading, body=s.body) for i, s in enumerate(fitted)]


async def embed_section(client: httpx.AsyncClient, section_id: int, body: str) -> bool:
    """Compute and store one section's vector, never truncated; never raises.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039).
        section_id: The section.
        body: Its text (never logged).

    Returns:
        Whether a vector was stored. A section the model refuses as too long is marked and stays
        searchable by its words.
    """
    return await _embed(client, section_id, body) == "stored"


async def _embed(
    client: httpx.AsyncClient, section_id: int, body: str
) -> Literal["stored", "refused", "failed"]:
    model = settings.embedding_model
    try:
        vector = await ollama_embed(
            client, body, model=model, timeout=settings.ollama_timeout_s, truncate=False
        )
        return "stored" if await store_section_vector(section_id, vector, model=model) else "failed"
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != _HTTP_BAD_REQUEST:
            _log_failure(exc, section_id)
            return "failed"
        try:
            await mark_section_refused(section_id, model=model)
        except Exception as mark_exc:  # background boundary: it is tried again on the next tick
            _log_failure(mark_exc, section_id)
            return "failed"
        logger.warning(
            "Document section longer than the model's window: kept by its words only",
            extra={"event": "document.section_too_long", "section_id": section_id},
        )
        return "refused"
    except Exception as exc:  # background boundary: a section without a vector is found by words
        _log_failure(exc, section_id)
        return "failed"


def _log_failure(exc: Exception, section_id: int) -> None:
    # Only the class is logged: the message of a failure could carry a text.
    logger.warning(
        "Document section not embedded (%s)",
        type(exc).__name__,
        extra={"event": "document.embed_error", "section_id": section_id},
    )


async def backfill_sections(client: httpx.AsyncClient, *, limit: int = 5) -> int:
    """Embed up to *limit* sections that need a vector; stop at the first failure.

    A refused section does not stop the batch: it is marked and the next one is tried.

    Returns:
        How many vectors were stored.
    """
    stored = 0
    for section_id, body in await sections_without_vector(limit):
        outcome = await _embed(client, section_id, body)
        if outcome == "failed":
            break
        stored += outcome == "stored"
    if stored:
        logger.info("Document backfill: %d vector(s) stored", stored)
    return stored
