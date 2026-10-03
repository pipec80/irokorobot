"""Staged personal / family / full-suite verdicts (Plan 0056, Task 3)."""

from pathlib import Path

import pytest

from scripts.eval_longitudinal_memory import load_suite
from scripts.longitudinal_eval_aggregation import STAGE_GATES, staged_verdicts
from scripts.longitudinal_eval_models import (
    LongitudinalOperation,
    LongitudinalScenario,
    LongitudinalStep,
    ProbeObservation,
    ScenarioScope,
    ScoredStep,
    StagedVerdict,
    StagedVerdicts,
)
from scripts.longitudinal_eval_report import _staged_section
from scripts.longitudinal_eval_scoring import score_step

_SCOPES: dict[str, ScenarioScope] = {"mine": "personal", "theirs": "family"}


def _expected(required_any: list[list[str]] | None = None) -> dict[str, object]:
    return {
        "required_any": required_any or [],
        "forbidden": [],
        "expected_items": [],
        "forbidden_items": [],
        "expected_provenance": {},
        "required_absent_derivatives": [],
    }


def _scored(scenario_id: str, status: str = "pass", *, fails: bool = False) -> ScoredStep:
    step = LongitudinalStep.model_validate(
        {
            "step_id": "s1",
            "category": "extraction",
            "operation": "extract",
            "session": 1,
            "actor_id": "aria",
            "message": "m",
            "expected": _expected([["zzz"]] if fails else None),
        }
    )
    observation = ProbeObservation.model_validate(
        {
            "status": status,
            "response": "",
            "observed_items": (),
            "observed_provenance": {},
            "latency_ms": 1.0,
            "reason": None,
            "inspected_derivatives": {},
        }
    )
    return score_step(scenario_id, step, observation)


@pytest.mark.unit
def test_personal_passes_while_family_is_pending_and_the_suite_still_fails() -> None:
    verdicts = staged_verdicts(
        [_scored("mine"), _scored("theirs", "unsupported")], _SCOPES, gating=False
    )

    assert verdicts.personal is StagedVerdict.PASS
    assert verdicts.family is StagedVerdict.PENDING
    assert verdicts.full_suite is StagedVerdict.FAIL


@pytest.mark.unit
def test_everything_passing_passes_every_stage() -> None:
    verdicts = staged_verdicts([_scored("mine"), _scored("theirs")], _SCOPES, gating=False)

    assert (verdicts.personal, verdicts.family, verdicts.full_suite) == (
        StagedVerdict.PASS,
        StagedVerdict.PASS,
        StagedVerdict.PASS,
    )


@pytest.mark.unit
def test_an_unsupported_personal_step_fails_personal() -> None:
    verdicts = staged_verdicts(
        [_scored("mine", "unsupported"), _scored("theirs")], _SCOPES, gating=False
    )

    assert verdicts.personal is StagedVerdict.FAIL
    assert verdicts.family is StagedVerdict.PASS


@pytest.mark.unit
def test_a_failed_family_step_is_a_failure_not_pending() -> None:
    verdicts = staged_verdicts(
        [_scored("mine"), _scored("theirs", fails=True)], _SCOPES, gating=False
    )

    assert verdicts.family is StagedVerdict.FAIL


@pytest.mark.unit
def test_a_harness_error_is_reported_as_error_in_its_scope_only() -> None:
    verdicts = staged_verdicts([_scored("mine"), _scored("theirs", "error")], _SCOPES, gating=False)

    assert verdicts.personal is StagedVerdict.PASS
    assert verdicts.family is StagedVerdict.ERROR
    assert verdicts.full_suite is StagedVerdict.ERROR


@pytest.mark.unit
def test_a_smoke_run_of_one_scope_does_not_claim_the_other_passed() -> None:
    verdicts = staged_verdicts([_scored("mine")], _SCOPES, gating=False)

    assert verdicts.personal is StagedVerdict.PASS
    assert verdicts.family is StagedVerdict.NOT_RUN


