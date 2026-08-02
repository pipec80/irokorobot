"""Unit tests for server.sentences.split_first_sentence."""

import pytest
from server.sentences import split_first_sentence


@pytest.mark.unit
def test_no_terminator_returns_none() -> None:
    assert split_first_sentence("Hola, ¿cómo estás") is None


@pytest.mark.unit
def test_empty_buffer_returns_none() -> None:
    assert split_first_sentence("") is None


@pytest.mark.unit
def test_single_closed_sentence() -> None:
    result = split_first_sentence("Hola humano.")
    assert result == ("Hola humano.", "")


@pytest.mark.unit
def test_multiple_sentences_splits_only_the_first() -> None:
    result = split_first_sentence("Hola humano. ¿Cómo estás?")
    assert result is not None
    sentence, remainder = result
    assert sentence == "Hola humano."
    assert remainder == "¿Cómo estás?"


@pytest.mark.unit
def test_question_mark_closes_a_sentence() -> None:
    result = split_first_sentence("¿Qué hora es?")
    assert result == ("¿Qué hora es?", "")


@pytest.mark.unit
def test_exclamation_mark_closes_a_sentence() -> None:
    result = split_first_sentence("¡Cuidado!")
    assert result == ("¡Cuidado!", "")


@pytest.mark.unit
def test_ellipsis_and_combined_punctuation_close_a_sentence() -> None:
    result = split_first_sentence("Esperá un momento... ¿listo?!")
    assert result is not None
    sentence, remainder = result
    assert sentence == "Esperá un momento..."
    assert remainder == "¿listo?!"


@pytest.mark.unit
def test_leading_whitespace_is_stripped_from_sentence() -> None:
    result = split_first_sentence("   Hola.")
    assert result == ("Hola.", "")


@pytest.mark.unit
def test_remainder_keeps_trailing_text_untouched() -> None:
    result = split_first_sentence("Uno. Dos. Tres")
    assert result is not None
    sentence, remainder = result
    assert sentence == "Uno."
    assert remainder == "Dos. Tres"


@pytest.mark.unit
def test_whitespace_only_buffer_returns_none() -> None:
    assert split_first_sentence("   ") is None
