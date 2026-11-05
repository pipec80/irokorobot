"""The fixed Spanish templates that word the owner's sensitive answers (Plan 0079 Task 4, D-7).

Canaries only: «Remedio A», «Calle Falsa 123 #4», Zeta and Omega are invented.
"""

from __future__ import annotations

from datetime import date

import pytest
from server.cognition import controller
from server.cognition.sensitive_answers import (
    spanish_join,
    spoken_blood_type,
    word_children_birthdays,
    word_own_answer,
)
from server.cognition.sensitive_questions import SensitiveTopic

pytestmark = pytest.mark.unit

_MARCH_THIRD = date(2015, 3, 3)
_SPOKEN_MARCH_THIRD = "el 3 de marzo"


@pytest.mark.parametrize(
    "values, expected",
    [
        (("Zeta",), "Zeta"),
        (("Zeta", "Omega"), "Zeta y Omega"),
        (("Zeta", "Omega", "Canary"), "Zeta, Omega y Canary"),
    ],
)
def test_spanish_join_is_unchanged(values: tuple[str, ...], expected: str) -> None:
    assert spanish_join(values) == expected


def test_the_controller_uses_the_one_spanish_join() -> None:
    assert controller.spanish_join is spanish_join
    assert not hasattr(controller, "_spanish_join")


@pytest.mark.parametrize(
    "topic, values, expected",
    [
        (SensitiveTopic.MEDICATION, ("Remedio A",), "Tu medicamento es Remedio A."),
        (
            SensitiveTopic.MEDICATION,
            ("Remedio A", "Remedio B"),
            "Tus medicamentos son Remedio A y Remedio B.",
        ),
        (
            SensitiveTopic.MEDICATION,
            ("Remedio A", "Remedio B", "Remedio C"),
            "Tus medicamentos son Remedio A, Remedio B y Remedio C.",
        ),
        (
            SensitiveTopic.RESCUE_MEDICATION,
            ("Remedio A",),
            "Tu medicamento de rescate es Remedio A.",
        ),
        (
            SensitiveTopic.RESCUE_MEDICATION,
            ("Remedio A", "Remedio B"),
            "Tus medicamentos de rescate son Remedio A y Remedio B.",
        ),
        (
            SensitiveTopic.HEALTH_CONDITION,
            ("Condición A",),
            "Tu condición de salud registrada es Condición A.",
        ),
        (
            SensitiveTopic.HEALTH_CONDITION,
            ("Condición A", "Condición B"),
            "Tus condiciones de salud registradas son Condición A y Condición B.",
        ),
        (SensitiveTopic.ALLERGY, ("Alérgeno A",), "Tienes alergia a Alérgeno A."),
        (
            SensitiveTopic.ALLERGY,
            ("Alérgeno A", "Alérgeno B"),
            "Tienes alergia a Alérgeno A y Alérgeno B.",
        ),
        (SensitiveTopic.BLOOD_TYPE, ("O-",), "Tu grupo sanguíneo es O negativo."),
        (SensitiveTopic.ADDRESS, ("Calle Falsa 123",), "Tu dirección es Calle Falsa 123."),
        (
            SensitiveTopic.EMERGENCY_FACILITY,
            ("Clínica Canary",),
            "Tu urgencia preferida es Clínica Canary.",
        ),
        (
            SensitiveTopic.OWN_BIRTHDAY,
            ("2015-03-03",),
            "Tu cumpleaños es el 3 de marzo.",
        ),
    ],
)
def test_each_template_in_singular_and_plural(
    topic: SensitiveTopic, values: tuple[str, ...], expected: str
) -> None:
    assert word_own_answer(topic, values) == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("A+", "A positivo"),
        ("A-", "A negativo"),
        ("B+", "B positivo"),
        ("B-", "B negativo"),
        ("AB+", "AB positivo"),
        ("AB-", "AB negativo"),
        ("O+", "O positivo"),
        ("O-", "O negativo"),
    ],
)
def test_every_blood_type_has_a_spoken_form(value: str, expected: str) -> None:
    assert spoken_blood_type(value) == expected
    assert (
        word_own_answer(SensitiveTopic.BLOOD_TYPE, (value,)) == f"Tu grupo sanguíneo es {expected}."
    )


def test_an_unknown_blood_type_is_read_as_written() -> None:
    assert spoken_blood_type("Rh nulo") == "Rh nulo"
    assert (
        word_own_answer(SensitiveTopic.BLOOD_TYPE, ("Rh nulo",)) == "Tu grupo sanguíneo es Rh nulo."
    )


def test_several_blood_types_are_joined() -> None:
    answer = word_own_answer(SensitiveTopic.BLOOD_TYPE, ("A+", "O-"))

    assert answer == "Tu grupo sanguíneo es A positivo y O negativo."


