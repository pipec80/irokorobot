"""Evaluate chat-response faithfulness against synthetic memory context."""

from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from contextlib import contextmanager
from datetime import UTC, datetime
import logging
import math
from pathlib import Path
import re
import time
from typing import TYPE_CHECKING, Literal, NoReturn
import unicodedata
from uuid import NAMESPACE_URL, uuid5

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    HouseholdRole,
    IdentityEvidence,
    IdentityEvidenceSource,
)
from server.cognition.models import Confidence, ConfidenceBasis
from server.schemas import (  # noqa: TC002 — Pydantic resolves these fields at runtime
    ConversationTurn,
    MemoryContext,
)
from server.settings import settings
import yaml

from server import llm

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

logger = logging.getLogger(__name__)

_CASE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_]*$")
_TYPOGRAPHIC_TRANSLATION = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2026": "...",
    }
)
_GOLDEN_PATH = Path("tests") / "evals" / "golden_chat_faithfulness.yaml"
_REPORT_DIRECTORY = Path("docs") / "evals"
_MIN_RUNS = 1
_MAX_RUNS = 10
_PERCENT_SCALE = 100
_EVALUATION_RESOLVED_AT = datetime(2026, 8, 10, tzinfo=UTC)

type ProviderChoice = Literal["configured", "ollama", "anthropic"]
type ProviderName = Literal["ollama", "anthropic"]


class ExpectedAssertions(BaseModel):
    """Deterministic content assertions for one golden case."""

    required_any: list[list[str]] = Field(default_factory=list)
    forbidden: list[str] = Field(default_factory=list)

    @field_validator("required_any")
    @classmethod
    def validate_required_groups(cls, groups: list[list[str]]) -> list[list[str]]:
        """Reject empty groups and blank alternatives."""
        if any(not group for group in groups):
            raise ValueError("required assertion group must not be empty")
        if any(not alternative.strip() for group in groups for alternative in group):
            raise ValueError("required assertion alternatives must not be blank")
        return groups

    @field_validator("forbidden")
    @classmethod
    def validate_forbidden(cls, expressions: list[str]) -> list[str]:
        """Reject blank forbidden expressions."""
        if any(not expression.strip() for expression in expressions):
            raise ValueError("forbidden assertion expressions must not be blank")
        return expressions

    @model_validator(mode="after")
    def validate_has_assertion(self) -> ExpectedAssertions:
        """Require at least one positive or negative assertion."""
        if not self.required_any and not self.forbidden:
            raise ValueError("expected assertions must not be empty")
        return self


