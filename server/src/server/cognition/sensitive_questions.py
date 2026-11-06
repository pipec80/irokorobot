"""Recognize the owner's first-person questions about their own sensitive data (Plan 0079, D-3).

A pure, closed Spanish grammar: it reads one message and returns the topic asked and the words that
narrow it, or ``None``. It identifies nobody, reads no store and grants nothing; the routes that
answer from storage decide who may hear what. The phrase must *open* the sentence body (after the
call to the robot and the fillers of ``household_request``), so a mention («ayer hablé de mis
remedios con el doctor») or a third person («¿qué remedios toma?») matches nothing. A closed topic
allows only a few trailing fillers after its phrase, so «¿cuál es mi dirección de correo?» is not
a question about the home address.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from server.cognition.household_request import (
    has_question_mark,
    sentence_body,
    without_leading_fillers,
)
from server.secret_values import SECRET_WORDS

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "TOPIC_LABEL",
    "TOPIC_LEVEL",
    "TOPIC_PREDICATE",
    "SensitiveLevel",
    "SensitiveQuery",
    "SensitiveTopic",
    "classify_sensitive_question",
]


class SensitiveTopic(StrEnum):
    """What an owner's sensitive question asks about."""

    MEDICATION = "medication"
    RESCUE_MEDICATION = "rescue_medication"
    HEALTH_CONDITION = "health_condition"
    ALLERGY = "allergy"
    BLOOD_TYPE = "blood_type"
    ANTICOAGULANT = "anticoagulant"
    ADDRESS = "address"
    EMERGENCY_FACILITY = "emergency_facility"
    OWN_BIRTHDAY = "own_birthday"
    CHILD_BIRTHDAY = "child_birthday"
    SECRET_HOLDER = "secret_holder"  # noqa: S105  # pragma: allowlist secret - a topic name
    DOCUMENT_LOCATION = "document_location"


class SensitiveLevel(StrEnum):
    """How strongly the identity behind a question must be proven (ADR 0016)."""

    SENSITIVE = "sensitive"
    SECURITY = "security"


@dataclass(frozen=True)
class SensitiveQuery:
    """A recognized question: its topic and the folded words that narrow it.

    Attributes:
        topic: What is asked about.
        keywords: Folded words after the matched phrase, with at least four letters and not a
            stopword; empty for a closed topic.
    """

    topic: SensitiveTopic
    keywords: tuple[str, ...] = field(repr=False)  # may hold a name or a medication word


_SENSITIVE: Final = SensitiveLevel.SENSITIVE
_SECURITY: Final = SensitiveLevel.SECURITY

#: The predicate each topic reads.
TOPIC_PREDICATE: Final[Mapping[SensitiveTopic, str]] = MappingProxyType(
    {
        SensitiveTopic.MEDICATION: "medication",
        SensitiveTopic.RESCUE_MEDICATION: "rescue_medication",
        SensitiveTopic.HEALTH_CONDITION: "health_condition",
        SensitiveTopic.ALLERGY: "allergic_to",
        SensitiveTopic.BLOOD_TYPE: "blood_type",
        SensitiveTopic.ANTICOAGULANT: "takes_anticoagulant",
        SensitiveTopic.ADDRESS: "home_address",
        SensitiveTopic.EMERGENCY_FACILITY: "preferred_emergency_facility",
        SensitiveTopic.OWN_BIRTHDAY: "birth_date",
        SensitiveTopic.CHILD_BIRTHDAY: "birth_date",
        SensitiveTopic.SECRET_HOLDER: "secret_holder",  # pragma: allowlist secret
        SensitiveTopic.DOCUMENT_LOCATION: "document_location",
    }
)

#: The level of proof each topic needs.
TOPIC_LEVEL: Final[Mapping[SensitiveTopic, SensitiveLevel]] = MappingProxyType(
    {
        SensitiveTopic.MEDICATION: _SENSITIVE,
        SensitiveTopic.RESCUE_MEDICATION: _SENSITIVE,
        SensitiveTopic.HEALTH_CONDITION: _SENSITIVE,
        SensitiveTopic.ALLERGY: _SENSITIVE,
        SensitiveTopic.BLOOD_TYPE: _SENSITIVE,
        SensitiveTopic.ANTICOAGULANT: _SENSITIVE,
        SensitiveTopic.ADDRESS: _SENSITIVE,
        SensitiveTopic.EMERGENCY_FACILITY: _SENSITIVE,
        SensitiveTopic.OWN_BIRTHDAY: _SENSITIVE,
        SensitiveTopic.CHILD_BIRTHDAY: _SENSITIVE,
        SensitiveTopic.SECRET_HOLDER: _SECURITY,
        SensitiveTopic.DOCUMENT_LOCATION: _SECURITY,
    }
)

