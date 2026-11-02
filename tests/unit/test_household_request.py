"""Unit tests for server.cognition.household_request — the shape of a household request.

The reviewed corpus (`tests/fixtures/intent_resolution_es.json`) proves the routing; these tests
pin what the corpus cannot say: the signals that must be absent, and the stored-name comparison.
"""

import pytest
from server.cognition.household_request import (
    has_question_mark,
    mentions_the_household,
    names_someone_known,
    opens_with,
    requests_data_of_a_name,
    requests_household_data,
    states_a_request,
)


def _request(message: str) -> bool:
    return requests_household_data(message)


@pytest.mark.unit
@pytest.mark.parametrize(
    "message",
    [
        "Cuando mi hijo nació lloré.",
        "Como mi hija vive lejos, la llamo.",
        "Que mi hijo sabe nadar.",
    ],
)
def test_a_subordinate_opening_is_a_story_not_a_question(message: str) -> None:
    """Without an accent «cuando mi hijo…» opens a story; a question puts the verb there."""
    assert _request(message) is False


@pytest.mark.unit
def test_a_question_mark_is_one_signal_and_not_the_only_one() -> None:
    """Whisper left the mark out of 3 of 10 questions (ADR 0023 decision 7)."""
    assert states_a_request("que edad tiene mi hija", marked=False) is True
    assert states_a_request("mi hijo tiene alergias", marked=False) is False
    assert states_a_request("mi hijo tiene alergias", marked=True) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "message",
    [
        "El cumpleaños de mi hijo fue genial.",
        "La fecha de nacimiento de mi hija es en marzo.",
        "El nombre de mi perro me gusta.",
    ],
)
def test_a_datum_followed_by_a_verb_is_a_story(message: str) -> None:
    """Only the bare phrase is a request: nothing may follow the person."""
    assert _request(message) is False


@pytest.mark.unit
@pytest.mark.parametrize(
    "message",
    ["fecha de nacimiento de mi hija", "la edad de mi mamá", "el teléfono de mi hermana"],
)
def test_a_bare_datum_of_a_relative_is_a_request(message: str) -> None:
    assert _request(message) is True


@pytest.mark.unit
def test_the_possessive_reaches_one_word_and_no_further() -> None:
    assert _request("¿Cómo se llaman mis dos perros?") is True
    assert _request("¿Cómo se llama mi nuevo vecino del perro?") is False


@pytest.mark.unit
@pytest.mark.parametrize(
    "tag", ["¿cachai?", "¿no?", "¿cierto?", "¿verdad?", "¿sabes?", "¿te conté?"]
)
def test_a_closing_tag_is_not_a_question(tag: str) -> None:
    assert has_question_mark(f"Mi hijo vive en Temuco, {tag}") is False
    assert _request(f"Mi hijo vive en Temuco, {tag}") is False


@pytest.mark.unit
def test_a_question_that_merely_ends_in_no_keeps_its_mark() -> None:
    assert has_question_mark("¿Mi hijo vive en Temuco, no?") is True


@pytest.mark.unit
def test_each_sentence_is_judged_alone() -> None:
    assert _request("¿Sabes dónde queda la farmacia? Mi mamá necesita remedios.") is False
    assert _request("Hola Iroko. ¿Qué edad tiene mi hija?") is True
    assert _request("A mi hijo, ¿qué le gusta?") is True


@pytest.mark.unit
@pytest.mark.parametrize("message", ["¿Cómo se llama tu perro?", "¿Cuándo nació su hijo?"])
def test_only_a_first_person_possessive_names_the_household(message: str) -> None:
    assert _request(message) is False


@pytest.mark.unit
def test_an_unmarked_question_must_close_on_the_person() -> None:
    assert _request("Cuando nació mi hija llovía mucho.") is False
    assert _request("Cuántos años tiene mi mamá en el cielo, pobrecita.") is False
    assert _request("cuando nacio mi hijo") is True
    assert _request("como se llama mi perro po") is True


@pytest.mark.unit
def test_requests_data_of_a_name_needs_a_datum_and_a_request() -> None:
    assert requests_data_of_a_name("¿Cuándo nació Mozart?") is True
    assert requests_data_of_a_name("cuando nacio mozart") is True
    assert requests_data_of_a_name("¿Qué sabes de Zeta?") is True
    assert requests_data_of_a_name("Mozart nació en 1756.") is False
    assert requests_data_of_a_name("¿Qué hora es?") is False
    assert requests_data_of_a_name("¿Cuándo nació mi hijo?") is False


