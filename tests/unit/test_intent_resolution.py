"""Unit tests for server.cognition.intent_resolution — the P0-C5 pure resolver.

Covers the reviewed Spanish corpus, precedence, normalization stability,
rule-ID privacy, and immutability. This resolver never identifies a speaker,
grants access, or calls an LLM/VLM/embedding/database — see
docs/plans/open/0021-p0-typed-intent-resolution.md.
"""

import json
from pathlib import Path

from pydantic import ValidationError
import pytest
from server.cognition.intent_resolution import (
    IntentMatch,
    IntentResolution,
    resolve_information_need,
)
from server.cognition.response_plan import InformationNeed

_FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "intent_resolution_es.json"
_CORPUS: list[dict[str, object]] = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.mark.unit
@pytest.mark.parametrize("row", _CORPUS, ids=[str(row["text"]) for row in _CORPUS])
def test_resolver_matches_the_reviewed_corpus(row: dict[str, object]) -> None:
    """Every reviewed phrase resolves to its exact expected need/match/rule."""
    expected = IntentResolution(
        need=InformationNeed(row["need"]),
        match=IntentMatch(row["match"]),
        rule_id=row["rule_id"],  # type: ignore[arg-type]  # str | None from JSON
    )

    result = resolve_information_need(str(row["text"]))

    assert result == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "variant,canonical",
    [
        ("¿QUÉ FECHA ES HOY?", "¿Qué fecha es hoy?"),
        ("que    fecha    es    hoy", "¿Qué fecha es hoy?"),
        ("¿Qué, fecha... es hoy?!", "¿Qué fecha es hoy?"),
        ("qué fecha es hoy", "¿Qué fecha es hoy?"),
    ],
)
def test_normalization_is_stable_across_case_spacing_and_punctuation(
    variant: str, canonical: str
) -> None:
    """Case, accents, repeated whitespace, and punctuation must not change the result."""
    assert resolve_information_need(variant) == resolve_information_need(canonical)


@pytest.mark.unit
def test_rule_id_never_contains_the_utterance_or_a_name() -> None:
    """rule_id is closed operational metadata, never the raw message or a name."""
    result = resolve_information_need("¿Cuándo nació Máximo?")

    assert result.rule_id is not None
    assert "maximo" not in result.rule_id.lower()
    assert "nacio" not in result.rule_id.lower()
    assert "cuando" not in result.rule_id.lower()


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "Aprende mi cara, soy PersonaDePrueba.",
        "Aprende mi cara.",
    ],
)
def test_enrollment_rule_id_never_contains_the_utterance_or_a_name(text: str) -> None:
    """The resolver never extracts or retains a name — same rule_id either way."""
    result = resolve_information_need(text)

    assert result.need is InformationNeed.BIOMETRIC_ENROLLMENT
    assert result.rule_id == "enrollment.biometric.v1"
    assert "personadeprueba" not in result.rule_id.lower()


@pytest.mark.unit
def test_resolution_is_frozen_and_rejects_mutation() -> None:
    """IntentResolution must be immutable, matching every other cognitive contract."""
    result = resolve_information_need("Hola, ¿cómo estás?")

    with pytest.raises(ValidationError):
        result.need = InformationNeed.CURRENT_DATE  # type: ignore[misc]  # proving frozen


@pytest.mark.unit
def test_resolution_rejects_unknown_fields() -> None:
    """The contract is closed — extra fields must be rejected, not silently dropped."""
    with pytest.raises(ValidationError):
        IntentResolution(
            need=InformationNeed.GENERIC_CONVERSATION,
            match=IntentMatch.NONE,
            rule_id=None,
            confidence=0.9,  # type: ignore[call-arg]  # deliberately unsupported field
        )