#: ``(visibility, sensitivity)`` as the canonical writer stores each topic (D-4). The owner's own
#: birthday is ``private``, not the registry's ``child_data``.
TOPIC_LABEL: Final[Mapping[SensitiveTopic, tuple[str, str]]] = MappingProxyType(
    {
        SensitiveTopic.MEDICATION: ("personal", "medical"),
        SensitiveTopic.RESCUE_MEDICATION: ("personal", "medical"),
        SensitiveTopic.HEALTH_CONDITION: ("personal", "medical"),
        SensitiveTopic.ALLERGY: ("personal", "medical"),
        SensitiveTopic.BLOOD_TYPE: ("personal", "medical"),
        SensitiveTopic.ANTICOAGULANT: ("personal", "medical"),
        SensitiveTopic.ADDRESS: ("personal", "location"),
        SensitiveTopic.EMERGENCY_FACILITY: ("personal", "location"),
        SensitiveTopic.OWN_BIRTHDAY: ("personal", "private"),
        SensitiveTopic.CHILD_BIRTHDAY: ("household", "child_data"),
        SensitiveTopic.SECRET_HOLDER: ("personal", "security"),
        SensitiveTopic.DOCUMENT_LOCATION: ("personal", "security"),
    }
)

# Folded phrases of D-3, in matching order. The last entries of a topic are spelling slips that
# folding cannot fix («sanguinio», «cumpleano»); accent-less slips come free from the folding.
# A phrase opening with «a» is matched without it: `sentence_body` eats that leading «a».
_PHRASES: Final[Mapping[SensitiveTopic, tuple[str, ...]]] = MappingProxyType(
    {
        SensitiveTopic.MEDICATION: (
            "que remedios tomo",
            "que medicamentos tomo",
            "que pastillas tomo",
            "cuales son mis remedios",
            "cuales son mis medicamentos",
            "que remedio tomo",
        ),
        SensitiveTopic.RESCUE_MEDICATION: (
            "cual es mi remedio de rescate",
            "cual es mi medicamento de rescate",
        ),
        SensitiveTopic.HEALTH_CONDITION: (
            "que enfermedades tengo",
            "cuales son mis enfermedades",
            "cuales son mis condiciones de salud",
            "que condiciones de salud tengo",
        ),
        SensitiveTopic.ALLERGY: (
            "a que soy alergico",
            "a que soy alergica",
            "que alergias tengo",
            "cuales son mis alergias",
        ),
        SensitiveTopic.BLOOD_TYPE: (
            "cual es mi grupo sanguineo",
            "que sangre tengo",
            "cual es mi tipo de sangre",
            "cual es mi grupo sanguinio",
        ),
        SensitiveTopic.ANTICOAGULANT: ("tomo anticoagulante", "tomo anticoagulantes"),
        SensitiveTopic.ADDRESS: ("cual es mi direccion", "donde vivo"),
        SensitiveTopic.EMERGENCY_FACILITY: (
            "cual es mi urgencia",
            "a que urgencia voy",
            "a que clinica me llevan",
        ),
        SensitiveTopic.OWN_BIRTHDAY: (
            "cuando es mi cumpleanos",
            "cuando naci",
            "cuando cumplo anos",
            "cual es mi fecha de nacimiento",
            "cuando es mi cumpleano",
        ),
        SensitiveTopic.CHILD_BIRTHDAY: (
            "cuando es el cumpleanos de",
            "cuando cumple",
            "cuando cumplen",
            "cuando nacio",
            "cuando nacieron",
            "cuando es el cumpleano de",
        ),
        SensitiveTopic.SECRET_HOLDER: (
            "quien conoce la",
            "quien sabe la",
            "quien tiene la",
            "quien conoce el",
            "quien sabe el",
            "quien tiene el",
        ),
        SensitiveTopic.DOCUMENT_LOCATION: (
            "donde esta mi",
            "donde estan mis",
            "donde guardo",
            "donde dejo",
        ),
    }
)

# Topics whose tail names what is asked (a child, a secret, a document); every other topic is
# closed: only the trailing fillers may follow its phrase.
_OPEN_TOPICS: Final[frozenset[SensitiveTopic]] = frozenset(
    {
        SensitiveTopic.CHILD_BIRTHDAY,
        SensitiveTopic.SECRET_HOLDER,
        SensitiveTopic.DOCUMENT_LOCATION,
    }
)
_DOCUMENT_WORDS: Final[frozenset[str]] = frozenset(
    {
        "documento",
        "documentos",
        "pasaporte",
        "carnet",
        "cedula",
        "escritura",
        "escrituras",
        "testamento",
        "papeles",
        "poder",
    }
)
# What follows a secret word to make it something else («código postal», «código de barras»).
_NOT_A_SECRET_AFTER: Final[tuple[tuple[str, ...], ...]] = (("postal",), ("de", "barras"))
# A document word must sit within this many words after «donde esta mi», «donde guardo la».
_DOCUMENT_REACH: Final[int] = 3
# What a person adds after the question is over; «por favor» is two words, handled apart.
_TRAILING_FILLERS: Final[frozenset[str]] = frozenset(
    {"po", "oye", "iroko", "porfa", "cachai", "ahora", "hoy"}
)
_TRAILING_PLEASE: Final[tuple[str, str]] = ("por", "favor")
_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "para",
        "como",
        "donde",
        "cuando",
        "quien",
        "esta",
        "estan",
        "tengo",
        "tiene",
        "sabe",
        "conoce",
    }
)
_MIN_KEYWORD_LETTERS: Final[int] = 4

