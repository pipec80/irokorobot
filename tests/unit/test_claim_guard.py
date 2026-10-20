"""The guard that keeps a model sentence from claiming a memory action (Plan 0064, Task 4a).

Nothing the model says stores anything: only the deterministic promotion of Plan 0063 does. A
model sentence that says it saved, registered or noted something is therefore false, and the
guard replaces it. The lexicon is closed and exact, so these tests pin both sides: what is
a claim and what, by construction, is not.
"""

import pytest
from server.claim_guard import (
    REPLACEMENT,
    claims_memory_action,
    neutralize_memory_claims,
    replace_if_claim,
)

pytestmark = pytest.mark.unit

_CLAIMS = [
    "El café siempre será guardado.",
    "El café está registrado.",
    "Lo guardé.",
    "No te preocupes, ya lo guardé.",
    "Lo anoto en mi memoria.",
    "Lo recordaré siempre.",
    "Ya lo tengo guardado.",
    "Lo he registrado.",
    "Eso lo anoté.",
    "Ya quedó guardado.",
    "Todo queda almacenado.",
    "Las memoricé.",
    "Esto lo apunto.",
    "Me acordaré de eso.",
    "Será registrada tu preferencia.",
    "LO GUARDÉ.",
    # Past and perfect forms need no pronoun object (review of Plan 0064).
    "Guardé tu café en mi memoria.",
    "He guardado tu gusto.",
    "Anoté que te gusta el mate.",
    "Ya guardé que te gusta el café.",
    "Tomé nota de tu gusto.",
    "Se ha guardado.",
    # The present tense of «tomar nota» is the same claim (Plan 0067, Task 6).
    "Genial, te tomo nota.",
    "Tomo nota.",
    "Ya tomo nota de eso.",
    "Tomaré nota.",
    # A question mark only exempts the question itself, not a claim before it.
    "Lo guardé, ¿quieres algo más?",
    "Listo, lo guardé, ¿y tú?",
]

_NOT_CLAIMS = [
    "Anotado.",
    "Guardado.",
    "¿Quieres que lo guarde?",
    "¿Ya lo guardé?",
    "No lo he guardado.",
    "Todavía no lo guardo.",
    "Nunca lo anoto sin preguntarte.",
    "Puedo guardar silencio.",
    "Guarda tus llaves.",
    "Recuerdo que me dijiste que hace calor.",
    "Eso no lo he guardado.",
    "Lo guardaría si me lo pides.",
    "Hoy hace calor.",
    "La mesa está ordenada.",
    "El mate es una bebida caliente.",
    "Me alegra verte.",
    "¿Quieres que lo guarde? Dime: sí, autorizo.",
    # An offer or a condition is not a claim to have saved.
    "Si quieres, lo guardo.",
    "Si quieres, tomo nota.",
    "No tomo nota de eso.",
    "Tampoco tomo nota.",
    "Tampoco lo guardé.",
    "¿Quieres que tome nota?",
    "Lo guardaré cuando me lo pidas.",
    "Aún no lo he guardado, pero lo guardaré si me lo pides.",
    "Nunca lo he guardado ni lo guardaré.",
    "¿Lo guardé, o no?",
]


@pytest.mark.parametrize("sentence", _CLAIMS)
def test_a_sentence_that_says_it_stored_something_is_a_claim(sentence: str) -> None:
    assert claims_memory_action(sentence)
    assert replace_if_claim(sentence) == REPLACEMENT


@pytest.mark.parametrize("sentence", _NOT_CLAIMS)
def test_everything_else_is_not_a_claim(sentence: str) -> None:
    assert not claims_memory_action(sentence)
    assert replace_if_claim(sentence) == sentence


def test_the_lexicon_is_exact_about_accents() -> None:
    """«guardé» (I saved) is a claim; «guarde» (that I save) is a question or an offer."""
    assert claims_memory_action("Lo guardé.")
    assert not claims_memory_action("Quieres que lo guarde.")


def test_a_negation_close_before_the_match_cancels_it_but_a_distant_one_does_not() -> None:
    assert not claims_memory_action("No lo guardé.")
    assert not claims_memory_action("Aún no lo he guardado.")
    assert claims_memory_action("No te preocupes, ya lo guardé.")


def test_the_replacement_is_not_itself_a_claim() -> None:
    assert not claims_memory_action(REPLACEMENT)
    assert replace_if_claim(REPLACEMENT) == REPLACEMENT


def test_only_the_claiming_sentence_of_a_reply_is_replaced() -> None:
    text = "Qué buen gusto. Lo guardé en mi memoria. ¿Y qué más te gusta?"

    assert neutralize_memory_claims(text) == (f"Qué buen gusto. {REPLACEMENT} ¿Y qué más te gusta?")


def test_consecutive_claims_collapse_into_one_replacement() -> None:
    assert neutralize_memory_claims("Lo guardé. Lo anoté. Lo he registrado.") == REPLACEMENT


def test_a_claim_in_the_unterminated_tail_is_replaced() -> None:
    assert neutralize_memory_claims("Hola. Lo guardé") == f"Hola. {REPLACEMENT}"


@pytest.mark.parametrize("text", ["", "Hola, ¿cómo estás?", "Anotado.", "Sin punto final"])
def test_a_reply_without_a_claim_is_returned_unchanged(text: str) -> None:
    assert neutralize_memory_claims(text) == text
