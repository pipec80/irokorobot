"""Frozen typed models for the longitudinal-memory evaluation suite (Plan 0046).

Types only, no behavior. Task 2 defined the strict suite schema (enums, actors,
steps, expectations); Task 3 adds the probe/result/summary models plus
``ScoredStep`` (``score_step`` output). Semantic validation lives in
``scripts.eval_longitudinal_memory``; the pure scoring functions live in
``scripts.longitudinal_eval_scoring``.

The models are deliberately strict: the suite is external YAML (a boundary),
so ``ConfigDict(extra="forbid")`` rejects unknown or misspelled fields.
"""

from __future__ import annotations

import enum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class LongitudinalCategory(enum.StrEnum):
    """Canonical longitudinal-memory capability a step exercises."""

    EXTRACTION = "extraction"
    MULTI_SESSION = "multi_session"
    TEMPORALITY = "temporality"
    UPDATE = "update"
    ABSTENTION = "abstention"
    PROVENANCE = "provenance"
    CROSS_PERSON_PRIVACY = "cross_person_privacy"
    COMPLETE_DELETION = "complete_deletion"
    FALSE_MEMORY_RESISTANCE = "false_memory_resistance"


class CapabilityStatus(enum.StrEnum):
    """Outcome of one scored step; ``UNSUPPORTED`` never counts as a pass."""

    PASS = "pass"  # noqa: S105  # enum status member, not a credential
    FAIL = "fail"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


class LongitudinalOperation(enum.StrEnum):
    """Seam a step drives against the current runtime."""

    EXTRACT = "extract"
    PROPOSE = "propose"
    RESTART = "restart"
    RECALL = "recall"
    CORRECT = "correct"
    FORGET = "forget"
    INSPECT_DERIVATIVES = "inspect_derivatives"


class EvaluationActor(BaseModel):
    """One synthetic participant referenced by a scenario's steps."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    actor_id: str
    role: Literal["subject", "other", "unknown"]


class ExpectedObservation(BaseModel):
    """Deterministic expectations scored against one probe observation.

    ``required_any`` inner lists are OR-groups (every group must be satisfied);
    ``forbidden`` substrings must be absent; ``expected_items`` /
    ``forbidden_items`` are canonical extraction keys; ``expected_provenance``
    is attribution independent of any extracted fact subject/object;
    ``required_absent_derivatives`` must be inspected and reported absent.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    required_any: list[list[str]]
    forbidden: list[str]
    expected_items: list[str]
    forbidden_items: list[str]
    expected_provenance: dict[Literal["subject", "assertor", "source"], str]
    required_absent_derivatives: list[str]


class LongitudinalStep(BaseModel):
    """One actor message and its expected longitudinal-memory behavior."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: str
    category: LongitudinalCategory
    operation: LongitudinalOperation
    session: int
    actor_id: str
    message: str
    expected: ExpectedObservation


class LongitudinalScenario(BaseModel):
    """An ordered, independently understandable sequence of steps."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    tags: list[str]
    actors: dict[str, EvaluationActor]
    steps: list[LongitudinalStep]


class LongitudinalSuite(BaseModel):
    """Top-level versioned container for every scenario."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    scenarios: list[LongitudinalScenario]


class ProbeObservation(BaseModel):
    """Driver output for one step (Task 4 produces it; Task 3 scores it)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: CapabilityStatus
    response: str
    observed_items: tuple[str, ...]
    observed_provenance: dict[Literal["subject", "assertor", "source"], str]
    latency_ms: float
    reason: str | None
    inspected_derivatives: dict[str, bool]


class StepResult(BaseModel):
    """Deterministic score for one step; unsupported/error stay visible."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    step_id: str
    category: LongitudinalCategory
    operation: LongitudinalOperation
    status: CapabilityStatus
    response: str
    latency_ms: float
    missing_required: list[list[str]]
    forbidden_found: list[str]
    expected_item_count: int
    matched_item_count: int
    unexpected_item_count: int
    forbidden_items_found: list[str]
    provenance_expected_count: int
    provenance_matched_count: int
    provenance_mismatches: dict[str, tuple[str, str | None]]
    derivative_presence: dict[str, bool]
    reason: str | None


class ScoredStep(BaseModel):
    """``score_step`` output: the verbatim ``StepResult`` plus the raw keys and
    flags ``aggregate_results`` needs (``StepResult`` stays serialization-pure).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    result: StepResult
    expected_item_keys: tuple[str, ...]
    observed_item_keys: tuple[str, ...]
    required_derivative_names: tuple[str, ...]
    inspected_derivative_names: tuple[str, ...]
    passed: bool


class CategorySummary(BaseModel):
    """Per-category totals with complete denominators and latency percentiles."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total: int
    passed: int
    failed: int
    unsupported: int
    errors: int
    pass_rate: float
    latency_p50_ms: float | None
    latency_p95_ms: float | None


class PrecisionRecallMetric(BaseModel):
    """Precision/recall with explicit counts; empty denominator -> ``None``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    precision: float | None
    recall: float | None
    expected_count: int
    observed_count: int
    matched_count: int


class BenchmarkSummary(BaseModel):
    """Whole-run aggregate: complete denominators, no shrunk populations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total: int
    passed: int
    failed: int
    unsupported: int
    errors: int
    forbidden_disclosure_count: int
    forbidden_disclosure_eligible_count: int
    forbidden_disclosure_rate: float | None
    deletion_expected_count: int
    deletion_inspected_count: int
    deletion_absent_count: int
    complete_deletion_rate: float | None
    extraction_precision: float | None
    extraction_recall: float | None
    candidate_by_type: dict[str, PrecisionRecallMetric]
    subject_metric: PrecisionRecallMetric
    object_metric: PrecisionRecallMetric
    relation_metric: PrecisionRecallMetric
    provenance_expected_count: int
    provenance_matched_count: int
    provenance_accuracy: float | None
    truth_current_accuracy: float | None
    correct_abstention_rate: float | None
    by_category: dict[LongitudinalCategory, CategorySummary]
