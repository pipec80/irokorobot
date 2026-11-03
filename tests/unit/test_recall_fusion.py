"""The gate and the fusion of the two recall rankings (Plan 0078 Task 7, ADR 0028 decision 6)."""

from __future__ import annotations

import pytest
from server.memory.recall_search import RRF_K, fuse

pytestmark = pytest.mark.unit

_GATE = 0.30


def test_a_far_vector_hit_does_not_qualify() -> None:
    assert fuse([], [(7, 0.31), (8, 0.29)], max_distance=_GATE) == [8]


def test_every_lexical_hit_qualifies() -> None:
    assert fuse([5, 6], [], max_distance=_GATE) == [5, 6]


def test_rrf_orders_a_unit_found_twice_first() -> None:
    fused = fuse([1, 2], [(2, 0.10), (3, 0.05)], max_distance=_GATE)

    assert fused[0] == 2
    assert set(fused) == {1, 2, 3}


def test_a_far_vector_hit_found_by_words_still_qualifies() -> None:
    assert fuse([4], [(4, 0.90)], max_distance=_GATE) == [4]


def test_zero_qualifying_is_an_empty_result() -> None:
    assert fuse([], [(1, 0.5), (2, 0.9)], max_distance=_GATE) == []
    assert fuse([], [], max_distance=_GATE) == []


def test_ties_go_to_the_newer_unit() -> None:
    # 9 is first by words, 4 first by vector: equal scores, the higher id first.
    assert fuse([9], [(4, 0.1)], max_distance=_GATE) == [9, 4]


def test_the_fusion_constant_is_sixty() -> None:
    assert RRF_K == 60
