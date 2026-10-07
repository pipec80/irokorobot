"""Counts-only aggregation of the streaming diagnosis (Plan 0057).

Every rule that turns a number into a reading is a constant below, fixed before the
measurement is run. Nothing here reads, prints or stores model output.

The baseline is the ``full`` variant: the rate and the dominant failure shape describe
production's own prompt. Every other variant is an intervention and is read apart,
against ``full`` on the very turns it ran, with its denominators in view.

Over the ~200-line guideline on purpose: every rule that turns a number into a reading
lives here, in one place, so they cannot drift apart before the run.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from scripts.eval_stream_protocol import StreamOutcome
from scripts.stream_diagnosis_variants import StreamVariant

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from scripts.eval_stream_diagnosis import Observation

PERCENT = 100
SIGNAL_THRESHOLD_PP = 15.0
DRIFT_THRESHOLD_PP = 15.0
DOMINANT_SHAPE_SHARE = 0.5
_BUCKETS = 4
_P50 = 50
_P95 = 95

# Variants that add something to the baseline; every other variant removes or moves it.
_ADDITIVE = frozenset({StreamVariant.PUBLIC_WITH_CONTEXT})
READING_SIGNAL = "exploratory signal"
READING_NO_SIGNAL = "no signal"
READING_INCOMPLETE = "incomplete"
READING_CONTROL = "control"
READING_OPPOSITE = "opposite direction"
_PP_DECIMALS = 6


@dataclass(frozen=True)
class GroupSummary:
    """Outcome counts of one group of observations."""

    valid: int
    invalid_protocol: int
    empty_stream: int
    errors: int
    undue_accept: int
    inconsistent: int

    @property
    def graded(self) -> int:
        """Observations that count toward the rate (provider errors excluded)."""
        return self.valid + self.invalid_protocol + self.empty_stream

    @property
    def fallbacks(self) -> int:
        """Graded replies that would drop to the fallback phrase."""
        return self.invalid_protocol + self.empty_stream

    @property
    def fallback_rate(self) -> float | None:
        """Share of graded replies that would drop to the fallback phrase."""
        if not self.graded:
            return None
        return self.fallbacks / self.graded


def summarize(observations: Iterable[Observation]) -> GroupSummary:
    """Count outcomes, undue accepts and fragmentation-dependent replies."""
    items = list(observations)
    return GroupSummary(
        valid=sum(o.outcome is StreamOutcome.VALID for o in items),
        invalid_protocol=sum(o.outcome is StreamOutcome.INVALID_PROTOCOL for o in items),
        empty_stream=sum(o.outcome is StreamOutcome.EMPTY_STREAM for o in items),
        errors=sum(o.outcome is StreamOutcome.ERROR for o in items),
        undue_accept=sum(o.undue_accept for o in items),
        inconsistent=sum(o.fragmentation_consistent is False for o in items),
    )


def _rate(observations: Iterable[Observation]) -> float | None:
    return summarize(observations).fallback_rate


def baseline_observations(observations: Iterable[Observation]) -> list[Observation]:
    """Return only the ``full`` observations: production's own prompt."""
    return [obs for obs in observations if obs.variant is StreamVariant.FULL]


def group_by_variant_and_source(
    observations: Sequence[Observation],
) -> dict[tuple[StreamVariant, str], list[Observation]]:
    """Group observations by variant (enum order) then source."""
    groups: dict[tuple[StreamVariant, str], list[Observation]] = defaultdict(list)
    for obs in observations:
        groups[(obs.variant, obs.source)].append(obs)
    return dict(
        sorted(groups.items(), key=lambda item: (list(StreamVariant).index(item[0][0]), item[0][1]))
    )


def shape_counts(observations: Iterable[Observation]) -> dict[str, int]:
    """Count the failure shapes of the replies that fell back, most frequent first."""
    counts: dict[str, int] = defaultdict(int)
    for obs in observations:
        if obs.fell_back and obs.shape is not None:
            counts[obs.shape.value] += 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def dominant_shape(counts: dict[str, int]) -> str | None:
    """Return the shape holding at least half of the fallbacks, if exactly one does.

    Two shapes at exactly half each are a mixed picture, not a dominant one.
    """
    total = sum(counts.values())
    leaders = [
        shape for shape, count in counts.items() if total and count / total >= DOMINANT_SHAPE_SHARE
    ]
    return leaders[0] if len(leaders) == 1 else None


def _pp(points: float) -> float:
    """Round percentage points so a threshold met exactly is not missed by float error.

    ``0.7 - 0.55`` is ``0.15000000000000002`` and ``(0.7 - 0.55) * 100`` can fall short
    of 15; the rules say "at least 15 points", so compare after rounding.
    """
    return round(points, _PP_DECIMALS)


@dataclass(frozen=True)
class CaseCounts:
    """What happened to one turn under one variant, against the runs that were expected."""

    fallbacks: int
    errors: int
    graded: int
    expected: int

    @property
    def complete(self) -> bool:
        """Whether every expected run produced a gradable reply (none missing, none failed)."""
        return self.graded == self.expected

    @property
    def fell_every_run(self) -> bool:
        """Whether every expected run was graded and fell back."""
        return self.fallbacks == self.expected


def per_case_counts(
    observations: Iterable[Observation], variant: StreamVariant, runs: int
) -> dict[str, CaseCounts]:
    """Return the counts of every turn of one variant, sorted by label.

    Args:
        observations: Every observation of the run.
        variant: The variant to read.
        runs: The repetitions that were expected per turn; a missing or failed one keeps
            the turn from being ``complete``.
    """
    by_label: dict[str, list[Observation]] = defaultdict(list)
    for obs in observations:
        if obs.variant is variant:
            by_label[obs.label].append(obs)
    result = {}
    for label, items in sorted(by_label.items()):
        summary = summarize(items)
        result[label] = CaseCounts(summary.fallbacks, summary.errors, summary.graded, runs)
    return result


