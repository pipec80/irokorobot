"""One module of text keys for names and values (Plan 0071 Task 1, ADR 0024 decision 12)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from server.text_keys import comparison_key, fold_name, normalize_spanish

import server

pytestmark = pytest.mark.unit


def test_a_name_folds_accents_and_case() -> None:
    assert fold_name("José") == fold_name("jose") == fold_name("JOSÉ")


def test_folding_keeps_the_words_and_their_spaces() -> None:
    assert fold_name("Canary  Owner") == "canary  owner"


def test_normalize_spanish_folds_and_collapses_punctuation() -> None:
    assert normalize_spanish("¡Me GUSTÓ el café,  ñandú!") == "me gusto el cafe nandu"


def test_the_key_of_a_phrase_drops_a_leading_article() -> None:
    assert comparison_key("El Café") == comparison_key("café") == "cafe"
    assert comparison_key("las empanadas") == "empanadas"


@pytest.mark.parametrize("phrase", ["la", "los", "  ", "¡!", "..."])
def test_an_article_or_punctuation_alone_gives_an_empty_key(phrase: str) -> None:
    assert comparison_key(phrase) == ""


def test_the_key_drops_punctuation_so_two_languages_collide() -> None:
    """Known limit (ADR 0024 decision 12): punctuation is not part of the key."""
    assert comparison_key("C++") == comparison_key("C#") == "c"


def test_the_module_imports_neither_cognition_nor_memory() -> None:
    """Both packages import it, so it must import neither (no cycle, no layering breach)."""
    source = (Path(server.__file__).resolve().parent / "text_keys.py").read_text(encoding="utf-8")
    imported = {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module is not None
    } | {
        alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert not {name for name in imported if name.startswith("server")}
