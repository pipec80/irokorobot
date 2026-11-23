"""The pure pieces both retrieval sources share (Plan 0088 D-5, Task A2)."""

from __future__ import annotations

import pytest
from server.memory import retrieval
from server.memory.retrieval import GateSignals, capped, covers, gate_or, match_expression, rrf

pytestmark = pytest.mark.unit


def _signals(
    distance: float | None, *, by_words: bool = False, covers_specific: bool = False
) -> GateSignals:
    return GateSignals(
        distance=distance, by_words=by_words, covers_specific=covers_specific, has_specific=False
    )


def test_gate_or_lets_a_near_vector_through() -> None:
    gate = gate_or(vector=0.30)

    assert gate(_signals(0.29))
    assert not gate(_signals(0.30))
    assert not gate(_signals(None))


def test_gate_or_lets_every_word_hit_through() -> None:
    gate = gate_or(vector=0.30)

    assert gate(_signals(None, by_words=True))
    assert gate(_signals(0.90, by_words=True))


def test_rrf_sums_the_ranks_and_ties_go_to_the_higher_id() -> None:
    assert rrf([[1, 2], [2, 3]])[0] == 2
    assert rrf([[9], [4]]) == [9, 4]
    assert rrf([[], []]) == []


def test_the_fusion_constant_is_sixty() -> None:
    assert retrieval.RRF_K == 60


def test_capped_keeps_the_order_the_total_and_the_per_key_limit() -> None:
    items = [(1, "a"), (2, "a"), (3, "a"), (4, "b"), (5, "c")]

    kept = capped(items, key=lambda item: ord(item[1]), total=3, per_key=2)

    assert kept == [(1, "a"), (2, "a"), (4, "b")]


def test_match_expression_quotes_each_term_and_joins_with_or() -> None:
    assert match_expression(["cerro", 'di"jo', " "]) == '"cerro" OR "di""jo"'
    assert match_expression([]) == ""


def test_covers_needs_every_word_folded() -> None:
    body = "Fuimos con Zeta al cerro Ñandú"

    assert covers(body, frozenset({"zeta", "nandu"}))
    assert not covers(body, frozenset({"zeta", "omega"}))
    assert covers(body, frozenset())


def test_covers_accepts_one_final_s() -> None:
    assert covers("Vino Canarias", frozenset({"canaria"}))
    assert covers("Vino Canaria", frozenset({"canarias"}))
    assert not covers("Vino Canariass", frozenset({"canaria"}))
    # A word under four letters is matched exactly, as Plan 0086's names are.
    assert not covers("los tres", frozenset({"tre"}))
