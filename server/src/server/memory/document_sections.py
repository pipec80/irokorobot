"""Cutting a document's text into sections under the embedding window (Plan 0088 D-10).

A block is a Markdown heading's text (with its heading path), a paragraph of plain text, or a page
of a PDF. A block within the cap is one section; a longer one is cut at its blank lines, a
paragraph still too long at its sentence ends, a sentence still too long at its spaces, and the
pieces are packed in order up to the cap. Whitespace inside a paragraph is collapsed; no word is
lost. Pure: no I/O.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

from server.memory.document_extract import DocumentRefusedError
from server.memory.document_store import NewSection

if TYPE_CHECKING:
    from collections.abc import Iterator

    from server.memory.document_extract import ExtractedText

__all__ = ["MAX_SECTIONS", "SECTION_MAX_CHARS", "cut_sections", "split_body"]

#: Characters per section: 433 tokens at the lowest ratio measured (2.77), under 512 (Task B0).
SECTION_MAX_CHARS: Final = 1200
#: The most sections one document may have. Not ``Final``: a test lowers it.
MAX_SECTIONS: int = 2000
# The heading column's own cap (migration 023); a deeper path keeps its last characters.
_MAX_HEADING: Final = 400
_HEADING: Final = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_BLANK_LINES: Final = re.compile(r"\n\s*\n")
_SENTENCE_END: Final = re.compile(r"(?<=[.!?…])\s+")
_TOO_LONG: Final = "Ese documento es demasiado largo; no lo guardo."
_PATH_JOIN: Final = " > "


def _paragraphs(block: str) -> list[str]:
    """The block's paragraphs, whitespace collapsed, empty ones dropped."""
    return [" ".join(p.split()) for p in _BLANK_LINES.split(block) if p.strip()]


def _pieces(paragraph: str, max_chars: int) -> Iterator[str]:
    """A paragraph as pieces within *max_chars*: sentences, then words, then characters."""
    if len(paragraph) <= max_chars:
        yield paragraph
        return
    for sentence in _SENTENCE_END.split(paragraph):
        if len(sentence) <= max_chars:
            yield sentence
            continue
        for word in sentence.split(" "):
            for start in range(0, len(word), max_chars):
                yield word[start : start + max_chars]


def _pack(pieces: Iterator[str], max_chars: int, glue: str) -> list[str]:
    """Join consecutive pieces with *glue* while the result stays within *max_chars*."""
    packed: list[str] = []
    for piece in pieces:
        if packed and len(packed[-1]) + len(glue) + len(piece) <= max_chars:
            packed[-1] = f"{packed[-1]}{glue}{piece}"
        else:
            packed.append(piece)
    return packed


def split_body(block: str, max_chars: int) -> list[str]:
    """Cut one block of text into bodies within *max_chars* (blank lines, sentences, words).

    Args:
        block: The text of one block.
        max_chars: The cap.

    Returns:
        The bodies, in order; empty when the block holds no text.
    """
    paragraphs = _paragraphs(block)
    whole = "\n\n".join(paragraphs)
    if len(whole) <= max_chars:
        return [whole] if whole else []
    bodies: list[str] = []
    for paragraph in paragraphs:
        glue = " "
        bodies += _pack(_pieces(paragraph, max_chars), max_chars, glue)
    return _pack(iter(bodies), max_chars, "\n\n")


def _markdown_blocks(text: str) -> Iterator[tuple[str, str]]:
    """``(heading path, text)`` of each heading's block, in order."""
    path: list[tuple[int, str]] = []
    lines: list[str] = []

    def heading() -> str:
        return _PATH_JOIN.join(title for _, title in path)[-_MAX_HEADING:]

    for line in text.splitlines():
        if match := _HEADING.match(line):
            yield heading(), "\n".join(lines)
            depth = len(match.group(1))
            path = [(d, t) for d, t in path if d < depth] + [(depth, match.group(2))]
            lines = []
        else:
            lines.append(line)
    yield heading(), "\n".join(lines)


def _blocks(text: ExtractedText) -> Iterator[tuple[str, str]]:
    match text.format:
        case "md":
            yield from _markdown_blocks(text.pages[0])
        case "txt":
            for paragraph in _BLANK_LINES.split(text.pages[0]):
                yield "", paragraph
        case "pdf":
            for page in text.pages:
                yield "", page


def cut_sections(text: ExtractedText, *, max_chars: int) -> list[NewSection]:
    """Cut a document's text into sections, positions from 0.

    Args:
        text: The extracted text.
        max_chars: The section cap (``SECTION_MAX_CHARS`` in production).

    Returns:
        The sections, in reading order.

    Raises:
        DocumentRefusedError: If the document has more than ``MAX_SECTIONS`` sections.
    """
    sections = [
        NewSection(position=0, heading=heading, body=body)
        for heading, block in _blocks(text)
        for body in split_body(block, max_chars)
    ]
    if len(sections) > MAX_SECTIONS:
        raise DocumentRefusedError(_TOO_LONG)
    return [NewSection(position=i, heading=s.heading, body=s.body) for i, s in enumerate(sections)]
