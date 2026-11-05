"""Tell whether a Spanish message states or asks for a secret value (Plan 0079 D-2).

A password, PIN or code is never stored nor repeated (ADR 0029). This module only decides, from the
words, whether a message *states* a value («mi clave es 1234») or *asks* for one («¿cuál es mi
clave del banco?»). The grammar is closed on purpose: it errs towards ordinary conversation for
«el código es un desastre» and accepts a few false positives («la clave es que llegues temprano»)
and one miss («1234 es mi clave»). It lives at the top of ``server`` so both ``cognition`` and
``memory`` may import it, and it logs nothing: a text never reaches a log line.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from server.text_keys import normalize_spanish

__all__ = ["SECRET_WORDS", "SecretKind", "secret_kind"]

#: Folded secret words (``normalize_spanish``), matched as whole words.
SECRET_WORDS: Final[frozenset[str]] = frozenset(
    {"clave", "claves", "contrasena", "contrasenas", "codigo", "codigos", "pin"}
)

# Only these may be followed by a copula and a value: «la clave es X». «El código es un desastre»
# and «mi código es en python» are ordinary turns of a developer.
_COPULA_SECRET_WORDS: Final[frozenset[str]] = frozenset(
    {"clave", "claves", "contrasena", "contrasenas"}
)
_COPULAS: Final[frozenset[str]] = frozenset({"es", "son", "era"})
_NUMBER_WORDS: Final[frozenset[str]] = frozenset(
    {
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
        "diez",
        "once",
        "doce",
        "trece",
        "catorce",
        "quince",
        "dieciseis",
        "diecisiete",
        "dieciocho",
        "diecinueve",
        "veinte",
        "veintiuno",
        "veintidos",
        "veintitres",
        "veinticuatro",
        "veinticinco",
        "veintiseis",
        "veintisiete",
        "veintiocho",
        "veintinueve",
        "treinta",
        "cuarenta",
        "cincuenta",
        "sesenta",
        "setenta",
        "ochenta",
        "noventa",
        "cien",
        "ciento",
        "doscientos",
        "trescientos",
        "cuatrocientos",
        "quinientos",
        "seiscientos",
        "setecientos",
        "ochocientos",
        "novecientos",
        "mil",
    }
)
# How many tokens after a secret word may carry its value.
_VALUE_WINDOW: Final[int] = 6

# «cual es mi clave»: openers with «mi» ask for any secret word; with «la»/«el» only when the
# secret word names an object («la clave del banco»), so «¿cuál es la clave del éxito?» is ordinary.
_ASK_OPENERS: Final[tuple[tuple[str, ...], ...]] = (
    ("cual", "es"),
    ("cual", "era"),
    ("dime",),
    ("me", "dices"),
    ("me", "recuerdas"),
    ("recuerdame",),
)
_OWN_DETERMINER: Final[str] = "mi"
_OBJECT_DETERMINERS: Final[tuple[str, ...]] = ("la", "el")
_OBJECT_LINKS: Final[tuple[tuple[str, ...], ...]] = (("del",), ("de", "la"))
_OBJECT_WORDS: Final[frozenset[str]] = frozenset(
    {
        "banco",
        "tarjeta",
        "cuenta",
        "cajero",
        "wifi",
        "alarma",
        "correo",
        "celular",
        "telefono",
        "computador",
        "casa",
        "porton",
    }
)


class SecretKind(StrEnum):
    """What a message does with a secret value."""

    STATED = "stated"
    ASKED = "asked"


def secret_kind(message: str) -> SecretKind | None:
    """Return whether *message* states or asks for a secret value.

    Pure and deterministic; the message is folded (lower case, no accents, no punctuation) and
    matched by whole words. A message that both states and asks is ``STATED``.

    Args:
        message: Raw transcript or chat text.

    Returns:
        ``SecretKind.STATED`` when a value follows a secret word, ``SecretKind.ASKED`` when the
        message asks for one in the closed grammar, ``None`` for an ordinary turn.
    """
    tokens = tuple(normalize_spanish(message).split())
    if _states_a_value(tokens):
        return SecretKind.STATED
    if _asks_for_a_value(tokens):
        return SecretKind.ASKED
    return None


def _starts_with(tokens: tuple[str, ...], start: int, phrase: tuple[str, ...]) -> bool:
    return tokens[start : start + len(phrase)] == phrase


def _is_value_token(token: str) -> bool:
    return any(character.isdigit() for character in token) or token in _NUMBER_WORDS


def _states_a_value(tokens: tuple[str, ...]) -> bool:
    for index, token in enumerate(tokens):
        if token not in SECRET_WORDS:
            continue
        window = tokens[index + 1 : index + 1 + _VALUE_WINDOW]
        if any(_is_value_token(word) for word in window):
            return True
        if token not in _COPULA_SECRET_WORDS:
            continue
        for offset, word in enumerate(window):
            # «es» then at least one more word, which may sit past the window.
            if word in _COPULAS and index + 2 + offset < len(tokens):
                return True
    return False


def _asks_for_a_value(tokens: tuple[str, ...]) -> bool:
    return any(
        _asks_at(tokens, start) or _asks_what_i_have(tokens, start) for start in range(len(tokens))
    )


def _asks_what_i_have(tokens: tuple[str, ...], start: int) -> bool:
    # «que clave tengo»
    return (
        tokens[start] == "que"
        and start + 2 < len(tokens)
        and tokens[start + 1] in SECRET_WORDS
        and tokens[start + 2] == "tengo"
    )


def _asks_at(tokens: tuple[str, ...], start: int) -> bool:
    for opener in _ASK_OPENERS:
        if not _starts_with(tokens, start, opener):
            continue
        after = start + len(opener)
        if after + 1 >= len(tokens):
            continue
        determiner, word = tokens[after], tokens[after + 1]
        if word not in SECRET_WORDS:
            continue
        if determiner == _OWN_DETERMINER:
            return True
        if determiner in _OBJECT_DETERMINERS and _names_an_object(tokens, after + 2):
            return True
    return False


def _names_an_object(tokens: tuple[str, ...], start: int) -> bool:
    """Return whether «del» or «de la» and an object word sit at *start* («del banco»)."""
    for link in _OBJECT_LINKS:
        if _starts_with(tokens, start, link):
            after = start + len(link)
            return after < len(tokens) and tokens[after] in _OBJECT_WORDS
    return False
