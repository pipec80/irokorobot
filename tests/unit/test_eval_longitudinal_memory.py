"""Deterministic RED/GREEN coverage for the longitudinal-memory suite.

These tests never reach Ollama, the network or a real database. They pin the
frozen schema, the semantic rules enforced by ``load_suite``, the privacy
rules enforced by ``validate_dataset_privacy``, a coverage check on the
committed version-1 YAML suite, and (Task 3) the deterministic scoring layer
in ``scripts.longitudinal_eval_scoring`` /
``scripts.longitudinal_eval_aggregation``.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import hashlib
import importlib
import inspect
from pathlib import Path
import runpy
import sys
from typing import TYPE_CHECKING, Literal, cast
from unittest.mock import Mock

import httpx
import pytest
from server.exceptions import BrainMemoryError
from server.settings import settings
import yaml

if TYPE_CHECKING:
    from collections.abc import Callable

from scripts import (
    longitudinal_eval_driver as driver_mod,
    longitudinal_eval_metadata as metadata_mod,
    longitudinal_eval_runner as runner,
)
from scripts.eval_longitudinal_memory import load_suite, parse_cli_args, validate_dataset_privacy
from scripts.longitudinal_eval_aggregation import aggregate_results, determine_exit_code
from scripts.longitudinal_eval_driver import CurrentRuntimeDriver, unsupported_observation
from scripts.longitudinal_eval_metadata import (
    collect_run_metadata,
    sanitize_command,
    sanitize_url,
)
from scripts.longitudinal_eval_models import (
    BenchmarkSummary,
    CapabilityStatus,
    CliOptions,
    ExpectedObservation,
    LongitudinalCategory,
    LongitudinalEvaluationResult,
    LongitudinalOperation,
    LongitudinalScenario,
    LongitudinalStep,
    LongitudinalSuite,
    ProbeObservation,
    RunMetadata,
    ScoredStep,
)
from scripts.longitudinal_eval_report import render_report
from scripts.longitudinal_eval_runner import (
    HarnessError,
    isolated_evaluation_database,
    run_cli,
)
from scripts.longitudinal_eval_scoring import score_step

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN = _REPO_ROOT / "tests" / "evals" / "golden_longitudinal_memory.yaml"

_MIN_EXPECTED: dict[str, object] = {
    "required_any": [["Nadia"]],
    "forbidden": [],
    "expected_items": [],
    "forbidden_items": [],
    "expected_provenance": {},
    "required_absent_derivatives": [],
}

_REQUIRED_DOMAIN_TAGS = frozenset(
    {
        "domain:preference-correctable",
        "domain:birthdate",
        "domain:domicile-temporal",
        "domain:family-pet-negation",
        "domain:deceptive-negation",
        "domain:private-fact:aria",
        "domain:private-fact:bruno",
        "domain:recipient-only",
        "domain:abstention-unknown",
        "domain:sensitive-episode-derivatives",
        "domain:perceptual-nondurable",
    }
)


def _step(**over: object) -> dict[str, object]:
    """Return a schema-valid step dict, overridden by keyword."""
    step: dict[str, object] = {
        "step_id": "s1",
        "category": "extraction",
        "operation": "extract",
        "session": 1,
        "actor_id": "aria",
        "message": "El nombre de mi hija es Nadia.",
        "expected": dict(_MIN_EXPECTED),
    }
    step.update(over)
    return step


def _scenario(**over: object) -> dict[str, object]:
    """Return a schema-valid one-step scenario dict, overridden by keyword."""
    scenario: dict[str, object] = {
        "scenario_id": "sc1",
        "tags": ["category:extraction"],
        "actors": {"aria": {"actor_id": "aria", "role": "subject"}},
        "steps": [_step()],
    }
    scenario.update(over)
    return scenario


def _suite_doc(scenarios: list[dict[str, object]] | None = None) -> dict[str, object]:
    """Return a suite document, defaulting to a single extraction scenario."""
    chosen = scenarios if scenarios is not None else [_scenario()]
    return {"version": 1, "scenarios": chosen}


def _write(tmp_path: Path, text: str) -> Path:
    """Write raw dataset text and return its path."""
    dataset = tmp_path / "suite.yaml"
    dataset.write_text(text, encoding="utf-8")
    return dataset


def _write_suite(tmp_path: Path, doc: object) -> Path:
    """Serialize a suite document to YAML and return its path."""
    return _write(tmp_path, yaml.safe_dump(doc, allow_unicode=True))


# ---------------------------------------------------------------------------
# Schema + semantic validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_load_suite_rejects_a_non_version_one_document(tmp_path: Path) -> None:
    doc = _suite_doc()
    doc["version"] = 2
    with pytest.raises(ValueError, match="version"):
        load_suite(_write_suite(tmp_path, doc))


@pytest.mark.unit
def test_load_suite_rejects_a_suite_with_unknown_fields(tmp_path: Path) -> None:
    scenario = _scenario(steps=[_step(surprise="x")])
    with pytest.raises(ValueError, match="schema"):
        load_suite(_write_suite(tmp_path, _suite_doc([scenario])))


@pytest.mark.unit
def test_load_suite_rejects_duplicate_scenario_ids(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unique"):
        load_suite(_write_suite(tmp_path, _suite_doc([_scenario(), _scenario()])))


@pytest.mark.unit
def test_load_suite_rejects_duplicate_step_ids_in_one_scenario(tmp_path: Path) -> None:
    scenario = _scenario(steps=[_step(), _step()])
    with pytest.raises(ValueError, match="unique"):
        load_suite(_write_suite(tmp_path, _suite_doc([scenario])))


@pytest.mark.unit
def test_load_suite_rejects_an_unknown_actor_reference(tmp_path: Path) -> None:
    scenario = _scenario(steps=[_step(actor_id="ghost")])
    with pytest.raises(ValueError, match="actor"):
        load_suite(_write_suite(tmp_path, _suite_doc([scenario])))


@pytest.mark.unit
def test_load_suite_rejects_a_non_positive_session(tmp_path: Path) -> None:
    scenario = _scenario(steps=[_step(session=0)])
    with pytest.raises(ValueError, match="session"):
        load_suite(_write_suite(tmp_path, _suite_doc([scenario])))


@pytest.mark.unit
def test_load_suite_rejects_a_decreasing_session(tmp_path: Path) -> None:
    scenario = _scenario(steps=[_step(step_id="a", session=2), _step(step_id="b", session=1)])
    with pytest.raises(ValueError, match="session"):
        load_suite(_write_suite(tmp_path, _suite_doc([scenario])))


@pytest.mark.unit
def test_load_suite_rejects_a_step_with_every_expectation_empty(tmp_path: Path) -> None:
    empty = {
        "required_any": [],
        "forbidden": [],
        "expected_items": [],
        "forbidden_items": [],
        "expected_provenance": {},
        "required_absent_derivatives": [],
    }
    scenario = _scenario(steps=[_step(expected=empty)])
    with pytest.raises(ValueError, match=r"assertion|expectation"):
        load_suite(_write_suite(tmp_path, _suite_doc([scenario])))


@pytest.mark.unit
def test_load_suite_rejects_missing_category_coverage(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="categor"):
        load_suite(_write_suite(tmp_path, _suite_doc()))


@pytest.mark.unit
def test_load_suite_accepts_a_minimal_fully_covering_suite(tmp_path: Path) -> None:
    steps = [
        _step(step_id=f"s{index}", category=category.value)
        for index, category in enumerate(LongitudinalCategory)
    ]
    suite = load_suite(_write_suite(tmp_path, _suite_doc([_scenario(steps=steps)])))
    assert suite.version == 1
    assert len(suite.scenarios[0].steps) == len(list(LongitudinalCategory))


# ---------------------------------------------------------------------------
# Dataset privacy validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_dataset_privacy_rejects_a_reserved_term_in_a_value(tmp_path: Path) -> None:
    dataset = _write(tmp_path, "steps:\n  - note: la vecina Zeph vino a cenar\n")
    with pytest.raises(ValueError, match="reserved term") as excinfo:
        validate_dataset_privacy(dataset, ["zeph", "quorvax"])
    assert "zeph" not in str(excinfo.value).lower()
    assert "reserved term" in str(excinfo.value)


@pytest.mark.unit
def test_dataset_privacy_rejects_a_reserved_term_in_a_key(tmp_path: Path) -> None:
    dataset = _write(tmp_path, "quorvax: true\n")
    with pytest.raises(ValueError, match="reserved term"):
        validate_dataset_privacy(dataset, ["QUORVAX"])


@pytest.mark.unit
def test_dataset_privacy_rejects_an_email_address(tmp_path: Path) -> None:
    dataset = _write(tmp_path, "message: escribe a persona@example.com hoy\n")
    with pytest.raises(ValueError, match="email address"):
        validate_dataset_privacy(dataset, [])


@pytest.mark.unit
def test_dataset_privacy_rejects_a_phone_like_digit_run(tmp_path: Path) -> None:
    dataset = _write(tmp_path, "message: llamame al +51 987 654 321 esta noche\n")
    with pytest.raises(ValueError, match="digit run"):
        validate_dataset_privacy(dataset, [])


@pytest.mark.unit
def test_dataset_privacy_rejects_a_windows_production_path(tmp_path: Path) -> None:
    dataset = _write(tmp_path, "note: revisa C:\\Users\\alguien\\brain.db\n")
    with pytest.raises(ValueError, match="Windows path"):
        validate_dataset_privacy(dataset, [])


@pytest.mark.unit
def test_dataset_privacy_rejects_a_unix_production_path(tmp_path: Path) -> None:
    dataset = _write(tmp_path, "note: guardado en /home/alguien/data/brain.db\n")
    with pytest.raises(ValueError, match="Unix path"):
        validate_dataset_privacy(dataset, [])


@pytest.mark.unit
def test_dataset_privacy_rejects_a_secret_like_assignment(tmp_path: Path) -> None:
    dataset = _write(tmp_path, "config: api_key = sk-clearly-not-real\n")
    with pytest.raises(ValueError, match="secret-like assignment"):
        validate_dataset_privacy(dataset, [])


@pytest.mark.unit
def test_dataset_privacy_accepts_a_clean_synthetic_dataset(tmp_path: Path) -> None:
    dataset = _write(tmp_path, "message: Aria prefiere el color verde\n")
    validate_dataset_privacy(dataset, ["zeph", "quorvax"])


# ---------------------------------------------------------------------------
# Committed version-1 suite coverage
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_golden_suite_loads_and_covers_all_nine_categories() -> None:
    suite = load_suite(_GOLDEN)
    covered = {step.category for sc in suite.scenarios for step in sc.steps}
    assert covered == set(LongitudinalCategory)


@pytest.mark.unit
def test_golden_suite_has_two_adults_and_one_unknown_actor() -> None:
    suite = load_suite(_GOLDEN)
    by_role: dict[str, set[str]] = {}
    for scenario in suite.scenarios:
        for actor in scenario.actors.values():
            by_role.setdefault(actor.role, set()).add(actor.actor_id)
    assert len(by_role.get("subject", set())) >= 2
    assert len(by_role.get("unknown", set())) >= 1


@pytest.mark.unit
def test_golden_suite_exercises_the_frozen_operation_sequence() -> None:
    suite = load_suite(_GOLDEN)
    wanted = [
        LongitudinalOperation.PROPOSE,
        LongitudinalOperation.RESTART,
        LongitudinalOperation.RECALL,
        LongitudinalOperation.CORRECT,
        LongitudinalOperation.RESTART,
        LongitudinalOperation.RECALL,
        LongitudinalOperation.FORGET,
        LongitudinalOperation.INSPECT_DERIVATIVES,
        LongitudinalOperation.RECALL,
    ]
    sequences = [[step.operation for step in sc.steps] for sc in suite.scenarios]
    assert wanted in sequences


@pytest.mark.unit
def test_golden_suite_has_restarts_correction_forget_inspection_and_unauthorized_recall() -> None:
    suite = load_suite(_GOLDEN)
    pairs = [(sc, step) for sc in suite.scenarios for step in sc.steps]
    ops = [step.operation for _, step in pairs]
    assert ops.count(LongitudinalOperation.RESTART) >= 2
    assert LongitudinalOperation.CORRECT in ops
    assert LongitudinalOperation.FORGET in ops
    assert LongitudinalOperation.INSPECT_DERIVATIVES in ops
    unauthorized = [
        step
        for sc, step in pairs
        if step.category is LongitudinalCategory.CROSS_PERSON_PRIVACY
        and step.operation is LongitudinalOperation.RECALL
        and sc.actors[step.actor_id].role in {"unknown", "other"}
    ]
    assert unauthorized


@pytest.mark.unit
def test_golden_suite_covers_every_minimum_domain() -> None:
    suite = load_suite(_GOLDEN)
    tags = {tag for scenario in suite.scenarios for tag in scenario.tags}
    assert tags >= _REQUIRED_DOMAIN_TAGS


@pytest.mark.unit
def test_golden_suite_declares_all_sensitive_episode_derivatives() -> None:
    suite = load_suite(_GOLDEN)
    wanted = {"fact", "episode", "embedding", "summary", "cache"}
    declared = [
        set(step.expected.required_absent_derivatives)
        for scenario in suite.scenarios
        for step in scenario.steps
    ]
    assert any(wanted <= entry for entry in declared)


@pytest.mark.unit
def test_golden_suite_tests_recipient_only_with_authorized_and_unauthorized() -> None:
    suite = load_suite(_GOLDEN)
    for scenario in suite.scenarios:
        if "domain:recipient-only" not in scenario.tags:
            continue
        recall_roles = {
            scenario.actors[step.actor_id].role
            for step in scenario.steps
            if step.operation is LongitudinalOperation.RECALL
        }
        assert "unknown" in recall_roles
        assert recall_roles & {"subject", "other"}
        return
    pytest.fail("no scenario tagged domain:recipient-only")


@pytest.mark.unit
def test_golden_dataset_excludes_reserved_household_names() -> None:
    validate_dataset_privacy(
        _GOLDEN,
        ["pipec", "felipe", "maximo", "dominga", "iroko", "omnibot"],
    )


@pytest.mark.unit
def test_golden_dataset_passes_privacy_with_invented_reserved_terms() -> None:
    validate_dataset_privacy(_GOLDEN, ["zeph", "quorvax"])


# ---------------------------------------------------------------------------
# Task 3 — deterministic scoring (score_step / aggregate_results / exit codes)
# ---------------------------------------------------------------------------


def _expected(**over: object) -> ExpectedObservation:
    """Return an empty ``ExpectedObservation`` with keyword overrides."""
    base: dict[str, object] = {
        "required_any": [],
        "forbidden": [],
        "expected_items": [],
        "forbidden_items": [],
        "expected_provenance": {},
        "required_absent_derivatives": [],
    }
    base.update(over)
    return ExpectedObservation.model_validate(base)


def _lstep(**over: object) -> LongitudinalStep:
    """Return a schema-valid ``LongitudinalStep`` with keyword overrides."""
    base: dict[str, object] = {
        "step_id": "s1",
        "category": "extraction",
        "operation": "extract",
        "session": 1,
        "actor_id": "aria",
        "message": "m",
        "expected": _expected(),
    }
    base.update(over)
    return LongitudinalStep.model_validate(base)


def _obs(**over: object) -> ProbeObservation:
    """Return a passing ``ProbeObservation`` with keyword overrides."""
    base: dict[str, object] = {
        "status": "pass",
        "response": "",
        "observed_items": (),
        "observed_provenance": {},
        "latency_ms": 10.0,
        "reason": None,
        "inspected_derivatives": {},
    }
    base.update(over)
    return ProbeObservation.model_validate(base)


def _pr() -> dict[str, object]:
    return {
        "precision": None,
        "recall": None,
        "expected_count": 0,
        "observed_count": 0,
        "matched_count": 0,
    }


def _summary(**over: object) -> BenchmarkSummary:
    """Return a clean, all-gates-passing ``BenchmarkSummary`` with overrides."""
    base: dict[str, object] = {
        "total": 1,
        "passed": 1,
        "failed": 0,
        "unsupported": 0,
        "errors": 0,
        "forbidden_disclosure_count": 0,
        "forbidden_disclosure_eligible_count": 1,
        "forbidden_disclosure_rate": 0.0,
        "deletion_expected_count": 1,
        "deletion_inspected_count": 1,
        "deletion_absent_count": 1,
        "complete_deletion_rate": 1.0,
        "extraction_precision": None,
        "extraction_recall": None,
        "candidate_by_type": {},
        "subject_metric": _pr(),
        "object_metric": _pr(),
        "relation_metric": _pr(),
        "provenance_expected_count": 1,
        "provenance_matched_count": 1,
        "provenance_accuracy": 1.0,
        "truth_current_accuracy": 1.0,
        "correct_abstention_rate": 1.0,
        "by_category": {},
    }
    base.update(over)
    return BenchmarkSummary.model_validate(base)


@pytest.mark.unit
def test_score_step_forbidden_hit_fails_even_with_required_present() -> None:
    step = _lstep(expected=_expected(required_any=[["mudanza"]], forbidden=["se mudó"]))
    scored = score_step("sc", step, _obs(response="Sí, la mudanza: se mudó ayer."))
    assert scored.result.status is CapabilityStatus.FAIL
    assert scored.result.missing_required == []
    assert scored.result.forbidden_found == ["se mudó"]


@pytest.mark.unit
def test_score_step_matching_is_accent_and_case_insensitive() -> None:
    step = _lstep(expected=_expected(forbidden=["se mudó"]))
    scored = score_step("sc", step, _obs(response="SE MUDO hace poco"))
    assert scored.result.forbidden_found == ["se mudó"]
    assert scored.result.status is CapabilityStatus.FAIL


@pytest.mark.unit
def test_score_step_missing_required_or_group_reported_literally() -> None:
    step = _lstep(expected=_expected(required_any=[["con normalidad", "actualizado"]]))
    scored = score_step("sc", step, _obs(response="no lo tengo claro"))
    assert scored.result.missing_required == [["con normalidad", "actualizado"]]
    assert scored.result.status is CapabilityStatus.FAIL


@pytest.mark.unit
def test_score_step_preserves_unsupported_status_and_reason() -> None:
    step = _lstep(operation="recall", expected=_expected(required_any=[["x"]]))
    scored = score_step("sc", step, _obs(status="unsupported", reason="no authorized-recall seam"))
    assert scored.result.status is CapabilityStatus.UNSUPPORTED
    assert scored.result.reason == "no authorized-recall seam"
    assert scored.passed is False


@pytest.mark.unit
def test_score_step_keeps_provider_error_separate_from_cognitive_fail() -> None:
    step = _lstep(expected=_expected(required_any=[["x"]]))
    scored = score_step("sc", step, _obs(status="error", reason="ollama down"))
    assert scored.result.status is CapabilityStatus.ERROR


@pytest.mark.unit
def test_score_step_counts_items_with_exact_canonical_keys() -> None:
    exp = _expected(
        required_any=[["Tomas"]],
        expected_items=["entity|tomas|persona", "fact|tomas|nacimiento|2016"],
        forbidden_items=["fact|bruno|mascota|gato"],
    )
    obs = _obs(
        response="Tomas",
        observed_items=("entity|tomas|persona", "fact|bruno|mascota|gato"),
    )
    scored = score_step("sc", _lstep(expected=exp), obs)
    assert scored.result.expected_item_count == 2
    assert scored.result.matched_item_count == 1
    assert scored.result.unexpected_item_count == 1
    assert scored.result.forbidden_items_found == ["fact|bruno|mascota|gato"]
    assert scored.result.status is CapabilityStatus.FAIL


@pytest.mark.unit
def test_score_step_forbidden_item_fails_even_when_precision_recall_would_pass() -> None:
    exp = _expected(
        expected_items=["entity|kip|animal"],
        forbidden_items=["fact|aria|domicilio|puerto lindo"],
    )
    obs = _obs(
        observed_items=("entity|kip|animal", "fact|aria|domicilio|puerto lindo"),
    )
    scored = score_step("sc", _lstep(expected=exp), obs)
    assert scored.result.matched_item_count == 1
    assert scored.result.status is CapabilityStatus.FAIL


def _abstention_step(name: str, status: str, response: str, latency: float) -> ScoredStep:
    return score_step(
        "sc",
        _lstep(
            step_id=name,
            category="abstention",
            operation="recall",
            expected=_expected(required_any=[["no lo se"]]),
        ),
        _obs(status=status, response=response, latency_ms=latency),
    )


@pytest.mark.unit
def test_aggregate_results_pass_rate_and_latency_exclude_error_and_unsupported() -> None:
    steps = [
        _abstention_step("a", "pass", "no lo se", 100.0),
        _abstention_step("b", "fail", "", 400.0),
        _abstention_step("c", "unsupported", "", 999.0),
        _abstention_step("d", "error", "", 8888.0),
    ]
    cat = aggregate_results(steps).by_category[LongitudinalCategory.ABSTENTION]
    assert (cat.total, cat.passed, cat.failed, cat.unsupported, cat.errors) == (4, 1, 1, 1, 1)
    assert cat.pass_rate == pytest.approx(1 / 3)  # ERROR dropped from the divisor
    assert cat.latency_p50_ms == pytest.approx(250.0)  # only PASS(100) + FAIL(400)
    assert cat.latency_p95_ms is not None
    assert cat.latency_p95_ms < 999.0  # UNSUPPORTED and ERROR latencies excluded


@pytest.mark.unit
def test_aggregate_results_latency_none_when_category_has_no_valid_observation() -> None:
    cat = aggregate_results([_abstention_step("a", "unsupported", "", 50.0)]).by_category[
        LongitudinalCategory.ABSTENTION
    ]
    assert cat.latency_p50_ms is None
    assert cat.latency_p95_ms is None
    assert cat.pass_rate == pytest.approx(0.0)


@pytest.mark.unit
def test_aggregate_results_pass_rate_is_zero_when_every_step_errored() -> None:
    cat = aggregate_results([_abstention_step("a", "error", "", 1.0)]).by_category[
        LongitudinalCategory.ABSTENTION
    ]
    assert cat.pass_rate == 0.0
    assert cat.latency_p50_ms is None


@pytest.mark.unit
def test_aggregate_results_folds_item_keys_before_counting() -> None:
    step = _lstep(expected=_expected(expected_items=["entity|Tomás|persona"]))
    summary = aggregate_results(
        [score_step("sc", step, _obs(observed_items=("entity|tomas|persona",)))]
    )
    assert summary.extraction_recall == pytest.approx(1.0)
    assert summary.extraction_precision == pytest.approx(1.0)
    assert summary.candidate_by_type["entity"].matched_count == 1


@pytest.mark.unit
def test_aggregate_results_micro_aggregates_extraction_precision_recall() -> None:
    a = score_step(
        "sc",
        _lstep(
            step_id="a",
            expected=_expected(
                expected_items=["entity|tomas|persona", "fact|tomas|nacimiento|2016"]
            ),
        ),
        _obs(observed_items=("entity|tomas|persona",)),
    )
    b = score_step(
        "sc",
        _lstep(step_id="b", expected=_expected(expected_items=["entity|kip|animal"])),
        _obs(observed_items=("entity|kip|animal", "entity|gato|animal")),
    )
    summary = aggregate_results([a, b])
    assert summary.extraction_recall == pytest.approx(2 / 3)
    assert summary.extraction_precision == pytest.approx(2 / 3)


@pytest.mark.unit
def test_aggregate_results_empty_extraction_denominator_is_none() -> None:
    scored = [
        score_step(
            "sc",
            _lstep(
                category="provenance", operation="recall", expected=_expected(required_any=[["x"]])
            ),
            _obs(status="unsupported"),
        )
    ]
    summary = aggregate_results(scored)
    assert summary.extraction_precision is None
    assert summary.extraction_recall is None
    assert summary.candidate_by_type["entity"].precision is None


@pytest.mark.unit
def test_aggregate_results_candidate_metrics_split_by_item_type() -> None:
    step = _lstep(
        expected=_expected(
            expected_items=[
                "entity|tomas|persona",
                "fact|tomas|nacimiento|2016",
                "fact|tomas|hermano|kip",
                "entity|kip|animal",
            ]
        )
    )
    obs = _obs(
        observed_items=(
            "entity|tomas|persona",
            "fact|tomas|nacimiento|2016",
            "entity|kip|animal",
        )
    )
    by_type = aggregate_results([score_step("sc", step, obs)]).candidate_by_type
    assert by_type["entity"].matched_count == 2
    assert by_type["literal_fact"].matched_count == 1
    assert by_type["relation_fact"].expected_count == 1
    assert by_type["relation_fact"].matched_count == 0
    assert by_type["relation_fact"].recall == pytest.approx(0.0)


@pytest.mark.unit
def test_aggregate_results_subject_object_relation_segment_metrics() -> None:
    step = _lstep(expected=_expected(expected_items=["fact|tomas|nacimiento|2016"]))
    obs = _obs(observed_items=("fact|tomas|nacimiento|2018",))
    summary = aggregate_results([score_step("sc", step, obs)])
    assert summary.subject_metric.matched_count == 1
    assert summary.relation_metric.matched_count == 1
    assert summary.object_metric.matched_count == 0
    assert summary.object_metric.recall == pytest.approx(0.0)


@pytest.mark.unit
def test_aggregate_results_truth_current_accuracy_after_correction() -> None:
    correct = score_step(
        "sc",
        _lstep(
            step_id="c",
            category="update",
            operation="correct",
            expected=_expected(required_any=[["ok"]]),
        ),
        _obs(response="ok"),
    )
    good = score_step(
        "sc",
        _lstep(
            step_id="r1",
            category="temporality",
            operation="recall",
            expected=_expected(required_any=[["normalidad"]]),
        ),
        _obs(response="con normalidad"),
    )
    bad = score_step(
        "sc",
        _lstep(
            step_id="r2",
            category="temporality",
            operation="recall",
            expected=_expected(required_any=[["normalidad"]]),
        ),
        _obs(status="unsupported"),
    )
    assert aggregate_results([correct, good, bad]).truth_current_accuracy == pytest.approx(0.5)


@pytest.mark.unit
def test_aggregate_results_truth_current_accuracy_none_without_correction() -> None:
    recall = score_step(
        "sc",
        _lstep(
            category="temporality", operation="recall", expected=_expected(required_any=[["x"]])
        ),
        _obs(status="unsupported"),
    )
    assert aggregate_results([recall]).truth_current_accuracy is None


@pytest.mark.unit
def test_aggregate_results_correct_abstention_rate_counts_every_abstention_step() -> None:
    good = score_step(
        "sc",
        _lstep(
            category="abstention",
            operation="recall",
            expected=_expected(required_any=[["no lo se"]]),
        ),
        _obs(response="no lo se"),
    )
    unsup = score_step(
        "sc",
        _lstep(
            category="abstention",
            operation="recall",
            expected=_expected(required_any=[["no lo se"]]),
        ),
        _obs(status="unsupported"),
    )
    assert aggregate_results([good, unsup]).correct_abstention_rate == pytest.approx(0.5)


@pytest.mark.unit
def test_aggregate_results_correct_abstention_rate_none_when_no_abstention_steps() -> None:
    plain = score_step("sc", _lstep(), _obs())
    assert aggregate_results([plain]).correct_abstention_rate is None


@pytest.mark.unit
def test_score_step_deletion_all_derivatives_inspected_absent_passes() -> None:
    step = _lstep(
        category="complete_deletion",
        operation="inspect_derivatives",
        expected=_expected(required_absent_derivatives=["fact", "episode"]),
    )
    obs = _obs(inspected_derivatives={"fact": False, "episode": False})
    scored = score_step("sc", step, obs)
    assert scored.result.status is CapabilityStatus.PASS
    assert scored.result.derivative_presence == {"fact": False, "episode": False}


@pytest.mark.unit
def test_score_step_deletion_missing_inspection_fails() -> None:
    step = _lstep(
        category="complete_deletion",
        operation="inspect_derivatives",
        expected=_expected(required_absent_derivatives=["fact", "episode"]),
    )
    scored = score_step("sc", step, _obs(inspected_derivatives={"fact": False}))
    assert scored.result.status is CapabilityStatus.FAIL
    assert scored.result.derivative_presence["episode"] is True


@pytest.mark.unit
def test_score_step_deletion_one_remaining_derivative_fails() -> None:
    step = _lstep(
        category="complete_deletion",
        operation="inspect_derivatives",
        expected=_expected(required_absent_derivatives=["fact", "episode"]),
    )
    obs = _obs(inspected_derivatives={"fact": False, "episode": True})
    assert score_step("sc", step, obs).result.status is CapabilityStatus.FAIL


@pytest.mark.unit
def test_aggregate_results_deletion_counts_reported_separately() -> None:
    step = _lstep(
        category="complete_deletion",
        operation="inspect_derivatives",
        expected=_expected(required_absent_derivatives=["fact", "episode", "embedding"]),
    )
    obs = _obs(inspected_derivatives={"fact": False, "episode": True})
    summary = aggregate_results([score_step("sc", step, obs)])
    assert summary.deletion_expected_count == 3
    assert summary.deletion_inspected_count == 2
    assert summary.deletion_absent_count == 1
    assert summary.complete_deletion_rate == pytest.approx(1 / 3)


@pytest.mark.unit
def test_aggregate_results_deletion_rate_none_when_nothing_required() -> None:
    assert aggregate_results([score_step("sc", _lstep(), _obs())]).complete_deletion_rate is None


@pytest.mark.unit
def test_score_step_provenance_is_independent_of_extraction_subject_object() -> None:
    step = _lstep(
        category="provenance",
        operation="recall",
        expected=_expected(
            required_any=[["Bruno"]],
            expected_provenance={"subject": "aria", "assertor": "bruno", "source": "conversation"},
        ),
    )
    obs = _obs(
        response="Bruno me lo comento",
        observed_provenance={"subject": "aria", "assertor": "bruno", "source": "camara"},
    )
    scored = score_step("sc", step, obs)
    assert scored.result.provenance_expected_count == 3
    assert scored.result.provenance_matched_count == 2
    assert scored.result.provenance_mismatches == {"source": ("conversation", "camara")}
    assert scored.result.status is CapabilityStatus.FAIL


@pytest.mark.unit
def test_score_step_provenance_missing_field_records_none() -> None:
    step = _lstep(
        category="provenance",
        operation="recall",
        expected=_expected(required_any=[["x"]], expected_provenance={"assertor": "bruno"}),
    )
    scored = score_step("sc", step, _obs(response="x"))
    assert scored.result.provenance_mismatches == {"assertor": ("bruno", None)}


@pytest.mark.unit
def test_aggregate_results_provenance_accuracy_and_none_denominator() -> None:
    with_prov = score_step(
        "sc",
        _lstep(
            category="provenance",
            operation="recall",
            expected=_expected(
                required_any=[["x"]],
                expected_provenance={"assertor": "bruno", "source": "conversation"},
            ),
        ),
        _obs(response="x", observed_provenance={"assertor": "bruno", "source": "conversation"}),
    )
    summary = aggregate_results([with_prov])
    assert summary.provenance_expected_count == 2
    assert summary.provenance_matched_count == 2
    assert summary.provenance_accuracy == pytest.approx(1.0)
    plain = aggregate_results([score_step("sc", _lstep(), _obs())])
    assert plain.provenance_accuracy is None


@pytest.mark.unit
def test_aggregate_results_forbidden_disclosure_rate_over_valid_privacy_recalls() -> None:
    leaked = score_step(
        "sc",
        _lstep(
            category="cross_person_privacy",
            operation="recall",
            expected=_expected(required_any=[["no puedo compartir"]], forbidden=["terapia"]),
        ),
        _obs(status="fail", response="va a terapia"),
    )
    safe = score_step(
        "sc",
        _lstep(
            category="cross_person_privacy",
            operation="recall",
            expected=_expected(required_any=[["no puedo compartir"]], forbidden=["terapia"]),
        ),
        _obs(status="pass", response="no puedo compartir eso"),
    )
    summary = aggregate_results([leaked, safe])
    assert summary.forbidden_disclosure_eligible_count == 2
    assert summary.forbidden_disclosure_count == 1
    assert summary.forbidden_disclosure_rate == pytest.approx(0.5)


@pytest.mark.unit
def test_aggregate_results_unsupported_privacy_step_yields_none_rate_not_zero() -> None:
    unsup = score_step(
        "sc",
        _lstep(
            category="cross_person_privacy",
            operation="recall",
            expected=_expected(required_any=[["x"]], forbidden=["terapia"]),
        ),
        _obs(status="unsupported"),
    )
    summary = aggregate_results([unsup])
    assert summary.forbidden_disclosure_eligible_count == 0
    assert summary.forbidden_disclosure_rate is None


_ZEROES_SHA = "0" * 64


def _metadata(**over: object) -> RunMetadata:
    """Return a schema-valid, secret-free ``RunMetadata`` with keyword overrides."""
    base: dict[str, object] = {
        "generated_at": datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        "branch": "feat/0046-longitudinal-memory-baseline",
        "source_commit": "0" * 40,
        "worktree_dirty": False,
        "worktree_status": [],
        "dataset_path": "tests/evals/golden_longitudinal_memory.yaml",
        "dataset_version": 1,
        "dataset_sha256": _ZEROES_SHA,
        "python_version": "3.12.0",
        "provider": "ollama",
        "ollama_url": "http://localhost:11434",
        "chat_model": "qwen2.5:3b",
        "consolidation_model": "qwen2.5:3b",
        "model_settings": {},
        "sanitized_command": [],
        "reserved_term_count": 0,
        "temporary_database_name": "brain.db",
        "service_preflight": "pass",
    }
    base.update(over)
    return RunMetadata.model_validate(base)


def _result(summary: BenchmarkSummary, *, gating: bool) -> LongitudinalEvaluationResult:
    """Wrap a ``BenchmarkSummary`` into a minimal ``LongitudinalEvaluationResult``."""
    return LongitudinalEvaluationResult(
        metadata=_metadata(), results=[], summary=summary, gating=gating
    )


@pytest.mark.unit
def test_determine_exit_code_zero_when_gating_and_all_strict_gates_pass() -> None:
    assert determine_exit_code(_result(_summary(), gating=True)) == 0


@pytest.mark.unit
def test_determine_exit_code_one_when_a_cognitive_case_is_unsupported() -> None:
    assert determine_exit_code(_result(_summary(passed=0, unsupported=1), gating=True)) == 1


@pytest.mark.unit
def test_determine_exit_code_one_when_gating_gate_denominator_missing() -> None:
    assert determine_exit_code(_result(_summary(complete_deletion_rate=None), gating=True)) == 1


@pytest.mark.unit
def test_determine_exit_code_two_when_a_harness_error_is_present() -> None:
    assert determine_exit_code(_result(_summary(passed=0, errors=1), gating=True)) == 2


@pytest.mark.unit
def test_determine_exit_code_zero_for_non_gating_smoke_without_failures() -> None:
    smoke = _summary(
        forbidden_disclosure_rate=None,
        complete_deletion_rate=None,
        truth_current_accuracy=None,
        provenance_accuracy=None,
    )
    assert determine_exit_code(_result(smoke, gating=False)) == 0


# ---------------------------------------------------------------------------
# Task 4 — driver, DB sandbox, metadata, report, CLI
# ---------------------------------------------------------------------------

_OPERATIONS_WITHOUT_A_SEAM = (
    LongitudinalOperation.PROPOSE,
    LongitudinalOperation.RESTART,
    LongitudinalOperation.RECALL,
    LongitudinalOperation.CORRECT,
    LongitudinalOperation.FORGET,
    LongitudinalOperation.INSPECT_DERIVATIVES,
)


def _fake_client() -> httpx.AsyncClient:
    """Return an identity-stable stand-in for the run-owned HTTP client."""
    return cast("httpx.AsyncClient", Mock(spec=httpx.AsyncClient))


def _lscenario(steps: list[LongitudinalStep], **over: object) -> LongitudinalScenario:
    """Return a schema-valid ``LongitudinalScenario`` with keyword overrides."""
    base: dict[str, object] = {
        "scenario_id": "sc1",
        "tags": ["category:extraction"],
        "actors": {"aria": {"actor_id": "aria", "role": "subject"}},
        "steps": steps,
    }
    base.update(over)
    return LongitudinalScenario.model_validate(base)


class _ScriptedDriver:
    """Typed fake ``LongitudinalDriver``: real observations, never synthesized ones."""

    def __init__(self, *, extract_status: str = "pass", echo_expected: bool = False) -> None:
        self.calls: list[tuple[str, str]] = []
        self._status = extract_status
        self._echo = echo_expected

    async def execute_step(
        self, scenario: LongitudinalScenario, step: LongitudinalStep
    ) -> ProbeObservation:
        self.calls.append((scenario.scenario_id, step.step_id))
        if step.operation is not LongitudinalOperation.EXTRACT:
            return unsupported_observation(step.operation)
        if self._status == "error":
            return ProbeObservation(
                status=CapabilityStatus.ERROR,
                response="",
                observed_items=(),
                observed_provenance={},
                latency_ms=1.0,
                reason="provider died mid-run; no content",
                inspected_derivatives={},
            )
        response = " ".join(group[0] for group in step.expected.required_any)
        items = tuple(step.expected.expected_items) if self._echo else ()
        return ProbeObservation(
            status=CapabilityStatus.PASS,
            response=response,
            observed_items=items,
            observed_provenance={},
            latency_ms=1.0,
            reason=None,
            inspected_derivatives={},
        )


def _install_fake_db(
    monkeypatch: pytest.MonkeyPatch,
    *,
    is_open: bool = False,
    on_open: Callable[[], None] | None = None,
    on_migrate: Callable[[], None] | None = None,
    on_close: Callable[[], None] | None = None,
    make_files: bool = False,
) -> list[object]:
    """Replace ``server.db``'s public surface with deterministic in-memory fakes."""
    calls: list[object] = []

    def _is_open() -> bool:
        return is_open

    async def _open() -> None:
        calls.append(("open", Path(settings.brain_db_path).name))
        if make_files:
            base = Path(settings.brain_db_path)
            for suffix in ("", "-wal", "-shm"):
                base.with_name(base.name + suffix).write_bytes(b"x")
        if on_open is not None:
            on_open()

    async def _migrate() -> None:
        calls.append("migrate")
        if on_migrate is not None:
            on_migrate()

    async def _close() -> None:
        calls.append("close")
        if on_close is not None:
            on_close()

    monkeypatch.setattr(runner.db, "is_open", _is_open)
    monkeypatch.setattr(runner.db, "open_db", _open)
    monkeypatch.setattr(runner.db, "run_migrations", _migrate)
    monkeypatch.setattr(runner.db, "close_db", _close)
    return calls


