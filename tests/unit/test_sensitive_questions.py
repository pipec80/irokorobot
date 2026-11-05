"""The sensitive-question grammar (Plan 0079 Task 3, D-3, D-4, D-5)."""

from __future__ import annotations

from pathlib import Path

import pytest
from server.cognition.sensitive_questions import (
    TOPIC_LABEL,
    TOPIC_LEVEL,
    TOPIC_PREDICATE,
    SensitiveLevel,
    SensitiveQuery,
    SensitiveTopic,
    classify_sensitive_question,
)
import yaml

pytestmark = pytest.mark.unit

_CORPUS = yaml.safe_load(
    (Path(__file__).resolve().parents[1] / "fixtures" / "sensitive_questions.yaml").read_text(
        encoding="utf-8"
    )
)
_QUESTIONS = [
    (phrase, SensitiveTopic(key))
    for key, phrases in _CORPUS["questions"].items()
    for phrase in phrases
]
_SLIPS = [
    (phrase, SensitiveTopic(key)) for key, phrases in _CORPUS["slips"].items() for phrase in phrases
]
_SLIPS_PER_TOPIC = 2


def _topic_of(message: str) -> SensitiveTopic | None:
    query = classify_sensitive_question(message)
    return None if query is None else query.topic


@pytest.mark.parametrize("message, topic", _QUESTIONS)
def test_each_fixture_question_has_its_topic(message: str, topic: SensitiveTopic) -> None:
    assert _topic_of(message) is topic


@pytest.mark.parametrize("message, topic", _SLIPS)
def test_each_speech_to_text_slip_keeps_its_topic(message: str, topic: SensitiveTopic) -> None:
    assert _topic_of(message) is topic


@pytest.mark.parametrize("message", _CORPUS["traps"])
def test_each_trap_resolves_to_nothing(message: str) -> None:
    assert classify_sensitive_question(message) is None


def test_the_fixture_covers_the_twelve_topics_with_two_slips_each() -> None:
    topics = {topic.value for topic in SensitiveTopic}

    assert len(topics) == 12
    assert set(_CORPUS["questions"]) == topics
    assert set(_CORPUS["slips"]) == topics
    assert all(len(phrases) == _SLIPS_PER_TOPIC for phrases in _CORPUS["slips"].values())
    assert set(_CORPUS) == {"questions", "slips", "traps"}


def test_every_topic_has_its_predicate_level_and_label() -> None:
    expected = {
        SensitiveTopic.MEDICATION: ("medication", "sensitive", ("personal", "medical")),
        SensitiveTopic.RESCUE_MEDICATION: (
            "rescue_medication",
            "sensitive",
            ("personal", "medical"),
        ),
        SensitiveTopic.HEALTH_CONDITION: ("health_condition", "sensitive", ("personal", "medical")),
        SensitiveTopic.ALLERGY: ("allergic_to", "sensitive", ("personal", "medical")),
        SensitiveTopic.BLOOD_TYPE: ("blood_type", "sensitive", ("personal", "medical")),
        SensitiveTopic.ANTICOAGULANT: ("takes_anticoagulant", "sensitive", ("personal", "medical")),
        SensitiveTopic.ADDRESS: ("home_address", "sensitive", ("personal", "location")),
        SensitiveTopic.EMERGENCY_FACILITY: (
            "preferred_emergency_facility",
            "sensitive",
            ("personal", "location"),
        ),
        SensitiveTopic.OWN_BIRTHDAY: ("birth_date", "sensitive", ("personal", "private")),
        SensitiveTopic.CHILD_BIRTHDAY: ("birth_date", "sensitive", ("household", "child_data")),
        SensitiveTopic.SECRET_HOLDER: ("secret_holder", "security", ("personal", "security")),
        SensitiveTopic.DOCUMENT_LOCATION: (
            "document_location",
            "security",
            ("personal", "security"),
        ),
    }

    assert set(expected) == set(SensitiveTopic)
    for topic, (predicate, level, label) in expected.items():
        assert TOPIC_PREDICATE[topic] == predicate
        assert TOPIC_LEVEL[topic] is SensitiveLevel(level)
        assert TOPIC_LABEL[topic] == label


def test_the_maps_are_read_only() -> None:
    with pytest.raises(TypeError):
        TOPIC_PREDICATE[SensitiveTopic.MEDICATION] = "other"  # type: ignore[index]  # read-only on purpose


@pytest.mark.parametrize(
    "message, keywords",
    [
        ("¿Quién conoce la clave del banco?", ("banco",)),
        ("¿Cuándo cumple Zeta?", ("zeta",)),
        ("Oye Iroko, ¿cuándo cumple Zeta, po?", ("zeta",)),
        ("¿Cuándo cumple Zeta para mí?", ("zeta",)),
        ("¿Cuándo es el cumpleaños de Omega?", ("omega",)),
        ("¿Dónde guardo la escritura de la casa?", ("casa",)),
        ("¿Dónde está mi pasaporte?", ()),
        ("¿Cuándo cumplen mis hijos?", ("hijos",)),
        ("¿Qué remedios tomo, po?", ()),
    ],
)
def test_keywords_drop_the_phrase_and_the_stopwords(
    message: str, keywords: tuple[str, ...]
) -> None:
    assert classify_sensitive_question(message) == SensitiveQuery(
        topic=_topic_of(message) or SensitiveTopic.MEDICATION, keywords=keywords
    )


def test_a_closed_topic_carries_no_keywords() -> None:
    query = classify_sensitive_question("¿Cuál es mi dirección, po?")

    assert query == SensitiveQuery(topic=SensitiveTopic.ADDRESS, keywords=())


def test_the_anticoagulant_statement_needs_a_question_mark() -> None:
    assert _topic_of("Tomo anticoagulante") is None
    assert _topic_of("¿Tomo anticoagulante?") is SensitiveTopic.ANTICOAGULANT


def test_a_leading_call_is_never_a_keyword() -> None:
    query = classify_sensitive_question("Iroko, ¿quién sabe la clave del banco?")

    assert query is not None
    assert "iroko" not in query.keywords


def test_the_query_is_immutable() -> None:
    query = SensitiveQuery(topic=SensitiveTopic.ADDRESS, keywords=())

    with pytest.raises(AttributeError):
        query.keywords = ("x",)  # type: ignore[misc]  # frozen on purpose