@pytest.mark.unit
def test_a_gating_run_needs_the_frozen_gates_so_clean_steps_alone_do_not_pass() -> None:
    """Extraction-only steps leave every strict-gate denominator empty: that fails."""
    verdicts = staged_verdicts([_scored("mine"), _scored("theirs")], _SCOPES, gating=True)

    assert verdicts.personal is StagedVerdict.FAIL
    assert verdicts.full_suite is StagedVerdict.FAIL


@pytest.mark.unit
def test_a_gating_run_with_an_empty_scope_fails_that_scope() -> None:
    verdicts = staged_verdicts([_scored("mine")], _SCOPES, gating=True)

    assert verdicts.family is StagedVerdict.FAIL


@pytest.mark.unit
def test_the_frozen_dataset_declares_a_scope_for_every_scenario() -> None:
    suite = load_suite(Path("tests/evals/golden_longitudinal_memory.yaml"))

    scopes = {scenario.scenario_id: scenario.scope for scenario in suite.scenarios}

    assert suite.version == 2
    assert {sid for sid, scope in scopes.items() if scope == "family"} == {
        "two_adult_private_facts",
        "recipient_only_message",
    }
    assert set(scopes.values()) == {"personal", "family"}


def _step(
    scenario_id: str,
    step_id: str,
    category: str,
    operation: str,
    *,
    response: str = "",
    forbidden: list[str] | None = None,
    required_any: list[list[str]] | None = None,
    required_absent: list[str] | None = None,
    provenance: dict[str, str] | None = None,
    inspected: dict[str, bool] | None = None,
) -> ScoredStep:
    """Score one passing-by-default step of any category (a gate-feeding building block)."""
    expected = _expected(required_any)
    expected["forbidden"] = forbidden or []
    expected["required_absent_derivatives"] = required_absent or []
    expected["expected_provenance"] = provenance or {}
    step = LongitudinalStep.model_validate(
        {
            "step_id": step_id,
            "category": category,
            "operation": operation,
            "session": 1,
            "actor_id": "aria",
            "message": "m",
            "expected": expected,
        }
    )
    observation = ProbeObservation.model_validate(
        {
            "status": "pass",
            "response": response,
            "observed_items": (),
            "observed_provenance": provenance or {},
            "latency_ms": 1.0,
            "reason": None,
            "inspected_derivatives": inspected or {},
        }
    )
    return score_step(scenario_id, step, observation)


def _cross_person_steps(scenario_id: str, *, leak: bool = False) -> list[ScoredStep]:
    """The shape of the family scenarios: private disclosures, then guarded recalls."""
    return [
        _step(scenario_id, "disclose", "cross_person_privacy", "propose"),
        _step(
            scenario_id,
            "guest_asks",
            "cross_person_privacy",
            "recall",
            forbidden=["canarysecret"],
            response="contiene canarysecret" if leak else "no puedo compartir eso",
        ),
    ]


def _personal_steps(scenario_id: str) -> list[ScoredStep]:
    """Personal steps that feed all four frozen gates, every one passing."""
    return [
        _step(scenario_id, "correct", "update", "correct", required_any=[["ok"]], response="ok"),
        _step(
            scenario_id,
            "recall_current",
            "temporality",
            "recall",
            required_any=[["normalidad"]],
            response="con normalidad",
        ),
        _step(
            scenario_id,
            "inspect",
            "complete_deletion",
            "inspect_derivatives",
            required_absent=["fact"],
            inspected={"fact": False},
        ),
        _step(
            scenario_id,
            "provenance",
            "provenance",
            "recall",
            provenance={"subject": "aria"},
        ),
        *_cross_person_steps(scenario_id),
    ]


@pytest.mark.unit
def test_a_complete_gating_run_can_pass_every_stage() -> None:
    """The family stage is judged on the gate its scenarios feed, so it can pass."""
    scored = [*_personal_steps("mine"), *_cross_person_steps("theirs")]

    verdicts = staged_verdicts(scored, _SCOPES, gating=True)

    assert (verdicts.personal, verdicts.family, verdicts.full_suite) == (
        StagedVerdict.PASS,
        StagedVerdict.PASS,
        StagedVerdict.PASS,
    )