class EvaluationActivePerson(BaseModel):
    """Explicit manual active-person fixture for one synthetic evaluation."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["manual"]
    person_id: int = Field(strict=True)
    display_name: str

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, display_name: str) -> str:
        """Reject blank display guidance in an explicit evaluation context."""
        if not display_name.strip():
            raise ValueError("active-person display_name must not be blank")
        return display_name

    def to_context(self) -> ActivePersonContext:
        """Build the immutable context passed to the production LLM boundary."""
        confidence = Confidence(
            score=1.0,
            basis=ConfidenceBasis.ASSERTED,
            calibrated=True,
            reason="Explicit evaluation selection",
        )
        return ActivePersonContext(
            person_id=self.person_id,
            display_name=self.display_name,
            status=ActivePersonStatus.IDENTIFIED,
            confidence=confidence,
            role=HouseholdRole.UNKNOWN,
            evidence=(
                IdentityEvidence(
                    evidence_id=uuid5(NAMESPACE_URL, f"eval-active-person:{self.person_id}"),
                    source=IdentityEvidenceSource.MANUAL,
                    candidate_person_id=self.person_id,
                    confidence=confidence,
                    observed_at=_EVALUATION_RESOLVED_AT,
                    reference="evaluation-manual-context",
                ),
            ),
            resolved_at=_EVALUATION_RESOLVED_AT,
        )


class GoldenCase(BaseModel):
    """One synthetic context-faithfulness evaluation case."""

    model_config = ConfigDict(extra="forbid")

    id: str
    tags: list[str] = Field(min_length=1)
    active_person: EvaluationActivePerson | None = None
    question: str
    context: MemoryContext
    history: list[ConversationTurn] = Field(default_factory=list)
    perception: str | None = None
    expected: ExpectedAssertions

    @field_validator("id")
    @classmethod
    def validate_id(cls, case_id: str) -> str:
        """Require a stable identifier suitable for ``--only``."""
        if not _CASE_ID_PATTERN.fullmatch(case_id):
            raise ValueError("case id must use lowercase letters, digits, and underscores")
        return case_id

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, tags: list[str]) -> list[str]:
        """Reject blank category tags."""
        if any(not tag.strip() for tag in tags):
            raise ValueError("case tags must not be blank")
        return tags

    @field_validator("question")
    @classmethod
    def validate_question(cls, question: str) -> str:
        """Reject questions containing only whitespace."""
        if not question.strip():
            raise ValueError("question must not be empty")
        return question


class GoldenSuite(BaseModel):
    """Versioned collection of golden chat cases."""

    version: int
    cases: list[GoldenCase] = Field(min_length=1)

    @field_validator("version")
    @classmethod
    def validate_version(cls, version: int) -> int:
        """Accept only the current golden-suite schema version."""
        if version != 1:
            raise ValueError("version must be exactly 1")
        return version

    @model_validator(mode="after")
    def validate_unique_ids(self) -> GoldenSuite:
        """Ensure case identifiers are unique within the suite."""
        case_ids = [case.id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("case ids must be unique")
        return self


class AssertionResult(BaseModel):
    """Deterministic assertion outcome for one model response."""

    passed: bool
    required_groups_satisfied: int
    required_groups_total: int
    missing_required: list[list[str]]
    forbidden_found: list[str]


class CaseRunResult(BaseModel):
    """Result of one case repetition, including provider failures."""

    case_id: str
    tags: list[str]
    repetition: int = Field(ge=1)
    response: str
    emotion: str
    latency_ms: float = Field(ge=0)
    assertion: AssertionResult
    error: str | None = None


class MetricSummary(BaseModel):
    """Aggregated faithfulness and latency metrics for a result subset."""

    total_runs: int = Field(ge=0)
    error_runs: int = Field(ge=0)
    case_pass_rate: float = Field(ge=0, le=1)
    required_group_recall: float = Field(ge=0, le=1)
    forbidden_violation_rate: float = Field(ge=0, le=1)
    stability: float = Field(ge=0, le=1)
    latency_p50_ms: float | None = Field(default=None, ge=0)
    latency_p95_ms: float | None = Field(default=None, ge=0)


class EvaluationResult(BaseModel):
    """Complete repeatable evaluation result ready for Markdown rendering."""

    generated_at: datetime
    provider: ProviderName
    model: str
    runs: int = Field(ge=_MIN_RUNS, le=_MAX_RUNS)
    results: list[CaseRunResult]
    summary: MetricSummary
    by_tag: dict[str, MetricSummary]


class CliOptions(BaseModel):
    """Validated command-line options for the chat evaluation."""

    provider: ProviderChoice = "configured"
    runs: int = Field(default=3, ge=_MIN_RUNS, le=_MAX_RUNS)
    only: str | None = None
    output: Path | None = None
    min_pass_rate: float | None = Field(default=None, ge=0, le=1)


def load_suite(path: Path) -> GoldenSuite:
    """Load and validate a versioned golden suite from YAML.

    Args:
        path: YAML file containing the synthetic evaluation cases.

    Returns:
        Fully validated suite using the production memory/history schemas.

    Raises:
        ValueError: If the file cannot be read, parsed, or validated.
    """
    try:
        raw_data: object = yaml.safe_load(path.read_text(encoding="utf-8"))
        return GoldenSuite.model_validate(raw_data)
    except OSError as exc:
        raise ValueError(f"could not read golden suite: {path}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML in golden suite: {path}") from exc
    except ValidationError as exc:
        raise ValueError(f"invalid golden suite schema: {exc}") from exc


def normalize_text(value: str) -> str:
    """Normalize response text for deterministic expression matching.

    Args:
        value: Text to normalize.

    Returns:
        Lowercase, accent-free text with normalized typography and whitespace.
    """
    typographic_normalized = value.translate(_TYPOGRAPHIC_TRANSLATION).lower()
    decomposed = unicodedata.normalize("NFKD", typographic_normalized)
    accent_free = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(accent_free.split())


def score_response(case: GoldenCase, response: str) -> AssertionResult:
    """Score one response against a golden case's deterministic assertions.

    Args:
        case: Golden case containing required and forbidden expressions.
        response: Full textual model response.

    Returns:
        Assertion details including missing groups and forbidden matches.
    """
    normalized_response = normalize_text(response)
    missing_required = [
        group
        for group in case.expected.required_any
        if not any(_expression_matches(normalized_response, alternative) for alternative in group)
    ]
    forbidden_found = [
        expression
        for expression in case.expected.forbidden
        if _expression_matches(normalized_response, expression)
    ]
    required_total = len(case.expected.required_any)
    required_satisfied = required_total - len(missing_required)
    return AssertionResult(
        passed=not missing_required and not forbidden_found,
        required_groups_satisfied=required_satisfied,
        required_groups_total=required_total,
        missing_required=missing_required,
        forbidden_found=forbidden_found,
    )


def select_cases(suite: GoldenSuite, only: str | None) -> list[GoldenCase]:
    """Select all cases or one exact identifier before provider execution.

    Args:
        suite: Validated golden suite.
        only: Optional exact case identifier.

    Returns:
        Cases selected for execution, preserving suite order.

    Raises:
        ValueError: If ``only`` does not identify a suite case.
    """
    if only is None:
        return list(suite.cases)
    selected = [case for case in suite.cases if case.id == only]
    if not selected:
        raise ValueError(f"golden case {only!r} does not exist")
    return selected


async def run_evaluation(
    cases: list[GoldenCase],
    *,
    runs: int,
    provider: ProviderChoice,
) -> EvaluationResult:
    """Execute selected golden cases sequentially against production generation.

    Args:
        cases: Validated synthetic cases in execution order.
        runs: Repetitions per case, from 1 through 10.
        provider: Configured provider or a temporary explicit override.

    Returns:
        Full per-run results plus global and per-tag aggregate metrics.

    Raises:
        ValueError: If the run count or selected-case list is invalid.
    """
    if not _MIN_RUNS <= runs <= _MAX_RUNS:
        raise ValueError(f"runs must be between {_MIN_RUNS} and {_MAX_RUNS}")
    if not cases:
        raise ValueError("at least one golden case must be selected")

    with _temporary_provider(provider) as effective_provider:
        model = _effective_model(effective_provider)
        results: list[CaseRunResult] = []
        for case in cases:
            for repetition in range(1, runs + 1):
                results.append(await _run_case(case, repetition))
        summary, by_tag = aggregate_results(results)
        return EvaluationResult(
            generated_at=datetime.now(UTC),
            provider=effective_provider,
            model=model,
            runs=runs,
            results=results,
            summary=summary,
            by_tag=by_tag,
        )


def aggregate_results(
    results: list[CaseRunResult],
) -> tuple[MetricSummary, dict[str, MetricSummary]]:
    """Aggregate global and per-tag faithfulness metrics.

    Args:
        results: Completed case repetitions.

    Returns:
        Global summary and summaries keyed by tag.
    """
    summary = _summarize(results)
    tags = sorted({tag for result in results for tag in result.tags})
    by_tag = {tag: _summarize([result for result in results if tag in result.tags]) for tag in tags}
    return summary, by_tag


def percentile(values: list[float], percentage: float) -> float:
    """Calculate a linearly interpolated percentile without external libraries.

    Args:
        values: Non-empty numeric samples.
        percentage: Percentile from 0 through 100.

    Returns:
        Interpolated percentile value; a single sample returns itself.

    Raises:
        ValueError: If no values exist or the percentile is outside bounds.
    """
    if not values:
        raise ValueError("percentile requires at least one value")
    if not 0 <= percentage <= _PERCENT_SCALE:
        raise ValueError(f"percentage must be between 0 and {_PERCENT_SCALE}")
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentage / _PERCENT_SCALE
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return ordered[lower_index]
    fraction = position - lower_index
    return ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * fraction


def determine_exit_code(
    summary: MetricSummary,
    *,
    min_pass_rate: float | None,
) -> int:
    """Determine CLI status from infrastructure errors and an optional threshold.

    Args:
        summary: Global evaluation metrics.
        min_pass_rate: Optional minimum accepted case pass rate.

    Returns:
        Zero for a valid baseline, or one for provider errors/threshold failure.
    """
    if summary.error_runs:
        return 1
    if min_pass_rate is not None and summary.case_pass_rate < min_pass_rate:
        return 1
    return 0


def render_report(evaluation: EvaluationResult) -> str:
    """Render a complete evaluation result as auditable Markdown.

    Args:
        evaluation: Full evaluation result.

    Returns:
        Markdown containing metadata, metrics, and complete model responses.
    """
    lines = [
        "# Chat context faithfulness evaluation",
        "",
        f"- Generated (UTC): `{evaluation.generated_at.isoformat()}`",
        f"- Provider: `{evaluation.provider}`",
        f"- Effective model: `{evaluation.model}`",
        f"- Repetitions per case: `{evaluation.runs}`",
        "",
        "## Global metrics",
        "",
        *_metric_table(evaluation.summary),
        "",
        "## Metrics by tag",
        "",
        "| Tag | Case pass rate | Required-group recall | Forbidden violation rate | "
        "Stability | Errors | p50 ms | p95 ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for tag, summary in evaluation.by_tag.items():
        lines.append(
            f"| {tag} | {_rate(summary.case_pass_rate)} | "
            f"{_rate(summary.required_group_recall)} | "
            f"{_rate(summary.forbidden_violation_rate)} | {_rate(summary.stability)} | "
            f"{summary.error_runs} | {_latency(summary.latency_p50_ms)} | "
            f"{_latency(summary.latency_p95_ms)} |"
        )
    lines.extend(["", "## Case repetitions"])
    for result in evaluation.results:
        lines.extend(_render_case_result(result))
    return "\n".join(lines) + "\n"


def write_report(path: Path, content: str) -> None:
    """Persist a Markdown report without overwriting prior evidence.

    Args:
        path: Destination report path.
        content: Fully rendered Markdown.

    Raises:
        FileExistsError: If the destination already exists.
        OSError: If the directory or file cannot be created.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as report_file:
        report_file.write(content)


