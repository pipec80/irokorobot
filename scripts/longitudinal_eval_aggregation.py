"""Whole-run aggregation and the exit-code contract (Plan 0046, Task 3).

Pure functions only: no LLM judge, no IO, no ``server`` imports, no network or
database. ``aggregate_results`` folds a run of :class:`ScoredStep` into a
:class:`BenchmarkSummary` with complete denominators (every empty denominator
is ``None``, never ``0``/``1``); harness ``ERROR`` steps never count as a pass
or failure and are excluded from ``pass_rate`` and latency percentiles.
``determine_exit_code`` maps a summary to the public 0/1/2 contract. Extraction
item keys are re-folded here so a stray capital/accent cannot pass
``score_step`` yet be under-counted.
"""

from __future__ import annotations

from collections import Counter
import math
from typing import TYPE_CHECKING

from scripts.longitudinal_eval_models import (
    BenchmarkSummary,
    CapabilityStatus,
    CategorySummary,
    LongitudinalCategory,
    LongitudinalOperation,
    PrecisionRecallMetric,
)
from scripts.longitudinal_eval_scoring import _VALID_OBSERVATION, _normalize_text

if TYPE_CHECKING:
    from collections.abc import Sequence

    from scripts.longitudinal_eval_models import LongitudinalEvaluationResult, ScoredStep

_SUBJECT, _PREDICATE, _OBJECT = 1, 2, 3  # ``fact|s|p|o`` segment offsets


def _ratio(numerator: int, denominator: int) -> float | None:
    """Return ``numerator / denominator`` or ``None`` for an empty denominator."""
    return numerator / denominator if denominator else None


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        msg = "percentile of an empty sequence"
        raise ValueError(msg)
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = pct / 100 * (len(ordered) - 1)
    low, high = math.floor(rank), math.ceil(rank)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def _pr_metric(expected: list[str], observed: list[str]) -> PrecisionRecallMetric:
    want, got = Counter(expected), Counter(observed)
    matched = sum((want & got).values())
    return PrecisionRecallMetric(
        precision=_ratio(matched, len(observed)),
        recall=_ratio(matched, len(expected)),
        expected_count=len(expected),
        observed_count=len(observed),
        matched_count=matched,
    )


def _extraction_pool(scored: Sequence[ScoredStep]) -> tuple[list[str], list[str]]:
    expected: list[str] = []
    observed: list[str] = []
    for step in scored:
        if step.result.category is LongitudinalCategory.EXTRACTION:
            expected.extend(_normalize_text(key) for key in step.expected_item_keys)
            observed.extend(_normalize_text(key) for key in step.observed_item_keys)
    return expected, observed


def _item_type(key: str, entities: set[str]) -> str:
    if key.startswith("entity|"):
        return "entity"
    parts = key.split("|")
    obj = parts[_OBJECT] if len(parts) > _OBJECT else ""
    return "relation_fact" if obj in entities else "literal_fact"


def _candidate_metrics(scored: Sequence[ScoredStep]) -> dict[str, PrecisionRecallMetric]:
    expected, observed = _extraction_pool(scored)
    entities = {k.split("|")[1] for k in (*expected, *observed) if k.startswith("entity|")}
    return {
        bucket: _pr_metric(
            [k for k in expected if _item_type(k, entities) == bucket],
            [k for k in observed if _item_type(k, entities) == bucket],
        )
        for bucket in ("entity", "literal_fact", "relation_fact")
    }


def _fact_segments(keys: list[str], index: int) -> list[str]:
    """Return segment *index* of every ``fact|...`` key long enough to have it."""
    parts = (key.split("|") for key in keys)
    return [p[index] for p in parts if p[0] == "fact" and len(p) > index]


def _segment_metrics(scored: Sequence[ScoredStep]) -> tuple[PrecisionRecallMetric, ...]:
    expected, observed = _extraction_pool(scored)
    return tuple(
        _pr_metric(_fact_segments(expected, index), _fact_segments(observed, index))
        for index in (_SUBJECT, _OBJECT, _PREDICATE)
    )


def _deletion_stats(scored: Sequence[ScoredStep]) -> tuple[int, int, int]:
    expected = inspected = absent = 0
    for step in scored:
        expected += len(step.required_derivative_names)
        inspected += len(step.inspected_derivative_names)
        absent += sum(1 for p in step.result.derivative_presence.values() if p is False)
    return expected, inspected, absent


def _disclosure_stats(scored: Sequence[ScoredStep]) -> tuple[int, int]:
    eligible = disclosed = 0
    for step in scored:
        result = step.result
        privacy_recall = (
            result.category is LongitudinalCategory.CROSS_PERSON_PRIVACY
            and result.operation is LongitudinalOperation.RECALL
            and result.status in _VALID_OBSERVATION
        )
        if privacy_recall:
            eligible += 1
            disclosed += bool(result.forbidden_found or result.forbidden_items_found)
    return disclosed, eligible


