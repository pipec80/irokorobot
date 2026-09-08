"""Deterministic Markdown report for the longitudinal-memory eval (Plan 0046).

``render_report`` prints one complete, ordering-stable report:

* every one of the nine canonical categories appears in the coverage table,
  even when no case executed or every case was ``unsupported``;
* every frozen metric field is printed literally -- precision/recall,
  candidate-by-type, subject/object/relation segments, the abstention rate and
  the truth-current accuracy -- never replaced by a category pass rate;
* unsupported cases are listed with the exact missing capability so no
  category silently leaves the denominator;
* the report may contain synthetic model output (the dataset is invented) but
  the metadata it echoes is already secret-free.

The frozen ``LongitudinalEvaluationResult`` carries no scenario tag list, so the
scenario-coverage table reconstructs the ``category:*`` / operation coverage
from the step results instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.longitudinal_eval_models import CapabilityStatus, LongitudinalCategory

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from scripts.longitudinal_eval_models import (
        BenchmarkSummary,
        LongitudinalEvaluationResult,
        PrecisionRecallMetric,
        RunMetadata,
        StepResult,
    )

# (label, BenchmarkSummary attribute, target value that passes the gate).
_GATES: tuple[tuple[str, str, float], ...] = (
    ("forbidden_disclosure_rate", "forbidden_disclosure_rate", 0.0),
    ("complete_deletion_rate", "complete_deletion_rate", 1.0),
    ("truth_current_accuracy", "truth_current_accuracy", 1.0),
    ("provenance_accuracy", "provenance_accuracy", 1.0),
)


def render_report(result: LongitudinalEvaluationResult) -> str:
    """Render one complete, deterministic Markdown report.

    Args:
        result: The finished evaluation result.

    Returns:
        A Markdown document ending in a single trailing newline.
    """
    sections = [
        _header(result),
        _metadata_section(result.metadata),
        _headline_section(result.summary),
        _gate_section(result.summary),
        _extraction_section(result.summary),
        _rate_section(result.summary),
        _deletion_section(result.summary),
        _category_table(result.summary),
        _scenario_coverage(result.results),
        _unsupported_table(result.results),
        _step_table(result.results),
    ]
    return "\n\n".join(sections) + "\n"


def _fmt(value: float | None) -> str:
    """Format a rate/accuracy: ``None`` -> an explicit empty-denominator note."""
    return "n/a (empty denominator)" if value is None else f"{value:.4f}"


def _ms(value: float | None) -> str:
    """Format a latency percentile in milliseconds."""
    return "-" if value is None else f"{value:.1f}"


def _format_model_settings(settings: Mapping[str, object]) -> str:
    """Render model knobs as a deterministic ``key=value`` list (``-`` when empty)."""
    if not settings:
        return "-"
    return "; ".join(f"{key}={settings[key]}" for key in sorted(settings))


def _ordered_unique(values: Iterable[str]) -> list[str]:
    """Return ``values`` de-duplicated, first-seen order preserved."""
    seen: dict[str, None] = {}
    for value in values:
        seen.setdefault(value, None)
    return list(seen)


def _header(result: LongitudinalEvaluationResult) -> str:
    mode = "gating baseline" if result.gating else "non-gating (--only smoke / debug)"
    return (
        f"# Longitudinal-memory evaluation report\n\n"
        f"- Generated: {result.metadata.generated_at.isoformat()}\n"
        f"- Mode: {mode}\n"
        f"- Steps scored: {result.summary.total}"
    )


def _metadata_section(metadata: RunMetadata) -> str:
    rows = [
        "## Run metadata",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| branch | {metadata.branch} |",
        f"| source_commit | {metadata.source_commit} |",
        f"| worktree_dirty | {metadata.worktree_dirty} |",
        f"| worktree_status lines | {len(metadata.worktree_status)} |",
        f"| dataset_path | {metadata.dataset_path} |",
        f"| dataset_version | {metadata.dataset_version} |",
        f"| dataset_sha256 | {metadata.dataset_sha256} |",
        f"| python_version | {metadata.python_version} |",
        f"| provider | {metadata.provider} |",
        f"| ollama_url | {metadata.ollama_url} |",
        f"| chat_model | {metadata.chat_model} |",
        f"| consolidation_model | {metadata.consolidation_model} |",
        f"| model_settings | {_format_model_settings(metadata.model_settings)} |",
        f"| sanitized_command | {' '.join(metadata.sanitized_command)} |",
        f"| reserved_term_count | {metadata.reserved_term_count} |",
        f"| temporary_database_name | {metadata.temporary_database_name} |",
        f"| service_preflight | {metadata.service_preflight} |",
    ]
    return "\n".join(rows)


def _headline_section(summary: BenchmarkSummary) -> str:
    return (
        "## Headline\n\n"
        f"- total: {summary.total}\n"
        f"- passed: {summary.passed}\n"
        f"- failed: {summary.failed}\n"
        f"- unsupported: {summary.unsupported}\n"
        f"- errors: {summary.errors}"
    )


def _gate_section(summary: BenchmarkSummary) -> str:
    rows = [
        "## Frozen cognitive gates",
        "",
        "Each gate passes only with a non-empty denominator; `None` fails.",
        "",
        "| Gate | Target | Observed | Verdict |",
        "|---|---|---|---|",
    ]
    for label, attr, target in _GATES:
        observed: float | None = getattr(summary, attr)
        verdict = "PASS" if observed == target else "FAIL"
        rows.append(f"| {label} | {target:.4f} | {_fmt(observed)} | {verdict} |")
    return "\n".join(rows)


def _extraction_section(summary: BenchmarkSummary) -> str:
    rows = [
        "## Extraction metrics (reported, no CM-0 release threshold)",
        "",
        "| Metric | Precision | Recall | Expected | Observed | Matched |",
        "|---|---|---|---|---|---|",
        f"| overall | {_fmt(summary.extraction_precision)} | {_fmt(summary.extraction_recall)} "
        "| - | - | - |",
    ]
    for name in ("entity", "literal_fact", "relation_fact"):
        metric = summary.candidate_by_type.get(name)
        rows.append(_pr_row(f"candidate:{name}", metric))
    rows.append(_pr_row("fact.subject", summary.subject_metric))
    rows.append(_pr_row("fact.object", summary.object_metric))
    rows.append(_pr_row("fact.relation", summary.relation_metric))
    return "\n".join(rows)


def _pr_row(label: str, metric: PrecisionRecallMetric | None) -> str:
    if metric is None:
        return f"| {label} | n/a | n/a | 0 | 0 | 0 |"
    return (
        f"| {label} | {_fmt(metric.precision)} | {_fmt(metric.recall)} "
        f"| {metric.expected_count} | {metric.observed_count} | {metric.matched_count} |"
    )


def _rate_section(summary: BenchmarkSummary) -> str:
    return (
        "## Rates\n\n"
        f"- correct_abstention_rate: {_fmt(summary.correct_abstention_rate)}\n"
        f"- truth_current_accuracy: {_fmt(summary.truth_current_accuracy)}\n"
        f"- provenance_accuracy: {_fmt(summary.provenance_accuracy)} "
        f"({summary.provenance_matched_count}/{summary.provenance_expected_count} fields)"
    )


def _deletion_section(summary: BenchmarkSummary) -> str:
    return (
        "## Complete deletion\n\n"
        f"- deletion_expected_count: {summary.deletion_expected_count}\n"
        f"- deletion_inspected_count: {summary.deletion_inspected_count}\n"
        f"- deletion_absent_count: {summary.deletion_absent_count}\n"
        f"- complete_deletion_rate: {_fmt(summary.complete_deletion_rate)}\n"
        f"- forbidden_disclosure: {summary.forbidden_disclosure_count}"
        f"/{summary.forbidden_disclosure_eligible_count} eligible recalls"
    )


def _category_table(summary: BenchmarkSummary) -> str:
    rows = [
        "## Category coverage (all nine canonical categories)",
        "",
        "| Category | Total | Passed | Failed | Unsupported | Errors | Pass rate | p50 ms | p95 ms |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for category in LongitudinalCategory:
        entry = summary.by_category.get(category)
        if entry is None:
            rows.append(f"| {category.value} | 0 | 0 | 0 | 0 | 0 | not executed | - | - |")
            continue
        rows.append(
            f"| {category.value} | {entry.total} | {entry.passed} | {entry.failed} "
            f"| {entry.unsupported} | {entry.errors} | {entry.pass_rate:.4f} "
            f"| {_ms(entry.latency_p50_ms)} | {_ms(entry.latency_p95_ms)} |"
        )
    return "\n".join(rows)


def _scenario_coverage(results: Sequence[StepResult]) -> str:
    rows = [
        "## Scenario coverage",
        "",
        "Reconstructed from step results (the frozen result model carries no scenario tag "
        "list). The category and operation columns stand in for the suite's `category:*` and "
        "domain/seam tags so no category leaves the denominator.",
        "",
        "| Scenario | Steps | Categories | Operations | Passed | Unsupported |",
        "|---|---|---|---|---|---|",
    ]
    for scenario_id in _ordered_unique(step_result.scenario_id for step_result in results):
        group = [step_result for step_result in results if step_result.scenario_id == scenario_id]
        cats = ", ".join(_ordered_unique(step_result.category.value for step_result in group))
        ops = ", ".join(_ordered_unique(step_result.operation.value for step_result in group))
        passed = sum(1 for step_result in group if step_result.status is CapabilityStatus.PASS)
        unsupported = sum(
            1 for step_result in group if step_result.status is CapabilityStatus.UNSUPPORTED
        )
        rows.append(f"| {scenario_id} | {len(group)} | {cats} | {ops} | {passed} | {unsupported} |")
    return "\n".join(rows)


def _unsupported_table(results: Sequence[StepResult]) -> str:
    unsupported = [
        step_result for step_result in results if step_result.status is CapabilityStatus.UNSUPPORTED
    ]
    rows = [
        "## Unsupported cases (no fabricated observation)",
        "",
        f"{len(unsupported)} step result(s) recorded a missing capability.",
        "",
        "| Scenario | Step | Category | Operation | Missing capability |",
        "|---|---|---|---|---|",
    ]
    for step_result in unsupported:
        rows.append(
            f"| {step_result.scenario_id} | {step_result.step_id} | {step_result.category.value} "
            f"| {step_result.operation.value} | {step_result.reason or ''} |"
        )
    return "\n".join(rows)


def _step_table(results: Sequence[StepResult]) -> str:
    rows = [
        "## Every step",
        "",
        "| Scenario | Step | Category | Operation | Status | Latency ms | Response |",
        "|---|---|---|---|---|---|---|",
    ]
    for step_result in results:
        response = step_result.response.replace("|", "\\|").replace("\n", " ")
        rows.append(
            f"| {step_result.scenario_id} | {step_result.step_id} | {step_result.category.value} "
            f"| {step_result.operation.value} | {step_result.status.value} "
            f"| {step_result.latency_ms:.1f} | {response} |"
        )
    return "\n".join(rows)