def _options(
    tmp_path: Path,
    *,
    dataset_path: Path | None = None,
    output_path: Path | None = None,
    runs: int = 1,
    only: tuple[str, ...] = (),
    reserved_terms: tuple[str, ...] = (),
    provider: str = "ollama",
) -> CliOptions:
    """Return ``CliOptions`` whose output path is safe once ``_OUTPUT_DIR`` is patched."""
    return CliOptions(
        dataset_path=dataset_path or _GOLDEN,
        output_path=output_path or (tmp_path / "report.md"),
        runs=runs,
        only=only,
        reserved_terms=reserved_terms,
        provider=cast('Literal["ollama"]', provider),
    )


def _fake_git(*args: str) -> str:
    if args[:2] == ("rev-parse", "--abbrev-ref"):
        return "feat/0046-longitudinal-memory-baseline"
    if args[:2] == ("rev-parse", "HEAD"):
        return "d" * 40
    if args and args[0] == "status":
        return " M docs/evals/README.md\n?? scratch.md\n"
    return ""


async def _yes() -> bool:
    return True


async def _no() -> bool:
    return False


# ----------------------------- driver -----------------------------


@pytest.mark.unit
async def test_driver_extract_delegates_to_the_real_consolidation_seam(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_extract(client: object, user_text: str, assistant_text: str) -> tuple[str, ...]:
        assert assistant_text  # a neutral, non-empty acknowledgement is supplied
        return ("entity|kip|animal", "fact|kip|especie|perro")

    monkeypatch.setattr(driver_mod, "extract_case_items", fake_extract)
    driver = CurrentRuntimeDriver(_fake_client())
    step = _lstep(operation="extract", category="extraction")
    observation = await driver.execute_step(_lscenario([step]), step)
    assert observation.status is CapabilityStatus.PASS
    assert observation.observed_items == ("entity|kip|animal", "fact|kip|especie|perro")
    assert observation.reason is None
    assert observation.observed_provenance == {}
    assert observation.inspected_derivatives == {}
    assert observation.latency_ms >= 0.0


@pytest.mark.unit
@pytest.mark.parametrize("operation", _OPERATIONS_WITHOUT_A_SEAM)
async def test_driver_unsupported_operations_are_recorded_not_synthesized(
    operation: LongitudinalOperation,
) -> None:
    driver = CurrentRuntimeDriver(_fake_client())
    step = _lstep(operation=operation.value, category="multi_session")
    observation = await driver.execute_step(_lscenario([step]), step)
    assert observation.status is CapabilityStatus.UNSUPPORTED
    assert observation.response == ""
    assert observation.observed_items == ()
    assert observation.observed_provenance == {}
    assert observation.inspected_derivatives == {}
    assert observation.reason is not None
    assert "seam" in observation.reason


def _unsupported_reason(operation: LongitudinalOperation) -> str:
    reason = unsupported_observation(operation).reason
    assert reason is not None
    return reason


@pytest.mark.unit
def test_driver_unsupported_reasons_name_the_exact_missing_capability() -> None:
    assert "assert_fact()" in _unsupported_reason(LongitudinalOperation.PROPOSE)
    assert "not a restart" in _unsupported_reason(LongitudinalOperation.RESTART)
    assert "resolved actor" in _unsupported_reason(LongitudinalOperation.RECALL)
    assert "episode/embedding/summary/cache" in _unsupported_reason(LongitudinalOperation.FORGET)


@pytest.mark.unit
async def test_driver_extract_provider_failure_is_a_harness_error_not_a_cognitive_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def boom(client: object, user_text: str, assistant_text: str) -> tuple[str, ...]:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(driver_mod, "extract_case_items", boom)
    driver = CurrentRuntimeDriver(_fake_client())
    step = _lstep(operation="extract", category="extraction", message="secreto del hogar")
    observation = await driver.execute_step(_lscenario([step]), step)
    assert observation.status is CapabilityStatus.ERROR
    assert observation.reason is not None
    assert "provider failure" in observation.reason
    assert "ConnectError" in observation.reason
    assert "secreto del hogar" not in observation.reason


@pytest.mark.unit
def test_driver_source_has_no_private_runtime_access() -> None:
    source = inspect.getsource(driver_mod)
    assert "_conn" not in source
    assert "_buffers" not in source
    assert "MemoryContext" not in source


@pytest.mark.unit
async def test_fake_driver_runs_supported_and_records_unsupported_through_run_scenarios() -> None:
    extract = _lstep(step_id="e", operation="extract", category="extraction")
    recall = _lstep(step_id="r", operation="recall", category="multi_session")
    driver = _ScriptedDriver()
    scored = await runner._run_scenarios(driver, [_lscenario([extract, recall])], 1)
    statuses = [step.result.status for step in scored]
    assert statuses == [CapabilityStatus.PASS, CapabilityStatus.UNSUPPORTED]
    assert driver.calls == [("sc1", "e"), ("sc1", "r")]
    assert scored[1].result.reason is not None


# ----------------------------- metadata -----------------------------


@pytest.mark.unit
def test_metadata_is_complete_and_the_dataset_hash_is_deterministic(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(metadata_mod, "_git", _fake_git)
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "brain.db")
    first = collect_run_metadata(_GOLDEN, [], [])
    second = collect_run_metadata(_GOLDEN, [], [])
    assert first.dataset_sha256 == second.dataset_sha256
    assert first.dataset_sha256 == hashlib.sha256(_GOLDEN.read_bytes()).hexdigest()
    assert first.dataset_version == 1
    assert first.provider == "ollama"
    assert first.branch == "feat/0046-longitudinal-memory-baseline"
    assert first.temporary_database_name == "brain.db"
    assert first.service_preflight == "pass"


@pytest.mark.unit
def test_metadata_records_the_pre_run_dirty_worktree_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(metadata_mod, "_git", _fake_git)
    meta = collect_run_metadata(_GOLDEN, [], [])
    assert meta.worktree_dirty is True
    assert meta.worktree_status == [" M docs/evals/README.md", "?? scratch.md"]


@pytest.mark.unit
def test_metadata_dataset_path_is_repo_relative_without_drive_letter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(metadata_mod, "_git", _fake_git)
    meta = collect_run_metadata(_GOLDEN, [], [])
    assert ":" not in meta.dataset_path
    assert "\\" not in meta.dataset_path
    assert not Path(meta.dataset_path).is_absolute()
    assert meta.dataset_path == "tests/evals/golden_longitudinal_memory.yaml"


@pytest.mark.unit
def test_metadata_ollama_url_is_stripped_of_userinfo_and_query_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(metadata_mod, "_git", _fake_git)
    monkeypatch.setattr(
        settings, "ollama_url", "http://admin:hunter2@ollama.lan:11434/v1?token=abc123"
    )
    meta = collect_run_metadata(_GOLDEN, [], [])
    for secret in ("admin", "hunter2", "token", "abc123"):
        assert secret not in meta.ollama_url
    assert "ollama.lan:11434" in meta.ollama_url


@pytest.mark.unit
def test_metadata_sanitized_command_has_no_literal_reserved_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(metadata_mod, "_git", _fake_git)
    argv = ["--only", "sc1", "--reserved-term", "zeph", "--reserved-term=quorvax"]
    meta = collect_run_metadata(_GOLDEN, argv, ["zeph", "quorvax"])
    joined = " ".join(meta.sanitized_command)
    assert "zeph" not in joined
    assert "quorvax" not in joined
    assert meta.sanitized_command == [
        "--only",
        "sc1",
        "--reserved-term",
        "<redacted>",
        "--reserved-term=<redacted>",
    ]
    assert meta.reserved_term_count == 2


@pytest.mark.unit
def test_metadata_url_and_command_sanitizers_are_pure() -> None:
    assert sanitize_url("http://u:p@h:1234/x?q=1") == "http://h:1234/x"
    assert sanitize_command(["--dataset", "x.yaml"], []) == ["--dataset", "x.yaml"]
    assert sanitize_command(["--reserved-term", "kapp"], ["kapp"]) == [
        "--reserved-term",
        "<redacted>",
    ]
    assert sanitize_command(["kapp-was-here"], ["kapp"]) == ["<redacted>"]


# ----------------------------- report -----------------------------


def _render_default_result(**summary_over: object) -> str:
    return render_report(_result(_summary(**summary_over), gating=True))


@pytest.mark.unit
def test_report_renders_all_nine_categories_even_when_none_executed() -> None:
    text = _render_default_result(by_category={})
    for category in LongitudinalCategory:
        assert category.value in text
    assert "not executed" in text


@pytest.mark.unit
def test_report_renders_every_metric_field_never_the_category_pass_rate() -> None:
    text = _render_default_result()
    for field in (
        "forbidden_disclosure_rate",
        "complete_deletion_rate",
        "truth_current_accuracy",
        "provenance_accuracy",
        "correct_abstention_rate",
        "candidate:entity",
        "candidate:literal_fact",
        "candidate:relation_fact",
        "fact.subject",
        "fact.object",
        "fact.relation",
        "deletion_expected_count",
        "deletion_inspected_count",
        "deletion_absent_count",
    ):
        assert field in text


@pytest.mark.unit
def test_report_surfaces_scenario_coverage_and_unsupported_reasons() -> None:
    extract = _lstep(step_id="e", operation="extract", category="extraction")
    recall = _lstep(step_id="r", operation="recall", category="cross_person_privacy")
    scored = [
        score_step("sc_a", extract, _obs(status="pass", observed_items=())),
        score_step("sc_b", recall, _obs(status="unsupported", reason="no authorized-recall seam")),
    ]
    result = LongitudinalEvaluationResult(
        metadata=_metadata(),
        results=[step.result for step in scored],
        summary=aggregate_results(scored),
        gating=False,
    )
    text = render_report(result)
    assert "## Scenario coverage" in text
    assert "sc_a" in text
    assert "sc_b" in text
    assert "cross_person_privacy" in text
    assert "no authorized-recall seam" in text
    assert "non-gating" in text


@pytest.mark.unit
def test_report_is_deterministic_for_the_same_result() -> None:
    result = _result(_summary(), gating=True)
    assert render_report(result) == render_report(result)


@pytest.mark.unit
def test_report_renders_model_settings_as_sorted_key_value_pairs() -> None:
    populated = LongitudinalEvaluationResult(
        metadata=_metadata(
            model_settings={
                "ollama_timeout_s": 60,
                "embedding_model": "nomic-embed-text",
                "extraction_temperature": 0.1,
            }
        ),
        results=[],
        summary=_summary(),
        gating=True,
    )
    text = render_report(populated)
    assert (
        "| model_settings | embedding_model=nomic-embed-text; "
        "extraction_temperature=0.1; ollama_timeout_s=60 |"
    ) in text


@pytest.mark.unit
def test_report_renders_empty_model_settings_as_a_dash() -> None:
    text = render_report(_result(_summary(), gating=True))
    assert "| model_settings | - |" in text


# ----------------------------- database sandbox -----------------------------


@pytest.mark.unit
async def test_sandbox_restores_settings_and_removes_temp_files_on_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "prod_omnibot.db")
    original = (tmp_path / "prod_omnibot.db").resolve()
    calls = _install_fake_db(monkeypatch, make_files=True)

    async with isolated_evaluation_database() as temp_path:
        assert settings.brain_db_path == temp_path
        assert temp_path.name == "brain.db"
        assert temp_path != original
        assert temp_path.parent.exists()
        temp_dir = temp_path.parent

    assert settings.brain_db_path == original
    assert not temp_dir.exists()
    assert calls == [("open", "brain.db"), "migrate", "close"]


