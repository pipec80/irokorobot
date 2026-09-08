"""Deterministic RED/GREEN coverage for the longitudinal-memory suite (Task 2).

These tests never reach Ollama, the network or a real database. They pin the
frozen schema, the semantic rules enforced by ``load_suite`` and the privacy
rules enforced by ``validate_dataset_privacy``, plus a coverage check that the
committed version-1 YAML suite exercises every canonical category and domain.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.eval_longitudinal_memory import load_suite, validate_dataset_privacy
from scripts.longitudinal_eval_models import LongitudinalCategory, LongitudinalOperation

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
