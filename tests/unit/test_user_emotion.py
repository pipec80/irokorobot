"""Tests for the deterministic user-emotion classifier (Plan 0059 Task 2, ADR 0018).

Every sentence is invented. The labelled sets below implement the plan's classifier rule:
0 false positives on the neutral sentences and at least 60 % recall on the explicit feelings.
"""

import pytest
from server.llm import FALLBACK_EMOTION, VALID_EMOTIONS
from server.user_emotion import classify_user_emotion

MIN_RECALL = 0.60
MIN_LABELLED_SENTENCES = 40

# Explicit statements of a feeling by the user: the rules are expected to catch each one.
EXPLICIT_COVERED: tuple[tuple[str, str], ...] = (
    ("Estoy muy feliz con la noticia", "joy"),
    ("Me alegra que hoy haya salido el sol", "joy"),
    ("¡Qué alegría tan grande!", "joy"),
    ("Hoy me siento contento", "joy"),
    ("Estoy emocionada por el viaje", "joy"),
    ("ESTOY FELIZ", "joy"),
    ("Estoy furioso con el vecino", "anger"),
    ("¡Qué rabia me da esto!", "anger"),
    ("Me da mucha rabia perder el tiempo así", "anger"),
    ("Estoy harto del ruido", "anger"),
    ("Me enoja que nadie ordene la sala", "anger"),
    ("que bronca", "anger"),
    ("Estoy triste hoy", "sadness"),
    ("Me siento muy solo esta noche", "sadness"),
    ("Qué tristeza más grande", "sadness"),
    ("Me entristece que se acabe el verano", "sadness"),
    ("Tengo ganas de llorar", "sadness"),
    ("estoy deprimida", "sadness"),
    ("No lo puedo creer", "surprise"),
    ("No puedo creerlo, ganamos el sorteo", "surprise"),
    ("¡Qué sorpresa verte aquí!", "surprise"),
    ("Estoy sorprendido con el resultado", "surprise"),
    ("Me sorprende que ya sea de noche", "surprise"),
    ("No me lo esperaba para nada", "surprise"),
)

# Explicit feelings worded in ways a small rule table may miss: counted in the recall only.
EXPLICIT_HARD: tuple[tuple[str, str], ...] = (
    ("Me muero de risa con este chiste", "joy"),
    ("Estoy que exploto con este tráfico", "anger"),
    ("Tengo el corazón roto", "sadness"),
    ("Me quedé con la boca abierta", "surprise"),
)

NEUTRAL: tuple[str, ...] = (
    "¿Qué hora es?",
    "Cuéntame un chiste",
    "¿Cómo está el clima mañana?",
    "Pon música tranquila, por favor",
    "Hola, buenos días",
    "¿Cuánto es doce por ocho?",
    "Necesito una receta de arroz con verduras",
    "Apaga la luz de la sala",
    "No estoy triste",
    "No estoy feliz ni triste, solo cansado",
    "Ya no estoy enojado",
    "No me alegra para nada",
    "No me sorprende",
    "¿Estás triste?",
    "¿Estoy triste o solo cansado?",
    "Mi amigo está triste por el examen",
    "Ella está muy feliz con su regalo",
    "Dice que estoy furioso pero no es cierto",
    "Mi vecina dijo que estoy sorprendido",
    "La película trata de un hombre triste",
    'El personaje dice "estoy muy feliz"',
    "Sí claro, estoy feliz, jaja",
    "Cuando estoy triste escucho jazz",
    "Si estoy enojado respiro hondo",
    "Quizás estoy triste, no sé",
    "¿Por qué estoy tan triste?",
    "¿Te alegra la lluvia?",
    "La palabra tristeza tiene tres sílabas",
    "Escribe un poema sobre la rabia",
    "Quiero aprender a hacer pan",
    "Me llamo Ana",
    "Tengo hambre y sueño",
    "Estoy en la cocina",
    "Estoy cansado de caminar",
    "Estoy listo para empezar",
    "No puedo creer en los horóscopos",
    "Quiero llorar de risa con ese chiste",
    "Qué pena tengo de preguntarte esto",
    "Dime qué rabia da esto, es una frase hecha",
    "",
    "   ",
)


