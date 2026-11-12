"""The fixed Spanish sentences that say a contact's phone (Plan 0082 Task 1, D-9 and D-10).

Canaries only: «Canary Daughter», «Canary Doctor» and the +569000000xx phones are invented.
"""

from __future__ import annotations

import pytest
from server.cognition.contact_answers import (
    CANNOT_CALL,
    MAX_SPOKEN_CONTACTS,
    NO_KEY_HOLDER,
    NO_PHONE,
    SpokenContact,
    role_descriptor,
    spoken_phone,
    word_contacts,
    word_key_holders,
)
from server.memory.care_contacts import ContactRole

pytestmark = pytest.mark.unit

_DAUGHTER_PHONE = "+56900000001"
_SPOKEN_DAUGHTER_PHONE = "más cinco seis nueve, cero cero cero cero, cero cero cero uno"
_ROLES = ("emergency", "caregiver", "doctor", "key_holder", "neighbor", "trusted", "other")


def _contact(
    name: str | None = "Canary Daughter",
    descriptor: str = "hija",
    phone: str = _DAUGHTER_PHONE,
    phone_alt: str | None = None,
) -> SpokenContact:
    return SpokenContact(name=name, descriptor=descriptor, phone=phone, phone_alt=phone_alt)


@pytest.mark.parametrize(
    "phone, expected",
    [
        (_DAUGHTER_PHONE, _SPOKEN_DAUGHTER_PHONE),
        ("+5622000000", "más cinco seis, dos dos cero cero, cero cero cero cero"),
        (
            "+123456789012345",
            "más uno dos tres, cuatro cinco seis siete, ocho nueve cero uno, dos tres cuatro cinco",
        ),
        ("+12345678", "más uno dos tres cuatro, cinco seis siete ocho"),
    ],
)
def test_spoken_phone_groups_from_the_right(phone: str, expected: str) -> None:
    assert spoken_phone(phone) == expected


@pytest.mark.parametrize("phone", ["56900000001", "+56 9 0000 0001", "+5690000abc1", "", "+"])
def test_spoken_phone_rejects_a_non_phone(phone: str) -> None:
    with pytest.raises(ValueError, match="canonical") as error:
        spoken_phone(phone)
    assert not any(character.isdigit() for character in str(error.value))


def test_every_role_has_a_descriptor() -> None:
    descriptors = {role: role_descriptor(role) for role in _ROLES}
    assert descriptors == {
        "emergency": "contacto de emergencia",
        "caregiver": "contacto de cuidado",
        "doctor": "contacto médico",
        "key_holder": "contacto con llave",
        "neighbor": "contacto vecino",
        "trusted": "contacto de confianza",
        "other": "contacto",
    }


def test_an_unknown_role_raises() -> None:
    with pytest.raises(ValueError, match="closed contact roles"):
        role_descriptor("plumber")


def test_one_contact_with_and_without_a_name() -> None:
    assert word_contacts((_contact(),)) == (
        f"El teléfono de Canary Daughter, tu hija, es {_SPOKEN_DAUGHTER_PHONE}."
    )
    assert word_contacts((_contact(name=None),)) == (
        f"El teléfono de tu hija es {_SPOKEN_DAUGHTER_PHONE}."
    )


def test_a_second_phone_is_appended() -> None:
    sentence = word_contacts((_contact(phone_alt="+56200000002"),))
    assert sentence == (
        f"El teléfono de Canary Daughter, tu hija, es {_SPOKEN_DAUGHTER_PHONE}. "
        "También tiene el más cinco seis dos, cero cero cero cero, cero cero cero dos."
    )


def test_several_contacts_are_joined() -> None:
    doctor = _contact("Canary Doctor", "contacto médico", "+56900000003")
    sentence = word_contacts((_contact(), doctor))
    assert sentence == (
        f"El teléfono de Canary Daughter, tu hija, es {_SPOKEN_DAUGHTER_PHONE}. "
        "El teléfono de Canary Doctor, tu contacto médico, es más cinco seis nueve, "
        "cero cero cero cero, cero cero cero tres."
    )


def test_no_contact_says_no_phone() -> None:
    assert word_contacts(()) == NO_PHONE == "No tengo ese teléfono guardado."


def test_key_holders_one_several_and_none() -> None:
    neighbor = _contact("Canary Neighbor", "vecina", "+56900000004")
    nameless = _contact(None, "", "+56900000005")
    labelled = _contact(None, "vecina", "+56900000006")
    assert word_key_holders((_contact(),)) == "Canary Daughter tiene llave de tu casa."
    assert word_key_holders((nameless,)) == "Una persona de tus contactos tiene llave de tu casa."
    assert word_key_holders((labelled,)) == "Tu vecina tiene llave de tu casa."
    assert word_key_holders((_contact(), neighbor, nameless)) == (
        "Tienen llave de tu casa: Canary Daughter, Canary Neighbor y una persona de tus contactos."
    )
    assert word_key_holders(()) == NO_KEY_HOLDER


def test_values_are_read_as_written() -> None:
    sentence = word_contacts((_contact(descriptor="Hija mayor"),))
    assert sentence.startswith("El teléfono de Canary Daughter, tu Hija mayor, es ")


def test_the_fixed_phrases_and_the_cap() -> None:
    assert CANNOT_CALL == "Todavía no puedo hacer llamadas."
    assert NO_KEY_HOLDER == "No tengo registrado que alguien tenga llave de tu casa."
    assert MAX_SPOKEN_CONTACTS == 3


def test_the_repr_holds_no_value() -> None:
    shown = repr(_contact(phone_alt="+56200000002"))
    assert "Canary" not in shown
    assert "hija" not in shown
    assert "569" not in shown


def test_every_contact_role_of_the_table_has_a_descriptor() -> None:
    assert set(_ROLES) == {role.value for role in ContactRole}


def test_a_second_phone_equal_to_the_first_is_said_once() -> None:
    sentence = word_contacts((_contact(phone_alt=_DAUGHTER_PHONE),))
    assert sentence == f"El teléfono de Canary Daughter, tu hija, es {_SPOKEN_DAUGHTER_PHONE}."
