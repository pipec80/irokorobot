"""Word the owner's sensitive answers with fixed Spanish templates (Plan 0079, D-7).

Pure functions: they receive values a later step already read and authorized, and return the
sentence the robot says. The model never sees a stored value; the template is the whole voice of
the answer. Values are read exactly as written («Remedio A 50 mg», «Calle Falsa 123 #4», an entry
with «clave» and digits): nothing here alters, hides or refuses one. A value that cannot be worded
raises ``ValueError`` whose message never carries it.
"""

from __future__ import annotations

from datetime import date
import re
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from server.cognition.sensitive_questions import SensitiveTopic
from server.cognition.spoken_dates import day_month_label

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "spanish_join",
    "spoken_blood_type",
    "word_children_birthdays",
    "word_own_answer",
]

_TWO_ITEMS: Final = 2
_ISO_DATE: Final = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_REFERENCE_SEPARATOR: Final = "; "

_BLOOD_TYPES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "A+": "A positivo",
        "A-": "A negativo",
        "B+": "B positivo",
        "B-": "B negativo",
        "AB+": "AB positivo",
        "AB-": "AB negativo",
        "O+": "O positivo",
        "O-": "O negativo",
    }
)

#: ``(singular, plural)`` per topic; ``{}`` takes the joined values.
_COUNTED_TEMPLATES: Final[Mapping[SensitiveTopic, tuple[str, str]]] = MappingProxyType(
    {
        SensitiveTopic.MEDICATION: ("Tu medicamento es {}.", "Tus medicamentos son {}."),
        SensitiveTopic.RESCUE_MEDICATION: (
            "Tu medicamento de rescate es {}.",
            "Tus medicamentos de rescate son {}.",
        ),
        SensitiveTopic.HEALTH_CONDITION: (
            "Tu condición de salud registrada es {}.",
            "Tus condiciones de salud registradas son {}.",
        ),
        SensitiveTopic.IMPLANTED_DEVICE: (
            "Tu dispositivo registrado es {}.",
            "Tus dispositivos registrados son {}.",
        ),
    }
)
#: One template for any number of values; ``{}`` takes the values joined with ``spanish_join``.
_SPANISH_JOIN_TEMPLATES: Final[Mapping[SensitiveTopic, str]] = MappingProxyType(
    {
        SensitiveTopic.ALLERGY: "Tienes alergia a {}.",
        SensitiveTopic.BLOOD_TYPE: "Tu grupo sanguíneo es {}.",
        SensitiveTopic.ADDRESS: "Tu dirección es {}.",
        SensitiveTopic.EMERGENCY_FACILITY: "Tu urgencia preferida es {}.",
        SensitiveTopic.HEALTH_COVERAGE: "Tu previsión de salud es {}.",
        SensitiveTopic.FLOOR: "Vives en el piso {}.",
    }
)
#: Reference topics: the entries are joined with «; », since an entry may hold commas or «y».
_REFERENCE_TEMPLATES: Final[Mapping[SensitiveTopic, str]] = MappingProxyType(
    {
        SensitiveTopic.SECRET_HOLDER: "Sobre las claves tengo anotado: {}.",  # pragma: allowlist secret
        SensitiveTopic.DOCUMENT_LOCATION: "Sobre tus documentos tengo anotado: {}.",
        SensitiveTopic.HOME_ACCESS: "Sobre cómo entrar a tu casa tengo anotado: {}.",
    }
)
#: The topics stored as one closed choice: the sentence each choice says (D-11).
_CHOICE_ANSWERS: Final[Mapping[SensitiveTopic, Mapping[str, str]]] = MappingProxyType(
    {
        SensitiveTopic.MOBILITY: MappingProxyType(
            {
                "solo": "Te desplazas sin ayuda.",
                "baston": "Te desplazas con bastón.",
                "andador": "Te desplazas con andador.",
                "silla_de_ruedas": "Te desplazas en silla de ruedas.",
            }
        ),
        SensitiveTopic.HEARING: MappingProxyType(
            {
                "normal": "Tienes registrada una audición normal.",
                "audifonos": "Usas audífonos.",
                "dificultad": "Tienes dificultad para escuchar.",
            }
        ),
        SensitiveTopic.VISION: MappingProxyType(
            {
                "normal": "Tienes registrada una visión normal.",
                "lentes": "Usas lentes.",
                "dificultad": "Tienes dificultad para ver.",
            }
        ),
        SensitiveTopic.DWELLING_TYPE: MappingProxyType(
            {"casa": "Vives en una casa.", "departamento": "Vives en un departamento."}
        ),
        SensitiveTopic.LIFT: MappingProxyType(
            {"si": "Sí, tu edificio tiene ascensor.", "no": "Tu edificio no tiene ascensor."}
        ),
        SensitiveTopic.LIVES_ALONE: MappingProxyType(
            {
                "si": "Tengo registrado que vives sin nadie más en casa.",
                "no": "Tengo registrado que vives con alguien más.",
            }
        ),
    }
)
_ANTICOAGULANT_ANSWERS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "si": "Sí, tomas anticoagulante.",
        "no": "No tomas anticoagulante.",
        "no_se": "No tengo claro si tomas anticoagulante.",
    }
)