def _recall(cases: tuple[tuple[str, str], ...]) -> float:
    hits = sum(1 for sentence, label in cases if classify_user_emotion(sentence) == label)
    return hits / len(cases)


@pytest.mark.unit
def test_labelled_set_is_large_enough_and_covers_every_emotion() -> None:
    explicit = EXPLICIT_COVERED + EXPLICIT_HARD
    labels = {label for _, label in explicit}

    assert len(explicit) + len(NEUTRAL) >= MIN_LABELLED_SENTENCES
    assert labels == VALID_EMOTIONS - {FALLBACK_EMOTION}
    assert len(NEUTRAL) >= len(explicit)


@pytest.mark.unit
@pytest.mark.parametrize("sentence, label", EXPLICIT_COVERED)
def test_explicit_feeling_is_classified_as_its_label(sentence: str, label: str) -> None:
    assert classify_user_emotion(sentence) == label


@pytest.mark.unit
@pytest.mark.parametrize("sentence", NEUTRAL)
def test_neutral_sentence_is_never_a_false_positive(sentence: str) -> None:
    assert classify_user_emotion(sentence) == FALLBACK_EMOTION


@pytest.mark.unit
def test_recall_on_explicit_feelings_meets_the_plan_threshold() -> None:
    recall = _recall(EXPLICIT_COVERED + EXPLICIT_HARD)

    assert recall >= MIN_RECALL


@pytest.mark.unit
def test_zero_false_positives_on_the_neutral_set() -> None:
    false_positives = [s for s in NEUTRAL if classify_user_emotion(s) != FALLBACK_EMOTION]

    assert false_positives == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "variant",
    ["estoy triste", "ESTOY TRISTE", "Estoy Triste", "estóy tristé", "  estoy   triste  "],
)
def test_case_accents_and_spacing_are_ignored(variant: str) -> None:
    assert classify_user_emotion(variant) == "sadness"


@pytest.mark.unit
def test_decomposed_unicode_accents_are_ignored() -> None:
    decomposed = "Qué rabia"  # "Qué rabia" with a combining accent

    assert classify_user_emotion(decomposed) == "anger"


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "",
        " ",
        "\n\t",
        "😀😡😢",
        "ESTOY TRISTE 😢",
        pytest.param("a" * 200_000, id="long-noise"),
        pytest.param("estoy triste " * 5_000, id="long-repeated-feeling"),
        pytest.param("¿¿¿???!!!...,,,;;;", id="punctuation-only"),
        pytest.param('"""«»“”', id="quotes-only"),
        pytest.param("\ud800", id="lone-surrogate"),
        pytest.param("İstanbul ß ñandú", id="special-casing"),
        pytest.param("\x00estoy\x00triste", id="nul-bytes"),
    ],
)
def test_output_is_always_a_valid_emotion_and_never_raises(text: str) -> None:
    assert classify_user_emotion(text) in VALID_EMOTIONS


@pytest.mark.unit
def test_default_is_the_fallback_emotion() -> None:
    assert classify_user_emotion("Enciende el ventilador") == FALLBACK_EMOTION


@pytest.mark.unit
@pytest.mark.parametrize("sentence, _label", EXPLICIT_COVERED + EXPLICIT_HARD)
def test_classifier_is_deterministic(sentence: str, _label: str) -> None:
    first = classify_user_emotion(sentence)

    assert all(classify_user_emotion(sentence) == first for _ in range(5))


@pytest.mark.unit
def test_a_feeling_after_a_question_is_still_heard() -> None:
    assert classify_user_emotion("¿Sabes qué? Estoy triste") == "sadness"


@pytest.mark.unit
def test_a_question_clause_does_not_hide_a_feeling_in_another_clause() -> None:
    assert classify_user_emotion("Estoy contento, ¿y tú?") == "joy"


@pytest.mark.unit
def test_the_first_explicit_feeling_wins() -> None:
    assert classify_user_emotion("Estoy triste, pero estoy feliz") == "sadness"
