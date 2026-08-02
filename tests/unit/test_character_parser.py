"""Unit tests for markdown character parsing and personality validation."""

from __future__ import annotations

import pytest
from server.characters.base import PersonalityProfile
from server.characters.parser import parse_character
import yaml

_VALID = """\
---
curiosity: 0.8
verbosity: 0.35
empathy: 0.85
humor: 0.35
social_energy: "moderate"
---
# BASE PROMPT
Sos un personaje de prueba.

FORMATO — respondé SIEMPRE con JSON válido:
{"response": "<texto>", "emotion": "<emoción>"}

# ONBOARDING PROMPT
Presentate brevemente.
"""


# --- PersonalityProfile validation ---


@pytest.mark.unit
def test_personality_valid_construction() -> None:
    p = PersonalityProfile(curiosity=0.5, verbosity=0.5, empathy=0.5, humor=0.5)
    assert p.social_energy == "moderate"


@pytest.mark.unit
@pytest.mark.parametrize("value", ["alto", None, [0.5]])
def test_personality_non_numeric_axis_rejected(value: object) -> None:
    with pytest.raises(ValueError, match="must be a number"):
        PersonalityProfile(curiosity=value)  # type: ignore[arg-type]


@pytest.mark.unit
def test_personality_bool_axis_rejected() -> None:
    """A YAML `humor: true` becomes a bool — not a valid axis value."""
    with pytest.raises(ValueError, match="must be a number"):
        PersonalityProfile(humor=True)  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.parametrize("value", [-0.1, 1.5, 2.0])
def test_personality_out_of_range_rejected(value: float) -> None:
    with pytest.raises(ValueError, match=r"in \[0, 1\]"):
        PersonalityProfile(empathy=value)


@pytest.mark.unit
def test_personality_unknown_social_energy_rejected() -> None:
    with pytest.raises(ValueError, match="social_energy"):
        PersonalityProfile(social_energy="cosmic")


# --- parse_character ---


@pytest.mark.unit
def test_parse_valid_profile() -> None:
    profile = parse_character(_VALID, "Prueba")

    assert profile.name == "prueba"
    assert profile.base_prompt.startswith("Sos un personaje de prueba.")
    assert "# BASE PROMPT" not in profile.base_prompt
    assert profile.onboarding_prompt == "Presentate brevemente."
    assert profile.personality.curiosity == 0.8


@pytest.mark.unit
def test_parse_without_onboarding_header() -> None:
    text = _VALID.split("# ONBOARDING PROMPT", 1)[0]

    profile = parse_character(text, "prueba")

    assert profile.onboarding_prompt == ""
    assert "personaje de prueba" in profile.base_prompt


@pytest.mark.unit
def test_parse_no_frontmatter_raises() -> None:
    with pytest.raises(ValueError, match="No YAML frontmatter"):
        parse_character("# BASE PROMPT\nsin frontmatter", "x")


@pytest.mark.unit
def test_parse_frontmatter_not_a_mapping_raises() -> None:
    text = "---\n- uno\n- dos\n---\n# BASE PROMPT\ntexto"

    with pytest.raises(ValueError, match="not a YAML mapping"):
        parse_character(text, "x")


@pytest.mark.unit
def test_parse_missing_json_contract_raises() -> None:
    """Dropping the JSON contract must fail loudly, not ship a broken robot."""
    text = "---\ncuriosity: 0.5\n---\n# BASE PROMPT\nSoy un personaje sin contrato."

    with pytest.raises(ValueError, match="JSON response"):
        parse_character(text, "x")


@pytest.mark.unit
def test_parse_empty_base_prompt_raises() -> None:
    text = '---\ncuriosity: 0.5\n---\n# BASE PROMPT\n\n# ONBOARDING PROMPT\n{"response","emotion"}'

    with pytest.raises(ValueError, match="base prompt is empty"):
        parse_character(text, "x")


@pytest.mark.unit
def test_parse_invalid_personality_value_raises() -> None:
    bad = _VALID.replace("curiosity: 0.8", 'curiosity: "muchísimo"')

    with pytest.raises(ValueError, match="must be a number"):
        parse_character(bad, "x")


@pytest.mark.unit
def test_parse_invalid_yaml_raises() -> None:
    text = "---\ncuriosity: : :\n---\n# BASE PROMPT\ntexto"

    with pytest.raises((ValueError, yaml.YAMLError)):
        parse_character(text, "x")


@pytest.mark.unit
def test_parse_ignores_unknown_frontmatter_keys() -> None:
    text = _VALID.replace("social_energy:", "malicious_key: 99\nsocial_energy:")

    profile = parse_character(text, "x")

    assert not hasattr(profile.personality, "malicious_key")