@pytest.mark.unit
def test_a_family_disclosure_fails_the_family_stage_on_a_gating_run() -> None:
    scored = [*_personal_steps("mine"), *_cross_person_steps("theirs", leak=True)]

    verdicts = staged_verdicts(scored, _SCOPES, gating=True)

    assert verdicts.personal is StagedVerdict.PASS
    assert verdicts.family is StagedVerdict.FAIL
    assert verdicts.full_suite is StagedVerdict.FAIL


@pytest.mark.unit
def test_family_scenarios_that_never_exercise_cross_person_privacy_cannot_pass() -> None:
    """No vacuous pass: the family gate still needs a non-empty denominator."""
    scored = [*_personal_steps("mine"), _scored("theirs")]

    assert staged_verdicts(scored, _SCOPES, gating=True).family is StagedVerdict.FAIL


@pytest.mark.unit
def test_the_personal_stage_still_needs_all_four_gates() -> None:
    """Without a deletion step the personal deletion gate has no denominator."""
    scored = [s for s in _personal_steps("mine") if s.result.step_id != "inspect"]
    scored += _cross_person_steps("theirs")

    verdicts = staged_verdicts(scored, _SCOPES, gating=True)

    assert verdicts.personal is StagedVerdict.FAIL
    assert verdicts.family is StagedVerdict.PASS


def _feeds(gate: str, scenario: LongitudinalScenario) -> bool:
    """Whether one dataset scenario can contribute a denominator to a frozen gate."""
    steps = scenario.steps
    if gate == "forbidden_disclosure_rate":
        return any(s.category == "cross_person_privacy" and s.operation == "recall" for s in steps)
    if gate == "complete_deletion_rate":
        return any(s.expected.required_absent_derivatives for s in steps)
    if gate == "truth_current_accuracy":
        operations = [s.operation for s in steps]
        if LongitudinalOperation.CORRECT not in operations:
            return False
        later = operations[operations.index(LongitudinalOperation.CORRECT) :]
        return LongitudinalOperation.RECALL in later
    if gate == "provenance_accuracy":
        return any(s.expected.expected_provenance for s in steps)
    raise AssertionError(f"unknown gate {gate}")


@pytest.mark.unit
@pytest.mark.parametrize("scope", ["personal", "family"])
def test_every_gate_of_a_stage_is_fed_by_a_scenario_of_that_stage(scope: ScenarioScope) -> None:
    """Otherwise the stage could never pass: the dataset must feed what the stage demands."""
    suite = load_suite(Path("tests/evals/golden_longitudinal_memory.yaml"))
    scenarios = [s for s in suite.scenarios if s.scope == scope]

    for gate in STAGE_GATES[scope]:
        assert any(_feeds(gate, scenario) for scenario in scenarios), (scope, gate)


@pytest.mark.unit
def test_the_report_section_lists_the_three_verdicts() -> None:
    section = _staged_section(
        StagedVerdicts(
            personal=StagedVerdict.PASS,
            family=StagedVerdict.PENDING,
            full_suite=StagedVerdict.FAIL,
        )
    )

    assert section is not None
    assert "| Personal acceptance (CM-7 exit evidence) | PASS |" in section
    assert "| Family acceptance (pending until P3.2) | PENDING |" in section
    assert "| Full suite | FAIL |" in section
    assert "family on the disclosure gate" in section
    assert _staged_section(None) is None


@pytest.mark.unit
def test_a_non_gating_section_is_not_presented_as_acceptance() -> None:
    """Without the frozen gates a PASS only means the steps passed, never CM-7."""
    section = _staged_section(
        StagedVerdicts(
            personal=StagedVerdict.PASS,
            family=StagedVerdict.NOT_RUN,
            full_suite=StagedVerdict.PASS,
        ),
        gating=False,
    )

    assert section is not None
    assert "partial run" in section
    assert "gates were not applied" in section
    assert "CM-7" not in section.replace("not CM-7", "")
    assert "judged on all four" not in section
    assert "| Personal | PASS |" in section
    assert "| Family | NOT_RUN |" in section
