"""The document search: first the document by its title, then its sections (Plan 0088 D-12).

The content words of the cue's «{tipo} {nombre}» must all be in a readable title (folded, with or
without one final «s»); the sources that hold them are the scope, and a cue that names none
(«según mis documentos») searches every readable source. Inside the scope the pipeline of recall
runs (ADR 0040 decision 1): the two rankings (FTS5 and the KNN, both filtered by owner, level and
source inside the query) → every candidate read through the delivery filter → the distance of
the ones the KNN did not rank → the gate → RRF → at most three sections. The document gate has
its own thresholds, calibrated on the document bench (D-13). Nothing here logs a text.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Final

from server.cognition.recall_cues import content_words
from server.llm_transport import ollama_embed
from server.memory.document_store import (
    DocumentHit,
    DocumentSearch,
    DocumentSection,
    count_sections_of_another_model,
    readable_titles,
    section_distances_of,
    section_lexical_hits,
    section_vector_hits,
    sections_by_id,
)
from server.memory.retrieval import (
    Gate,
    GateSignals,
    capped,
    covers,
    gate_and_fuse,
    gate_near_or_named,
)
from server.settings import settings

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    import httpx

    from server.cognition.document_cues import DocumentCue
    from server.memory.document_store import DocumentLevel

logger = logging.getLogger(__name__)

__all__ = [
    "DOCUMENT_MAX_RESULTS",
    "DOCUMENT_VECTOR_K",
    "production_document_gate",
    "search_documents",
]

#: Neighbours asked of the vector index, and sections returned at most.
DOCUMENT_VECTOR_K: Final = 20
DOCUMENT_MAX_RESULTS: Final = 3
_MAX_TERMS: Final = 8


@dataclass(frozen=True)
class _Scope:
    owner: int
    levels: frozenset[DocumentLevel]
    sources: Sequence[int] | None


def production_document_gate() -> Gate:
    """ADR 0040's rule with the document thresholds (``DOCUMENT_MAX_DISTANCE``,
    ``DOCUMENT_WORD_MAX_DISTANCE``), read at call time."""
    return gate_near_or_named(
        vector=settings.document_max_distance, words=settings.document_word_max_distance
    )


async def _sources_named(
    owner: int, cue: DocumentCue, levels: frozenset[DocumentLevel]
) -> list[int]:
    """The readable sources whose title holds every named word."""
    named = frozenset(cue.named)
    return [
        source_id
        for source_id, title in await readable_titles(owner_entity_id=owner, levels=levels)
        if covers(title, named)
    ]


async def _vector_side(
    client: httpx.AsyncClient, query: str, scope: _Scope
) -> tuple[list[float], list[tuple[int, float]]] | None:
    """The question's embedding and the KNN ranking, or ``None`` when words alone search."""
    if await count_sections_of_another_model(scope.owner):
        logger.warning(
            "document.vector off reason=model_changed", extra={"event": "document.vector_off"}
        )
        return None
    try:
        vector = await ollama_embed(
            client, query, model=settings.embedding_model, timeout=settings.ollama_timeout_s
        )
    except Exception as exc:  # degradation boundary: the words still search (as recall)
        logger.warning("Document search by words only (%s)", type(exc).__name__)
        return None
    ranked = await section_vector_hits(
        owner_entity_id=scope.owner,
        vector=vector,
        levels=scope.levels,
        source_ids=scope.sources,
        k=DOCUMENT_VECTOR_K,
    )
    return vector, ranked


async def _gated(
    cue: DocumentCue,
    lexical: Sequence[int],
    side: tuple[list[float], list[tuple[int, float]]] | None,
    scope: _Scope,
    gate: Gate,
) -> tuple[list[tuple[DocumentSection, float | None]], int]:
    """Read every candidate, measure the missing distances, gate and fuse (D-5)."""
    ranked = [] if side is None else side[1]
    distances = dict(ranked)
    candidates = list(dict.fromkeys([*lexical, *distances]))
    sections = await sections_by_id(candidates, owner_entity_id=scope.owner, levels=scope.levels)
    unmeasured = [s.id for s in sections if s.id not in distances]
    if side is not None and unmeasured:
        distances |= await section_distances_of(unmeasured, side[0], owner_entity_id=scope.owner)
    words = set(lexical)
    signals = {
        s.id: GateSignals(
            distance=distances.get(s.id),
            by_words=s.id in words,
            covers_specific=covers(f"{s.heading} {s.body}", cue.specific),
            has_specific=bool(cue.specific),
        )
        for s in sections
    }
    order, rejected = gate_and_fuse(
        lexical, [section_id for section_id, _ in ranked], signals, gate
    )
    by_id = {s.id: s for s in sections}
    return [(by_id[section_id], distances.get(section_id)) for section_id in order], rejected


async def search_documents(
    owner_entity_id: int,
    cue: DocumentCue,
    *,
    levels: frozenset[DocumentLevel],
    client: httpx.AsyncClient,
    now: datetime,
    gate: Gate | None = None,
    title_step: bool = True,
) -> DocumentSearch:
    """Search the owner's readable documents for a document question.

    Args:
        owner_entity_id: The owner whose documents are searched (already authorized).
        cue: The document question.
        levels: The levels the speaker may hear (``document_access.readable_levels``).
        client: Shared, lifecycle-owned HTTP client (Plan 0039), for the question's embedding.
        now: The current time; documents do not expire, so it is unused today.
        gate: The relevance gate; ``None`` is the production rule with the document thresholds.
            The document bench passes candidate rules here, so it measures the real pipeline.
        title_step: ``False`` searches every readable source whatever the cue names (the bench
            measures the title step's gain).

    Returns:
        ``scope_found=False`` when the cue names a document none of the titles holds; else at
        most three qualifying sections, best first, and how many candidates the gate refused.

    Raises:
        aiosqlite.Error: If the database fails; the caller answers that it does not find it.
    """
    del now  # documents do not expire; kept so both searches share their signature
    sources: list[int] | None = None
    if title_step and cue.named:
        sources = await _sources_named(owner_entity_id, cue, levels)
        if not sources:
            return DocumentSearch(scope_found=False, hits=())
    scope = _Scope(owner=owner_entity_id, levels=levels, sources=sources)
    terms = content_words(cue.query)[:_MAX_TERMS]
    lexical = await section_lexical_hits(
        owner_entity_id=owner_entity_id,
        terms=terms,
        levels=levels,
        source_ids=sources,
        limit=DOCUMENT_VECTOR_K,
    )
    side = await _vector_side(client, cue.query, scope)
    qualified, rejected = await _gated(
        cue, lexical, side, scope, production_document_gate() if gate is None else gate
    )
    kept = capped(
        qualified,
        key=lambda pair: pair[0].source_id,
        total=DOCUMENT_MAX_RESULTS,
        per_key=DOCUMENT_MAX_RESULTS,
    )
    return DocumentSearch(
        scope_found=True,
        hits=tuple(DocumentHit(section=section, distance=distance) for section, distance in kept),
        rejected=rejected,
    )
