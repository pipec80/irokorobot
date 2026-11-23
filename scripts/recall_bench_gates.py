"""The candidate relevance gates of Plan 0088 D-2, fixed before the bench runs.

Each is a ``retrieval.Gate`` over a candidate's signals: ``d`` its cosine distance (absent with the
vector side off or no vector yet), ``W`` whether the word index found it, and ``S`` the question's
specific words (``has_specific``, ``covers_specific``).

| Id | Rule |
|---|---|
| G0 | Today: ``d < T_v`` or ``W`` |
| G1 | ``d < T_v``, or ``W`` and ``d < T_w``; with ``d`` absent, ``W`` only if ``S`` is covered |
| G2 | If ``S`` is not empty, only a unit that covers ``S``, by G0; else G0 |
| G3 | G1 and G2 together |
"""

from __future__ import annotations

from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from typing import TYPE_CHECKING, Final  # after the sys.path bootstrap, by design

from server.memory.retrieval import gate_near_or_named, gate_or

if TYPE_CHECKING:
    from server.memory.retrieval import Gate, GateSignals

__all__ = ["PARAMETERS", "RULES", "SWEPT", "build"]

#: The rules, in D-2's order.
RULES: Final = ("G0", "G1", "G2", "G3")
#: The rules with a second gate ``T_w``, swept by the bench.
SWEPT: Final = frozenset({"G1", "G3"})
#: How many thresholds each rule has (D-3's tie-break: the fewest parameters).
PARAMETERS: Final[dict[str, int]] = {"G0": 1, "G1": 2, "G2": 1, "G3": 2}


def _g1(*, vector: float, words: float) -> Gate:
    def gate(signals: GateSignals) -> bool:
        if signals.distance is None:
            return signals.by_words and signals.has_specific and signals.covers_specific
        return signals.distance < vector or (signals.by_words and signals.distance < words)

    return gate


def _named(inner: Gate) -> Gate:
    """A unit must hold the question's specific words, when it has any, then *inner* decides."""

    def gate(signals: GateSignals) -> bool:
        if signals.has_specific and not signals.covers_specific:
            return False
        return inner(signals)

    return gate


def build(rule: str, *, vector: float, words: float | None = None) -> Gate:
    """Build one candidate rule of D-2.

    Args:
        rule: ``G0`` to ``G3``.
        vector: ``T_v``, the vector gate (``RECALL_MAX_DISTANCE``).
        words: ``T_w``, the second gate of a word hit; needed by G1 and G3 only.

    Returns:
        The gate.

    Raises:
        ValueError: For an unknown rule, or G1 or G3 without ``T_w``.
    """
    if rule in SWEPT and words is None:
        raise ValueError(f"{rule} needs its second gate T_w")
    match rule:
        case "G0":
            return gate_or(vector=vector)
        case "G1" if words is not None:
            return _g1(vector=vector, words=words)
        case "G2":
            return _named(gate_or(vector=vector))
        case "G3" if words is not None:
            # The production rule since ADR 0040: the bench measures the very same function.
            return gate_near_or_named(vector=vector, words=words)
        case _:
            raise ValueError(f"unknown rule {rule}")