# Request introducers that come before the question itself, longest first («una pregunta, ¿cuál es
# mi dirección?», «¿me puede decir quién conoce la clave del banco?»). They are not fillers of
# `household_request`: other grammars must keep reading these sentences as today.
_OPENERS: Final[tuple[tuple[str, ...], ...]] = tuple(
    sorted(
        (
            tuple(opener.split())
            for opener in (
                "una pregunta",
                "otra pregunta",
                "quiero saber",
                "quisiera saber",
                "necesito saber",
                "me puedes decir",
                "me puede decir",
                "me podrias decir",
                "me podria decir",
                "me dices",
                "me dice",
                "dime",
                "digame",
                "puedes decirme",
                "podrias decirme",
                "puede decirme",
                "podria decirme",
                "me gustaria saber",
            )
        ),
        key=len,
        reverse=True,
    )
)

# The folded phrases as word tuples, topic by topic, without a leading «a».
_PATTERNS: Final[tuple[tuple[SensitiveTopic, tuple[str, ...]], ...]] = tuple(
    (topic, tuple(phrase.removeprefix("a ").split()))
    for topic, phrases in _PHRASES.items()
    for phrase in phrases
)


def classify_sensitive_question(message: str) -> SensitiveQuery | None:
    """Return the sensitive topic the message asks about, or ``None``.

    Pure and deterministic; the phrase must open the sentence body (once the fillers and the
    request openers, «una pregunta», «me puede decir», are set aside) and, for a closed topic, only
    trailing fillers may follow it. ``ANTICOAGULANT`` also needs a question mark, since «tomo
    anticoagulante desde hace años» is a statement.

    Args:
        message: Raw transcript or chat text.

    Returns:
        The topic and its keywords, or ``None`` for any other turn.
    """
    body = _without_openers(sentence_body(message))
    for topic, phrase in _PATTERNS:
        if body[: len(phrase)] != phrase:
            continue
        span_end = _span_end(topic, body, len(phrase))
        if span_end is None:
            continue
        tail = _without_trailing_fillers(body[span_end:])
        if topic not in _OPEN_TOPICS:
            if tail:
                continue
            if topic is SensitiveTopic.ANTICOAGULANT and not has_question_mark(message):
                continue
            return SensitiveQuery(topic=topic, keywords=())
        return SensitiveQuery(topic=topic, keywords=_keywords(tail))
    return None


def _without_openers(body: tuple[str, ...]) -> tuple[str, ...]:
    """Strip request openers and the fillers they uncover until nothing more comes off.

    The fillers are those of ``household_request`` (``without_leading_fillers``); the openers are
    this grammar's own, so no other grammar changes.
    """
    while True:
        opener = next((o for o in _OPENERS if body[: len(o)] == o), None)
        if opener is None:
            return body
        rest = body[len(opener) :]
        body = tuple(without_leading_fillers(" ".join(rest)).split())


def _span_end(topic: SensitiveTopic, body: tuple[str, ...], phrase_end: int) -> int | None:
    """Return where the matched span ends, or ``None`` when the word it needs is missing."""
    match topic:
        case SensitiveTopic.SECRET_HOLDER:
            # «quien conoce la» + the secret word, which belongs to the span, unless the word
            # names something else: «el código postal», «el código de barras».
            if phrase_end < len(body) and body[phrase_end] in SECRET_WORDS:
                end = phrase_end + 1
                if any(body[end : end + len(trap)] == trap for trap in _NOT_A_SECRET_AFTER):
                    return None
                return end
            return None
        case SensitiveTopic.DOCUMENT_LOCATION:
            # A document word within reach, which belongs to the span.
            for index in range(phrase_end, min(phrase_end + _DOCUMENT_REACH, len(body))):
                if body[index] in _DOCUMENT_WORDS:
                    return index + 1
            return None
        case _:
            return phrase_end


def _without_trailing_fillers(words: tuple[str, ...]) -> tuple[str, ...]:
    end = len(words)
    while end > 0:
        if words[end - 1] in _TRAILING_FILLERS:
            end -= 1
        elif tuple(words[max(end - 2, 0) : end]) == _TRAILING_PLEASE:
            end -= 2
        else:
            break
    return words[:end]


def _keywords(words: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        word for word in words if len(word) >= _MIN_KEYWORD_LETTERS and word not in _STOPWORDS
    )
