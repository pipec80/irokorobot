"""The sensitive-question grammar (Plan 0079 Task 3, D-3, D-4, D-5)."""

from __future__ import annotations

from pathlib import Path

import pytest
from server.cognition.contact_questions import contact_selector
from server.cognition.sensitive_questions import (
    ALTA_TOPICS,
    CONTACT_TOPICS,
    TOPIC_LABEL,
    TOPIC_LEVEL,
    TOPIC_PREDICATE,
    SensitiveLevel,
    SensitiveQuery,
    SensitiveTopic,
    classify_sensitive_question,
)
from server.secret_values import SecretKind, secret_kind
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
_ALTA = yaml.safe_load(
    (Path(__file__).resolve().parents[1] / "fixtures" / "alta_questions.yaml").read_text(
        encoding="utf-8"
    )
)
_ALTA_QUESTIONS = [
    (phrase, SensitiveTopic(key))
    for key, phrases in _ALTA["questions"].items()
    for phrase in phrases
]
_ALTA_SLIPS = [
    (phrase, SensitiveTopic(key)) for key, phrases in _ALTA["slips"].items() for phrase in phrases
]
_FLAGS = [False, True]


def _topic_of(message: str, *, alta: bool = False) -> SensitiveTopic | None:
    query = classify_sensitive_question(message, alta=alta)
    return None if query is None else query.topic


@pytest.mark.parametrize("alta", _FLAGS)
@pytest.mark.parametrize("message, topic", _QUESTIONS)
def test_each_fixture_question_has_its_topic(
    message: str, topic: SensitiveTopic, *, alta: bool
) -> None:
    assert _topic_of(message, alta=alta) is topic


@pytest.mark.parametrize("alta", _FLAGS)
@pytest.mark.parametrize("message, topic", _SLIPS)
def test_each_speech_to_text_slip_keeps_its_topic(
    message: str, topic: SensitiveTopic, *, alta: bool
) -> None:
    assert _topic_of(message, alta=alta) is topic


@pytest.mark.parametrize("alta", _FLAGS)
@pytest.mark.parametrize("message", _CORPUS["traps"])
def test_each_trap_resolves_to_nothing(message: str, *, alta: bool) -> None:
    assert classify_sensitive_question(message, alta=alta) is None


def test_the_fixture_covers_the_twelve_topics_with_two_slips_each() -> None:
    topics = {topic.value for topic in SensitiveTopic if topic not in ALTA_TOPICS}

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

    assert set(expected) == set(SensitiveTopic) - ALTA_TOPICS
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
        ("¿Me puede decir quién conoce la clave del banco?", ("banco",)),
        ("Una pregunta, ¿me puedes decir cuándo cumple Zeta?", ("zeta",)),
        ("Una pregunta, oye Iroko, ¿me puedes decir cuándo cumple Zeta?", ("zeta",)),
    ],
)
def test_keywords_drop_the_phrase_and_the_stopwords(
    message: str, keywords: tuple[str, ...]
) -> None:
    assert classify_sensitive_question(message) == SensitiveQuery(
        topic=_topic_of(message) or SensitiveTopic.MEDICATION, keywords=keywords
    )


@pytest.mark.parametrize(
    "message",
    [
        "Una pregunta oye Iroko, ¿cuál es mi dirección?",
        "Oye, quiero saber, por favor, ¿me puedes decir cuál es mi dirección?",
        "Otra pregunta, una pregunta, ¿dónde vivo?",
        "Quisiera saber, ¿me podría decir dónde vivo?",
        "Necesito saber ¿puedes decirme dónde vivo?",
        "Dígame cuál es mi dirección",
        "Me gustaría saber cuál es mi dirección",
    ],
)
def test_request_openers_and_fillers_strip_alternately(message: str) -> None:
    assert _topic_of(message) is SensitiveTopic.ADDRESS


def test_an_opener_alone_matches_nothing() -> None:
    assert classify_sensitive_question("Dime") is None
    assert classify_sensitive_question("Una pregunta") is None


def test_the_polite_opener_does_not_change_the_secret_rule() -> None:
    """``secret_kind`` is a separate grammar: the opener fix lives in the sensitive grammar only."""
    assert secret_kind("Una pregunta, ¿cuál es mi clave del banco?") is SecretKind.ASKED
    assert secret_kind("¿Me puede decir quién conoce la clave del banco?") is None


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


def test_a_query_hides_its_keywords_from_repr() -> None:
    """A keyword may be a stored name or a medication word; a stray ``%r`` must not print it."""
    query = SensitiveQuery(topic=SensitiveTopic.CHILD_BIRTHDAY, keywords=("zeta",))

    assert "zeta" not in repr(query)


# --- Plan 0082 Task 3: the rest of the alta, behind the flag (D-3, D-4, D-5) ---


