"""The closed grammar of a spoken answer to a memory offer (ADR 0021 decision 9, Plan 0063).

Pipec's decision (option A): an answer is a closed verb **and** the value. A bare «sí», or a verb
without the value, is never an answer, so nothing an attacker can know in advance promotes.
"""

import pytest
from server.cognition.intent_resolution import (
    MemoryAnswer,
    parse_memory_answer,
    resolve_information_need,
)
from server.cognition.response_plan import InformationNeed

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "message, accept, phrase",
    [
        ("Sí, autorizo guardar el mate.", True, "el mate"),
        ("autorizo guardar el mate", True, "el mate"),
        ("Sí, apruebo guardar el mate", True, "el mate"),
        ("apruebo que guardes el jazz", True, "el jazz"),
        ("Guárdalo, el mate", True, "el mate"),
        ("sí, guarda el mate", True, "el mate"),
        ("Iroko, sí, autorizo guardar las empanadas", True, "las empanadas"),
        ("Oye, autorizo guardar el café", True, "el cafe"),
        ("No autorizo guardar el mate", False, "el mate"),
        ("no apruebo que guardes el mate", False, "el mate"),
        ("No lo guardes, el mate", False, "el mate"),
        ("no guardes el mate", False, "el mate"),
        ("Olvídalo, el mate", False, "el mate"),
        ("bórralo, el mate", False, "el mate"),
        ("Sí, autorizo guardar lo picante", True, "lo picante"),
        ("Sí, sí, autorizo guardar el mate", True, "el mate"),
        ("Sí, claro, autorizo guardar el mate", True, "el mate"),
        ("Sí, autorizo a guardar el mate", True, "el mate"),
        ("Sí, autorizo guardar el mate, gracias", True, "el mate"),
        ("autorizo guardar el mate por favor", True, "el mate"),
        ("No, no autorizo guardar el mate", False, "el mate"),
        ("No. No autorizo guardar el mate.", False, "el mate"),
        ("Sí, autorizo guardar bailar", True, "bailar"),
    ],
)
def test_a_closed_verb_and_the_value_make_an_answer(
    message: str, accept: bool, phrase: str
) -> None:
    assert parse_memory_answer(message) == MemoryAnswer(accept=accept, phrase=phrase)
    resolution = resolve_information_need(message)
    assert resolution.need is InformationNeed.MEMORY_ANSWER
    assert resolution.rule_id == "memory.answer.v1"


@pytest.mark.parametrize(
    "message",
    [
        "sí",
        "Sí, autorizo",
        "autorizo guardar",
        "sí, guárdalo",
        "guárdalo",
        "no lo guardes",
        "olvídalo",
        "dale",
        "ok",
        "no",
        "sí, por favor",
        "me gusta el mate",
        "Guarda silencio, por favor",
        "Olvídalo, no importa",
        "Bórralo todo",
        "no guardes nada",
        "sí, autorizo a guardar",
        "",
        "   ",
    ],
)
def test_a_bare_yes_or_a_verb_without_the_value_is_never_an_answer(message: str) -> None:
    assert parse_memory_answer(message) is None
    assert resolve_information_need(message).need is not InformationNeed.MEMORY_ANSWER


def test_a_closed_rule_resolved_earlier_wins_over_the_shape_of_an_answer() -> None:
    """A protected or dated message is never read as an answer: those rules run first."""
    assert resolve_information_need("guarda la fecha de hoy").need is InformationNeed.CURRENT_DATE
    assert (
        resolve_information_need("sí, autorizo guardar a mi hijo").need
        is InformationNeed.PROTECTED_HOUSEHOLD
    )


def test_the_value_is_a_short_phrase() -> None:
    long_value = "uno dos tres cuatro cinco seis siete"

    assert parse_memory_answer(f"sí, autorizo guardar {long_value}") is None
    assert parse_memory_answer("sí, autorizo guardar uno dos tres cuatro cinco seis") == (
        MemoryAnswer(accept=True, phrase="uno dos tres cuatro cinco seis")
    )


def test_the_answer_is_frozen() -> None:
    answer = MemoryAnswer(accept=True, phrase="el mate")

    with pytest.raises(ValueError, match="frozen"):
        answer.phrase = "el cafe"  # type: ignore[misc]  # mutation is what this test refutes
