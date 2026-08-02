"""Unit tests for the relation-trigger lexicon."""

import pytest
from server.memory.lexicon import predicates_in


@pytest.mark.unit
def test_hijos_triggers_hijo_de() -> None:
    assert predicates_in("¿cómo se llaman mis hijos?") == {"hijo_de"}


@pytest.mark.unit
def test_mascota_and_perra_trigger_mascota_de() -> None:
    assert predicates_in("cómo se llama mi mascota") == {"mascota_de"}
    assert predicates_in("mi perra está durmiendo") == {"mascota_de"}


@pytest.mark.unit
def test_multiple_relations_in_one_question() -> None:
    result = predicates_in("háblame de mi esposa y mis hijas")
    assert result == {"pareja_de", "hijo_de"}


@pytest.mark.unit
def test_plain_greeting_triggers_nothing() -> None:
    assert predicates_in("hola robot cómo estás") == set()


@pytest.mark.unit
def test_whole_word_matching_no_substring_false_positives() -> None:
    """'regata' must not trigger 'gata', 'perrota' must not trigger 'perro'."""
    assert predicates_in("gané la regata") == set()
    assert predicates_in("qué perrota enorme") == set()


@pytest.mark.unit
def test_case_insensitive() -> None:
    assert predicates_in("MIS HIJOS") == {"hijo_de"}


@pytest.mark.unit
def test_self_referential_age_triggers_fecha_nacimiento() -> None:
    """ "¿Cuántos años tengo?" names no entity — must still resolve via
    the owner's birthdate, same predicate "cumpleaños" already triggers."""
    assert predicates_in("¿Cuántos años tengo?") == {"fecha_nacimiento"}
    assert predicates_in("¿Qué edad tengo?") == {"fecha_nacimiento"}
