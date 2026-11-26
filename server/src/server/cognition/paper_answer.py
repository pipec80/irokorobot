"""Answer a closed question about the paper just read, by quoting it (Plan 0090, ADR 0041).

**No model is called**, for the reason of ADR 0034 deviation 9: the local 3B obeyed an order
planted in a document in 12 of 24 answers. The paper is cut line by line (the OCR returns its
lines), each line into its sentences, and every sentence in the closed shapes of an order or that
the document secret detector flags is left out (``document_answer``'s own filters). A closed
extractor raises the sentence that answers: an amount for «¿cuánto…?», a date for «¿para
cuándo…?», the paper's first lines for «¿quién lo manda?» and «¿de qué se trata?». The answer is
«Según el papel: …» (capped like a document answer) or «Eso no aparece en lo que leí.». Pure: no
I/O, nothing logged.
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
from server.memory.document_answer import cap_answer, readable_sentences
from server.text_keys import normalize_spanish

__all__ = ["word_paper"]

_AMOUNT: Final = re.compile(r"\$\s?\d|\d[\d.,]*\s*(?:pesos|clp)\b", re.IGNORECASE)
_AMOUNT_WORDS: Final = ("total", "pagar", "monto", "deuda", "importe", "saldo")
_MONTHS: Final = "ene|feb|mar|abr|may|jun|jul|ago|sep|set|oct|nov|dic"
_DATE: Final = re.compile(
    rf"\b\d{{1,2}}\s?[-/.]\s?(?:\d{{1,2}}|(?:{_MONTHS})[a-z]*)\s?[-/.]\s?\d{{2,4}}\b"
    rf"|\b\d{{1,2}} de (?:{_MONTHS})[a-z]*(?: de \d{{4}})?\b",
    re.IGNORECASE,
)
_DATE_WORDS: Final = ("venc", "fecha", "hasta", "plazo", "pagar antes", "pague antes")
_START_SENTENCES: Final = 2


def _candidates(paper: str) -> list[str]:
    """The paper's readable sentences in reading order, line by line."""
    return [sentence for line in paper.splitlines() for sentence in readable_sentences(line)]


def _first_with(
    candidates: list[str], pattern: re.Pattern[str], words: tuple[str, ...]
) -> str | None:
    """The first sentence holding *pattern* and one of *words*; else the first holding *pattern*."""
    holding = [sentence for sentence in candidates if pattern.search(sentence)]
    for sentence in holding:
        folded = normalize_spanish(sentence)
        if any(word in folded for word in words):
            return sentence
    return holding[0] if holding else None


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
    candidates = _candidates(paper)
    found: list[str]
    match ask:
        case PaperAsk.INTERPRET:
            return PAPER_NOT_INTERPRETED
        case PaperAsk.AMOUNT:
            found = [s] if (s := _first_with(candidates, _AMOUNT, _AMOUNT_WORDS)) else []
        case PaperAsk.DUE_DATE:
            found = [s] if (s := _first_with(candidates, _DATE, _DATE_WORDS)) else []
        case PaperAsk.SENDER:
            found = candidates[:1]
        case PaperAsk.TOPIC:
            found = candidates[:_START_SENTENCES]
        case PaperAsk.CONTENT:
            found = candidates
    return _quoted(found) if found else NOT_IN_PAPER
