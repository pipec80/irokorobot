"""Dataset version 3 and the frozen version-2 copy (Plan 0065, Tasks 7a and 7b).

Task 7a made the loader, the models and the run metadata accept versions 2 and 3,
and kept the version-2 dataset loadable as a frozen copy beside the live one.
Task 7b changed the scenarios: version 3 is version 2 plus two personal-scope
scenarios, with ``provenance_attribution`` moved from the personal to the family
stage; the tests below pin that delta and the comparability cut the dataset header
declares. Nothing here reaches Ollama, the network or a database.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from server.settings import settings
import yaml

from scripts import longitudinal_eval_metadata as metadata_mod, longitudinal_eval_models as models
from scripts.eval_longitudinal_memory import load_suite
from scripts.longitudinal_eval_metadata import collect_run_metadata

_EVALS = Path(__file__).resolve().parents[1] / "evals"
_LIVE = _EVALS / "golden_longitudinal_memory.yaml"
_FROZEN_V2 = _EVALS / "golden_longitudinal_memory_v2.yaml"

# The frozen copy is the byte-for-byte version-2 file of Plan 0056 (LF endings are
# enforced by .gitattributes, so the digest is the same on every platform). Editing
# it breaks this pin on purpose: a frozen baseline is replaced, never patched.
_FROZEN_V2_SHA256 = "3ba532c3521db99c509a704be64c84e923748594cf442776d0d77a5fd77c4913"


def _fake_git(*args: str) -> str:
    """Stand in for ``git`` so metadata collection never shells out."""
    if args[:2] == ("rev-parse", "--abbrev-ref"):
        return "feat/0065-cm3b-a-writer-core"
    if args[:1] == ("rev-parse",):
        return "0" * 40
    return ""


@pytest.fixture(autouse=True)
def _stable_metadata_inputs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep ``collect_run_metadata`` away from git and the configured database."""
    monkeypatch.setattr(metadata_mod, "_git", _fake_git)
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "brain.db")


@pytest.mark.unit
def test_the_supported_dataset_versions_are_two_and_three() -> None:
    assert models.SUPPORTED_DATASET_VERSIONS == (2, 3)


@pytest.mark.unit
def test_the_live_dataset_declares_version_three() -> None:
    assert load_suite(_LIVE).version == 3


@pytest.mark.unit
def test_the_frozen_v2_copy_loads_through_the_same_loader_as_version_two() -> None:
    assert load_suite(_FROZEN_V2).version == 2


@pytest.mark.unit
def test_the_frozen_v2_copy_is_byte_for_byte_the_plan_0056_dataset() -> None:
    assert hashlib.sha256(_FROZEN_V2.read_bytes()).hexdigest() == _FROZEN_V2_SHA256


# The two scenarios version 3 adds to the version-2 set (Plan 0065, Task 7b).
_NEW_IN_V3 = ("personal_provenance_owner_statement", "personal_access_code_pending")
# What the live dataset's header declares about the cut with the version-2 baseline,
# per dataset: (whole suite, personal stage, family stage), each as scenarios / steps.
_HEADER_SIZES = {
    _FROZEN_V2: ("9 scenarios / 25 steps", "7 scenarios / 18 steps", "2 scenarios / 7 steps"),
    _LIVE: ("11 scenarios / 30 steps", "8 scenarios / 21 steps", "3 scenarios / 9 steps"),
}
# Unsupported steps per dataset: every step but the single extraction one.
_HEADER_UNSUPPORTED = {_FROZEN_V2: 24, _LIVE: 29}


def _by_id(path: Path) -> dict[str, models.LongitudinalScenario]:
    """One dataset's scenarios keyed by id, in file order."""
    return {scenario.scenario_id: scenario for scenario in load_suite(path).scenarios}


def _size(scenarios: list[models.LongitudinalScenario]) -> str:
    """``N scenarios / M steps``, the wording the dataset header uses."""
    return f"{len(scenarios)} scenarios / {sum(len(s.steps) for s in scenarios)} steps"


@pytest.mark.unit
def test_version_three_is_version_two_plus_exactly_the_two_new_scenarios() -> None:
    frozen = _by_id(_FROZEN_V2)
    live = _by_id(_LIVE)

    assert set(live) - set(frozen) == set(_NEW_IN_V3)
    assert set(frozen) <= set(live)
    assert len(live) == len(frozen) + len(_NEW_IN_V3)
    # The shared scenarios keep their relative order.
    assert [sid for sid in live if sid not in _NEW_IN_V3] == list(frozen)


