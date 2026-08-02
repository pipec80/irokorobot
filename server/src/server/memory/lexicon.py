"""Spanish lexicon constants for memory retrieval.

Stopwords keep greetings from firing entity lookups; relation triggers map
possessive questions ("mis hijos", "mi mascota") to the canonical predicate
that answers them via reverse fact lookup (see memory/relations.py).
"""

from __future__ import annotations

import re

# Common Spanish conversation words (4+ chars) that are never entity names.
# Without this filter every greeting fires LIKE queries against `entities`.
STOPWORDS_ES = frozenset(
    {
        "ahora",
        "algo",
        "alguien",
        "aquí",
        "bien",
        "bueno",
        "buenas",
        "buenos",
        "cada",
        "casa",
        "como",
        "cómo",
        "cual",
        "cuál",
        "cuales",
        "cuáles",
        "cuando",
        "cuándo",
        "cuanto",
        "cuánto",
        "decime",
        "desde",
        "días",
        "dias",
        "dime",
        "donde",
        "dónde",
        "entonces",
        "eres",
        "esta",
        "está",
        "estas",
        "estás",
        "este",
        "esto",
        "favor",
        "gracias",
        "hace",
        "hacer",
        "hasta",
        "hola",
        "llama",
        "llaman",
        "llamas",
        "llamo",
        "mucho",
        "nada",
        "noches",
        "para",
        "pero",
        "podes",
        "podés",
        "porque",
        "puedes",
        "quien",
        "quién",
        "quiero",
        "robot",
        "sabes",
        "sabés",
        "siempre",
        "sobre",
        "también",
        "tambien",
        "tarde",
        "tardes",
        "tenes",
        "tenés",
        "tengo",
        "tiene",
        "tienes",
        "todavía",
        "todo",
        "todos",
    }
)

# Relation words → canonical predicate answered by reverse fact lookup.
# "¿cómo se llaman mis hijos?" names no child, so forward name-lookup fails;
# the answer lives in facts with predicate hijo_de.
RELATION_TRIGGERS: dict[str, str] = {
    "hijo": "hijo_de",
    "hijos": "hijo_de",
    "hija": "hijo_de",
    "hijas": "hijo_de",
    "mascota": "mascota_de",
    "mascotas": "mascota_de",
    "perro": "mascota_de",
    "perra": "mascota_de",
    "perros": "mascota_de",
    "gato": "mascota_de",
    "gata": "mascota_de",
    "gatos": "mascota_de",
    "esposa": "pareja_de",
    "esposo": "pareja_de",
    "pareja": "pareja_de",
    "cumpleaños": "fecha_nacimiento",
    "nació": "fecha_nacimiento",
    "nacio": "fecha_nacimiento",
    "nací": "fecha_nacimiento",
    "naci": "fecha_nacimiento",
    # "¿cuántos años tengo?" / "¿qué edad tengo?" name no entity either —
    # self-referential age questions resolve via the owner's fecha_nacimiento
    # (found 2026-07-27 during M1: this phrasing returned zero context).
    "años": "fecha_nacimiento",
    "edad": "fecha_nacimiento",
}

_WORD_RE = re.compile(r"[a-záéíóúüñ]+")


def predicates_in(text: str) -> set[str]:
    """Return the canonical predicates triggered by relation words in *text*.

    Matches whole words only ("regata" does not trigger "gata").

    Args:
        text: Raw user input text.

    Returns:
        Set of canonical predicate names (possibly empty).
    """
    words = set(_WORD_RE.findall(text.casefold()))
    return {pred for word, pred in RELATION_TRIGGERS.items() if word in words}
