"""A cheap, deterministic "is this reply Spanish?" check for the streaming evaluator.

Plan 0059 saw one reply in French although the transcript was Spanish and no contract asked
for Spanish. The measurement needs a count, not a classifier: this compares how many tokens of
a reply are very frequent Spanish words against French and English ones. It is a heuristic with
a documented limit (a reply made only of proper nouns or numbers, or one that is too short, is
*undetermined*, never a verdict), and it never stores or prints the reply.
"""

from __future__ import annotations

import re

_MIN_TOKENS = 4
_TOKEN = re.compile(r"[^\W\d_]+")

# Frequent words that belong to ONE of the three languages. A word that two of them share is
# left out of every list, so a hit is evidence for one language only: `que`, `tu`, `te`, `un`,
# `y`, `se`, `son`, `es`, `bien`, `he`, `has`, `me`, `no`, `de`, `la`, `en`, `a` are all absent
# on purpose. A French sentence full of those words must not be counted as Spanish.
_SPANISH = frozenset(
    {
        "el", "los", "las", "una", "unos", "unas", "del", "al", "lo", "mi", "mis", "su", "sus",
        "muy", "más", "pero", "porque", "con", "para", "por", "está", "están", "estoy", "estás",
        "soy", "eres", "somos", "hay", "ser", "tengo", "tienes", "tiene", "quiero", "quieres",
        "puedo", "puedes", "dijiste", "dije", "cuando", "donde", "dónde", "cómo", "qué", "cuál",
        "cuáles", "cuándo", "algo", "nada", "todo", "siempre", "nunca", "mucho", "poco",
        "también", "aquí", "ahora", "todavía", "otra", "vez", "decir", "claro", "gracias",
        "hola", "sí", "necesites", "buena", "idea", "ayudarte", "favorito", "número", "mañana",
        "noche", "hoy", "ayer", "casa", "recuerdo", "dime", "sabes", "gusta",
    }
)  # fmt: skip
_FRENCH = frozenset(
    {
        "le", "les", "des", "une", "est", "sont", "et", "je", "vous", "nous", "ils", "elle",
        "pas", "pour", "avec", "dans", "sur", "votre", "vos", "mon", "ma", "mes", "ce", "cette",
        "ces", "qui", "quoi", "très", "plus", "sûr", "suis", "ici", "aider", "dit", "dis",
        "dites", "besoin", "avez", "ai", "merci", "bonjour", "oui", "aussi", "mais", "ne", "du",
        "au", "aux", "veux", "veut", "peux", "peut", "fait", "ton", "ta", "tes", "as", "aimais",
        "aime", "sucre", "rendez", "demain", "heures", "neuf", "problème", "réfléchir", "j",
        "qu", "c", "l", "puis", "alors", "voudrais", "comprends", "souviens",
    }
)  # fmt: skip
_ENGLISH = frozenset(
    {
        "the", "and", "is", "are", "you", "your", "i", "am", "with", "this", "that", "what",
        "for", "it", "of", "to", "in", "do", "not", "could", "would", "help", "tell", "again",
        "yet", "remember", "course", "happy", "number", "favorite", "said", "have", "can", "she",
        "we", "they", "them", "was", "were", "will", "be", "been", "there", "here", "where",
        "when", "who", "how", "my", "its", "an", "or", "but", "if", "so", "because", "about",
    }
)  # fmt: skip


def judge_language(text: str) -> bool | None:
    """Judge whether a reply is written in Spanish.

    Args:
        text: The reply, as spoken.

    Returns:
        ``True`` when Spanish words clearly outnumber French and English ones, ``False`` when
        another language does, and ``None`` when the reply is too short to say (fewer than four
        words) or the evidence is a tie.
    """
    tokens = _TOKEN.findall(text.lower())
    if len(tokens) < _MIN_TOKENS:
        return None
    spanish = sum(token in _SPANISH for token in tokens)
    other = max(
        sum(token in _FRENCH for token in tokens),
        sum(token in _ENGLISH for token in tokens),
    )
    if spanish == other:
        return None
    return spanish > other