@pytest.mark.unit
def test_the_only_change_to_a_version_two_scenario_is_the_scope_of_provenance_attribution() -> None:
    """ADR 0022 decision 5: a fact reported by another person leaves the personal stage."""
    frozen = _by_id(_FROZEN_V2)
    live = _by_id(_LIVE)

    changed = [
        scenario_id for scenario_id, scenario in frozen.items() if live[scenario_id] != scenario
    ]

    assert changed == ["provenance_attribution"]
    before = frozen["provenance_attribution"]
    assert (before.scope, live["provenance_attribution"].scope) == ("personal", "family")
    assert live["provenance_attribution"] == before.model_copy(update={"scope": "family"})


@pytest.mark.unit
def test_the_new_scenarios_are_personal_and_the_family_stage_only_gains_the_moved_one() -> None:
    frozen = _by_id(_FROZEN_V2)
    live = _by_id(_LIVE)

    assert {live[scenario_id].scope for scenario_id in _NEW_IN_V3} == {"personal"}
    family = {sid for sid, scenario in live.items() if scenario.scope == "family"}
    frozen_family = {sid for sid, scenario in frozen.items() if scenario.scope == "family"}
    assert family == {*frozen_family, "provenance_attribution"}


@pytest.mark.unit
@pytest.mark.parametrize("dataset", [_FROZEN_V2, _LIVE], ids=["frozen-v2", "live-v3"])
def test_the_header_declares_the_comparability_cut_with_the_sizes_the_files_really_have(
    dataset: Path,
) -> None:
    """The cut is written where the dataset is read; its numbers are the real ones."""
    scenarios = list(_by_id(dataset).values())
    personal = [s for s in scenarios if s.scope == "personal"]
    family = [s for s in scenarios if s.scope == "family"]
    header = _LIVE.read_text(encoding="utf-8").split("\nversion:", maxsplit=1)[0]

    assert "COMPARABILITY CUT" in header
    declared = _HEADER_SIZES[dataset]
    assert (_size(scenarios), _size(personal), _size(family)) == declared
    for size in declared:
        assert size in header
    steps = [step for scenario in scenarios for step in scenario.steps]
    unsupported = [s for s in steps if s.operation is not models.LongitudinalOperation.EXTRACT]
    assert len(unsupported) == _HEADER_UNSUPPORTED[dataset]
    assert f"{_HEADER_UNSUPPORTED[dataset]} unsupported steps" in header


@pytest.mark.unit
@pytest.mark.parametrize(
    "dataset, expected",
    [pytest.param(_FROZEN_V2, 2, id="frozen-v2"), pytest.param(_LIVE, 3, id="live-v3")],
)
def test_the_run_metadata_reports_the_version_the_dataset_declares(
    dataset: Path, expected: int
) -> None:
    assert collect_run_metadata(dataset, [], []).dataset_version == expected


@pytest.mark.unit
@pytest.mark.parametrize("text", ["version: 4\nscenarios: []\n", "scenarios: []\n", "- a\n- b\n"])
def test_the_run_metadata_rejects_a_dataset_with_an_unsupported_version(
    tmp_path: Path, text: str
) -> None:
    dataset = tmp_path / "suite.yaml"
    dataset.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="version"):
        collect_run_metadata(dataset, [], [])


@pytest.mark.unit
@pytest.mark.parametrize("version", [2, 3])
def test_the_suite_model_accepts_each_supported_version(version: int) -> None:
    assert models.LongitudinalSuite.model_validate({"version": version, "scenarios": []})


@pytest.mark.unit
@pytest.mark.parametrize("version", [1, 4])
def test_the_suite_model_rejects_any_other_version(version: int) -> None:
    with pytest.raises(ValueError, match="version"):
        models.LongitudinalSuite.model_validate({"version": version, "scenarios": []})


@pytest.mark.unit
def test_a_dataset_file_round_trips_its_declared_version(tmp_path: Path) -> None:
    """The metadata reads the same ``version`` key the loader validates."""
    dataset = tmp_path / "suite.yaml"
    dataset.write_text(yaml.safe_dump({"version": 3, "scenarios": []}), encoding="utf-8")

    assert collect_run_metadata(dataset, [], []).dataset_version == 3