@dataclass(frozen=True)
class Comparison:
    """One variant against ``full`` on the turns where every needed side is complete."""

    variant: StreamVariant
    paired_cases: int
    excluded_cases: int
    baseline_fallbacks: int
    baseline_graded: int
    variant_fallbacks: int
    variant_graded: int
    noise_pp: float | None

    @property
    def baseline_rate(self) -> float | None:
        """The ``full`` rate on the paired turns."""
        return self.baseline_fallbacks / self.baseline_graded if self.baseline_graded else None

    @property
    def variant_rate(self) -> float | None:
        """The variant's rate on the paired turns."""
        return self.variant_fallbacks / self.variant_graded if self.variant_graded else None

    @property
    def change_pp(self) -> float | None:
        """Points the intervention moved the rate in the direction that would be a cause.

        Removing or moving a factor: ``full`` minus the variant. Adding one: the variant
        minus ``full``. ``None`` when there is no complete pair.
        """
        if self.baseline_rate is None or self.variant_rate is None:
            return None
        if self.variant in _ADDITIVE:
            return (self.variant_rate - self.baseline_rate) * PERCENT
        return (self.baseline_rate - self.variant_rate) * PERCENT

    @property
    def reading(self) -> str:
        """An exploratory reading, never a cause.

        A signal needs a change of at least 15 points that also exceeds the noise measured
        on the very same turns. A comparison without a complete control on its turns is
        ``incomplete``: it can never be a signal. A change of the same size in the
        opposite direction (the intervention made the rate worse) is labelled as such, so
        it is not read as "no effect"; it is not a cause either.
        """
        if self.variant is StreamVariant.FULL_REPEAT:
            return READING_CONTROL
        change = self.change_pp
        if change is None or self.noise_pp is None:
            return READING_INCOMPLETE
        change, noise = _pp(change), _pp(self.noise_pp)
        if change >= SIGNAL_THRESHOLD_PP and change > noise:
            return READING_SIGNAL
        if change <= -SIGNAL_THRESHOLD_PP and -change > noise:
            return READING_OPPOSITE
        return READING_NO_SIGNAL


def _turn_rate(counts: CaseCounts) -> float:
    return counts.fallbacks / counts.graded


def compare_to_full(
    observations: Sequence[Observation], variant: StreamVariant, runs: int
) -> Comparison:
    """Compare ``variant`` with ``full`` on the turns where every needed side is complete.

    A turn needs all ``runs`` graded on ``full``, on the variant and, for an
    intervention, on the ``full_repeat`` control. A turn missing any of them is excluded,
    never compared on a different sample.

    The noise is how much repeating ``full`` alone moved each paired turn, averaged as an
    absolute difference turn by turn (opposite swings on two turns never cancel). It is
    measured on exactly the turns the comparison uses.
    """
    full = per_case_counts(observations, StreamVariant.FULL, runs)
    ran = per_case_counts(observations, variant, runs)
    control = per_case_counts(observations, StreamVariant.FULL_REPEAT, runs)
    is_control = variant is StreamVariant.FULL_REPEAT
    paired = [
        label
        for label, counts in ran.items()
        if counts.complete
        and label in full
        and full[label].complete
        and (is_control or (label in control and control[label].complete))
    ]
    noise = None
    if paired and not is_control:
        noise = (
            sum(abs(_turn_rate(full[label]) - _turn_rate(control[label])) for label in paired)
            / len(paired)
            * PERCENT
        )
    return Comparison(
        variant=variant,
        paired_cases=len(paired),
        excluded_cases=len(ran) - len(paired),
        baseline_fallbacks=sum(full[label].fallbacks for label in paired),
        baseline_graded=sum(full[label].graded for label in paired),
        variant_fallbacks=sum(ran[label].fallbacks for label in paired),
        variant_graded=sum(ran[label].graded for label in paired),
        noise_pp=noise,
    )


def comparisons(observations: Sequence[Observation], runs: int) -> list[Comparison]:
    """Compare every variant that ran with ``full``, the noise control first."""
    present = {obs.variant for obs in observations}
    return [
        compare_to_full(observations, variant, runs)
        for variant in StreamVariant
        if variant is not StreamVariant.FULL and variant in present
    ]


def drift_rates(observations: Sequence[Observation]) -> list[float | None]:
    """Return the fallback rate in each quarter of the execution order."""
    if not observations:
        return []
    total = max(o.position for o in observations) + 1
    buckets: list[list[Observation]] = [[] for _ in range(_BUCKETS)]
    for obs in observations:
        buckets[min(_BUCKETS - 1, obs.position * _BUCKETS // total)].append(obs)
    return [_rate(bucket) for bucket in buckets]


def drift_flagged(rates: Sequence[float | None]) -> bool:
    """Whether the highest and lowest quarter differ by at least 15 percentage points."""
    known = [rate for rate in rates if rate is not None]
    return bool(known) and _pp((max(known) - min(known)) * PERCENT) >= DRIFT_THRESHOLD_PP


def _nearest_rank(ordered: Sequence[int], percent: int) -> int:
    """The value at rank ``ceil(n * percent / 100)`` of an ascending list (integer math)."""
    rank = -(-len(ordered) * percent // PERCENT)
    return ordered[max(rank, 1) - 1]


def percentiles(values: Sequence[int]) -> tuple[int, int] | None:
    """Return ``(p50, p95)`` by the nearest-rank method, or ``None`` for no values."""
    if not values:
        return None
    ordered = sorted(values)
    return _nearest_rank(ordered, _P50), _nearest_rank(ordered, _P95)
