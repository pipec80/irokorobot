"""Answer a closed question about the paper just read, by quoting it (Plan 0090, ADR 0041).

**No model is called**, for the reason of ADR 0034 deviation 9: the local 3B obeyed an order
planted in a document in 12 of 24 answers. The paper is cut into sentences as a document section
is (``document_answer.body_sentences``): a line wrapped inside a sentence stays one sentence, so an
order wrapped over lines is filtered whole, and a bill's label line («Total a pagar») joins the
figure printed under it. Every sentence in the closed shapes of an order, or that the document
secret detector flags, is left out. A closed extractor raises the answering sentence by the
strongest words it holds («vencimiento» before «hasta» before «fecha»; «total» or «pagar» before
«importe»), never a sentence with no such word: a guessed figure is worse than «Eso no aparece en
lo que leí.». The answer is «Según el papel: …», capped like a document answer. Pure: no I/O,
nothing logged.
"""

from __future__ import annotations

import re
from typing import Final

from server.cognition.document_cues import PaperAsk
from server.cognition.response_plan import (
    NOT_IN_PAPER,
    PAPER_ANSWER_OPENING,
    PAPER_NOT_INTERPRETED,
)
from server.memory.document_answer import body_sentences, cap_answer
from server.text_keys import normalize_spanish

__all__ = ["word_paper"]

_AMOUNT: Final = re.compile(r"\$\s?\d|\d[\d.,]*\s*(?:pesos|clp)\b", re.IGNORECASE)
#: The words that name the amount to pay, strongest first; «saldo anterior» names none.
_AMOUNT_WORDS: Final = (("total", "a pagar"), ("importe", "deuda", "monto"))
_MONTHS: Final = "ene|feb|mar|abr|may|jun|jul|ago|sep|set|oct|nov|dic"
_DATE: Final = re.compile(
    rf"\b\d{{1,2}}\s?[-/.]\s?(?:\d{{1,2}}|(?:{_MONTHS})[a-z]*)\s?[-/.]\s?\d{{2,4}}\b"
    rf"|\b\d{{1,2}} de (?:{_MONTHS})[a-z]*(?: de \d{{4}})?\b",
    re.IGNORECASE,
)
#: The words that name the due date, strongest first; an emission date names none.
_DATE_WORDS: Final = (
    ("venc", "pagar antes", "pague antes", "pagar hasta", "plazo"),
    ("hasta",),
    ("fecha",),
)
_NOT_DUE: Final = ("emision", "emitid")
_START_SENTENCES: Final = 2


def _best(
    candidates: list[str],
    pattern: re.Pattern[str],
    ranks: tuple[tuple[str, ...], ...],
    excluded: tuple[str, ...] = (),
) -> str | None:
    """The first sentence holding *pattern* and a word of the strongest rank found; else None."""
    holding = [
        (sentence, normalize_spanish(sentence))
        for sentence in candidates
        if pattern.search(sentence)
    ]
    for words in ranks:
        for sentence, folded in holding:
            if any(word in folded for word in words) and not any(w in folded for w in excluded):
                return sentence
    return None


def _quoted(sentences: list[str]) -> str:
    joined = ". ".join(sentence.rstrip(".") for sentence in sentences)
    return f"{PAPER_ANSWER_OPENING} {cap_answer(joined)}"


def word_paper(paper: str, ask: PaperAsk) -> str:
    """Answer *ask* from *paper* by quotation, never from a model.

    Args:
        paper: The whole text read by the camera, one line per text line.
        ask: The closed question.

    Returns:
        «Según el papel: …» with the answering sentence(s), the fixed phrase of a question that
        asks to interpret, or «Eso no aparece en lo que leí.».
    """
    candidates = body_sentences(paper)
    found: list[str]
    match ask:
        case PaperAsk.INTERPRET:
            return PAPER_NOT_INTERPRETED
        case PaperAsk.AMOUNT:
            found = [s] if (s := _best(candidates, _AMOUNT, _AMOUNT_WORDS)) else []
        case PaperAsk.DUE_DATE:
            found = [s] if (s := _best(candidates, _DATE, _DATE_WORDS, _NOT_DUE)) else []
        case PaperAsk.SENDER:
            found = candidates[:1]
        case PaperAsk.TOPIC:
            found = candidates[:_START_SENTENCES]
        case PaperAsk.CONTENT:
            found = candidates
    return _quoted(found) if found else NOT_IN_PAPER