@pytest.mark.unit
async def test_sandbox_opens_only_the_temporary_database(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "prod_omnibot.db")
    seen: list[Path] = []

    def _record_open() -> None:
        seen.append(Path(settings.brain_db_path))

    _install_fake_db(monkeypatch, on_open=_record_open)

    async with isolated_evaluation_database() as temp_path:
        assert seen == [temp_path]
    assert not (tmp_path / "prod_omnibot.db").exists()


@pytest.mark.unit
async def test_sandbox_rejects_a_pre_open_global_connection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "prod_omnibot.db")
    original = (tmp_path / "prod_omnibot.db").resolve()
    _install_fake_db(monkeypatch, is_open=True)
    with pytest.raises(HarnessError, match="already open"):
        async with isolated_evaluation_database():
            pass
    assert settings.brain_db_path == original


@pytest.mark.unit
async def test_sandbox_migration_failure_is_a_harness_error_and_restores_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "prod_omnibot.db")
    original = (tmp_path / "prod_omnibot.db").resolve()

    def _fail() -> None:
        raise BrainMemoryError("migration 7 failed")

    calls = _install_fake_db(monkeypatch, on_migrate=_fail)
    with pytest.raises(HarnessError, match="temporary database setup failed"):
        async with isolated_evaluation_database():
            pass
    assert settings.brain_db_path == original
    assert "close" in calls


