"""Tell whether a Spanish message states, asks for or offers a secret value (Plan 0079 D-2).

A password, PIN or code is never stored nor repeated (ADR 0029). This module only decides, from the
words, whether a message *states* a value («mi clave es 1234»), *asks* for one («¿cuál es mi
clave del banco?») or *offers* to give one («guarda mi contraseña», with no value yet: it must not
invite the value in the next turn). The grammar is closed on purpose: it errs towards ordinary
conversation for «el código es un desastre» and for the Chilean «es clave» (important), and accepts
a few false positives («la clave es que llegues temprano») and one miss («1234 es mi clave»). It
lives at the top of ``server`` so both ``cognition`` and ``memory`` may import it, and it logs
nothing: a text never reaches a log line.
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

# Chilean slang: «es clave», «lo clave», «muy clave» say «important» (ADR 0029 decision 5), so a
# «clave» right after one of these words is no secret word.
_CLAVE_WORDS: Final[frozenset[str]] = frozenset({"clave", "claves"})
# «super» is not listed: «mi super clave es 4821» is a real credential, not slang.
_SLANG_BEFORE_CLAVE: Final[frozenset[str]] = frozenset({"es", "lo", "muy", "tan"})

# «guarda mi clave», «te voy a decir mi pin»: a request to keep a secret with no value yet. The
# opener must open the sentence body and a secret word must follow within two words («guarda mi
# super clave»). «recuerdame» and «me recuerdas» belong to the ask grammar.
_OFFER_OPENERS: Final[tuple[tuple[str, ...], ...]] = (
    ("guarda",),
    ("guardame",),
    ("anota",),
    ("anotame",),
    ("apunta",),
    ("memoriza",),
    ("recuerda",),
    ("te", "voy", "a", "decir"),
    ("te", "voy", "a", "dar"),
    ("te", "voy", "a", "pasar"),
    ("te", "digo"),
)
# A secret word may follow the opener after up to two words: determiner and adjective.
_OFFER_REACH: Final[int] = 3

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
# The own possessive, singular and plural, for asks and offers alike («mis claves»).
_OWN_DETERMINERS: Final[frozenset[str]] = frozenset({"mi", "mis"})
# The developer's words: an offer names them only through the object rule («anota mi codigo»).
_DEVELOPER_WORDS: Final[frozenset[str]] = frozenset({"codigo", "codigos"})
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
    OFFERED = "offered"


def secret_kind(message: str) -> SecretKind | None:
    """Return whether *message* states, asks for or offers a secret value.

    Pure and deterministic; the message is folded (lower case, no accents, no punctuation) and
    matched by whole words. Precedence: ``STATED``, then ``ASKED``, then ``OFFERED``.

    Args:
        message: Raw transcript or chat text.

    Returns:
        ``SecretKind.STATED`` when a value follows a secret word, ``SecretKind.ASKED`` when the
        message asks for one in the closed grammar, ``SecretKind.OFFERED`` when it opens with a
        request to keep a secret and gives no value, ``None`` for an ordinary turn.
    """
    tokens = tuple(normalize_spanish(message).split())
    if _states_a_value(tokens):
        return SecretKind.STATED
    if _asks_for_a_value(tokens):
        return SecretKind.ASKED
    if _offers_a_secret(message):
        return SecretKind.OFFERED
    return None


def _starts_with(tokens: tuple[str, ...], start: int, phrase: tuple[str, ...]) -> bool:
    """Whether *phrase* sits in *tokens* from *start*."""
    return tokens[start : start + len(phrase)] == phrase


def _is_value_token(token: str) -> bool:
    """Whether a token carries a digit or is a number word."""
    return any(character.isdigit() for character in token) or token in _NUMBER_WORDS


def _is_secret_word(tokens: tuple[str, ...], index: int) -> bool:
    """Whether the token at *index* is a secret word, not the slang «es clave» (important)."""
    token = tokens[index]
    if token not in SECRET_WORDS:
        return False
    return not (token in _CLAVE_WORDS and index > 0 and tokens[index - 1] in _SLANG_BEFORE_CLAVE)


def _offers_a_secret(message: str) -> bool:
    """Whether the sentence body opens with an offer opener and a secret word within reach."""
    # Lazy: `server.cognition.__init__` imports `intent_resolution`, which imports this module.
    from server.cognition.household_request import sentence_body  # noqa: PLC0415

    body = sentence_body(message)
    return any(
        _starts_with(body, 0, opener) and _offer_reaches_a_secret(body, len(opener))
        for opener in _OFFER_OPENERS
    )


def _offer_reaches_a_secret(body: tuple[str, ...], start: int) -> bool:
    """Whether a secret word sits within reach of an offer opener that ends before *start*.

    Whatever the article or adjective («la clave», «el pin», «mi super clave»), except for the
    developer's word «codigo»: that one needs the object rule of the ask grammar, so «guarda el
    codigo del proyecto» stays an ordinary turn.
    """
    for index in range(start, min(start + _OFFER_REACH, len(body))):
        if not _is_secret_word(body, index):
            continue
        if body[index] not in _DEVELOPER_WORDS:
            return True
        if index > start and _names_a_secret(body, index - 1):
            return True
    return False


def _names_a_secret(tokens: tuple[str, ...], determiner_index: int) -> bool:
    """Whether a determiner and a secret word sit at *determiner_index* (the object rule).

    An own determiner (``mi``, ``mis``) accepts any secret word; «la» and «el» only before an account
    object («la clave del wifi»), so «el codigo del proyecto» stays a developer's ordinary turn.
    """
    if determiner_index + 1 >= len(tokens) or not _is_secret_word(tokens, determiner_index + 1):
        return False
    determiner = tokens[determiner_index]
    if determiner in _OWN_DETERMINERS:
        return True
    return determiner in _OBJECT_DETERMINERS and _names_an_object(tokens, determiner_index + 2)


def _states_a_value(tokens: tuple[str, ...]) -> bool:
    """Whether a value (digit, number word or «es» + word) follows a secret word."""
    for index, token in enumerate(tokens):
        if not _is_secret_word(tokens, index):
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
    """Whether the closed ask grammar matches anywhere in *tokens*."""
    return any(
        _asks_at(tokens, start) or _asks_what_i_have(tokens, start) for start in range(len(tokens))
    )


def _asks_what_i_have(tokens: tuple[str, ...], start: int) -> bool:
    """Whether «que» + a secret word + «tengo» sits at *start* («que clave tengo»)."""
    return (
        tokens[start] == "que"
        and start + 2 < len(tokens)
        and _is_secret_word(tokens, start + 1)
        and tokens[start + 2] == "tengo"
    )


def _asks_at(tokens: tuple[str, ...], start: int) -> bool:
    """Whether an ask opener, a determiner and a secret word sit at *start*."""
    for opener in _ASK_OPENERS:
        if not _starts_with(tokens, start, opener):
            continue
        if _names_a_secret(tokens, start + len(opener)):
            return True
    return False


def _names_an_object(tokens: tuple[str, ...], start: int) -> bool:
    """Return whether «del» or «de la» and an object word sit at *start* («del banco»)."""
    for link in _OBJECT_LINKS:
        if _starts_with(tokens, start, link):
            after = start + len(link)
            return after < len(tokens) and tokens[after] in _OBJECT_WORDS
    return False