@pytest.mark.parametrize(
    "stored, expected",
    [
        ("si", "Sí, tomas anticoagulante."),
        ("no", "No tomas anticoagulante."),
        ("no_se", "No tengo claro si tomas anticoagulante."),
    ],
)
def test_the_three_anticoagulant_answers(stored: str, expected: str) -> None:
    assert word_own_answer(SensitiveTopic.ANTICOAGULANT, (stored,)) == expected


def test_a_medication_with_a_dose_is_read_as_written() -> None:
    answer = word_own_answer(SensitiveTopic.MEDICATION, ("Remedio A 50 mg",))

    assert answer == "Tu medicamento es Remedio A 50 mg."


def test_an_address_with_a_hash_and_digits_is_read_as_written() -> None:
    answer = word_own_answer(SensitiveTopic.ADDRESS, ("Calle Falsa 123 #4",))

    assert answer == "Tu dirección es Calle Falsa 123 #4."


def test_a_reference_is_read_as_written() -> None:
    answer = word_own_answer(SensitiveTopic.SECRET_HOLDER, ("clave del banco 4821 con Canary",))

    assert answer == "Sobre las claves tengo anotado: clave del banco 4821 con Canary."


def test_references_are_joined_with_semicolons() -> None:
    holder = word_own_answer(SensitiveTopic.SECRET_HOLDER, ("clave 12 con Zeta", "pin con Omega"))
    documents = word_own_answer(
        SensitiveTopic.DOCUMENT_LOCATION, ("pasaporte en el cajón", "escritura en la caja")
    )

    assert holder == "Sobre las claves tengo anotado: clave 12 con Zeta; pin con Omega."
    assert documents == (
        "Sobre tus documentos tengo anotado: pasaporte en el cajón; escritura en la caja."
    )


def test_one_document_reference() -> None:
    answer = word_own_answer(SensitiveTopic.DOCUMENT_LOCATION, ("pasaporte en el cajón",))

    assert answer == "Sobre tus documentos tengo anotado: pasaporte en el cajón."


@pytest.mark.parametrize(
    "topic, values",
    [
        (SensitiveTopic.CHILD_BIRTHDAY, ("2015-03-03",)),
        (SensitiveTopic.OWN_BIRTHDAY, ()),
        (SensitiveTopic.OWN_BIRTHDAY, ("2015-03-03", "2016-04-04")),
        (SensitiveTopic.OWN_BIRTHDAY, ("3 de marzo Canary",)),
        (SensitiveTopic.OWN_BIRTHDAY, ("2015-13-40",)),
        (SensitiveTopic.OWN_BIRTHDAY, ("20150303",)),
        (SensitiveTopic.ANTICOAGULANT, ()),
        (SensitiveTopic.ANTICOAGULANT, ("si", "no")),
        (SensitiveTopic.ANTICOAGULANT, ("quizas Canary",)),
        (SensitiveTopic.MEDICATION, ()),
    ],
)
def test_an_unwordable_answer_raises_without_a_value(
    topic: SensitiveTopic, values: tuple[str, ...]
) -> None:
    with pytest.raises(ValueError) as raised:  # noqa: PT011  # the message is checked below
        word_own_answer(topic, values)

    message = str(raised.value)
    assert "Canary" not in message
    assert "2015" not in message
    assert "20150303" not in message


def test_one_child_with_a_date() -> None:
    answer = word_children_birthdays((("Zeta", _MARCH_THIRD),))

    assert answer == "El cumpleaños de Zeta es el 3 de marzo."


def test_several_children_with_a_date() -> None:
    answer = word_children_birthdays(
        (("Zeta", _MARCH_THIRD), ("Omega", date(2018, 11, 21)), ("Canary", date(2020, 1, 1)))
    )

    assert answer == (
        "Zeta cumple el 3 de marzo, Omega cumple el 21 de noviembre y Canary cumple el 1 de enero."
    )


def test_two_children_with_a_date() -> None:
    answer = word_children_birthdays((("Zeta", _MARCH_THIRD), ("Omega", date(2018, 11, 21))))

    assert answer == "Zeta cumple el 3 de marzo y Omega cumple el 21 de noviembre."


def test_one_child_without_a_date_in_a_list() -> None:
    answer = word_children_birthdays((("Zeta", None), ("Omega", _MARCH_THIRD)))

    assert answer == "De Zeta no tengo la fecha y Omega cumple el 3 de marzo."


def test_a_child_without_a_date_after_one_with_a_date() -> None:
    answer = word_children_birthdays((("Omega", _MARCH_THIRD), ("Zeta", None)))

    assert answer == "Omega cumple el 3 de marzo y de Zeta no tengo la fecha."


@pytest.mark.parametrize(
    "children",
    [(), (("Zeta", None),), (("Zeta", None), ("Omega", None))],
)
def test_no_child_with_a_date_raises_without_a_value(
    children: tuple[tuple[str, date | None], ...],
) -> None:
    with pytest.raises(ValueError) as raised:  # noqa: PT011  # the message is checked below
        word_children_birthdays(children)

    assert "Zeta" not in str(raised.value)
    assert "Omega" not in str(raised.value)
