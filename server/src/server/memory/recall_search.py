"""Search the recall units: filter first, two rankings, an absolute gate, at most three.

ADR 0028 decision 6, Plan 0078 D-4. The store filters by owner, visibility, sensitivity
``normal``, expiry and the date window inside each query. A unit qualifies only when its vector
distance is under ``RECALL_MAX_DISTANCE`` or it shares a content word with the question; zero
qualifying units is a valid result. Reciprocal Rank Fusion orders what qualifies. Without the
embedding model the search is by words only. Nothing here logs a text.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from typing import TYPE_CHECKING, Final
from zoneinfo import ZoneInfo

from server.cognition.recall_cues import content_words
from server.cognition.spoken_dates import window_utc_bounds
from server.llm_transport import ollama_embed
from server.memory.recall_store import (
    RecallUnit,
    lexical_hits,
    recent_units,
    units_by_id,
    vector_hits,
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
    "RRF_K",
    "RecallHit",
    "RecallSearch",
    "fuse",
    "household_zone",
    "search_recall",
]

#: Reciprocal Rank Fusion constant.
RRF_K: Final = 60
#: Neighbours asked of the vector index before the window and expiry filters.
RECALL_VECTOR_K: Final = 20
#: Results at most, and at most this many from one conversation.
RECALL_MAX_RESULTS: Final = 3
RECALL_MAX_PER_RECORD: Final = 2
#: Content words sent to the word index.
RECALL_MAX_TERMS: Final = 8


def household_zone() -> ZoneInfo:
    """Return the household time zone of ``HOUSEHOLD_TIMEZONE`` (ADR 0028 decision 7)."""
    return ZoneInfo(settings.household_timezone)


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
    """

    hits: tuple[RecallHit, ...]
    best_distance: float | None
    lexical_only: bool


@dataclass(frozen=True)
class _Window:
    """The filters both rankings share."""

    owner: int
    since: str | None
    until: str | None
    now: str


def fuse(
    lexical: Sequence[int], vector: Sequence[tuple[int, float]], *, max_distance: float
) -> list[int]:
    """Gate and fuse the two rankings with Reciprocal Rank Fusion.

    Args:
        lexical: Unit ids found by words, best first; each qualifies.
        vector: ``(unit id, distance)`` nearest first; one qualifies only under *max_distance*.
        max_distance: The absolute cosine-distance gate.

    Returns:
        The qualifying unit ids, best first; ties go to the newer (higher) id.
    """
    near = [unit_id for unit_id, distance in vector if distance < max_distance]
    scores: dict[int, float] = {}
    for ranking in (lexical, near):
        for rank, unit_id in enumerate(ranking, start=1):
            scores[unit_id] = scores.get(unit_id, 0.0) + 1.0 / (RRF_K + rank)
    return sorted(scores, key=lambda unit_id: (-scores[unit_id], -unit_id))


def _capped(units: Sequence[RecallUnit]) -> list[RecallUnit]:
    """At most three units, at most two of one conversation, in the given order."""
    kept: list[RecallUnit] = []
    per_record: Counter[int] = Counter()
    for unit in units:
        if per_record[unit.record_id] < RECALL_MAX_PER_RECORD:
            kept.append(unit)
            per_record[unit.record_id] += 1
        if len(kept) == RECALL_MAX_RESULTS:
            break
    return kept


async def _vector_side(
    client: httpx.AsyncClient, query: str, window: _Window
) -> list[tuple[int, float]] | None:
    """The vector ranking, or ``None`` when the embedding model failed."""
    try:
        vector = await ollama_embed(
            client, query, model=settings.embedding_model, timeout=settings.ollama_timeout_s
        )
    except Exception as exc:  # degradation boundary: the words still search (ADR 0028 d. 6.7)
        logger.warning("Recall search by words only (%s)", type(exc).__name__)
        return None
    return await vector_hits(
        owner_entity_id=window.owner,
        vector=vector,
        since=window.since,
        until=window.until,
        now=window.now,
        k=RECALL_VECTOR_K,
    )


async def search_recall(
    owner_entity_id: int, cue: RecallCue, *, client: httpx.AsyncClient, now: datetime
) -> RecallSearch:
    """Search the owner's readable units for a recall question.

    Args:
        owner_entity_id: The owner whose units are searched (already authorized).
        cue: The recall question.
        client: Shared, lifecycle-owned HTTP client (Plan 0039), for the question's embedding.
        now: The current time (timezone-aware); expired records are skipped.

    Returns:
        The qualifying hits, the best vector distance and whether only words were searched.
        A question with only a date returns that window's episodes, newest first.

    Raises:
        aiosqlite.Error: If the database fails; the caller answers that it does not remember.
    """
    since, until = (
        window_utc_bounds(cue.window, household_zone()) if cue.window is not None else (None, None)
    )
    now_iso = now.astimezone(UTC).isoformat(timespec="microseconds")
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
        )
        return RecallSearch(
            hits=tuple(RecallHit(unit=unit, distance=None) for unit in recent),
            best_distance=None,
            lexical_only=False,
        )
    window = _Window(owner=owner_entity_id, since=since, until=until, now=now_iso)
    lexical = await lexical_hits(
        owner_entity_id=owner_entity_id,
        terms=terms,
        since=since,
        until=until,
        now=now_iso,
        limit=RECALL_VECTOR_K,
    )
    vector = await _vector_side(client, cue.query, window)
    distances = dict(vector or [])
    fused = fuse(lexical, vector or [], max_distance=settings.recall_max_distance)
    units = _capped(await units_by_id(fused))
    return RecallSearch(
        hits=tuple(RecallHit(unit=unit, distance=distances.get(unit.id)) for unit in units),
        best_distance=min(distances.values()) if distances else None,
        lexical_only=vector is None,
    )