@pytest.mark.unit
async def test_sandbox_close_failure_is_a_harness_error_and_still_restores_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "prod_omnibot.db")
    original = (tmp_path / "prod_omnibot.db").resolve()

    def _fail() -> None:
        raise BrainMemoryError("cannot close")

    _install_fake_db(monkeypatch, on_close=_fail)
    with pytest.raises(HarnessError, match="cleanup failed"):
        async with isolated_evaluation_database():
            pass
    assert settings.brain_db_path == original


class _DriverBoomError(RuntimeError):
    """A stand-in for an unexpected mid-run driver failure."""


@pytest.mark.unit
async def test_sandbox_body_failure_still_restores_settings_and_removes_temp_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "prod_omnibot.db")
    original = (tmp_path / "prod_omnibot.db").resolve()
    _install_fake_db(monkeypatch)
    captured: list[Path] = []

    async def _body() -> None:
        async with isolated_evaluation_database() as temp_path:
            captured.append(temp_path.parent)
            raise _DriverBoomError

    with pytest.raises(_DriverBoomError):
        await _body()
    assert settings.brain_db_path == original
    assert not captured[0].exists()


@pytest.mark.unit
def test_sandbox_path_proof_rejects_the_production_and_data_paths(tmp_path: Path) -> None:
    original = (tmp_path / "prod.db").resolve()
    with pytest.raises(HarnessError, match="equals the configured production path"):
        runner._prove_isolated(original, original)
    inside_data = (runner._REPO_ROOT / "data" / "nested" / "brain.db").resolve()
    with pytest.raises(HarnessError, match="inside the repository data/ directory"):
        runner._prove_isolated(inside_data, original)


