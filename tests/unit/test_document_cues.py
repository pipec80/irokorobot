"""The document cue: a closed grammar, no model (Plan 0088 Task B5, D-11).

Strong when the owner's possession is said («mis documentos», «mi manual»), weak otherwise; a weak
cue whose title step finds no document falls through to conversation (decided by the search).
"""

from __future__ import annotations

import pytest
from server.cognition.document_cues import DocumentCue, classify_document_cue
from server.cognition.intent_resolution import resolve_information_need
from server.cognition.recall_cues import CueStrength
from server.cognition.response_plan import InformationNeed

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "message, strength, named, query",
    [
        (
            "¿Qué dice el manual de la lavadora sobre el filtro de pelusas?",
            CueStrength.WEAK,
            ("manual", "lavadora"),
            "el filtro de pelusas",
        ),
        (
            "¿Qué dice mi receta del pan sobre la levadura?",
            CueStrength.STRONG,
            ("receta", "pan"),
            "la levadura",
        ),
        (
            "¿Qué dice la guía de cuidados de la rodilla acerca del hielo?",
            CueStrength.WEAK,
            ("guia", "cuidados", "rodilla"),
            "hielo",
        ),
        (
            "En el manual de la lavadora, ¿cuánto dura la garantía?",
            CueStrength.WEAK,
            ("manual", "lavadora"),
            "cuanto dura la garantia",
        ),
        (
            "en mi receta del pan cuánto reposa la masa",
            CueStrength.STRONG,
            ("receta", "pan"),
            "cuanto reposa la masa",
        ),
        (
            "Según mis documentos, ¿cuándo vence el pasaporte?",
            CueStrength.STRONG,
            (),
            "cuando vence el pasaporte",
        ),
        (
            "Busca en mis papeles el horario del gimnasio.",
            CueStrength.STRONG,
            (),
            "el horario del gimnasio",
        ),
    ],
)
def test_each_shape_gives_its_strength_names_and_query(
    message: str, strength: CueStrength, named: tuple[str, ...], query: str
) -> None:
    cue = classify_document_cue(message)

    assert cue is not None
    assert (cue.strength, cue.named, cue.query) == (strength, named, query)
    assert isinstance(cue, DocumentCue)


@pytest.mark.parametrize(
    "message",
    [
        "Me leí el manual de la lavadora.",
        "¿Qué dice el manual?",
        "¿Qué dice el doctor sobre la rodilla?",
        "¿Qué dice la receta del pan?",
        "El manual de la lavadora es largo.",
        "¿Qué te conté del manual de la lavadora?",
        "",
    ],
)
def test_the_traps_are_no_cue(message: str) -> None:
    assert classify_document_cue(message) is None


def test_the_named_document_s_words_are_not_specific() -> None:
    cue = classify_document_cue("¿Qué dice la guía de Santiago sobre el error E21?")

    assert cue is not None
    assert cue.specific == frozenset({"e21"})


def test_with_documents_off_every_resolution_is_today_s() -> None:
    message = "¿Qué dice el manual de la lavadora sobre el filtro?"

    assert (
        resolve_information_need(message, recall=True).need is InformationNeed.GENERIC_CONVERSATION
    )
    assert (
        resolve_information_need(message, recall=True, documents=True).need
        is InformationNeed.DOCUMENT
    )


def test_a_document_cue_comes_before_a_recall_cue_and_after_a_stated_secret() -> None:
    assert (
        resolve_information_need(
            "Según mis documentos, ¿qué te conté ayer?", recall=True, documents=True
        ).need
        is InformationNeed.DOCUMENT
    )
    assert (
        resolve_information_need(
            "Según mis documentos, mi clave es 4821", secrets=True, documents=True
        ).need
        is InformationNeed.SECRET_VALUE
    )
