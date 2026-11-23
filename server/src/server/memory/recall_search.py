"""Search the recall units: filter first, two rankings, an absolute gate, at most three.

ADR 0028 decision 6, Plan 0078 D-4. The store filters by owner, visibility, sensitivity
``normal``, expiry and the date window inside each query. Since Plan 0088 D-5 the relevance gate
is one step of the search: every candidate of the two rankings is read (the delivery filter), the
distance of a word hit the KNN did not rank is measured, the gate decides on each candidate, and
Reciprocal Rank Fusion orders what qualified (``memory/retrieval.py``). The production rule is
ADR 0040's: a question's named words must be in the unit, then a distance under
``RECALL_MAX_DISTANCE``, or a word hit under ``RECALL_WORD_MAX_DISTANCE`` (with no distance, a
word hit only when the question named something the unit holds). Zero qualifying units is a valid
result. Without the embedding model the search is by words
only. Nothing here logs a text.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from typing import TYPE_CHECKING, Final

from server.cognition.recall_cues import content_words
from server.cognition.spoken_dates import window_utc_bounds
from server.llm_transport import ollama_embed
from server.memory.household_time import household_day, household_zone
from server.memory.recall_store import (
    RecallUnit,
    count_units_of_another_model,
    distances_of,
    lexical_hits,
    occurred_time_on,
    recent_units,
    units_by_id,
    vector_hits,
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

    import httpx

    from server.cognition.recall_cues import RecallCue

logger = logging.getLogger(__name__)

__all__ = [
    "RECALL_MAX_PER_RECORD",
    "RECALL_MAX_RESULTS",
    "RECALL_MAX_TERMS",
    "RECALL_VECTOR_K",
    "RecallHit",
    "RecallSearch",
    "household_day",
    "household_zone",
    "production_gate",
    "search_recall",
]

#: Neighbours asked of the vector index before the window and expiry filters.
RECALL_VECTOR_K: Final = 20
#: Results at most, and at most this many from one conversation.
RECALL_MAX_RESULTS: Final = 3
RECALL_MAX_PER_RECORD: Final = 2
#: Content words sent to the word index.
RECALL_MAX_TERMS: Final = 8


@dataclass(frozen=True)
class RecallHit:
    """A found unit and its vector distance (``None`` when only its words matched)."""

    unit: RecallUnit
    distance: float | None


@dataclass(frozen=True)
class RecallSearch:
    """What one search found.

    Attributes:
        hits: At most three qualifying units, best first.
        best_distance: The nearest vector distance seen, qualifying or not (calibration).
        lexical_only: Whether the embedding model failed and only words were searched.
        rejected: How many readable candidates the relevance gate refused (Plan 0088 D-6).
    """

    hits: tuple[RecallHit, ...]
    best_distance: float | None
    lexical_only: bool
    rejected: int = 0


@dataclass(frozen=True)
class _Window:
    """The filters both rankings share."""

    owner: int
    since: str | None
    until: str | None
    now: str
    first_day: str | None = None
    last_day: str | None = None
    occurred: bool = False


def production_gate() -> Gate:
    """The rule of ADR 0040 (G3) with the configured ``RECALL_MAX_DISTANCE`` and
    ``RECALL_WORD_MAX_DISTANCE``, read at call time."""
    return gate_near_or_named(
        vector=settings.recall_max_distance, words=settings.recall_word_max_distance
    )


async def _vector_side(
    client: httpx.AsyncClient, query: str, window: _Window
) -> tuple[list[float], list[tuple[int, float]]] | None:
    """The question's embedding and the vector ranking, or ``None`` when only words search.

    Words alone search when the embedding model failed or when a unit of the owner still holds a
    vector of another model: a vector search would compare two embedding spaces, so it stays off
    until the background re-index leaves none (ADR 0031 decision 8, Plan 0085 D-10).
    """
    remaining = await count_units_of_another_model(window.owner)
    if remaining:
        logger.warning(
            "recall.vector off reason=model_changed remaining=%d",
            remaining,
            extra={"event": "recall.vector_off", "remaining": remaining},
        )
        return None
    try:
        vector = await ollama_embed(
            client, query, model=settings.embedding_model, timeout=settings.ollama_timeout_s
        )
    except Exception as exc:  # degradation boundary: the words still search (ADR 0028 d. 6.7)
        logger.warning("Recall search by words only (%s)", type(exc).__name__)
        return None
    ranked = await vector_hits(
        owner_entity_id=window.owner,
        vector=vector,
        since=window.since,
        until=window.until,
        now=window.now,
        k=RECALL_VECTOR_K,
        first_day=window.first_day,
        last_day=window.last_day,
        occurred=window.occurred,
    )
    return vector, ranked


async def _gated(
    cue: RecallCue,
    lexical: Sequence[int],
    side: tuple[list[float], list[tuple[int, float]]] | None,
    window: _Window,
    gate: Gate,
) -> tuple[list[RecallUnit], int]:
    """Read every candidate, measure the missing distances, gate, fuse (Plan 0088 D-5).

    Returns:
        The qualifying readable units best first, and how many readable candidates were refused.
    """
    ranked = [] if side is None else side[1]
    distances = dict(ranked)
    candidates = list(dict.fromkeys([*lexical, *distances]))
    units = await units_by_id(
        candidates, owner_entity_id=window.owner, now=window.now, occurred=window.occurred
    )
    unmeasured = [unit.id for unit in units if unit.id not in distances]
    if side is not None and unmeasured:
        distances |= await distances_of(unmeasured, side[0], owner_entity_id=window.owner)
    words = set(lexical)
    signals = {
        unit.id: GateSignals(
            distance=distances.get(unit.id),
            by_words=unit.id in words,
            covers_specific=covers(unit.body, cue.specific),
            has_specific=bool(cue.specific),
        )
        for unit in units
    }
    order, rejected = gate_and_fuse(lexical, [unit_id for unit_id, _ in ranked], signals, gate)
    by_id = {unit.id: unit for unit in units}
    return [by_id[unit_id] for unit_id in order], rejected


async def search_recall(
    owner_entity_id: int,
    cue: RecallCue,
    *,
    client: httpx.AsyncClient,
    now: datetime,
    gate: Gate | None = None,
) -> RecallSearch:
    """Search the owner's readable units for a recall question.

    Args:
        owner_entity_id: The owner whose units are searched (already authorized).
        cue: The recall question.
        client: Shared, lifecycle-owned HTTP client (Plan 0039), for the question's embedding.
        now: The current time (timezone-aware); expired records are skipped.
        gate: The relevance gate; ``None`` is the production rule (``production_gate``). The
            recall bench passes each candidate rule here, so it measures the real pipeline.

    Returns:
        The qualifying hits, the best vector distance and whether only words were searched.
        A question with only a date returns that window's episodes, newest first. With the
        occurred time on (Plan 0083 D-9) the window matches a unit by when its event happened.

    Raises:
        aiosqlite.Error: If the database fails; the caller answers that it does not remember.
    """
    since, until = (
        window_utc_bounds(cue.window, household_zone()) if cue.window is not None else (None, None)
    )
    now_iso = now.astimezone(UTC).isoformat(timespec="microseconds")
    occurred = occurred_time_on()
    window = _Window(
        owner=owner_entity_id,
        since=since,
        until=until,
        now=now_iso,
        first_day=None if cue.window is None else cue.window.start.isoformat(),
        last_day=None if cue.window is None else cue.window.end.isoformat(),
        occurred=occurred,
    )
    terms = content_words(cue.query)[:RECALL_MAX_TERMS]
    if not terms:
        if since is None or until is None:
            return RecallSearch(hits=(), best_distance=None, lexical_only=False)
        recent = await recent_units(
            owner_entity_id=owner_entity_id,
            since=since,
            until=until,
            now=now_iso,
            limit=RECALL_MAX_RESULTS,
            first_day=window.first_day,
            last_day=window.last_day,
            occurred=occurred,
        )
        return RecallSearch(
            hits=tuple(RecallHit(unit=unit, distance=None) for unit in recent),
            best_distance=None,
            lexical_only=False,
        )
    lexical = await lexical_hits(
        owner_entity_id=owner_entity_id,
        terms=terms,
        since=since,
        until=until,
        now=now_iso,
        limit=RECALL_VECTOR_K,
        first_day=window.first_day,
        last_day=window.last_day,
        occurred=occurred,
    )
    side = await _vector_side(client, cue.query, window)
    qualified, rejected = await _gated(
        cue, lexical, side, window, production_gate() if gate is None else gate
    )
    units = capped(
        qualified,
        key=lambda unit: unit.record_id,
        total=RECALL_MAX_RESULTS,
        per_key=RECALL_MAX_PER_RECORD,
    )
    knn = {} if side is None else dict(side[1])
    return RecallSearch(
        hits=tuple(RecallHit(unit=unit, distance=knn.get(unit.id)) for unit in units),
        best_distance=min(knn.values()) if knn else None,
        lexical_only=side is None,
        rejected=rejected,
    )
