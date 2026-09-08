"""Deterministic RED/GREEN coverage for the longitudinal-memory suite.

These tests never reach Ollama, the network or a real database. They pin the
frozen schema, the semantic rules enforced by ``load_suite``, the privacy
rules enforced by ``validate_dataset_privacy``, a coverage check on the
committed version-1 YAML suite, and (Task 3) the deterministic scoring layer
in ``scripts.longitudinal_eval_scoring`` /
``scripts.longitudinal_eval_aggregation``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.eval_longitudinal_memory import load_suite, validate_dataset_privacy
from scripts.longitudinal_eval_aggregation import aggregate_results, determine_exit_code
from scripts.longitudinal_eval_models import (
    BenchmarkSummary,
    CapabilityStatus,
    ExpectedObservation,
    LongitudinalCategory,
    LongitudinalOperation,
    LongitudinalStep,
    ProbeObservation,
    ScoredStep,
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


@pytest.mark.unit
def test_determine_exit_code_zero_when_gating_and_all_strict_gates_pass() -> None:
    assert determine_exit_code(_summary(), gating=True) == 0


@pytest.mark.unit
def test_determine_exit_code_one_when_a_cognitive_case_is_unsupported() -> None:
    assert determine_exit_code(_summary(passed=0, unsupported=1), gating=True) == 1


@pytest.mark.unit
def test_determine_exit_code_one_when_gating_gate_denominator_missing() -> None:
    assert determine_exit_code(_summary(complete_deletion_rate=None), gating=True) == 1


@pytest.mark.unit
def test_determine_exit_code_two_when_a_harness_error_is_present() -> None:
    assert determine_exit_code(_summary(passed=0, errors=1), gating=True) == 2


@pytest.mark.unit
def test_determine_exit_code_zero_for_non_gating_smoke_without_failures() -> None:
    smoke = _summary(
        forbidden_disclosure_rate=None,
        complete_deletion_rate=None,
        truth_current_accuracy=None,
        provenance_accuracy=None,
    )
    assert determine_exit_code(smoke, gating=False) == 0
