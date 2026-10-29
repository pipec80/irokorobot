"""Task 3 (Plan 0075): the pure statistics for the voice-rate report."""

import pytest

from scripts import cm4_stats


def test_pooled_rate() -> None:
    assert cm4_stats.pooled_rate(3, 12) == 0.25
    assert cm4_stats.pooled_rate(0, 0) == 0.0


def test_rule_of_three() -> None:
    assert cm4_stats.rule_of_three(18) == pytest.approx(0.16667, abs=1e-4)
    assert cm4_stats.rule_of_three(0) == 1.0


def test_wilson_interval_small_case() -> None:
    low, high = cm4_stats.wilson_interval(1, 10)
    assert low == pytest.approx(0.0179, abs=1e-3)
    assert high == pytest.approx(0.4042, abs=1e-3)


def test_wilson_interval_empty_is_zero() -> None:
    assert cm4_stats.wilson_interval(0, 0) == (0.0, 0.0)


def test_bootstrap_by_conversation_is_deterministic_and_ordered() -> None:
    data = [(2, 3), (0, 4), (1, 1), (3, 5)]
    first = cm4_stats.bootstrap_by_conversation(data)
    second = cm4_stats.bootstrap_by_conversation(data)
    assert first == second
    assert first[0] <= first[1]


def test_bootstrap_empty_is_zero() -> None:
    assert cm4_stats.bootstrap_by_conversation([]) == (0.0, 0.0)