def parse_cli_args(argv: Sequence[str] | None = None) -> CliOptions:
    """Parse and validate command-line arguments.

    Args:
        argv: Optional arguments excluding the executable name.

    Returns:
        Typed, validated CLI options.
    """
    parser = argparse.ArgumentParser(
        description="Evaluate LLM faithfulness to synthetic server context"
    )
    parser.add_argument(
        "--provider",
        choices=("configured", "ollama", "anthropic"),
        default="configured",
    )
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--only")
    parser.add_argument("--output")
    parser.add_argument("--min-pass-rate", type=float)
    namespace = parser.parse_args(argv)
    output = Path(namespace.output).expanduser().resolve() if namespace.output else None
    return CliOptions(
        provider=namespace.provider,
        runs=namespace.runs,
        only=namespace.only,
        output=output,
        min_pass_rate=namespace.min_pass_rate,
    )


async def run_cli(options: CliOptions) -> int:
    """Run the real-provider CLI workflow and write its Markdown report.

    Args:
        options: Validated command-line options.

    Returns:
        Process exit code.
    """
    suite = load_suite(_GOLDEN_PATH)
    cases = select_cases(suite, options.only)
    evaluation = await run_evaluation(cases, runs=options.runs, provider=options.provider)
    output = options.output or _default_report_path(evaluation)
    write_report(output, render_report(evaluation))
    logger.info(
        "Evaluation complete: provider=%s model=%s pass_rate=%.3f report=%s",
        evaluation.provider,
        evaluation.model,
        evaluation.summary.case_pass_rate,
        output,
    )
    return determine_exit_code(
        evaluation.summary,
        min_pass_rate=options.min_pass_rate,
    )


