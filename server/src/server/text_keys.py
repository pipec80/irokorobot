"""One comparison for names and values, shared by every package (ADR 0024 decision 12).

A spoken «El Café» and an imported «café» must be one row, and «Joaquín» and «Joaquin» one
person. The folding lives here, at the top of ``server``, so both ``cognition`` and ``memory`` may
import it; it imports neither.
"""

from __future__ import annotations

import re
import unicodedata

__all__ = ["ARTICLES", "comparison_key", "fold_name", "normalize_spanish"]

#: Articles a spoken object may begin with; the comparison key drops them.
ARTICLES = frozenset({"el", "la", "los", "las", "un", "una", "unos", "unas", "lo"})

_NON_WORD_RUN = re.compile(r"[^\w]+", re.UNICODE)


def fold_name(name: str) -> str:
    """Return an accent- and case-insensitive form of *name*, its spaces kept.

    Whisper drops accents unpredictably ("Joaquín" → "Joaquin"); without folding, each variant
    would become a separate entity.

    Args:
        name: A person's, a pet's or a predicate's name.

    Returns:
        The name without combining accents, case-folded.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def normalize_spanish(message: str) -> str:
    """Fold accents/case and collapse punctuation for closed Spanish matching.

    NFD-decomposes, strips combining accents, casefolds, replaces each
    non-word run with one space, then trims — so surrounding punctuation and
    inconsistent whitespace never affect classification. The cognitive core's closed
    grammars and the memory layer's (ADR 0021) fold text the same way through it.

    Args:
        message: Raw transcript or chat text.

    Returns:
        The folded text: lower case, no accents, words separated by single spaces.
    """
    decomposed = unicodedata.normalize("NFD", message)
    stripped = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    ).casefold()
    return _NON_WORD_RUN.sub(" ", stripped).strip()


def comparison_key(phrase: str) -> str:
    """Return the key two phrases are compared by: folded, without a leading article.

    Known limit (pinned by a test): punctuation is dropped, so «C++» and «C#» collide. A caller
    whose key comes out empty compares the phrases exactly instead.

    Args:
        phrase: A spoken or written object ("El Café").

    Returns:
        The folded words without leading articles ("cafe"); empty when nothing remains.
    """
    words = normalize_spanish(phrase).split()
    while words and words[0] in ARTICLES:
        words.pop(0)
    return " ".join(words)
