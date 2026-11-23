"""The document secret detector (Plan 0088 D-15, ADR 0029 decision 5): codes never enter a document.

``secret_values`` is a grammar of spoken turns; a document is written text, so it gets its own
deterministic guard, pure and with known limits (it is no promise that no code can be read). It
flags:

- a secret word («clave», «contraseña», «código», «pin», «password») followed within four tokens
  by a value: a token of four or more characters holding a digit, or any token of four or more
  characters after «:» or «=»;
- a run of six or more digits standing alone;
- the shape of a card number (13 to 19 digits, spaces or dashes between groups) that passes the
  Luhn check, and the shape of an IBAN.

A manual's «pin 3 del conector», «código de error 5», «E21», a year or «1000 vueltas» pass.
"""

from __future__ import annotations

import re
from typing import Final

from server.secret_values import SECRET_WORDS
from server.text_keys import normalize_spanish

__all__ = ["flags_secret"]

# The spoken guard's words (one definition, `secret_values`) and the written «password».
_SECRET_WORDS: Final = SECRET_WORDS | {"password"}
_LOOKAHEAD: Final = 4
_MIN_DIGIT_VALUE: Final = 4
_MIN_LABELLED_VALUE: Final = 4
_TOKEN: Final = re.compile(r"[:=]|[^\s:=]+")
_LONE_DIGITS: Final = re.compile(r"(?<![\w/.,-])\d{6,}(?![\w/.,-]|[.,]\d)")
_CARD: Final = re.compile(r"(?<![\w-])\d(?:[ -]?\d){12,18}(?![\w-])")
_IBAN: Final = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]){11,30}\b")
_CARD_MIN: Final = 13
_LUHN_BASE: Final = 10
_LUHN_DOUBLE_OVER: Final = 9


def _luhn(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2:
            value *= 2
            if value > _LUHN_DOUBLE_OVER:
                value -= _LUHN_DOUBLE_OVER
        total += value
    return total % _LUHN_BASE == 0


def _labelled_value(tokens: list[str], start: int) -> bool:
    """Whether a value follows the secret word at *start*, within a few tokens."""
    labelled = False
    for token in tokens[start + 1 : start + 1 + _LOOKAHEAD]:
        if token in {":", "="}:
            labelled = True
            continue
        has_digit = any(char.isdigit() for char in token)
        if (has_digit and len(token) >= _MIN_DIGIT_VALUE) or (
            labelled and len(token) >= _MIN_LABELLED_VALUE
        ):
            return True
    return False


def _secret_word_with_value(text: str) -> bool:
    tokens = [normalize_spanish(token) or token for token in _TOKEN.findall(text)]
    return any(
        token in _SECRET_WORDS and _labelled_value(tokens, index)
        for index, token in enumerate(tokens)
    )


def _card_number(text: str) -> bool:
    for match in _CARD.finditer(text):
        digits = re.sub(r"\D", "", match.group())
        if len(digits) >= _CARD_MIN and _luhn(digits):
            return True
    return False


def flags_secret(text: str) -> bool:
    """Whether *text* holds a code, a key or an account number in one of the closed shapes.

    Args:
        text: A document's text, a section, a camera reading or a reply.

    Returns:
        ``True`` when any shape matches; the text is never logged.
    """
    return bool(
        _secret_word_with_value(text)
        or _LONE_DIGITS.search(text)
        or _card_number(text)
        or _IBAN.search(text)
    )
