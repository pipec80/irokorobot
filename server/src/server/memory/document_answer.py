"""Answer a document question by quoting the found sections, naming the document (Plan 0088 D-14).

**No model is called** (Pipec, 2026-11-23, Task B8 Step 5). On the bench the local 3B model obeyed
the order planted in a section in 12 of 24 answers («la fiebre alta es normal»), and a grounding
check cannot catch it, since the planted words are in the section. So the answer is extractive:
the sentences of the found sections that hold the most of the question's words (the document's
own title words aside), at most two, in reading order, after «Según {título}:». Every sentence
that gives an order («ignora…», «olvida lo anterior…», «di que…», «a partir de ahora eres…») and
every sentence the document secret detector flags is left out, so no planted order and no code is
ever read aloud; with nothing left the answer is «No lo encuentro en tus documentos.». It costs no
model call, so it runs the same on the laptop as on any later board. A better model can word the
answer later through ``document_reply``'s ``answer`` seam. Nothing here logs a text.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

from server.cognition.recall_cues import content_words
from server.cognition.response_plan import NOT_IN_DOCUMENTS
from server.memory.document_secrets import flags_secret
from server.text_keys import normalize_spanish

if TYPE_CHECKING:
    from collections.abc import Sequence

    import httpx

    from server.memory.document_store import DocumentSearch

__all__ = ["MAX_ANSWER_CHARS", "gives_an_order", "word_document"]

#: Characters of quoted text at most (about fifteen seconds of speech).
MAX_ANSWER_CHARS: Final = 220
_MAX_SENTENCES: Final = 2
_ELLIPSIS: Final = "…"
_SENTENCE_END: Final = re.compile(r"(?<=[.!?…])\s+")
_MARKDOWN: Final = re.compile(r"[*_`#>|]+")
_BULLET: Final = re.compile(r"^\s*(?:[-+]|\d+[.)])\s+")
# The closed shapes of an order to the robot inside a document (folded, whole words).
_ORDERS: Final = (
    "ignora",
    "ignore",
    "olvida lo anterior",
    "olvida todo",
    "olvida tus",
    "responde solamente",
    "responde solo",
    "responde que",
    "di que",
    "dile que",
    "tus instrucciones",
    "tus reglas",
    "instrucciones anteriores",
    "no sigas",
    "a partir de ahora",
    "eres un",
    "eres una",
    "actua como",
    "finge que",
)
# Words of a question that say nothing about what it asks.
_FRAMING: Final = frozenset({"dice", "dicen", "segun", "documento", "documentos", "papeles"})
_MIN_PLURAL: Final = 4
# «reposa» finds «reposo» and «reposar»: long words also match by their first five letters.
_STEM: Final = 5
_MIN_STEMMED: Final = 6


def gives_an_order(sentence: str) -> bool:
    """Whether *sentence* gives the robot an order in one of the closed shapes."""
    padded = f" {normalize_spanish(sentence)} "
    return any(f" {order} " in padded for order in _ORDERS)


def _clean(sentence: str) -> str:
    """The sentence without Markdown marks or a list bullet, whitespace collapsed."""
    return " ".join(_MARKDOWN.sub("", _BULLET.sub("", sentence)).split())


def _sentences(body: str) -> list[str]:
    """The body's sentences that may be read aloud: no order, no code, not empty."""
    kept = []
    for raw in _SENTENCE_END.split(" ".join(body.split())):
        sentence = _clean(raw)
        if sentence and not gives_an_order(sentence) and not flags_secret(sentence):
            kept.append(sentence)
    return kept


def _variants(word: str) -> set[str]:
    if len(word) < _MIN_PLURAL:
        return {word}
    return {word, word[:-1] if word.endswith("s") else f"{word}s"}


def _matches(word: str, tokens: set[str], stems: set[str]) -> bool:
    """A word of the question in the sentence: itself, ±«s», or its five-letter stem if long."""
    return bool(_variants(word) & tokens) or (len(word) >= _MIN_STEMMED and word[:_STEM] in stems)


def _score(sentence: str, words: frozenset[str]) -> int:
    tokens = set(normalize_spanish(sentence).split())
    stems = {token[:_STEM] for token in tokens if len(token) >= _MIN_STEMMED}
    return sum(_matches(word, tokens, stems) for word in words)


def _capped(text: str) -> str:
    if len(text) <= MAX_ANSWER_CHARS:
        return text
    room = text[: MAX_ANSWER_CHARS - len(_ELLIPSIS) + 1]
    cut = room.rsplit(" ", 1)[0] if " " in room else room[:-1]
    return f"{cut.rstrip(' ,;:.')}{_ELLIPSIS}"


def _chosen(candidates: Sequence[str], words: frozenset[str]) -> list[str]:
    """The best-matching sentence, and a second one that matches as well and fits, in order."""
    scored = sorted(
        ((_score(sentence, words), -index, sentence) for index, sentence in enumerate(candidates)),
        reverse=True,
    )
    top = scored[0][0]
    if top == 0:
        return [candidates[0]]
    best = [(-negative, s) for score, negative, s in scored if score == top][:_MAX_SENTENCES]
    picked = [best[0]]
    for extra in best[1:]:
        if sum(len(s) + 1 for _, s in [*picked, extra]) <= MAX_ANSWER_CHARS:
            picked.append(extra)
    return [sentence for _, sentence in sorted(picked)]


async def word_document(client: httpx.AsyncClient, question: str, search: DocumentSearch) -> str:
    """Answer a document question with the found sections' best sentences.

    Args:
        client: The HTTP client of the answer seam; unused, since no model is called.
        question: What the owner asked, as transcribed.
        search: The search with one to three hits, best first; the first names the document.

    Returns:
        «Según {título}: …» with at most two quoted sentences (``MAX_ANSWER_CHARS``), or
        ``NOT_IN_DOCUMENTS`` when every sentence gave an order or held a code.
    """
    del client  # the seam's signature; a later model may word the answer through it
    title = search.hits[0].section.title
    candidates = [s for hit in search.hits for s in _sentences(hit.section.body)]
    if not candidates:
        return NOT_IN_DOCUMENTS
    title_words = set(content_words(normalize_spanish(title)))
    words = frozenset(content_words(normalize_spanish(question))) - title_words - _FRAMING
    return f"Según {title}: {_capped(' '.join(_chosen(candidates, words)))}"