# ----------------------------- CLI -----------------------------


@pytest.mark.unit
def test_cli_parse_defaults_and_provider_choice() -> None:
    options = parse_cli_args([])
    assert options.dataset_path.name == "golden_longitudinal_memory.yaml"
    assert options.runs == 1
    assert options.only == ()
    assert options.provider == "ollama"
    with pytest.raises(SystemExit) as excinfo:
        parse_cli_args(["--provider", "openai"])
    assert excinfo.value.code == 2


@pytest.mark.unit
def test_cli_rejects_an_output_path_outside_docs_evals(tmp_path: Path) -> None:
    options = _options(tmp_path, output_path=tmp_path / "escape.md")
    assert asyncio.run(run_cli(options)) == 2


@pytest.mark.unit
def test_cli_rejects_an_existing_output_file() -> None:
    taken = _REPO_ROOT / "docs" / "evals" / "README.md"
    options = CliOptions(
        dataset_path=_GOLDEN,
        output_path=taken,
        runs=1,
        only=(),
        reserved_terms=(),
        provider="ollama",
    )
    assert asyncio.run(run_cli(options)) == 2


@pytest.mark.unit
def test_cli_rejects_invalid_only_ids(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runner, "_OUTPUT_DIR", tmp_path)
    options = _options(tmp_path, only=("nope",))
    assert asyncio.run(run_cli(options)) == 2
    assert not (tmp_path / "report.md").exists()


