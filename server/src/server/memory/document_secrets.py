"""The document secret detector (Plan 0088 D-15, ADR 0029 decision 5): codes never enter a document.

``secret_values`` is a grammar of spoken turns; a document is written text, so it gets its own
deterministic guard, pure and with known limits (it is no promise that no code can be read). It
flags:

- a secret word («clave», «contraseña», «pin», «puk», «token», «password», or «código de
  acceso / de seguridad / secreto») followed, within eight words («:» and «=» not counted), by a
  value: a token of four or more characters holding a digit, or any token of four or more
  characters after «:» or «=»; or a value right before «es mi clave» (the reversed order);
- a plain «código» (of an error, of a product) only with four or more digits in a row;
- the shape of a card number (13 to 19 digits) that passes the Luhn check, written in groups or
  with a card word («tarjeta», «visa»…) right before it, and the shape of an IBAN.

A lone run of digits is not flagged: on a real medical text (Plan 0088 B10) record and episode
numbers made 89 of 128 sections «secret», so a code needs its secret word.

A manual's «pin 3 del conector», «código de error E-21», «código de producto ABC123», «E21»,
a year, «1000 vueltas», a service phone or a record number pass. A code with no secret word
near it is not caught: a known limit of a deterministic guard.
"""

from __future__ import annotations

import re
from typing import Final

from server.secret_values import SECRET_WORDS
from server.text_keys import normalize_spanish

__all__ = ["flags_secret"]

# The spoken guard's words (one definition, `secret_values`) and the written ones.
_SECRET_WORDS: Final = (SECRET_WORDS - {"codigo", "codigos"}) | {"password", "puk", "token"}
_CODE_WORDS: Final = frozenset({"codigo", "codigos"})
# «código» is a secret word only in these shapes; otherwise it is an error or a product code.
_SECRET_CODE_NEXT: Final = (("de", "acceso"), ("de", "seguridad"), ("secreto",))
_CARD_WORDS: Final = frozenset(
    {"tarjeta", "visa", "mastercard", "amex", "credito", "debito", "redcompra"}
)
_CARD_LOOKBEHIND: Final = 4
_SEPARATORS: Final = frozenset({":", "="})
_LOOKAHEAD: Final = 8
# «1234 es mi clave»: a value and a copula or article in the three words before the secret word.
_LOOKBEHIND: Final = 3
_VALUE_AND_COPULA: Final = 2
_COPULA_WORDS: Final = frozenset({"es", "mi", "la", "tu", "su"})
_MIN_VALUE: Final = 4
_CODE_DIGITS: Final = re.compile(r"\d{4,}")
_TOKEN: Final = re.compile(r"[:=]|[^\s:=]+")
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


def _folded(text: str) -> list[str]:
    """The tokens of *text*, each folded into one word («E-21» is «e21»); separators kept."""
    return [
        token if token in _SEPARATORS else normalize_spanish(token).replace(" ", "")
        for token in _TOKEN.findall(text)
    ]


def _is_value(token: str, *, labelled: bool) -> bool:
    has_digit = any(char.isdigit() for char in token)
    return len(token) >= _MIN_VALUE and (has_digit or labelled)


def _value_after(tokens: list[str], start: int) -> bool:
    """Whether a value follows the secret word at *start* within ``_LOOKAHEAD`` words."""
    labelled, seen = False, 0
    for token in tokens[start + 1 :]:
        if token in _SEPARATORS:
            labelled = True
            continue
        if _is_value(token, labelled=labelled):
            return True
        seen += 1
        if seen == _LOOKAHEAD:
            break
    return False


def _value_before(tokens: list[str], index: int) -> bool:
    """«1234 es mi clave»: a value right before «es» and the secret word (or its article)."""
    before = [t for t in tokens[max(0, index - _LOOKBEHIND) : index] if t not in _SEPARATORS]
    return (
        len(before) >= _VALUE_AND_COPULA
        and before[-1] in _COPULA_WORDS
        and any(_is_value(t, labelled=False) for t in before[:-1])
    )


def _is_secret_code(tokens: list[str], index: int) -> bool:
    following = tuple(tokens[index + 1 : index + 3])
    return any(following[: len(shape)] == shape for shape in _SECRET_CODE_NEXT)


def _secret_word_with_value(text: str) -> bool:
    tokens = _folded(text)
    for index, token in enumerate(tokens):
        if token in _CODE_WORDS and not _is_secret_code(tokens, index):
            window = tokens[index + 1 : index + 1 + _LOOKAHEAD]
            if any(_CODE_DIGITS.search(t) for t in window):
                return True
        elif (token in _SECRET_WORDS or token in _CODE_WORDS) and (
            _value_after(tokens, index) or _value_before(tokens, index)
        ):
            return True
    return False


def _card_number(text: str) -> bool:
    """A Luhn-valid 13-19 digit run, grouped («4111 1111 …») or after a card word."""
    for match in _CARD.finditer(text):
        digits = re.sub(r"\D", "", match.group())
        if len(digits) < _CARD_MIN or not _luhn(digits):
            continue
        before = _folded(text[: match.start()])[-_CARD_LOOKBEHIND:]
        if digits != match.group() or _CARD_WORDS & set(before):
            return True
    return False


def flags_secret(text: str) -> bool:
    """Whether *text* holds a code, a key or an account number in one of the closed shapes.

    Args:
        text: A document's text, a section, a camera reading or a reply.

    Returns:
        ``True`` when any shape matches; the text is never logged.
    """
    return _secret_word_with_value(text) or _card_number(text) or bool(_IBAN.search(text))
