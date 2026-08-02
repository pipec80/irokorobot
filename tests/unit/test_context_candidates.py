"""Unit tests for entity-candidate extraction in memory.context."""

import pytest
from server.memory.context import _candidates


@pytest.mark.unit
def test_candidates_filters_spanish_stopwords() -> None:
    """A plain greeting must produce zero entity lookups."""
    assert _candidates("hola robot como estas") == []


@pytest.mark.unit
def test_candidates_keeps_proper_nouns() -> None:
    """Proper nouns survive the stopword filter and rank first."""
    result = _candidates("Qué sabes de María")
    assert result == ["María"]


@pytest.mark.unit
def test_candidates_prioritises_capitalised_tokens() -> None:
    result = _candidates("el cumpleaños de Valentina y de Máximo")
    assert result[0] in {"Valentina", "Máximo"}
    assert "Valentina" in result
    assert "Máximo" in result


@pytest.mark.unit
def test_candidates_caps_at_five() -> None:
    text = "Pedro Pablo Andrea Camila Ignacio Josefa"
    assert len(_candidates(text)) == 5