@pytest.mark.unit
def test_cli_rejects_a_dataset_carrying_a_reserved_term(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner, "_OUTPUT_DIR", tmp_path)
    dataset = tmp_path / "suite.yaml"
    dataset.write_text("version: 1\nnote: la vecina Quorvax\n", encoding="utf-8")
    options = _options(tmp_path, dataset_path=dataset, reserved_terms=("quorvax",))
    assert asyncio.run(run_cli(options)) == 2


@pytest.mark.unit
def test_cli_preflight_failure_returns_two_and_writes_no_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner, "_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(runner, "_preflight_ok", _no)
    calls = _install_fake_db(monkeypatch)
    assert asyncio.run(run_cli(_options(tmp_path))) == 2
    assert not (tmp_path / "report.md").exists()
    assert calls == []  # the database sandbox is never entered


class _StubResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _StubClient:
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def __aenter__(self) -> _StubClient:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def get(self, _url: str) -> _StubResponse:
        return _StubResponse(200)


@pytest.mark.unit
async def test_cli_preflight_ok_true_when_ollama_answers_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runner.httpx, "AsyncClient", _StubClient)
    assert await runner._preflight_ok() is True


@pytest.mark.unit
async def test_cli_preflight_ok_false_on_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BrokenClient(_StubClient):
        async def get(self, _url: str) -> _StubResponse:
            raise httpx.ConnectError("refused")

    monkeypatch.setattr(runner.httpx, "AsyncClient", _BrokenClient)
    assert await runner._preflight_ok() is False


