"""Recall cues and the relatives question: a closed grammar, no model (ADR 0028, Plan 0078).

A message is a recall question only when it is a question («?», or it opens with an
interrogative or a cue word once its fillers are dropped) and it carries a cue (Plan 0078 D-1).
A **strong** cue asks about what the owner told or did; a **weak** one may be memory or general
knowledge. «me acuerdo», «no me acuerdo» and «recuerdo que» are never cues, so a story never
becomes a search. A cue with neither a date nor a content word after it is no recall question:
«¿qué te conté?» stays the profile summary.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from server.cognition.household_request import (
    has_question_mark,
    opens_with,
    without_leading_fillers,
)
from server.cognition.spoken_dates import DayWindow, parse_spoken_window, strip_window_words
from server.text_keys import normalize_spanish

if TYPE_CHECKING:
    from datetime import date

__all__ = [
    "CueStrength",
    "RecallCue",
    "classify_recall_cue",
    "content_words",
    "relation_of",
]

# Longest first, so «como te dije» is removed whole before «te dije».
_STRONG_PHRASES: Final = (
    "te habia contado",
    "te habia dicho",
    "como te dije",
    "que hicimos",
    "te comente",
    "que hice",
    "te conte",
    "te dije",
    # What the speech-to-text wrote for «te conté» / «te dije» on Pipec's hardware run
    # (2026-11-03). Ungrammatical in Spanish, so no story says them.
    "se conte",
    "se dije",
)
_WEAK_PHRASES: Final = ("te recuerdas", "te acuerdas", "te acordai", "recuerdas", "acuerdate")
_INTERROGATIVES: Final = frozenset(
    {"que", "cual", "cuales", "quien", "quienes", "cuando", "como", "donde", "cuanto", "cuantos"}
)
# Not searched: articles, prepositions, pronouns and possessives, links, fillers and the
# interrogatives. Everything else in the query is a content word (Plan 0078 Tasks 6 and 7).
_STOP_WORDS: Final = frozenset(
    {
        "el", "la", "los", "las", "un", "una", "unos", "unas", "lo",
        "a", "al", "ante", "con", "contra", "de", "del", "desde", "en", "entre", "hacia",
        "hasta", "para", "por", "segun", "sin", "sobre", "tras",
        "yo", "tu", "ella", "ellos", "ellas", "nosotros", "ustedes", "usted", "me", "te", "se",
        "nos", "le", "les", "mi", "mis", "tus", "su", "sus", "nuestro", "nuestra",
        "que", "algo", "eso", "esto", "esa", "ese", "aquello", "y", "o", "ni", "si", "no",
        "muy", "mas", "ya", "es", "fue", "era", "algun", "alguna", "alguien", "nada", "todo",
        "iroko", "oye", "hola", "bueno", "po", "pues", "cachai", "ah", "eh",
        *_INTERROGATIVES,
    }
)  # fmt: skip
# The relatives question (Plan 0078 D-9): its shapes, and the words naming each relation.
_RELATIVE_SHAPES: Final = (
    "como se llama mi",
    "como se llaman mis",
    "quien es mi",
    "quienes son mis",
    # What the speech-to-text wrote on Pipec's hardware run (2026-11-03): an inserted «a», a
    # dropped «n». Ungrammatical, so they catch no story.
    "como se llama a mi",
    "como se llama a mis",
    "como se llaman a mis",
    "como se llama mis",
)
_RELATION_WORDS: Final[dict[str, str]] = {
    **dict.fromkeys(("mama", "papa", "papas", "padres", "madre", "padre"), "has_parent"),
    **dict.fromkeys(("hermano", "hermana", "hermanos", "hermanas"), "has_sibling"),
    **dict.fromkeys(("abuelo", "abuela", "abuelos"), "has_grandparent"),
    **dict.fromkeys(("nieto", "nieta", "nietos", "nietas"), "has_grandchild"),
    **dict.fromkeys(("pareja", "esposa", "esposo", "marido", "senora"), "partner_of"),
    **dict.fromkeys(
        (
            "mascota",
            "mascotas",
            "perro",
            "perra",
            "perrito",
            "perrita",
            "gato",
            "gata",
            "gatito",
            "gatita",
        ),
        "pet_of",
    ),
}


class CueStrength(StrEnum):
    """How surely a recall cue asks about what the owner told."""

    STRONG = "strong"
    WEAK = "weak"


@dataclass(frozen=True)
class RecallCue:
    """A recall question.

    Attributes:
        strength: Whether it asks about what the owner told (strong) or may be general (weak).
        query: The folded message without its fillers, cue words and date words.
        window: The local days it names, or ``None``.
    """

    strength: CueStrength
    query: str
    window: DayWindow | None


def _has(padded: str, phrase: str) -> bool:
    return f" {phrase} " in padded


def _strength(normalized: str) -> CueStrength | None:
    padded = f" {normalized} "
    if any(_has(padded, phrase) for phrase in _STRONG_PHRASES):
        return CueStrength.STRONG
    if any(_has(padded, phrase) for phrase in _WEAK_PHRASES):
        return CueStrength.WEAK
    return None


def _is_question(message: str, normalized: str) -> bool:
    if has_question_mark(message):
        return True
    return any(
        opens_with(normalized, opener)
        for opener in (*_INTERROGATIVES, *_STRONG_PHRASES, *_WEAK_PHRASES)
    )


def _without_cues(normalized: str) -> str:
    padded = f" {normalized} "
    for phrase in (*_STRONG_PHRASES, *_WEAK_PHRASES):
        padded = padded.replace(f" {phrase} ", " ")
    return " ".join(padded.split())


def content_words(query: str) -> tuple[str, ...]:
    """Return the words of *query* worth searching, without stop words or repeats, in order."""
    seen: dict[str, None] = {}
    for word in query.split():
        if word not in _STOP_WORDS:
            seen.setdefault(word, None)
    return tuple(seen)


def classify_recall_cue(message: str, *, today: date) -> RecallCue | None:
    """Return the recall question *message* asks, or ``None`` when it asks none.

    Args:
        message: Raw transcript or chat text in Spanish.
        today: The household's local date, for the date window.

    Returns:
        The cue, or ``None`` for a statement, a message without a cue, or a cue with neither a
        date nor a content word after it.
    """
    normalized = normalize_spanish(message)
    strength = _strength(normalized)
    if strength is None or not _is_question(message, normalized):
        return None
    window = parse_spoken_window(normalized, today)
    query = without_leading_fillers(strip_window_words(_without_cues(normalized)))
    if window is None and not content_words(query):
        return None
    return RecallCue(strength=strength, query=query, window=window)


def relation_of(message: str) -> str | None:
    """Return the predicate a «¿cómo se llama mi mamá?» question asks about, or ``None``.

    Args:
        message: Raw transcript or chat text in Spanish.

    Returns:
        ``has_parent``, ``has_sibling``, ``has_grandparent``, ``has_grandchild``,
        ``partner_of`` or ``pet_of``; ``None`` for anything else (the children keep their own
        route).
    """
    padded = f" {normalize_spanish(message)} "
    for shape in _RELATIVE_SHAPES:
        for word, predicate in _RELATION_WORDS.items():
            if f" {shape} {word} " in padded:
                return predicate
    return None
