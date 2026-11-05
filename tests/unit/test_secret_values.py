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
    for kind, key in ((SecretKind.STATED, "stated"), (SecretKind.ASKED, "asked"), (None, "none"))
    for phrase in _CORPUS[key]
]


@pytest.mark.parametrize("phrase, kind", _PHRASES)
def test_each_fixture_phrase_has_its_kind(phrase: str, kind: SecretKind | None) -> None:
    assert secret_kind(phrase) is kind


def test_the_fixture_has_the_three_lists() -> None:
    assert set(_CORPUS) == {"stated", "asked", "none"}
    assert all(_CORPUS[key] for key in _CORPUS)


def test_stated_wins_when_a_message_also_asks() -> None:
    message = "Dime mi clave del banco, es 1234"

    assert secret_kind(message) is SecretKind.STATED


def test_an_empty_message_has_no_kind() -> None:
    assert secret_kind("") is None
    assert secret_kind("   ") is None
