"""Settings of the memory-candidate subsystem (ADR 0021 decision 10)."""

from pathlib import Path

from pydantic import ValidationError
import pytest
from server.cognition.intent_resolution import normalize_spanish
from server.settings import Settings, settings

pytestmark = pytest.mark.unit

_DEFAULTS = {
    "memory_candidates_enabled": False,
    "memory_candidate_ttl_seconds": 86_400,
    "memory_candidate_max_live": 5,
    "memory_candidate_value_max_chars": 80,
    "memory_candidate_max_offers": 2,
    "memory_candidate_answer_seconds": 60,
    "memory_candidate_extractions_per_hour": 12,
}
_LIMITS = [name for name in _DEFAULTS if name != "memory_candidates_enabled"]


def test_the_candidate_defaults_are_the_ones_of_the_adr() -> None:
    """Field defaults, so neither the shell nor a local `.env` can change the answer."""
    assert {name: Settings.model_fields[name].default for name in _DEFAULTS} == _DEFAULTS


@pytest.mark.parametrize("name", _LIMITS)
def test_a_limit_of_zero_is_refused(name: str) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({name: 0})


def test_the_test_suite_pins_the_kill_switch_off() -> None:
    """The autouse fixture of `tests/conftest.py` keeps a developer's `.env` out of the tests."""
    assert settings.memory_candidates_enabled is False


def test_env_example_documents_every_candidate_setting() -> None:
    text = (Path(__file__).resolve().parents[2] / ".env.example").read_text(encoding="utf-8")

    for name in _DEFAULTS:
        assert f"{name.upper()}=" in text


def test_normalize_spanish_folds_accents_case_and_punctuation() -> None:
    assert normalize_spanish("¡Me GUSTÓ el café,  ñandú!") == "me gusto el cafe nandu"
