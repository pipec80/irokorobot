"""Whether a message is about tastes, so the card's tastes may enter the prompt (Plan 0081, D-4).

Pure and deterministic: the 3B model ignored the card's «solo si viene al caso» on hardware, so the
code decides when the owner's tastes reach the model instead of the prompt asking it to. Logs
nothing: a message and a taste are household text.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from server.memory.lexicon import STOPWORDS_ES
from server.text_keys import ARTICLES, normalize_spanish

if TYPE_CHECKING:
    from collections.abc import Sequence

    from server.memory.profile_card import CardTaste

__all__ = ["TASTE_CUE_WORDS", "tastes_are_relevant"]

#: Folded words that make a message taste talk, whatever taste the card holds.
TASTE_CUE_WORDS: Final = frozenset(
    {
        "gusta",
        "gustan",
        "gustaba",
        "gustaria",
        "gusto",
        "gustos",
        "encanta",
        "encantan",
        "prefiero",
        "prefieres",
        "prefiere",
        "favorito",
        "favorita",
        "favoritos",
        "favoritas",
        "recomiendas",
        "recomienda",
        "recomiendes",
        "sugieres",
        "comer",
        "comemos",
        "comida",
        "cenar",
        "cena",
        "almorzar",
        "almuerzo",
        "desayunar",
        "desayuno",
        "beber",
        "musica",
        "cancion",
        "canciones",
        "escuchar",
        "pelicula",
        "peliculas",
        "serie",
        "series",
        "libro",
        "libros",
        "leer",
        "regalo",
        "regalar",
        "panorama",
        "plan",
    }
)
# A shorter taste word («té») folds onto common words («te»): it is reached only through a cue.
_MIN_TASTE_WORD_LETTERS: Final = 4


def _taste_words(tastes: Sequence[CardTaste]) -> frozenset[str]:
    """Return the folded content words of the tastes, without articles, stopwords or short words."""
    return frozenset(
        word
        for taste in tastes
        for word in normalize_spanish(taste.value).split()
        if len(word) >= _MIN_TASTE_WORD_LETTERS and word not in ARTICLES | STOPWORDS_ES
    )


def tastes_are_relevant(message: str, tastes: Sequence[CardTaste]) -> bool:
    """Say whether the card's tastes may enter the prompt of this turn.

    Args:
        message: What the person said this turn.
        tastes: The card's tastes.

    Returns:
        ``True`` when the folded message holds a word of ``TASTE_CUE_WORDS`` or a content word
        (4 letters or more) of one of the tastes; ``False`` otherwise, so a greeting never
        carries a taste.
    """
    words = frozenset(normalize_spanish(message).split())
    return bool(words & TASTE_CUE_WORDS or words & _taste_words(tastes))