@pytest.mark.unit
def test_a_stored_name_matches_as_whole_folded_words() -> None:
    names = frozenset({"Joaquín", "Ana María", "Eva-Luna", ""})

    assert names_someone_known("¿Cuándo nació joaquin?", names) is True
    assert names_someone_known("¿Qué le gusta a ANA MARÍA?", names) is True
    assert names_someone_known("¿Qué edad tiene Joaquina?", names) is False
    assert names_someone_known("¿Cuándo nació Ana?", names) is False
    assert names_someone_known("¿Cuándo nació Mozart?", frozenset()) is False
    assert names_someone_known("¿Qué edad tiene Eva Luna?", names) is True
    assert names_someone_known("", names) is False


@pytest.mark.unit
def test_the_broad_mention_test_keeps_every_family_value_out_of_an_answer() -> None:
    """Used only on the shape of an answer, so a family value never becomes a memory answer."""
    assert mentions_the_household("si autorizo guardar a mi hijo") is True
    assert mentions_the_household("guarda lo que le gusta") is True
    assert mentions_the_household("guarda la fecha de nacimiento") is True
    assert mentions_the_household("guarda las papas fritas") is False
    assert mentions_the_household("guarda mi papa") is True
    assert mentions_the_household("guarda mi perro") is True


@pytest.mark.unit
def test_opens_with_skips_the_call_to_the_robot() -> None:
    assert opens_with("iroko conoce a esta persona", "conoce a") is True
    assert opens_with("mi mama conoce a todos", "conoce a") is False


@pytest.mark.unit
def test_a_story_with_a_question_tag_stays_protected() -> None:
    """A stated limit: the mark and the datum are there, and only meaning tells it apart."""
    assert _request("Mi hijo nació en marzo, ¿de verdad?") is True


@pytest.mark.unit
@pytest.mark.parametrize("message", ["", "oye", "Iroko, por favor"])
def test_an_empty_or_filler_message_is_no_request(message: str) -> None:
    assert _request(message) is False
    assert requests_data_of_a_name(message) is False


@pytest.mark.unit
@pytest.mark.parametrize(
    "message",
    [
        "¿Qué fue lo que te conté de mi familia?",
        "¿Qué está haciendo mi hijo?",
        "¿Sabes qué come mi perrita?",
    ],
)
def test_a_question_about_the_household_is_a_request_whatever_the_datum(message: str) -> None:
    """D-22: the closed list of data words is not what makes a question about the family."""
    assert _request(message) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "message",
    [
        "¿Qué le puedo regalar a mi nieto?",
        "¿Qué debería hacer con mi perro?",
        "¿Cómo ayudo a mi hijo con las tareas?",
        "¿Qué es bueno para la tos de mi hijo?",
        "¿Te gusta mi perro?",
    ],
)
def test_advice_for_the_speaker_or_a_question_to_the_robot_is_not_a_request(message: str) -> None:
    assert _request(message) is False


@pytest.mark.unit
def test_a_first_person_past_is_no_advice() -> None:
    """«compré», «conté» tell what happened: only the present asks what to do."""
    assert _request("Ayer le compré comida a mi perrita, ¿sabes qué come?") is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "message",
    [
        "Sabes qué, dime cuántos años tiene mi hijo",
        "¿Me podría decir cómo se llama mi hermana?",
        "Puedes decirme el nombre de mi perro",
        "Tengo una duda, no me acuerdo cuándo cumple años mi hijo",
        "Cuántos años tiene mi hijo, no me acuerdo",
        "¿Qué animales tengo?",
    ],
)
def test_requests_found_by_the_review_of_d22(message: str) -> None:
    """The opening of a polite request is no advice, and «sabes qué» only sets it aside."""
    assert _request(message) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "message",
    [
        "Sabes qué, mi vieja hacía sopaipillas.",
        "Cuéntame un cuento para mi nieta.",
        "Dime cómo se prepara un té para mi mamá.",
        "Cómo extraño a mi mamá.",
        "Cuánto quiero a mis nietos.",
        "Mi hijo me dijo: oye papá, ¿cuándo vamos a la playa?",
    ],
)
def test_conversation_found_by_the_review_of_d22(message: str) -> None:
    """Something for the family, or a feeling of the speaker, asks nothing about it."""
    assert _request(message) is False