def spanish_join(values: tuple[str, ...]) -> str:
    """Join already-authorized labels with deterministic Spanish punctuation.

    Args:
        values: One or more labels.

    Returns:
        «A», «A y B» or «A, B y C».
    """
    if len(values) == 1:
        return values[0]
    if len(values) == _TWO_ITEMS:
        return f"{values[0]} y {values[1]}"
    return f"{', '.join(values[:-1])} y {values[-1]}"


def spoken_blood_type(value: str) -> str:
    """Return a blood type as it is spoken: ``A+`` is «A positivo».

    Args:
        value: A stored blood type.

    Returns:
        The spoken form of one of the eight closed choices; any other value as written.
    """
    return _BLOOD_TYPES.get(value, value)


def word_own_answer(topic: SensitiveTopic, values: tuple[str, ...]) -> str:
    """Word the owner's answer about one of their own data topics.

    Args:
        topic: What was asked; ``CHILD_BIRTHDAY`` is no own topic (see
            ``word_children_birthdays``).
        values: The stored values, as written and never empty; ISO dates for ``OWN_BIRTHDAY``;
            ``si``, ``no`` or ``no_se`` for ``ANTICOAGULANT``.

    Returns:
        The sentence to say.

    Raises:
        ValueError: When the topic has no own template, there are no values, or the values do not
            fit the topic (several birthdays or anticoagulant answers, a non-ISO date, an
            anticoagulant outside si/no/no_se). The message never carries a value.
    """
    if not values:
        raise ValueError(f"no values to word for {topic.value}")
    if topic in _COUNTED_TEMPLATES:
        one, several = _COUNTED_TEMPLATES[topic]
        return (one if len(values) == 1 else several).format(spanish_join(values))
    if topic is SensitiveTopic.BLOOD_TYPE:
        spoken = tuple(spoken_blood_type(value) for value in values)
        return _SPANISH_JOIN_TEMPLATES[topic].format(spanish_join(spoken))
    if topic in _SPANISH_JOIN_TEMPLATES:
        return _SPANISH_JOIN_TEMPLATES[topic].format(spanish_join(values))
    if topic in _REFERENCE_TEMPLATES:
        return _REFERENCE_TEMPLATES[topic].format(_REFERENCE_SEPARATOR.join(values))
    if topic in _CHOICE_ANSWERS:
        return _word_choice(topic, values)
    return _word_single_value(topic, values)


def _word_choice(topic: SensitiveTopic, values: tuple[str, ...]) -> str:
    """Word a topic stored as one closed choice; raise for several values or an unknown choice."""
    if len(values) != 1:
        raise ValueError(f"{topic.value} needs one value and got {len(values)}")
    answer = _CHOICE_ANSWERS[topic].get(values[0])
    if answer is None:
        raise ValueError(f"{topic.value} value outside its closed choices")
    return answer


def _word_single_value(topic: SensitiveTopic, values: tuple[str, ...]) -> str:
    """Word the topics that take exactly one value; raise for any other topic or shape."""
    if topic not in (SensitiveTopic.OWN_BIRTHDAY, SensitiveTopic.ANTICOAGULANT):
        raise ValueError(f"no own template for {topic.value}")
    if len(values) != 1:
        raise ValueError(f"{topic.value} needs one value and got {len(values)}")
    value = values[0]
    if topic is SensitiveTopic.ANTICOAGULANT:
        answer = _ANTICOAGULANT_ANSWERS.get(value)
        if answer is None:
            raise ValueError("anticoagulant value outside si, no and no_se")
        return answer
    return f"Tu cumpleaños es {day_month_label(_parse_iso_date(value))}."


def _parse_iso_date(value: str) -> date:
    """Parse a strict ``YYYY-MM-DD`` date; the error never carries the value."""
    if _ISO_DATE.fullmatch(value) is None:
        raise ValueError("birth date is not an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError:
        # `from None`: the chained error would ride in a traceback, and a stored value must not.
        raise ValueError("birth date is not a calendar date") from None


def word_children_birthdays(children: tuple[tuple[str, date | None], ...]) -> str:
    """Word the birthdays of the owner's children.

    Args:
        children: ``(name, birth date or None)`` per child, in the order to say them.

    Returns:
        «El cumpleaños de Zeta es el 3 de marzo.» for one child; for several, a sentence such as
        «De Zeta no tengo la fecha y Omega cumple el 3 de marzo.»

    Raises:
        ValueError: When no child has a date (the caller says «No tengo registrada su fecha.»).
            The message never carries a name.
    """
    dated = [(name, day) for name, day in children if day is not None]
    if not dated:
        raise ValueError(f"no birth date among {len(children)} children")
    if len(children) == 1:
        name, day = dated[0]
        return f"El cumpleaños de {name} es {day_month_label(day)}."
    parts = tuple(
        f"{name} cumple {day_month_label(day)}"
        if day is not None
        else f"de {name} no tengo la fecha"
        for name, day in children
    )
    sentence = f"{spanish_join(parts)}."
    return sentence[0].upper() + sentence[1:]
