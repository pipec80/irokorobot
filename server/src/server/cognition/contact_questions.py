"""Tell which of the owner's own contacts a question names (Plan 0082, D-5 to D-7).

A pure, closed parser over the folded words that follow a contact question's phrase («¿tienes el
teléfono de *mi hija*?», «llama a *mi contacto 1*»). It reads no store: the selector says what was
named, and ``selects`` tells whether one stored contact matches it, after the policy and its audit
row. A question that names no own contact (no «mi», no call order) is not the owner's to answer
from storage; the caller keeps it as ordinary conversation (D-6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from server.text_keys import normalize_spanish

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["ContactSelector", "contact_selector", "match_score", "selects"]

_OWN_WORDS: Final = frozenset({"mi", "mis"})
_CONTACT_WORDS: Final = frozenset({"contacto", "contactos"})
_NUMBER_WORD: Final = "numero"
_ORDER_VALUES: Final[Mapping[str, int]] = MappingProxyType(
    {
        **{str(digit): digit for digit in range(1, 10)},
        **dict(
            zip(
                ("uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve"),
                range(1, 10),
                strict=True,
            )
        ),
    }
)
_ORDINALS: Final[Mapping[str, int]] = MappingProxyType(
    {
        "primer": 1,
        "primero": 1,
        "segundo": 2,
        "tercer": 3,
        "tercero": 3,
        "cuarto": 4,
        "quinto": 5,
    }
)
_ROLE_WORDS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "emergencia": "emergency",
        "cuidador": "caregiver",
        "cuidadora": "caregiver",
        "doctor": "doctor",
        "doctora": "doctor",
        "medico": "doctor",
        "medica": "doctor",
        "vecino": "neighbor",
        "vecina": "neighbor",
        "confianza": "trusted",
    }
)
# Words that name nothing about a contact; the order words are dropped where they are read.
_FUNCTION_WORDS: Final = frozenset(
    {
        *_OWN_WORDS,
        *_CONTACT_WORDS,
        _NUMBER_WORD,
        "de",
        "del",
        "el",
        "la",
        "los",
        "las",
        "a",
        "al",
        "telefono",
        "telefonos",
        "celular",
        "y",
        "por",
        "favor",
        "porfa",
        "po",
        "iroko",
        "oye",
    }
)


@dataclass(frozen=True)
class ContactSelector:
    """What a contact question named.

    Attributes:
        own: The question is about the owner's own contacts («mi», «mis» or a call order).
        order: The call order named («contacto 1», «primer contacto»), or ``None``.
        roles: The ``ContactRole`` values a role word named («emergencia» → ``emergency``).
        words: The folded content words left, role words included (a label «doctora» may sit on
            any role), matched against a contact's relationship and name.
    """

    own: bool
    order: int | None
    roles: frozenset[str]
    words: frozenset[str] = field(repr=False)  # may hold a name

    @property
    def is_empty(self) -> bool:
        """Whether nothing narrows the selection, so every contact is meant («mis contactos»)."""
        return self.order is None and not self.roles and not self.words


def contact_selector(tail: tuple[str, ...]) -> ContactSelector:
    """Parse the folded words after a contact question's phrase.

    Args:
        tail: The folded words, as ``classify_sensitive_question`` keeps them for a contact topic.

    Returns:
        The selector; ``own`` is false when neither «mi», «mis» nor a call order is said.
    """
    order, order_positions = _order_of(tail)
    roles = frozenset(_ROLE_WORDS[word] for word in tail if word in _ROLE_WORDS)
    words = frozenset(
        word
        for index, word in enumerate(tail)
        if index not in order_positions and word not in _FUNCTION_WORDS
    )
    own = order is not None or bool(_OWN_WORDS.intersection(tail))
    return ContactSelector(own=own, order=order, roles=roles, words=words)


def _order_of(tail: tuple[str, ...]) -> tuple[int | None, frozenset[int]]:
    """Return the call order named and the positions of the words that said it."""
    for index, word in enumerate(tail):
        if word not in _CONTACT_WORDS:
            continue
        before = index - 1
        if before >= 0 and tail[before] in _ORDINALS:
            return _ORDINALS[tail[before]], frozenset({before})
        after = index + 1
        if after < len(tail) and tail[after] == _NUMBER_WORD:
            after += 1
        if after < len(tail) and tail[after] in _ORDER_VALUES:
            return _ORDER_VALUES[tail[after]], frozenset(range(index + 1, after + 1))
    return None, frozenset()


def selects(
    selector: ContactSelector,
    *,
    call_order: int | None,
    role: str,
    relationship: str | None,
    name: str | None,
) -> bool:
    """Tell whether one stored contact is among those a selector named (D-7).

    Args:
        selector: What the question named.
        call_order: The contact's call order, or ``None``.
        role: The contact's ``ContactRole`` value.
        relationship: The contact's relationship label as stored, or ``None``.
        name: The contact's stored name, or ``None``.

    Returns:
        ``True`` when the order, a role or a word (also without a final «s») matches. An empty
        selector selects every contact.
    """
    return (
        match_score(
            selector, call_order=call_order, role=role, relationship=relationship, name=name
        )
        > 0
    )


def match_score(
    selector: ContactSelector,
    *,
    call_order: int | None,
    role: str,
    relationship: str | None,
    name: str | None,
) -> int:
    """Count how much of a selector one stored contact matches, so the best match wins.

    One point for the call order, one for the role, one per word found in the relationship or the
    name (also without a final «s»). Two people who share a surname both match «canary»; «mi amiga
    canary» then selects the one who is also the friend.

    Args:
        selector: What the question named.
        call_order: The contact's call order, or ``None``.
        role: The contact's ``ContactRole`` value.
        relationship: The contact's relationship label as stored, or ``None``.
        name: The contact's stored name, or ``None``.

    Returns:
        ``0`` for no match; ``1`` for every contact when the selector is empty.
    """
    if selector.is_empty:
        return 1
    stored = set(normalize_spanish(relationship or "").split()) | set(
        normalize_spanish(name or "").split()
    )
    words = sum(1 for word in selector.words if word in stored or word.removesuffix("s") in stored)
    ordered = int(selector.order is not None and selector.order == call_order)
    return ordered + int(role in selector.roles) + words
