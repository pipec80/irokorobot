"""Dataset version 3 and the frozen version-2 copy (Plan 0065, Task 7a).

Version 3 changes only the plumbing in this task: the loader, the models and the
run metadata accept versions 2 and 3, the live dataset declares 3, and the
version-2 dataset stays loadable as a frozen copy beside it. Scenario content is
Task 7b, so the comparison with the frozen copy below is a conscious edit there.
Nothing here reaches Ollama, the network or a database.
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


@pytest.mark.unit
def test_version_three_changes_no_scenario_until_task_7b() -> None:
    """Task 7a only bumps the version; 7b edits this test when it changes the scenarios."""
    frozen = load_suite(_FROZEN_V2)
    live = load_suite(_LIVE)

    assert [(s.scenario_id, s.scope) for s in live.scenarios] == [
        (s.scenario_id, s.scope) for s in frozen.scenarios
    ]
    assert live.scenarios == frozen.scenarios


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
