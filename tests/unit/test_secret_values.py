"""The secret words and the stated or asked value rule (Plan 0079 Task 1, D-2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from server.secret_values import SecretKind, secret_kind
import yaml

pytestmark = pytest.mark.unit

_CORPUS = yaml.safe_load(
    (Path(__file__).resolve().parents[1] / "fixtures" / "secret_phrases.yaml").read_text(
        encoding="utf-8"
    )
)
_PHRASES = [
    (phrase, kind)
    for kind, key in (
        (SecretKind.STATED, "stated"),
        (SecretKind.ASKED, "asked"),
        (SecretKind.OFFERED, "offered"),
        (None, "none"),
    )
    for phrase in _CORPUS[key]
]


@pytest.mark.parametrize("phrase, kind", _PHRASES)
def test_each_fixture_phrase_has_its_kind(phrase: str, kind: SecretKind | None) -> None:
    assert secret_kind(phrase) is kind


def test_the_fixture_has_the_four_lists() -> None:
    assert set(_CORPUS) == {"stated", "asked", "offered", "none"}
    assert all(_CORPUS[key] for key in _CORPUS)


def test_stated_wins_when_a_message_also_asks() -> None:
    message = "Dime mi clave del banco, es 1234"

    assert secret_kind(message) is SecretKind.STATED


def test_an_empty_message_has_no_kind() -> None:
    assert secret_kind("") is None
    assert secret_kind("   ") is None


def test_asked_wins_over_offered() -> None:
    """«¿Me recuerdas mi pin?» asks; «recuerda» alone only offers (the ask grammar owns the rest)."""
    assert secret_kind("¿Me recuerdas mi pin?") is SecretKind.ASKED
    assert secret_kind("Recuérdame mi pin") is SecretKind.ASKED
    assert secret_kind("Recuerda mi pin") is SecretKind.OFFERED


def test_stated_wins_over_offered() -> None:
    assert secret_kind("Guarda mi clave, es 1234") is SecretKind.STATED


@pytest.mark.parametrize("opener", ["te voy a decir", "te voy a dar", "te voy a pasar", "te digo"])
def test_the_spoken_openers_of_an_offer(opener: str) -> None:
    assert secret_kind(f"{opener} mi contraseña") is SecretKind.OFFERED


def test_the_ask_grammar_is_unchanged_by_the_offer_rule() -> None:
    """«mis» and a bare article without an account object ask nothing; only the offer is wider."""
    assert secret_kind("Dime mis claves") is None
    assert secret_kind("Dime la clave") is None
    assert secret_kind("Dime la clave del banco") is SecretKind.ASKED


def test_an_offer_must_open_the_sentence() -> None:
    """«ayer te digo mi clave» is a story, not the start of an offer; the opener must open."""
    assert secret_kind("Ayer hablamos de que guarda mi pin") is None


@pytest.mark.parametrize("before", ["es", "lo", "muy", "tan"])
def test_clave_after_a_slang_word_is_no_secret_word(before: str) -> None:
    assert secret_kind(f"Eso {before} clave para el 5") is None
    assert secret_kind(f"Eso {before} claves, dime las 3") is None


def test_clave_after_mi_or_la_stays_a_secret_word() -> None:
    assert secret_kind("mi clave es 1234") is SecretKind.STATED
    assert secret_kind("la clave 1234") is SecretKind.STATED
