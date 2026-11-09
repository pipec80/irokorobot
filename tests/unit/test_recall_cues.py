"""Recall cues and the relatives question (Plan 0078 Task 6, ADR 0028 decisions 4 and 9)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from server.cognition.intent_resolution import resolve_information_need
from server.cognition.recall_cues import (
    CueStrength,
    classify_recall_cue,
    content_words,
    relation_of,
)
from server.cognition.response_plan import InformationNeed
from server.cognition.spoken_dates import DayWindow
import yaml

pytestmark = pytest.mark.unit

_CORPUS = yaml.safe_load(
    (Path(__file__).resolve().parents[1] / "fixtures" / "recall_routes.yaml").read_text(
        encoding="utf-8"
    )
)
_WEDNESDAY = date(2026, 11, 4)


@pytest.mark.parametrize("line", _CORPUS, ids=[line["phrase"] for line in _CORPUS])
def test_every_corpus_phrase_takes_its_route(line: dict[str, str]) -> None:
    assert resolve_information_need(line["phrase"], recall=True).need == InformationNeed(
        line["need"]
    )


@pytest.mark.parametrize("line", _CORPUS, ids=[line["phrase"] for line in _CORPUS])
def test_without_recall_every_corpus_phrase_resolves_as_on_main(line: dict[str, str]) -> None:
    assert resolve_information_need(line["phrase"]).need == InformationNeed(line["today"])
    assert resolve_information_need(line["phrase"], recall=False).need == InformationNeed(
        line["today"]
    )


def test_the_corpus_covers_both_cues_and_the_relatives() -> None:
    needs = {line["need"] for line in _CORPUS}

    assert {"recall", "relatives_names", "generic_conversation", "profile_summary"} <= needs


@pytest.mark.parametrize(
    "message, rule_id",
    [("¿Qué te conté ayer?", "recall.strong.v1"), ("¿Te acuerdas de Mozart?", "recall.weak.v1")],
)
def test_each_cue_has_its_rule_id(message: str, rule_id: str) -> None:
    assert resolve_information_need(message, recall=True).rule_id == rule_id


def test_a_strong_phrase_wins_over_a_weak_one() -> None:
    cue = classify_recall_cue("¿Te acuerdas qué te conté del viaje?", today=_WEDNESDAY)

    assert cue is not None
    assert cue.strength is CueStrength.STRONG


@pytest.mark.parametrize(
    "message",
    [
        "Hoy vamos a cocinar sushi porque les gusta a mis hijos",
        "Me acuerdo que de chico íbamos al cerro",
        "No me acuerdo dónde dejé las llaves",
        "Recuerdo que ayer fuimos al cerro",
        "Mañana te cuento lo que hice",
        "Ayer fuimos al cerro con Zeta",
    ],
)
def test_a_statement_is_never_a_cue(message: str) -> None:
    assert classify_recall_cue(message, today=_WEDNESDAY) is None


def test_without_a_question_mark_an_opening_interrogative_still_counts() -> None:
    cue = classify_recall_cue("que te conte ayer", today=_WEDNESDAY)

    assert cue is not None
    assert cue.strength is CueStrength.STRONG
    assert cue.window == DayWindow(start=date(2026, 11, 3), end=date(2026, 11, 3))


def test_a_cue_word_opening_the_message_counts_as_a_question() -> None:
    cue = classify_recall_cue("bueno te acuerdas de Mozart", today=_WEDNESDAY)

    assert cue is not None
    assert cue.strength is CueStrength.WEAK


def test_the_query_drops_cue_and_window_words() -> None:
    cue = classify_recall_cue(
        "Oye, ¿te acuerdas qué te conté el martes del viaje a la playa?", today=_WEDNESDAY
    )

    assert cue is not None
    assert cue.query == "que del viaje a la playa"
    assert cue.window == DayWindow(start=date(2026, 11, 3), end=date(2026, 11, 3))
    assert content_words(cue.query) == ("viaje", "playa")


def test_a_cue_with_nothing_after_it_is_no_recall() -> None:
    assert classify_recall_cue("¿Qué te conté?", today=_WEDNESDAY) is None
    assert classify_recall_cue("¿Te acuerdas?", today=_WEDNESDAY) is None
    assert classify_recall_cue("¿Te acuerdas de eso?", today=_WEDNESDAY) is None


def test_a_date_alone_is_enough() -> None:
    cue = classify_recall_cue("¿Qué te dije anteayer?", today=_WEDNESDAY)

    assert cue is not None
    assert content_words(cue.query) == ()
    assert cue.window == DayWindow(start=date(2026, 11, 2), end=date(2026, 11, 2))


def test_a_weak_cue_about_household_data_keeps_the_protected_route() -> None:
    resolution = resolve_information_need("¿Te acuerdas qué comen mis hijos?", recall=True)

    assert resolution.need is InformationNeed.PROTECTED_HOUSEHOLD


def test_content_words_drop_stop_words_and_repeats() -> None:
    assert content_words("que con mi hijo y mi hijo en el cerro") == ("hijo", "cerro")


@pytest.mark.parametrize(
    "message, predicate",
    [
        ("¿Cómo se llaman mis papás?", "has_parent"),
        ("¿Cómo se llama mi mamá?", "has_parent"),
        ("¿Cómo se llama mi padre?", "has_parent"),
        ("¿Quiénes son mis hermanas?", "has_sibling"),
        ("¿Cómo se llaman mis abuelos?", "has_grandparent"),
        ("¿Quién es mi nieta?", "has_grandchild"),
        ("¿Cómo se llama mi esposa?", "partner_of"),
        ("¿Cómo se llama mi señora?", "partner_of"),
        ("¿Cómo se llama mi perrita?", "pet_of"),
        ("¿Cómo se llaman mis mascotas?", "pet_of"),
        ("¿Cuál es el nombre de mi papá?", "has_parent"),
        ("Dime el nombre de mi mamá", "has_parent"),
        ("¿Cuáles son los nombres de mis hermanos?", "has_sibling"),
        ("Dime los nombres de mis papás", "has_parent"),
        ("Oye Iroko, ¿cuál es el nombre de mi perro?", "pet_of"),
    ],
)
def test_relation_of_names_the_predicate(message: str, predicate: str) -> None:
    assert relation_of(message) == predicate


@pytest.mark.parametrize(
    "message",
    [
        "¿Cómo se llaman mis hijos?",
        "Mi mamá se llama Zeta",
        "¿Cómo se llama la mamá de Zeta?",
        "¿Cómo se llama tu perro?",
        "No sé cuál es el nombre de mi mamá",
        "Mi mamá dijo cuál es el nombre de mi perro",
        "¿Cuál es el nombre de la calle de mi papá?",
        "¿Cuál es el nombre de mi hijo?",
    ],
)
def test_relation_of_is_none_for_anything_else(message: str) -> None:
    assert relation_of(message) is None
