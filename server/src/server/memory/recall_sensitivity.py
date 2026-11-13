"""The sensitivity of one recalled turn, from its words (ADR 0028 decision 3, Plan 0078 D-5).

Deterministic and closed: a folded whole word or phrase of a category marks the turn, and with
several categories the most protective wins. It errs on the protective side on purpose: a turn
marked too high is only not recalled now; the episode of its record can raise it further later,
never lower it. Nothing here logs a text.
"""

from __future__ import annotations

from typing import Final

from server.memory.conversation_summary import EpisodeSensitivity
from server.secret_values import SECRET_WORDS
from server.text_keys import normalize_spanish

__all__ = ["RecallSensitivity", "classify_turn_text", "most_protective"]

type RecallSensitivity = EpisodeSensitivity

# From the least to the most protective; `most_protective` compares by this rank.
_RANK: Final[dict[RecallSensitivity, int]] = {
    "normal": 0,
    "private": 1,
    "location": 2,
    "medical": 3,
    "security": 4,
}
# Folded words and phrases (`normalize_spanish`), matched as whole words; checked from the most
# protective category down, so the first category found is the answer.
_CATEGORY_TERMS: Final[tuple[tuple[RecallSensitivity, frozenset[str]], ...]] = (
    ("security", SECRET_WORDS | {"alarma", "llave", "llaves", "porton"}),
    (
        "medical",
        frozenset(
            {
                "doctor",
                "doctora",
                "medico",
                "medica",
                "hospital",
                "clinica",
                "remedio",
                "remedios",
                "pastilla",
                "pastillas",
                "medicamento",
                "enfermedad",
                "enfermo",
                "enferma",
                "dolor",
                "presion",
                "diabetes",
                "cancer",
                "examen",
                "examenes",
                "operacion",
                "cirugia",
                "diagnostico",
                "tratamiento",
                "depresion",
                "ansiedad",
                # Plan 0084 review: the health plans a greeting must not say as normal.
                "psicologo",
                "psicologa",
                "psiquiatra",
                "terapia",
                "dentista",
                "ecografia",
                "radiografia",
                "resonancia",
                "kinesiologo",
                "kinesiologa",
                "kine",
                "quimioterapia",
                "quimio",
                "vacuna",
                "consultorio",
                "cesfam",
                "urgencia",
                "urgencias",
                "cardiologo",
                "cardiologa",
                "ginecologo",
                "ginecologa",
                "matrona",
            }
        ),
    ),
    (
        "location",
        frozenset(
            {
                "direccion",
                "vivo en",
                "vivimos en",
                "mi casa queda",
                "calle",
                "avenida",
                "pasaje",
                "departamento numero",
                "numero de casa",
            }
        ),
    ),
    # Plan 0084 review: a legal or family-law matter is not said aloud in a greeting.
    ("private", frozenset({"abogado", "abogada", "juicio", "divorcio", "demanda"})),
)


def classify_turn_text(text: str) -> RecallSensitivity:
    """Return the sensitivity of one turn's words.

    Args:
        text: What the owner said.

    Returns:
        ``security``, ``medical``, ``location`` or ``private`` when a word of that category
        appears (the most protective when several do), ``normal`` otherwise.
    """
    padded = f" {normalize_spanish(text)} "
    for category, terms in _CATEGORY_TERMS:
        if any(f" {term} " in padded for term in terms):
            return category
    return "normal"


def most_protective(a: RecallSensitivity, b: RecallSensitivity) -> RecallSensitivity:
    """Return the more protective of two sensitivities; a sensitivity only goes up."""
    return a if _RANK[a] >= _RANK[b] else b
