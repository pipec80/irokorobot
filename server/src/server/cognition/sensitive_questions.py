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
    "ALTA_TOPICS",
    "CONTACT_TOPICS",
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
    # The rest of the alta (Plan 0082, ADR 0037 decisions 1 and 5), matched only with the flag on.
    IMPLANTED_DEVICE = "implanted_device"
    MOBILITY = "mobility"
    HEARING = "hearing"
    VISION = "vision"
    HEALTH_COVERAGE = "health_coverage"
    DWELLING_TYPE = "dwelling_type"
    FLOOR = "floor"
    LIFT = "lift"
    HOME_ACCESS = "home_access"
    LIVES_ALONE = "lives_alone"
    CONTACT_PHONE = "contact_phone"
    CONTACT_CALL = "contact_call"
    KEY_HOLDERS = "key_holders"


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
            stopword; empty for a closed topic; for a contact topic, the whole folded tail as is
            (short words and digits included, Plan 0082 D-5).
    """

    topic: SensitiveTopic
    keywords: tuple[str, ...] = field(repr=False)  # may hold a name or a medication word


_SENSITIVE: Final = SensitiveLevel.SENSITIVE
_SECURITY: Final = SensitiveLevel.SECURITY

#: The topics read from the ``care_contacts`` table, not from a V4 literal: no predicate (D-3).
CONTACT_TOPICS: Final[frozenset[SensitiveTopic]] = frozenset(
    {SensitiveTopic.CONTACT_PHONE, SensitiveTopic.CONTACT_CALL, SensitiveTopic.KEY_HOLDERS}
)
#: The topics Plan 0082 adds; ``classify_sensitive_question`` matches them only with ``alta``.
ALTA_TOPICS: Final[frozenset[SensitiveTopic]] = frozenset(
    {
        SensitiveTopic.IMPLANTED_DEVICE,
        SensitiveTopic.MOBILITY,
        SensitiveTopic.HEARING,
        SensitiveTopic.VISION,
        SensitiveTopic.HEALTH_COVERAGE,
        SensitiveTopic.DWELLING_TYPE,
        SensitiveTopic.FLOOR,
        SensitiveTopic.LIFT,
        SensitiveTopic.HOME_ACCESS,
        SensitiveTopic.LIVES_ALONE,
        *CONTACT_TOPICS,
    }
)

#: The predicate each topic reads; the contact topics have none.
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
        SensitiveTopic.IMPLANTED_DEVICE: "implanted_device",
        SensitiveTopic.MOBILITY: "mobility",
        SensitiveTopic.HEARING: "hearing",
        SensitiveTopic.VISION: "vision",
        SensitiveTopic.HEALTH_COVERAGE: "health_coverage",
        SensitiveTopic.DWELLING_TYPE: "dwelling_type",
        SensitiveTopic.FLOOR: "floor",
        SensitiveTopic.LIFT: "has_lift",
        SensitiveTopic.HOME_ACCESS: "home_access_note",
        SensitiveTopic.LIVES_ALONE: "lives_alone",
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
        SensitiveTopic.IMPLANTED_DEVICE: _SENSITIVE,
        SensitiveTopic.MOBILITY: _SENSITIVE,
        SensitiveTopic.HEARING: _SENSITIVE,
        SensitiveTopic.VISION: _SENSITIVE,
        SensitiveTopic.HEALTH_COVERAGE: _SENSITIVE,
        SensitiveTopic.DWELLING_TYPE: _SENSITIVE,
        SensitiveTopic.FLOOR: _SENSITIVE,
        SensitiveTopic.LIFT: _SENSITIVE,
        SensitiveTopic.HOME_ACCESS: _SENSITIVE,
        # With the address it is a burglar's map (ADR 0024): the face and a verified voice.
        SensitiveTopic.LIVES_ALONE: _SECURITY,
        SensitiveTopic.CONTACT_PHONE: _SENSITIVE,
        SensitiveTopic.CONTACT_CALL: _SENSITIVE,
        SensitiveTopic.KEY_HOLDERS: _SENSITIVE,
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
        SensitiveTopic.IMPLANTED_DEVICE: ("personal", "medical"),
        SensitiveTopic.MOBILITY: ("personal", "medical"),
        SensitiveTopic.HEARING: ("personal", "medical"),
        SensitiveTopic.VISION: ("personal", "medical"),
        SensitiveTopic.HEALTH_COVERAGE: ("personal", "private"),
        SensitiveTopic.DWELLING_TYPE: ("personal", "location"),
        SensitiveTopic.FLOOR: ("personal", "location"),
        SensitiveTopic.LIFT: ("personal", "location"),
        SensitiveTopic.HOME_ACCESS: ("personal", "location"),
        SensitiveTopic.LIVES_ALONE: ("personal", "location"),
        # The strictest label the contacts table holds; the policy request names both (D-8).
        SensitiveTopic.CONTACT_PHONE: ("personal", "location"),
        SensitiveTopic.CONTACT_CALL: ("personal", "location"),
        SensitiveTopic.KEY_HOLDERS: ("personal", "location"),
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
        SensitiveTopic.IMPLANTED_DEVICE: (
            "que dispositivos tengo",
            "que implantes tengo",
            "cuales son mis dispositivos",
            "cuales son mis implantes",
            "tengo algun dispositivo",
            "tengo algun implante",
        ),
        SensitiveTopic.MOBILITY: (
            "cual es mi movilidad",
            "como es mi movilidad",
            "como me desplazo",
            "como me muevo",
        ),
        SensitiveTopic.HEARING: (
            "cual es mi audicion",
            "como es mi audicion",
            "como escucho",
            "uso audifonos",
        ),
        SensitiveTopic.VISION: ("cual es mi vision", "como es mi vision", "como veo", "uso lentes"),
        SensitiveTopic.HEALTH_COVERAGE: (
            "cual es mi prevision",
            "cual es mi prevision de salud",
            "que prevision tengo",
            "cual es mi seguro de salud",
            "que seguro de salud tengo",
        ),
        SensitiveTopic.DWELLING_TYPE: (
            "vivo en casa o departamento",
            "vivo en casa o en departamento",
            "en que tipo de vivienda vivo",
            "que tipo de vivienda tengo",
        ),
        SensitiveTopic.FLOOR: (
            "en que piso vivo",
            "en que piso esta mi departamento",
            "cual es mi piso",
        ),
        SensitiveTopic.LIFT: ("tengo ascensor", "mi edificio tiene ascensor"),
        SensitiveTopic.HOME_ACCESS: (
            "como se entra a mi casa",
            "como se entra a mi departamento",
            "como entran a mi casa",
            "como entra la ambulancia",
        ),
        SensitiveTopic.LIVES_ALONE: ("vivo solo", "vivo sola"),
        SensitiveTopic.KEY_HOLDERS: tuple(
            f"{holder}{place}"
            for holder in (
                "quien tiene llave",
                "quien tiene llaves",
                "quien tiene la llave",
                "quien tiene las llaves",
            )
            for place in ("", " de mi casa", " de la casa", " de mi departamento")
        ),
        SensitiveTopic.CONTACT_PHONE: tuple(
            f"{asking} {number} {joint}"
            for asking in (
                "tienes el",
                "cual es el",
                "dame el",
                "me das el",
                "me puedes dar el",
                "me podrias dar el",
                # The usted forms, and «tienes» as Whisper often writes it (hardware 2026-11-12).
                "tiene el",
                "me da el",
                "me puede dar el",
                "me podria dar el",
                # Only after a request opener («dime», «me puedes decir»): see `_NEEDS_OPENER`.
                "el",
            )
            for number in ("telefono", "numero", "celular")
            for joint in ("de", "del")
        ),
        SensitiveTopic.CONTACT_CALL: tuple(
            f"{calling} {joint}"
            for calling in (
                "llama",
                "llamale",
                "puedes llamar",
                "podrias llamar",
                "quiero llamar",
                "necesito llamar",
                "llame",
                "llamele",
                "puede llamar",
                "podria llamar",
            )
            for joint in ("a", "al")
        ),
    }
)

# Contact phrases that are a question only after a request opener: «dime el teléfono de mi hija»
# is one, «el teléfono de mi hija es nuevo» is a statement.
_NEEDS_OPENER: Final[frozenset[str]] = frozenset(
    f"el {number} {joint}"
    for number in ("telefono", "numero", "celular")
    for joint in ("de", "del")
)

# Phrases with the form of a statement: they need a question mark («tomo anticoagulante desde
# hace años», «uso lentes desde chico», «vivo solo desde 2010» are statements).
_NEEDS_QUESTION_MARK: Final[frozenset[str]] = frozenset(
    {
        "tomo anticoagulante",
        "tomo anticoagulantes",
        "tengo algun dispositivo",
        "tengo algun implante",
        "uso audifonos",
        "uso lentes",
        "tengo ascensor",
        "mi edificio tiene ascensor",
        "vivo solo",
        "vivo sola",
    }
)

# Topics whose tail names what is asked (a child, a secret, a document); every other topic is
# closed: only the trailing fillers may follow its phrase.
_OPEN_TOPICS: Final[frozenset[SensitiveTopic]] = frozenset(
    {
        SensitiveTopic.CHILD_BIRTHDAY,
        SensitiveTopic.SECRET_HOLDER,
        SensitiveTopic.DOCUMENT_LOCATION,
        SensitiveTopic.CONTACT_PHONE,
        SensitiveTopic.CONTACT_CALL,
    }
)
# Open topics whose whole tail is kept as is, short words and digits included («mi tio», «mi
# contacto 1»): ``contact_questions`` reads it (D-5).
_RAW_TAIL_TOPICS: Final[frozenset[SensitiveTopic]] = frozenset(
    {SensitiveTopic.CONTACT_PHONE, SensitiveTopic.CONTACT_CALL}
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


@dataclass(frozen=True)
class _Pattern:
    """One folded phrase as words, its topic, and what else it needs to be a question."""

    topic: SensitiveTopic
    words: tuple[str, ...]
    needs_mark: bool
    needs_opener: bool = False


# The folded phrases as word tuples, topic by topic, without a leading «a».
_ALL_PATTERNS: Final[tuple[_Pattern, ...]] = tuple(
    _Pattern(
        topic,
        tuple(phrase.removeprefix("a ").split()),
        phrase in _NEEDS_QUESTION_MARK,
        phrase in _NEEDS_OPENER,
    )
    for topic, phrases in _PHRASES.items()
    for phrase in phrases
)
# Plan 0079's grammar alone, the one used while the alta read is off.
_BASE_PATTERNS: Final[tuple[_Pattern, ...]] = tuple(
    pattern for pattern in _ALL_PATTERNS if pattern.topic not in ALTA_TOPICS
)


def classify_sensitive_question(message: str, *, alta: bool = False) -> SensitiveQuery | None:
    """Return the sensitive topic the message asks about, or ``None``.

    Pure and deterministic; the phrase must open the sentence body (once the fillers and the
    request openers, «una pregunta», «me puede decir», are set aside) and, for a closed topic, only
    trailing fillers may follow it. A phrase with the form of a statement («tomo anticoagulante»,
    «vivo solo») also needs a question mark.

    Args:
        message: Raw transcript or chat text.
        alta: Whether the rest of the alta's topics (``ALTA_TOPICS``, Plan 0082) may match; off,
            the grammar is exactly Plan 0079's.

    Returns:
        The topic and its keywords, or ``None`` for any other turn. A contact topic carries its
        whole folded tail (D-5) and needs one.
    """
    whole = sentence_body(message)
    body = _without_openers(whole)
    opened = body != whole
    for pattern in _ALL_PATTERNS if alta else _BASE_PATTERNS:
        topic = pattern.topic
        if body[: len(pattern.words)] != pattern.words or (pattern.needs_opener and not opened):
            continue
        span_end = _span_end(topic, body, len(pattern.words))
        if span_end is None:
            continue
        tail = _without_trailing_fillers(body[span_end:])
        if topic in _RAW_TAIL_TOPICS:
            if tail:
                return SensitiveQuery(topic=topic, keywords=tail)
            continue
        if topic not in _OPEN_TOPICS:
            if tail or (pattern.needs_mark and not has_question_mark(message)):
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