def main() -> NoReturn:
    """Run the command-line evaluation and exit with its status."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    try:
        options = parse_cli_args()
        exit_code = asyncio.run(run_cli(options))
    except (ValueError, OSError) as exc:
        logger.error("Evaluation failed: %s", exc)
        exit_code = 1
    raise SystemExit(exit_code)


def _expression_matches(normalized_response: str, expression: str) -> bool:
    """Return whether a normalized response contains an expected expression."""
    normalized_expression = normalize_text(expression)
    if " " in normalized_expression:
        return normalized_expression in normalized_response
    pattern = rf"(?<!\w){re.escape(normalized_expression)}(?!\w)"
    return re.search(pattern, normalized_response) is not None


async def _run_case(case: GoldenCase, repetition: int) -> CaseRunResult:
    """Execute and score one golden-case repetition."""
    started_at = time.perf_counter()
    try:
        response, emotion = await llm.generate_response(
            case.question,
            context=case.context,
            history=case.history,
            active_person=case.active_person.to_context() if case.active_person else None,
            perception=case.perception,
        )
        assertion = score_response(case, response)
        error = None
    except Exception as exc:
        response = ""
        emotion = ""
        assertion = score_response(case, response)
        error = f"{type(exc).__name__}: provider call failed"
        logger.warning(
            "Provider call failed for case=%s repetition=%d error_type=%s",
            case.id,
            repetition,
            type(exc).__name__,
        )
    latency_ms = (time.perf_counter() - started_at) * 1000
    return CaseRunResult(
        case_id=case.id,
        tags=case.tags,
        repetition=repetition,
        response=response,
        emotion=emotion,
        latency_ms=latency_ms,
        assertion=assertion,
        error=error,
    )


@contextmanager
def _temporary_provider(provider: ProviderChoice) -> Iterator[ProviderName]:
    """Temporarily select a provider and restore configuration unconditionally."""
    original_provider = settings.llm_provider
    effective_provider = _resolve_provider(provider)
    try:
        settings.llm_provider = effective_provider
        yield effective_provider
    finally:
        settings.llm_provider = original_provider


def _resolve_provider(provider: ProviderChoice) -> ProviderName:
    """Resolve ``configured`` to one supported production provider."""
    configured_provider = settings.llm_provider if provider == "configured" else provider
    if configured_provider == "ollama":
        return "ollama"
    if configured_provider == "anthropic":
        return "anthropic"
    raise ValueError("configured LLM provider must be 'ollama' or 'anthropic'")


def _effective_model(provider: ProviderName) -> str:
    """Return the configured model for an effective provider."""
    if provider == "ollama":
        return settings.ollama_model
    return settings.anthropic_model


def _summarize(results: list[CaseRunResult]) -> MetricSummary:
    """Calculate metrics for a non-tagged subset of case repetitions."""
    if not results:
        return MetricSummary(
            total_runs=0,
            error_runs=0,
            case_pass_rate=0,
            required_group_recall=1,
            forbidden_violation_rate=0,
            stability=0,
        )
    total_runs = len(results)
    required_total = sum(result.assertion.required_groups_total for result in results)
    required_satisfied = sum(result.assertion.required_groups_satisfied for result in results)
    grouped: defaultdict[str, list[CaseRunResult]] = defaultdict(list)
    for result in results:
        grouped[result.case_id].append(result)
    stable_cases = sum(
        all(item.error is None and item.assertion.passed for item in repetitions)
        for repetitions in grouped.values()
    )
    latencies = [result.latency_ms for result in results if result.error is None]
    return MetricSummary(
        total_runs=total_runs,
        error_runs=sum(result.error is not None for result in results),
        case_pass_rate=sum(result.error is None and result.assertion.passed for result in results)
        / total_runs,
        required_group_recall=required_satisfied / required_total if required_total else 1,
        forbidden_violation_rate=sum(bool(result.assertion.forbidden_found) for result in results)
        / total_runs,
        stability=stable_cases / len(grouped),
        latency_p50_ms=percentile(latencies, 50) if latencies else None,
        latency_p95_ms=percentile(latencies, 95) if latencies else None,
    )


def _metric_table(summary: MetricSummary) -> list[str]:
    """Render the global metric summary as a Markdown table."""
    return [
        "| Metric | Value |",
        "|---|---:|",
        f"| Case pass rate | {_rate(summary.case_pass_rate)} |",
        f"| Required-group recall | {_rate(summary.required_group_recall)} |",
        f"| Forbidden violation rate | {_rate(summary.forbidden_violation_rate)} |",
        f"| Stability | {_rate(summary.stability)} |",
        f"| Provider error runs | {summary.error_runs}/{summary.total_runs} |",
        f"| Latency p50 | {_latency(summary.latency_p50_ms)} ms |",
        f"| Latency p95 | {_latency(summary.latency_p95_ms)} ms |",
    ]


def _render_case_result(result: CaseRunResult) -> list[str]:
    """Render one complete case repetition."""
    status = "ERROR" if result.error else ("PASS" if result.assertion.passed else "FAIL")
    missing = "; ".join(" | ".join(group) for group in result.assertion.missing_required)
    forbidden = "; ".join(result.assertion.forbidden_found)
    response_lines = result.response.splitlines() or ["_(empty response)_"]
    return [
        "",
        f"### `{result.case_id}` — repetition {result.repetition}",
        "",
        f"- Status: **{status}**",
        f"- Tags: {', '.join(result.tags)}",
        f"- Emotion: `{result.emotion or 'n/a'}`",
        f"- Latency: `{result.latency_ms:.3f} ms`",
        f"- Missing required groups: {missing or 'none'}",
        f"- Forbidden expressions found: {forbidden or 'none'}",
        f"- Error: `{result.error}`" if result.error else "- Error: none",
        "",
        "**Full response:**",
        "",
        *(f"> {line}" for line in response_lines),
    ]


def _rate(value: float) -> str:
    """Format a ratio as a percentage."""
    return f"{value:.2%}"


def _latency(value: float | None) -> str:
    """Format an optional latency value."""
    return "n/a" if value is None else f"{value:.3f}"


def _default_report_path(evaluation: EvaluationResult) -> Path:
    """Build the timestamped default report path."""
    timestamp = evaluation.generated_at.strftime("%Y-%m-%d-%H%M%S")
    return _REPORT_DIRECTORY / f"{timestamp}-chat-{evaluation.provider}.md"


if __name__ == "__main__":
    main()
