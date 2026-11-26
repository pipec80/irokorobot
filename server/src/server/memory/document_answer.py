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
import unicodedata

from server.cognition.recall_cues import content_words
from server.cognition.response_plan import NOT_IN_DOCUMENTS
from server.memory.document_secrets import flags_secret
from server.text_keys import normalize_spanish

if TYPE_CHECKING:
    from collections.abc import Sequence

    import httpx

    from server.memory.document_store import DocumentSearch

__all__ = [
    "MAX_ANSWER_CHARS",
    "cap_answer",
    "gives_an_order",
    "readable_sentences",
    "word_document",
]

#: Characters of quoted text at most (about fifteen seconds of speech).
MAX_ANSWER_CHARS: Final = 220
_MAX_SENTENCES: Final = 2
_ELLIPSIS: Final = "…"
_SENTENCE_END: Final = re.compile(r"(?<=[.!?…])\s+")
# A line with no closing mark followed by a line that opens a sentence: a PDF page's heading.
# A line wrapped inside a sentence goes on in lowercase and stays one sentence.
_HEADING_LINE_END: Final = re.compile(r"(?<![.!?…:;,])[ \t]*\n(?=[ \t]*[A-ZÁÉÍÓÚÑ¿¡])")
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
# Stems of the order verbs and «dile(s) … que» (folded), and «di:» / «responde:» (raw).
_ORDER_STEMS: Final = re.compile(
    r" ignor\w*| olvid\w* (?:de )?(?:lo anterior|todo|tus|las instrucciones|las reglas)"
    r"| diles? (?:\w+ ){0,3}que | actu\w* como | fing\w* que "
)
_SPOKEN_ORDER: Final = re.compile(r"(?i)\b(?:di|responde|repite)\s*:")
#: The document's name when its own title gives an order or holds a code.
_UNNAMED: Final = "tu documento"
# Words of a question that say nothing about what it asks.
_FRAMING: Final = frozenset({"dice", "dicen", "segun", "documento", "documentos", "papeles"})
_MIN_PLURAL: Final = 4
# «reposa» finds «reposo» and «reposar»: long words also match by their first five letters.
_STEM: Final = 5
_MIN_STEMMED: Final = 6


def _visible(text: str) -> str:
    """*text* without invisible format characters (a zero-width space splits no word)."""
    return "".join(character for character in text if unicodedata.category(character) != "Cf")


def gives_an_order(sentence: str) -> bool:
    """Whether *sentence* gives the robot an order in one of the closed shapes.

    The closed phrases, their stems («ignórala», «ignorad», «olvídate de tus reglas»), «di:» and
    «dile … que» with up to three words between, after invisible characters are removed.
    """
    visible = _visible(sentence)
    padded = f" {normalize_spanish(visible)} "
    return (
        any(f" {order} " in padded for order in _ORDERS)
        or bool(_ORDER_STEMS.search(padded))
        or bool(_SPOKEN_ORDER.search(visible))
    )


def _clean(sentence: str) -> str:
    """The sentence without Markdown marks or a list bullet, whitespace collapsed."""
    return " ".join(_MARKDOWN.sub("", _BULLET.sub("", sentence)).split())


def readable_sentences(text: str) -> list[str]:
    """The sentences of one line or paragraph that may be read aloud: no order, no code, not empty.

    Also used by the paper's answer (Plan 0090), which cuts a paper line by line first.
    """
    kept = []
    for raw in _SENTENCE_END.split(" ".join(text.split())):
        sentence = _clean(raw)
        if sentence and not gives_an_order(sentence) and not flags_secret(sentence):
            kept.append(sentence)
    return kept


def _sentences(body: str) -> list[str]:
    """A section body's readable sentences, a heading line closed as its own sentence."""
    return readable_sentences(_HEADING_LINE_END.sub(".\n", body))


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


def cap_answer(text: str) -> str:
    """*text* cut at ``MAX_ANSWER_CHARS`` on a word, with an ellipsis when cut."""
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
    first = search.hits[0].section
    title = first.title
    if gives_an_order(title) or flags_secret(title):
        title = _UNNAMED
    # The answer names one document and stays inside it: only that source's sections are quoted.
    candidates = [
        s
        for hit in search.hits
        if hit.section.source_id == first.source_id
        for s in _sentences(hit.section.body)
    ]
    if not candidates:
        return NOT_IN_DOCUMENTS
    title_words = set(content_words(normalize_spanish(first.title)))
    words = frozenset(content_words(normalize_spanish(question))) - title_words - _FRAMING
    return f"Según {title}: {cap_answer(' '.join(_chosen(candidates, words)))}"