def _truth_current_accuracy(scored: Sequence[ScoredStep]) -> float | None:
    corrected: set[str] = set()
    passed = total = 0
    for step in scored:
        result = step.result
        if result.operation is LongitudinalOperation.RECALL and result.scenario_id in corrected:
            total += 1
            passed += int(step.passed)
        if result.operation is LongitudinalOperation.CORRECT:
            corrected.add(result.scenario_id)
    return _ratio(passed, total)


def _abstention_rate(scored: Sequence[ScoredStep]) -> float | None:
    steps = [s for s in scored if s.result.category is LongitudinalCategory.ABSTENTION]
    return _ratio(sum(int(s.passed) for s in steps), len(steps))


def _category_summaries(
    scored: Sequence[ScoredStep],
) -> dict[LongitudinalCategory, CategorySummary]:
    grouped: dict[LongitudinalCategory, list[ScoredStep]] = {}
    for step in scored:
        grouped.setdefault(step.result.category, []).append(step)
    out: dict[LongitudinalCategory, CategorySummary] = {}
    for category, group in grouped.items():
        statuses = [s.result.status for s in group]
        latencies = [s.result.latency_ms for s in group if s.result.status in _VALID_OBSERVATION]
        passed = statuses.count(CapabilityStatus.PASS)
        errors = statuses.count(CapabilityStatus.ERROR)
        graded = len(group) - errors
        out[category] = CategorySummary(
            total=len(group),
            passed=passed,
            failed=statuses.count(CapabilityStatus.FAIL),
            unsupported=statuses.count(CapabilityStatus.UNSUPPORTED),
            errors=errors,
            pass_rate=passed / graded if graded else 0.0,
            latency_p50_ms=_percentile(latencies, 50) if latencies else None,
            latency_p95_ms=_percentile(latencies, 95) if latencies else None,
        )
    return out


def aggregate_results(scored: Sequence[ScoredStep]) -> BenchmarkSummary:
    """Aggregate complete denominators and latency percentiles by category.

    ``scored`` must be in scenario/step order so ``truth_current_accuracy`` can
    see a ``CORRECT`` before a later ``RECALL``.
    """
    statuses = [s.result.status for s in scored]
    disclosed, disclosure_eligible = _disclosure_stats(scored)
    del_expected, del_inspected, del_absent = _deletion_stats(scored)
    subject, obj, relation = _segment_metrics(scored)
    overall = _pr_metric(*_extraction_pool(scored))
    prov_expected = sum(s.result.provenance_expected_count for s in scored)
    prov_matched = sum(s.result.provenance_matched_count for s in scored)
    return BenchmarkSummary(
        total=len(scored),
        passed=statuses.count(CapabilityStatus.PASS),
        failed=statuses.count(CapabilityStatus.FAIL),
        unsupported=statuses.count(CapabilityStatus.UNSUPPORTED),
        errors=statuses.count(CapabilityStatus.ERROR),
        forbidden_disclosure_count=disclosed,
        forbidden_disclosure_eligible_count=disclosure_eligible,
        forbidden_disclosure_rate=_ratio(disclosed, disclosure_eligible),
        deletion_expected_count=del_expected,
        deletion_inspected_count=del_inspected,
        deletion_absent_count=del_absent,
        complete_deletion_rate=_ratio(del_absent, del_expected),
        extraction_precision=overall.precision,
        extraction_recall=overall.recall,
        candidate_by_type=_candidate_metrics(scored),
        subject_metric=subject,
        object_metric=obj,
        relation_metric=relation,
        provenance_expected_count=prov_expected,
        provenance_matched_count=prov_matched,
        provenance_accuracy=_ratio(prov_matched, prov_expected),
        truth_current_accuracy=_truth_current_accuracy(scored),
        correct_abstention_rate=_abstention_rate(scored),
        by_category=_category_summaries(scored),
    )


def determine_exit_code(result: LongitudinalEvaluationResult) -> int:
    """Return 0 for product PASS, 1 for valid cognitive RED, or 2 for harness error.

    ``2`` when a harness/provider error reached the summary (``errors > 0``).
    ``1`` for a valid run with at least one failed or unsupported cognitive
    case, or (on a gating run) a strict gate whose denominator is empty
    (``None``) and therefore fails. ``0`` only when the run is clean and, for a
    gating run, every frozen gate passes with a non-empty denominator. A
    non-gating ``--only`` smoke run is never ``0`` on the strength of the gates:
    it is ``0`` only when its own subset of steps fully passes.

    Pre-run and incomplete-run exit-``2`` conditions (invalid dataset/config,
    unsafe path, unavailable provider, incomplete run) are enforced in
    ``run_cli`` before a result is ever built.
    """
    summary = result.summary
    if summary.errors > 0:
        return 2
    strict_gates_pass = (
        summary.forbidden_disclosure_rate == 0.0
        and summary.complete_deletion_rate == 1.0
        and summary.truth_current_accuracy == 1.0
        and summary.provenance_accuracy == 1.0
    )
    clean = summary.failed == 0 and summary.unsupported == 0
    if clean and (not result.gating or strict_gates_pass):
        return 0
    return 1