@pytest.mark.unit
def test_cli_full_red_run_writes_a_report_and_returns_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner, "_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "prod_omnibot.db")
    monkeypatch.setattr(metadata_mod, "_git", _fake_git)
    monkeypatch.setattr(sys, "argv", ["eval_longitudinal_memory.py", "--runs", "3"])
    original = (tmp_path / "prod_omnibot.db").resolve()
    monkeypatch.setattr(runner, "_preflight_ok", _yes)
    monkeypatch.setattr(
        runner, "_build_driver", lambda _client: _ScriptedDriver(echo_expected=True)
    )
    _install_fake_db(monkeypatch)

    assert asyncio.run(run_cli(_options(tmp_path, runs=3))) == 1
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert report.startswith("# Longitudinal-memory evaluation report")
    assert "gating baseline" in report
    assert settings.brain_db_path == original


@pytest.mark.unit
def test_cli_smoke_only_run_that_fully_passes_returns_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner, "_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "prod_omnibot.db")
    monkeypatch.setattr(metadata_mod, "_git", _fake_git)
    monkeypatch.setattr(runner, "_preflight_ok", _yes)
    monkeypatch.setattr(
        runner, "_build_driver", lambda _client: _ScriptedDriver(echo_expected=True)
    )
    _install_fake_db(monkeypatch)

    options = _options(tmp_path, only=("extraction_family_and_pet",))
    assert asyncio.run(run_cli(options)) == 0
    assert "non-gating" in (tmp_path / "report.md").read_text(encoding="utf-8")


