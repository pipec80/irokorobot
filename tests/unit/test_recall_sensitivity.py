"""The word sensitivity of a recalled turn (Plan 0078 Task 3, ADR 0028 decision 3)."""

from __future__ import annotations

from itertools import product
from typing import get_args

import pytest
from server.memory.conversation_summary import EpisodeSensitivity
from server.memory.recall_sensitivity import classify_turn_text, most_protective

pytestmark = pytest.mark.unit

_ORDER = ("normal", "private", "location", "medical", "security")


@pytest.mark.parametrize(
    "text",
    [
        "Mañana tengo hora con la doctora",
        "Me tomé las pastillas de la presión",
        "Me operaron, la cirugía salió bien",
        "Ando con mucha ansiedad",
    ],
)
def test_medical_words_are_medical(text: str) -> None:
    assert classify_turn_text(text) == "medical"


@pytest.mark.parametrize(
    "text",
    [
        "Mi dirección es otra ahora",
        "Vivo en la avenida Canary",
        "Mi casa queda cerca del cerro",
        "El número de casa es fácil",
    ],
)
def test_location_words_are_location(text: str) -> None:
    assert classify_turn_text(text) == "location"


@pytest.mark.parametrize(
    "text",
    [
        "La clave del wifi la cambié",
        "Olvidé la contraseña",
        "El PIN es el de siempre",
        "Dejé las llaves en la mesa",
        "Hay que arreglar el portón",
    ],
)
def test_security_words_are_security(text: str) -> None:
    assert classify_turn_text(text) == "security"


def test_two_categories_keep_the_most_protective() -> None:
    assert classify_turn_text("Fui al hospital y dejé la llave adentro") == "security"
    assert classify_turn_text("Vivo en la calle del hospital") == "medical"


def test_a_story_about_sushi_and_the_children_is_normal() -> None:
    assert classify_turn_text("Hoy vamos a cocinar sushi porque les gusta a mis hijos") == "normal"


def test_a_word_inside_another_word_does_not_match() -> None:
    assert classify_turn_text("Zeta pinto la pieza de azul") == "normal"
    assert classify_turn_text("Compré claveles para Omega") == "normal"
    assert classify_turn_text("Le gusta el dolorcito de cabeza") == "normal"


def test_an_empty_text_is_normal() -> None:
    assert classify_turn_text("") == "normal"


def test_the_literal_is_the_episode_literal() -> None:
    assert set(_ORDER) == set(get_args(EpisodeSensitivity.__value__))


@pytest.mark.parametrize("a, b", list(product(_ORDER, repeat=2)))
def test_most_protective_never_goes_down(a: EpisodeSensitivity, b: EpisodeSensitivity) -> None:
    result = most_protective(a, b)

    assert result in (a, b)
    assert _ORDER.index(result) == max(_ORDER.index(a), _ORDER.index(b))
    assert most_protective(b, a) == result
