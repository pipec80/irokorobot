"""Unit tests for the cheap Spanish check used by the streaming evaluator (Plan 0061)."""

import pytest

from scripts.reply_language import judge_language

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "reply",
    [
        "Claro, tu número favorito es el cuarenta y dos.",
        "No lo recuerdo todavía, ¿me lo puedes decir otra vez?",
        "Dijiste que ibas a cocinar lentejas esta noche, ¡qué buena idea!",
        "Estoy aquí para ayudarte con lo que necesites.",
        "Sé que tú quieres que te cuente un secreto y se lo diré mañana.",
        "Dijiste que te gustaba el té sin azúcar y que tu café es muy amargo.",
    ],
)
def test_a_spanish_reply_is_judged_spanish(reply: str) -> None:
    assert judge_language(reply) is True


@pytest.mark.parametrize(
    "reply",
    [
        "Bien sûr, votre nombre préféré est le quarante-deux et je vous le dis avec plaisir.",
        "Je suis ici pour vous aider avec ce dont vous avez besoin aujourd'hui.",
        "Of course, your favorite number is forty-two and I am happy to help you with that.",
        "I do not remember that yet, could you tell me again what you said?",
        # French sentences that borrow function words Spanish also has (que, tu, te, un, y, se):
        "Tu m'as dit que tu aimais le thé sans sucre.",
        "Il y a un problème, mais je vais y réfléchir.",
        "Tu veux que je te dise un secret ?",
        "Tu as dit que ton numéro favori est 42.",
        "Tu as un rendez-vous demain à neuf heures, je crois.",
    ],
)
def test_a_french_or_english_reply_is_judged_not_spanish(reply: str) -> None:
    assert judge_language(reply) is False


@pytest.mark.parametrize("reply", ["", "   ", "Hola.", "Sí, claro.", "¡Gracias!"])
def test_a_reply_too_short_to_judge_is_undetermined(reply: str) -> None:
    assert judge_language(reply) is None


def test_the_verdict_ignores_case_and_punctuation() -> None:
    assert judge_language("CLARO, TU NÚMERO FAVORITO ES EL CUARENTA Y DOS!!!") is True