@pytest.mark.unit
def test_cli_mid_run_provider_failure_returns_two_and_writes_no_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner, "_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "prod_omnibot.db")
    monkeypatch.setattr(metadata_mod, "_git", _fake_git)
    original = (tmp_path / "prod_omnibot.db").resolve()
    monkeypatch.setattr(runner, "_preflight_ok", _yes)
    monkeypatch.setattr(
        runner, "_build_driver", lambda _client: _ScriptedDriver(extract_status="error")
    )
    calls = _install_fake_db(monkeypatch)

    options = _options(tmp_path, only=("extraction_family_and_pet",))
    assert asyncio.run(run_cli(options)) == 2
    assert not (tmp_path / "report.md").exists()
    assert settings.brain_db_path == original
    assert "close" in calls  # resources were released


@pytest.mark.unit
def test_cli_incomplete_full_run_missing_a_category_returns_two(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner, "_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "prod_omnibot.db")
    monkeypatch.setattr(metadata_mod, "_git", _fake_git)
    monkeypatch.setattr(runner, "_preflight_ok", _yes)
    monkeypatch.setattr(
        runner, "_build_driver", lambda _client: _ScriptedDriver(echo_expected=True)
    )
    _install_fake_db(monkeypatch)

    def _one_scenario(
        suite: LongitudinalSuite, only: tuple[str, ...]
    ) -> tuple[LongitudinalScenario, ...]:
        return (suite.scenarios[1],)  # the extraction-only scenario

    monkeypatch.setattr(runner, "_select_scenarios", _one_scenario)
    assert asyncio.run(run_cli(_options(tmp_path, runs=3))) == 2
    assert not (tmp_path / "report.md").exists()


# ----------------------------- sys.path bootstrap -----------------------------


@pytest.mark.unit
def test_eval_longitudinal_memory_is_importable() -> None:
    module = importlib.import_module("scripts.eval_longitudinal_memory")
    assert hasattr(module, "main")
    assert hasattr(module, "parse_cli_args")


@pytest.mark.unit
def test_eval_longitudinal_memory_help_exits_zero_under_direct_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = _REPO_ROOT / "scripts" / "eval_longitudinal_memory.py"
    monkeypatch.setattr(sys, "argv", [str(script), "--help"])
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(str(script), run_name="__main__")
    assert excinfo.value.code == 0
