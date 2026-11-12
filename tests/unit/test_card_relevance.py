"""The owner's tastes enter the prompt only when the message is about tastes (Plan 0081, D-4).

The 3B model ignored the card's «solo si viene al caso» on hardware: it brought a taste into a cold
«hola» and voiced one as its own. A pure gate decides instead, so a greeting never carries one.
"""

import pytest
from server.memory.card_relevance import TASTE_CUE_WORDS, tastes_are_relevant
from server.memory.profile_card import CardTaste
from server.text_keys import normalize_spanish

pytestmark = pytest.mark.unit

_TASTES = (
    CardTaste("likes", "el mate"),
    CardTaste("likes", "la lluvia"),
    CardTaste("dislikes", "comida china"),
)


@pytest.mark.parametrize(
    "message",
    [
        "hola",
        "Hola.",
        "hola Iroko, ¿cómo estás?",
        "buenos días",
        "buenas",
        "oye hola",
        "¿cómo te va?",
    ],
)
def test_a_greeting_carries_no_taste(message: str) -> None:
    assert tastes_are_relevant(message, _TASTES) is False


@pytest.mark.parametrize(
    "message",
    [
        "¿qué me recomiendas comer?",
        "¿qué música te gusta?",
        "pon una canción",
        "¿qué película vemos?",
    ],
)
def test_a_cue_word_carries_the_tastes(message: str) -> None:
    assert tastes_are_relevant(message, _TASTES) is True


@pytest.mark.parametrize(
    "message, expected",
    [
        ("hoy tomé mate", True),
        ("¿va a haber lluvia?", True),
        ("ayer tomé mate con pan", True),
        # The folded words must be equal: «chino» is not «china».
        ("quiero algo chino", False),
    ],
)
def test_a_taste_word_carries_the_tastes(message: str, expected: bool) -> None:
    assert tastes_are_relevant(message, _TASTES) is expected


def test_a_shared_article_or_stopword_is_not_a_match() -> None:
    assert tastes_are_relevant("la casa está fría", _TASTES) is False


def test_a_short_taste_matches_only_by_cue() -> None:
    tea = (CardTaste("likes", "el té"),)

    assert tastes_are_relevant("¿te acuerdas de mí?", tea) is False
    assert tastes_are_relevant("¿qué me gusta tomar?", tea) is True


def test_no_tastes_is_never_relevant_by_word() -> None:
    assert tastes_are_relevant("hola", ()) is False


def test_the_cues_are_folded() -> None:
    assert all(normalize_spanish(word) == word for word in TASTE_CUE_WORDS)
