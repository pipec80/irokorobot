"""What every retrieval source shares: the relevance gate, the fusion, the cap, the match (D-5).

Plan 0088 Part A. The diary's recall uses it today; the documents of ADR 0034 decision 4 reuse it
instead of copying it. Pure: no I/O, no settings, no database, no model. A source computes each
candidate's signals (``GateSignals``), a ``Gate`` decides alone whether it qualifies, and
Reciprocal Rank Fusion orders what qualified.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Hashable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Final

from server.text_keys import normalize_spanish

__all__ = [
    "GATE_ID",
    "RRF_K",
    "Gate",
    "GateSignals",
    "capped",
    "covers",
    "gate_and_fuse",
    "gate_near_or_named",
    "match_expression",
    "rrf",
]

#: Reciprocal Rank Fusion constant (ADR 0028 decision 6.4).
RRF_K: Final = 60
#: The production rule's id (ADR 0040), logged with every recall read.
GATE_ID: Final = "G3"
# A word shorter than this is matched exactly, never with one final «s» added or dropped
# (Plan 0086's names, `forget_scope._with_variants`).
_MIN_PLURAL_WORD: Final = 4


@dataclass(frozen=True)
class GateSignals:
    """What the gate may know about one candidate.

    Attributes:
        distance: Its cosine distance to the question; ``None`` when the vector side is off or
            the unit has no vector yet.
        by_words: Whether the word index found it.
        covers_specific: Whether its body holds every specific word of the question.
        has_specific: Whether the question has specific words at all.
    """

    distance: float | None
    by_words: bool
    covers_specific: bool
    has_specific: bool


type Gate = Callable[[GateSignals], bool]


def gate_near_or_named(*, vector: float, words: float) -> Gate:
    """G3, the rule of ADR 0040: named things must be there, then a near meaning or a near word hit.

    A question with specific words qualifies only a unit that holds them. Then, with a distance:
    under *vector*, or a word hit under *words*; without one (the embedding model down, or no
    vector yet): a word hit, and only when the question named something the unit holds.

    Args:
        vector: ``T_v``, the gate of a unit found by its meaning (``RECALL_MAX_DISTANCE``).
        words: ``T_w``, the gate of a word hit (``RECALL_WORD_MAX_DISTANCE``).

    Returns:
        The gate.
    """

    def gate(signals: GateSignals) -> bool:
        if signals.has_specific and not signals.covers_specific:
            return False
        if signals.distance is None:
            return signals.by_words and signals.has_specific
        return signals.distance < vector or (signals.by_words and signals.distance < words)

    return gate


def rrf(rankings: Sequence[Sequence[int]]) -> list[int]:
    """Fuse rankings with Reciprocal Rank Fusion; ties go to the higher (newer) id."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (RRF_K + rank)
    return sorted(scores, key=lambda item: (-scores[item], -item))


def gate_and_fuse(
    lexical: Sequence[int],
    vector: Sequence[int],
    signals: Mapping[int, GateSignals],
    gate: Gate,
) -> tuple[list[int], int]:
    """Gate every candidate, then fuse the two rankings over what qualified.

    A candidate scores on the word ranking when it qualifies, and on the vector ranking only when
    it would qualify without its word hit: a far vector rank adds nothing to a unit the words
    found, as in ADR 0028 decision 6.

    Args:
        lexical: Candidate ids found by words, best first.
        vector: Candidate ids found by the vector index, nearest first.
        signals: Each readable candidate's signals; a ranked id without signals is not readable
            and takes no part.
        gate: The rule.

    Returns:
        The qualifying ids best first, and how many readable candidates the gate refused.
    """
    qualified = {unit_id for unit_id, signal in signals.items() if gate(signal)}
    words = [unit_id for unit_id in lexical if unit_id in qualified]
    near = [
        unit_id
        for unit_id in vector
        if unit_id in qualified and gate(replace(signals[unit_id], by_words=False))
    ]
    return rrf([words, near]), len(signals) - len(qualified)


def capped[T](
    items: Sequence[T], *, key: Callable[[T], Hashable], total: int, per_key: int
) -> list[T]:
    """At most *total* items and at most *per_key* of one key, in the given order."""
    kept: list[T] = []
    per: Counter[Hashable] = Counter()
    for item in items:
        if len(kept) == total:
            break
        if per[key(item)] < per_key:
            kept.append(item)
            per[key(item)] += 1
    return kept


def match_expression(terms: Sequence[str]) -> str:
    """Quote each term as an FTS5 string, so no input is FTS syntax, and join with ``OR``."""
    quoted = ['"' + term.replace('"', '""') + '"' for term in terms if term.strip()]
    return " OR ".join(quoted)


def _variants(word: str) -> set[str]:
    if len(word) < _MIN_PLURAL_WORD:
        return {word}
    return {word, word[:-1] if word.endswith("s") else f"{word}s"}


def covers(body: str, words: frozenset[str]) -> bool:
    """Whether *body* holds every one of *words*, folded, with or without one final «s».

    Args:
        body: A candidate's text.
        words: Folded words (``normalize_spanish``); an empty set is always covered.

    Returns:
        ``True`` when each word, or its one-«s» variant, is a whole word of the folded body.
    """
    if not words:
        return True
    tokens = set(normalize_spanish(body).split())
    return all(_variants(word) & tokens for word in words)
