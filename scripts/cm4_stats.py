"""Task 3 (Plan 0075): pure statistics for the voice-rate report.

Pooled rates, a Wilson 95 % interval, the rule-of-three upper bound for a zero
cell, and a by-conversation bootstrap interval (conversations are the resampling
unit because turns within one are correlated). No I/O; deterministic under a
fixed seed.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "bootstrap_by_conversation",
    "pooled_rate",
    "rule_of_three",
    "wilson_interval",
]

# 97.5th percentile of the standard normal — the two-sided 95 % z.
_Z95 = 1.96
_LOW_PCT = 0.025
_HIGH_PCT = 0.975
_DEFAULT_RESAMPLES = 2000
_DEFAULT_SEED = 75


def pooled_rate(successes: int, n: int) -> float:
    """Return ``successes / n`` as a pooled rate, or ``0.0`` when ``n`` is zero.

    Args:
        successes: Count of successes (for example verified clips).
        n: Total count (for example clips).

    Returns:
        The pooled rate in ``[0, 1]``.
    """
    return successes / n if n else 0.0


def rule_of_three(n: int) -> float:
    """Return the rule-of-three 95 % upper bound for zero successes in *n* trials.

    Args:
        n: Number of trials with no observed success.

    Returns:
        ``3 / n`` for ``n > 0`` (about the 95 % upper bound), or ``1.0`` when
        ``n`` is zero (nothing is ruled out).
    """
    return 3.0 / n if n else 1.0


def wilson_interval(successes: int, n: int) -> tuple[float, float]:
    """Return the Wilson score 95 % interval for *successes* out of *n*.

    Args:
        successes: Count of successes.
        n: Total count.

    Returns:
        ``(low, high)`` bounds in ``[0, 1]``; ``(0.0, 0.0)`` when ``n`` is zero.
    """
    if n == 0:
        return (0.0, 0.0)
    phat = successes / n
    denominator = 1.0 + _Z95**2 / n
    center = (phat + _Z95**2 / (2 * n)) / denominator
    margin = (_Z95 / denominator) * math.sqrt(phat * (1 - phat) / n + _Z95**2 / (4 * n**2))
    return (max(0.0, center - margin), min(1.0, center + margin))


def bootstrap_by_conversation(
    per_conversation: Sequence[tuple[int, int]],
    *,
    resamples: int = _DEFAULT_RESAMPLES,
    seed: int = _DEFAULT_SEED,
) -> tuple[float, float]:
    """Return a by-conversation bootstrap 95 % interval of the pooled verified rate.

    Each resample draws whole conversations with replacement and recomputes the
    pooled rate (sum of verified clips over sum of clips), so the interval
    reflects the correlation of turns inside a conversation.

    Args:
        per_conversation: One ``(verified, total)`` pair per conversation.
        resamples: Bootstrap resamples.
        seed: Fixed seed for determinism.

    Returns:
        ``(low, high)`` percentile bounds; ``(0.0, 0.0)`` for an empty input.
    """
    if not per_conversation:
        return (0.0, 0.0)
    rng = random.Random(seed)  # noqa: S311 -- bootstrap resampling, not a cryptographic RNG
    count = len(per_conversation)
    rates: list[float] = []
    for _ in range(resamples):
        sample = [per_conversation[rng.randrange(count)] for _ in range(count)]
        total = sum(total for _verified, total in sample)
        verified = sum(verified for verified, _total in sample)
        rates.append(verified / total if total else 0.0)
    rates.sort()
    low = rates[int(_LOW_PCT * resamples)]
    high = rates[int(_HIGH_PCT * resamples) - 1]
    return (low, high)
