"""The closed grammar of changing a memory by voice (Plan 0086 D-4, ADR 0032 decisions 3 and 4).

Pure: no store, no model. Two kinds, each a closed list of Spanish forms matched on the folded
words (case, accents and punctuation folded as the preference gate does):

* **correct** a taste: «ya no me gusta(n) X», «ya no me encanta(n) X», «ya no prefiero X»,
  «ya no odio X», «ya no detesto X», «ya no soporto X», at the start of the message (after an
  opening «me equivoqué» or a greeting), optionally followed by «ahora me gusta(n) Y» or
  «ahora prefiero Y»;
* **archive**: «no quiero saber (nunca) más de X», «no me hables más de X», «no me recuerdes más
  (a | lo de | nada de) X», «olvídate de X», anywhere in the message, so a reason may come first
  («mi mejor amiga Canaria me traicionó; no quiero saber nunca más de ella»).

A pronoun as the archive target (``ella``, ``él``, ``ellos``, ``ellas``) names the one name of the
same message that follows a person word («mi mejor amiga Canaria»); none or two: no match. A
question, a conditional, a third person and a clause as the object never match: they are
ordinary conversation. The targets keep the words as said (their accents and case), so the
read-back speaks them right.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Final, Literal

from server.text_keys import ARTICLES, GREETING_WORDS, PERSON_WORDS, normalize_spanish

__all__ = ["MemoryChange", "parse_memory_change"]

type ChangeKind = Literal["correct", "archive"]

_MAX_TARGET_WORDS: Final = 6
_WORD: Final = re.compile(r"\w+")

# Folded word sequences → the predicate a correction closes.
_CORRECTIONS: Final[tuple[tuple[tuple[str, ...], str], ...]] = (
    (("ya", "no", "me", "gusta"), "likes"),
    (("ya", "no", "me", "gustan"), "likes"),
    (("ya", "no", "me", "encanta"), "likes"),
    (("ya", "no", "me", "encantan"), "likes"),
    (("ya", "no", "prefiero"), "prefers"),
    (("ya", "no", "odio"), "dislikes"),
    (("ya", "no", "detesto"), "dislikes"),
    (("ya", "no", "soporto"), "dislikes"),
)
_REPLACEMENTS: Final[tuple[tuple[tuple[str, ...], str], ...]] = (
    (("ahora", "me", "gusta"), "likes"),
    (("ahora", "me", "gustan"), "likes"),
    (("ahora", "me", "encanta"), "likes"),
    (("ahora", "me", "encantan"), "likes"),
    (("ahora", "prefiero"), "prefers"),
)
_REPLACEMENT_LEADS: Final = frozenset({"y", "pero"})
_OPENERS: Final[tuple[tuple[str, ...], ...]] = (("me", "equivoque"), ("es", "que"))
_ARCHIVES: Final[tuple[tuple[str, ...], ...]] = (
    ("no", "quiero", "saber", "nunca", "mas", "de"),
    ("no", "quiero", "saber", "nada", "mas", "de"),
    ("no", "quiero", "saber", "mas", "de"),
    ("no", "quiero", "saber", "nada", "de"),
    ("no", "me", "hables", "nunca", "mas", "de"),
    ("no", "me", "hables", "mas", "de"),
    ("no", "me", "recuerdes", "nunca", "mas"),
    ("no", "me", "recuerdes", "mas"),
    ("olvidate", "de"),
)
# After «no me recuerdes más», these words lead the target and are not part of it.
_ARCHIVE_LEADS: Final[tuple[tuple[str, ...], ...]] = (
    ("nada", "de"),
    ("lo", "de"),
    ("lo", "del"),
    ("a",),
)
_PRONOUNS: Final = frozenset({"ella", "el", "ellos", "ellas"})
_TRAILERS: Final[tuple[tuple[str, ...], ...]] = (
    ("por", "favor"),
    ("porfa",),
    ("po",),
    ("gracias",),
)
# A word that opens a clause, never a thing («ya no me gusta que me hables así»).
_CLAUSE_OPENERS: Final = frozenset({"que", "cuando", "si", "como", "donde", "porque", "aunque"})
# Words that never name a person after a person word («mi amiga de la infancia»).
_NOT_A_NAME: Final = frozenset({"de", "del", "que", "y", "o", "me", "te", "se", "le", "mi", "tu"})


@dataclass(frozen=True)
class MemoryChange:
    """One parsed change: what to correct or set aside, in the owner's own words.

    Attributes:
        kind: ``correct`` (a taste) or ``archive``.
        predicate: The taste a correction closes (``likes``, ``dislikes``, ``prefers``).
        target: The thing or name as said.
        replacement: The new value of a correction, as said, or ``None``.
        replacement_predicate: Its predicate, or ``None``.
    """

    kind: ChangeKind
    predicate: str | None
    target: str
    replacement: str | None
    replacement_predicate: str | None


def _starts(words: list[str], start: int, pattern: tuple[str, ...]) -> bool:
    return tuple(words[start : start + len(pattern)]) == pattern


def _trimmed_end(words: list[str], start: int, end: int) -> int:
    """The end of a target once a courtesy trailer («por favor», «po») is left out."""
    for trailer in _TRAILERS:
        if end - start > len(trailer) and tuple(words[end - len(trailer) : end]) == trailer:
            return end - len(trailer)
    return end


def _span(folded: list[str], said: list[str], start: int, end: int) -> str | None:
    """The target between *start* and *end*, as said, or ``None`` when it is not a thing."""
    end = _trimmed_end(folded, start, end)
    if end <= start or end - start > _MAX_TARGET_WORDS or folded[start] in _CLAUSE_OPENERS:
        return None
    if all(word in ARTICLES for word in folded[start:end]):
        return None
    return " ".join(said[start:end])


def _skip_openers(words: list[str]) -> int:
    """Where the change starts: after greetings and one opening «me equivoqué» or «es que»."""
    start = 0
    while start < len(words) and words[start] in GREETING_WORDS - {"que", "es"}:
        start += 1
    for opener in _OPENERS:
        if _starts(words, start, opener):
            return start + len(opener)
    return start


def _correction(folded: list[str], said: list[str]) -> MemoryChange | None:
    start = _skip_openers(folded)
    for pattern, predicate in _CORRECTIONS:
        if not _starts(folded, start, pattern):
            continue
        first = start + len(pattern)
        for index in range(first, len(folded)):
            for replacement, new_predicate in _REPLACEMENTS:
                if _starts(folded, index, replacement):
                    lead = (
                        index - 1
                        if index > first and folded[index - 1] in _REPLACEMENT_LEADS
                        else index
                    )
                    target = _span(folded, said, first, lead)
                    new = _span(folded, said, index + len(replacement), len(folded))
                    if target is None or new is None:
                        return None
                    return MemoryChange("correct", predicate, target, new, new_predicate)
        target = _span(folded, said, first, len(folded))
        return None if target is None else MemoryChange("correct", predicate, target, None, None)
    return None


def _named_person(folded: list[str], said: list[str]) -> str | None:
    """The one name of the message that follows a person word, as said; else ``None``."""
    names = {
        said[index + 1]
        for index, word in enumerate(folded[:-1])
        if word in PERSON_WORDS and folded[index + 1] not in _NOT_A_NAME | ARTICLES | _PRONOUNS
    }
    return names.pop() if len(names) == 1 else None


def _archive(folded: list[str], said: list[str]) -> MemoryChange | None:
    for index in range(len(folded)):
        for pattern in _ARCHIVES:
            if not _starts(folded, index, pattern):
                continue
            first = index + len(pattern)
            for lead in _ARCHIVE_LEADS:
                if pattern[-1] != "de" and _starts(folded, first, lead):
                    first += len(lead)
                    break
            end = _trimmed_end(folded, first, len(folded))
            if end - first == 1 and folded[first] in _PRONOUNS:
                name = _named_person(folded[:index], said[:index])
                return None if name is None else MemoryChange("archive", None, name, None, None)
            target = _span(folded, said, first, len(folded))
            return None if target is None else MemoryChange("archive", None, target, None, None)
    return None


def parse_memory_change(message: str) -> MemoryChange | None:
    """Parse a spoken correction or archive of a memory, or ``None`` for anything else.

    Args:
        message: The transcript of one turn.

    Returns:
        The change, or ``None`` when the message is not one of the closed forms.
    """
    if "?" in message or "¿" in message:
        return None
    said = _WORD.findall(message)
    folded = normalize_spanish(message).split()
    if len(said) != len(folded) or not folded:
        return None  # a word the folding split or merged: never guess the target's spelling
    return _correction(folded, said) or _archive(folded, said)
