"""Say the owner's contacts aloud with fixed Spanish sentences (Plan 0082, D-9 and D-10).

Pure functions over values a later step already read and authorized: the model never sees a
phone, a name or a relationship. A phone is said digit by digit, each digit as its word, in groups
of four from the right, so the voice never reads «569» as a number. Values are read as written;
nothing here holds one in a ``repr`` or an exception message.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from server.cognition.sensitive_answers import capitalized, spanish_join

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "CANNOT_CALL",
    "MAX_SPOKEN_CONTACTS",
    "NO_KEY_HOLDER",
    "NO_PHONE",
    "SpokenContact",
    "role_descriptor",
    "spoken_phone",
    "word_contacts",
    "word_key_holders",
]

CANNOT_CALL: Final = "Todavía no puedo hacer llamadas."
NO_PHONE: Final = "No tengo ese teléfono guardado."
NO_KEY_HOLDER: Final = "No tengo registrado que alguien tenga llave de tu casa."
#: The most people one answer says: a robot turn is capped at 28 s (D-7).
MAX_SPOKEN_CONTACTS: Final = 3

_GROUP: Final = 4
_DIGIT_WORDS: Final = (
    "cero",
    "uno",
    "dos",
    "tres",
    "cuatro",
    "cinco",
    "seis",
    "siete",
    "ocho",
    "nueve",
)
_ROLE_DESCRIPTORS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "emergency": "contacto de emergencia",
        "caregiver": "contacto de cuidado",
        "doctor": "contacto médico",
        "key_holder": "contacto con llave",
        "neighbor": "contacto vecino",
        "trusted": "contacto de confianza",
        "other": "contacto",
    }
)


@dataclass(frozen=True)
class SpokenContact:
    """One person to say: a stored name, the words that say what they are, their phones.

    Attributes:
        name: The contact's stored name, or ``None`` when none is stored.
        descriptor: The relationship label as stored, or the role's words (``role_descriptor``).
        phone: The canonical phone (``+`` and digits).
        phone_alt: A second canonical phone, or ``None``.
    """

    name: str | None = field(repr=False)
    descriptor: str = field(repr=False)
    phone: str = field(repr=False)
    phone_alt: str | None = field(repr=False)


def spoken_phone(phone: str) -> str:
    """Return a canonical phone as it is said: «más», then its digits as words, grouped.

    Args:
        phone: ``+`` followed by ASCII digits, as the contacts writer stores it.

    Returns:
        For ``+56900000001``, «más cinco seis nueve, cero cero cero cero, cero cero cero uno».

    Raises:
        ValueError: For anything else; the message never carries a digit.
    """
    digits = phone.removeprefix("+")
    if digits == phone or not digits or not (digits.isascii() and digits.isdigit()):
        raise ValueError("phone is not a canonical international number")
    head = len(digits) % _GROUP or _GROUP
    groups = [digits[:head]] + [digits[i : i + _GROUP] for i in range(head, len(digits), _GROUP)]
    spoken = (" ".join(_DIGIT_WORDS[int(digit)] for digit in group) for group in groups)
    return f"más {', '.join(spoken)}"


def role_descriptor(role: str) -> str:
    """Return the words that say a contact's role when no relationship label is stored.

    Args:
        role: A ``ContactRole`` value.

    Returns:
        For example «contacto de emergencia».

    Raises:
        ValueError: For a role outside the closed list.
    """
    descriptor = _ROLE_DESCRIPTORS.get(role)
    if descriptor is None:
        raise ValueError("role is not one of the closed contact roles")
    return descriptor


def word_contacts(contacts: tuple[SpokenContact, ...]) -> str:
    """Say each contact's phones, one sentence per person, in the order given.

    Args:
        contacts: The people to say, already selected and capped.

    Returns:
        The sentences joined with a space, or ``NO_PHONE`` when there is nobody.
    """
    if not contacts:
        return NO_PHONE
    return " ".join(_contact_sentence(contact) for contact in contacts)


def _contact_sentence(contact: SpokenContact) -> str:
    who = (
        f"de {contact.name}, tu {contact.descriptor},"
        if contact.name
        else f"de tu {contact.descriptor}"
    )
    sentence = f"El teléfono {who} es {spoken_phone(contact.phone)}."
    if contact.phone_alt is not None:
        sentence += f" También tiene el {spoken_phone(contact.phone_alt)}."
    return sentence


def word_key_holders(contacts: tuple[SpokenContact, ...]) -> str:
    """Say who holds a key of the owner's home.

    Args:
        contacts: The contacts that hold a key, already selected.

    Returns:
        «Canary Daughter tiene llave de tu casa.», a list for several, or ``NO_KEY_HOLDER``.
    """
    if not contacts:
        return NO_KEY_HOLDER
    names = tuple(contact.name or f"tu {contact.descriptor}" for contact in contacts)
    if len(names) == 1:
        return capitalized(f"{names[0]} tiene llave de tu casa.")
    return f"Tienen llave de tu casa: {spanish_join(names)}."