@pytest.mark.parametrize("message, topic", _ALTA_QUESTIONS + _ALTA_SLIPS)
def test_the_new_topics_need_the_flag(message: str, topic: SensitiveTopic) -> None:
    assert _topic_of(message, alta=True) is topic
    assert classify_sensitive_question(message) is None


@pytest.mark.parametrize("message", _ALTA["traps"])
def test_each_alta_trap_resolves_to_nothing(message: str) -> None:
    assert classify_sensitive_question(message, alta=True) is None


def test_the_alta_fixture_covers_the_thirteen_topics() -> None:
    assert len(ALTA_TOPICS) == 13
    assert {SensitiveTopic(key) for key in _ALTA["questions"]} == ALTA_TOPICS
    assert {SensitiveTopic(key) for key in _ALTA["slips"]} == ALTA_TOPICS
    assert all(len(phrases) == _SLIPS_PER_TOPIC for phrases in _ALTA["slips"].values())


def test_the_key_and_the_alarm_code_are_told_apart() -> None:
    assert _topic_of("¿Quién tiene la llave de mi casa?", alta=True) is SensitiveTopic.KEY_HOLDERS
    assert _topic_of("¿Quién tiene la clave de la alarma?", alta=True) is (
        SensitiveTopic.SECRET_HOLDER
    )
    assert _topic_of("¿Quién tiene la llave de mi casa?") is None


@pytest.mark.parametrize(
    "message, keywords",
    [
        ("¿Tienes el teléfono de mi tío?", ("mi", "tio")),
        ("Oye Iroko, llama a mi contacto 1, po", ("mi", "contacto", "1")),
        ("¿Cuál es el número de los bomberos?", ("los", "bomberos")),
        ("Llama a Canary", ("canary",)),
    ],
)
def test_a_contact_question_keeps_its_tail(message: str, keywords: tuple[str, ...]) -> None:
    query = classify_sensitive_question(message, alta=True)
    assert query is not None
    assert query.topic in CONTACT_TOPICS
    assert query.keywords == keywords


def test_a_contact_question_needs_a_tail() -> None:
    assert classify_sensitive_question("¿Tienes el teléfono de?", alta=True) is None
    assert classify_sensitive_question("Llama a", alta=True) is None


def test_every_alta_topic_has_its_level_and_label() -> None:
    sensitive, security = SensitiveLevel.SENSITIVE, SensitiveLevel.SECURITY
    expected = {
        SensitiveTopic.IMPLANTED_DEVICE: ("implanted_device", sensitive, ("personal", "medical")),
        SensitiveTopic.MOBILITY: ("mobility", sensitive, ("personal", "medical")),
        SensitiveTopic.HEARING: ("hearing", sensitive, ("personal", "medical")),
        SensitiveTopic.VISION: ("vision", sensitive, ("personal", "medical")),
        SensitiveTopic.HEALTH_COVERAGE: ("health_coverage", sensitive, ("personal", "private")),
        SensitiveTopic.DWELLING_TYPE: ("dwelling_type", sensitive, ("personal", "location")),
        SensitiveTopic.FLOOR: ("floor", sensitive, ("personal", "location")),
        SensitiveTopic.LIFT: ("has_lift", sensitive, ("personal", "location")),
        SensitiveTopic.HOME_ACCESS: ("home_access_note", sensitive, ("personal", "location")),
        SensitiveTopic.LIVES_ALONE: ("lives_alone", security, ("personal", "location")),
    }
    for topic, (predicate, level, label) in expected.items():
        assert TOPIC_PREDICATE[topic] == predicate
        assert TOPIC_LEVEL[topic] is level
        assert TOPIC_LABEL[topic] == label
    assert set(expected) | CONTACT_TOPICS == ALTA_TOPICS


def test_contact_topics_have_no_predicate() -> None:
    assert {
        SensitiveTopic.CONTACT_PHONE,
        SensitiveTopic.CONTACT_CALL,
        SensitiveTopic.KEY_HOLDERS,
    } == CONTACT_TOPICS
    for topic in CONTACT_TOPICS:
        assert topic not in TOPIC_PREDICATE
        assert TOPIC_LEVEL[topic] is SensitiveLevel.SENSITIVE
        assert TOPIC_LABEL[topic] == ("personal", "location")


@pytest.mark.parametrize(
    "message, order",
    [
        ("Llama a mi contacto número uno.", 1),
        ("Llama a mi contacto 1.", 1),
        ("¿Tienes el teléfono de mi tercer contacto?", 3),
        ("Dame el número de mi cuarto contacto", 4),
        ("Llama a mi quinto contacto", 5),
        ("¿Cuál es el teléfono de mi contacto 9?", 9),
        ("¿Cuál es el teléfono de mi contacto seis?", 6),
        ("Llama al contacto nueve", 9),
    ],
)
def test_whispers_order_forms_reach_the_selector(message: str, order: int) -> None:
    query = classify_sensitive_question(message, alta=True)
    assert query is not None
    assert contact_selector(query.keywords).order == order
