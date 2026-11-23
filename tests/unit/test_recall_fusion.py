"""The gate and the fusion of the two recall rankings (Plan 0078 Task 7, ADR 0028 decision 6).

Since Plan 0088 Task A2 the gate is one step of the search (``retrieval.gate_and_fuse``) and
today's rule is ``gate_or`` (G0); the expectations are those of Plan 0078.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from server.memory.retrieval import GateSignals, gate_and_fuse, gate_or
from server.settings import Settings

if TYPE_CHECKING:
    from collections.abc import Sequence

pytestmark = pytest.mark.unit

_GATE = 0.30


def _fuse(
    lexical: Sequence[int], vector: Sequence[tuple[int, float]], *, max_distance: float
) -> list[int]:
    """Today's fusion through the gate step: every candidate's signals, then G0."""
    distances = dict(vector)
    signals = {
        unit_id: GateSignals(
            distance=distances.get(unit_id),
            by_words=unit_id in lexical,
            covers_specific=False,
            has_specific=False,
        )
        for unit_id in (*lexical, *distances)
    }
    ordered, _ = gate_and_fuse(
        lexical, [unit_id for unit_id, _ in vector], signals, gate_or(vector=max_distance)
    )
    return ordered


def test_a_far_vector_hit_does_not_qualify() -> None:
    assert _fuse([], [(7, 0.31), (8, 0.29)], max_distance=_GATE) == [8]


def test_every_lexical_hit_qualifies() -> None:
    assert _fuse([5, 6], [], max_distance=_GATE) == [5, 6]


def test_rrf_orders_a_unit_found_twice_first() -> None:
    fused = _fuse([1, 2], [(2, 0.10), (3, 0.05)], max_distance=_GATE)

    assert fused[0] == 2
    assert set(fused) == {1, 2, 3}


def test_a_far_vector_hit_found_by_words_still_qualifies() -> None:
    assert _fuse([4], [(4, 0.90)], max_distance=_GATE) == [4]


def test_a_far_vector_rank_adds_nothing_to_a_word_hit() -> None:
    """Only a unit that qualifies by its vector alone scores on the vector side (Plan 0078)."""
    assert _fuse([1, 2], [(2, 0.90)], max_distance=_GATE) == [1, 2]


def test_zero_qualifying_is_an_empty_result() -> None:
    assert _fuse([], [(1, 0.5), (2, 0.9)], max_distance=_GATE) == []
    assert _fuse([], [], max_distance=_GATE) == []


def test_ties_go_to_the_newer_unit() -> None:
    # 9 is first by words, 4 first by vector: equal scores, the higher id first.
    assert _fuse([9], [(4, 0.1)], max_distance=_GATE) == [9, 4]


def test_the_refused_candidates_are_counted() -> None:
    signals = {
        unit_id: GateSignals(
            distance=distance, by_words=False, covers_specific=False, has_specific=False
        )
        for unit_id, distance in ((1, 0.1), (2, 0.5), (3, 0.9))
    }

    ordered, rejected = gate_and_fuse([], [1, 2, 3], signals, gate_or(vector=_GATE))

    assert (ordered, rejected) == ([1], 2)


def test_the_default_gate_is_the_calibrated_one() -> None:
    """Calibrated on Pipec's hardware run (2026-11-03): his memories at 0.395 and 0.414, the
    questions with no memory at 0.469 to 0.517 (Plan 0078 Task 12)."""
    assert Settings.model_fields["recall_max_distance"].default == pytest.approx(0.43)
