"""A document's text, one adapter per format (Plan 0088 D-9, ADR 0034 decision 1).

``EXTRACTORS`` is a closed table from a file extension to its extractor; R2b adds formats by adding
adapters. Markdown and text are read as UTF-8 (a BOM is accepted). A PDF with a text layer is read
by ``pypdf`` in a child process killed at ``EXTRACT_TIMEOUT_S``, with pypdf's decompression limits
set explicitly, so a file built to hang or bloat the parser stores nothing. Every refusal carries
a closed Spanish reason for the person at the terminal; nothing here logs a text.

Run as a module (``python -m server.memory.document_extract FILE``) it is that child: it writes the
pages' text as JSON to stdout, or exits with a closed code.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
import json
from pathlib import Path
import subprocess
import sys
from typing import Final, Literal
import unicodedata

from server.exceptions import BrainMemoryError

__all__ = [
    "EXTRACTORS",
    "EXTRACT_TIMEOUT_S",
    "MAX_FILE_BYTES",
    "MAX_PAGES",
    "DocumentRefusedError",
    "ExtractedText",
    "Extractor",
    "extract_text",
]

#: The largest file read, of any format.
MAX_FILE_BYTES: Final = 10_000_000
#: The most pages a PDF may have.
MAX_PAGES: Final = 200
#: Seconds the PDF child may run before it is killed. Not ``Final``: a test shortens it.
EXTRACT_TIMEOUT_S: float = 30.0
# pypdf's limit on one decompressed stream, set in the child below its own default (75 MB). The
# memory the child takes is bounded by this and the time limit only (Plan 0088 D-9, accepted).
_MAX_DECOMPRESSED_BYTES: Final = 20_000_000

_UNKNOWN_FORMAT: Final = "Ese formato todavía no lo leo."
_NOT_UTF8: Final = "Ese archivo no está en UTF-8; guárdalo como UTF-8 y vuelve a intentarlo."
_NO_TEXT: Final = "Este PDF no tiene texto que pueda leer."
_TOO_BIG: Final = "Ese archivo pasa de 10 MB; no lo leo."
_TOO_MANY_PAGES: Final = "Ese PDF pasa de 200 páginas; no lo leo."
_TOO_SLOW: Final = "Ese PDF tardó demasiado en leerse; no lo guardo."
_UNREADABLE: Final = "No pude leer ese archivo."
_EMPTY: Final = "Ese archivo está vacío."
_NOT_WHAT_IT_SAYS: Final = "Ese archivo no es lo que dice su extensión; no lo abro."
_ACTIVE: Final = (
    "Este PDF trae enlaces, firmas, códigos QR o de barras, adjuntos o acciones; no lo abro."
)
# A PDF says what it is in its first bytes (ISO 32000: «%PDF-» within the first kilobyte).
_PDF_MAGIC: Final = b"%PDF-"
_PDF_MAGIC_WINDOW: Final = 1024
# A text file holds no NUL byte; a few stray control characters are cleaned, more is binary.
_MAX_CONTROL_SHARE: Final = 0.01
_MAX_STRAY_CONTROLS: Final = 8
_KEPT_CONTROLS: Final = frozenset("\n\t")

# The child's closed exit codes, and the reason each one gives.
_EXIT_NO_TEXT: Final = 3
_EXIT_TOO_MANY_PAGES: Final = 4
_EXIT_ACTIVE: Final = 5
_EXIT_REASONS: Final[Mapping[int, str]] = {
    _EXIT_NO_TEXT: _NO_TEXT,
    _EXIT_TOO_MANY_PAGES: _TOO_MANY_PAGES,
    _EXIT_ACTIVE: _ACTIVE,
}

type DocumentFileFormat = Literal["md", "txt", "pdf"]


class DocumentRefusedError(BrainMemoryError):
    """A document the robot does not store, with the closed Spanish reason to show the owner."""

    def __init__(self, reason: str) -> None:
        """Keep the reason.

        Args:
            reason: One of this module's closed Spanish reasons.
        """
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ExtractedText:
    """The text of one file: one entry per page (a single one for Markdown and text)."""

    format: DocumentFileFormat
    pages: tuple[str, ...] = field(repr=False)


type Extractor = Callable[[Path], ExtractedText]


def clean_text(text: str) -> str:
    """*text* without control characters (but line breaks and tabs) or invisible format ones.

    A right-to-left override, a zero-width space or a terminal escape never reaches a section,
    the screen of `iroko-admin` or a spoken answer.
    """
    return "".join(
        character
        for character in text.replace("\r\n", "\n").replace("\r", "\n")
        if character in _KEPT_CONTROLS or unicodedata.category(character)[0] != "C"
    )


def _looks_binary(raw: bytes, text: str) -> bool:
    """A NUL byte, or more control characters than a text file has."""
    if b"\x00" in raw:
        return True
    controls = sum(1 for c in text if c not in _KEPT_CONTROLS and unicodedata.category(c) == "Cc")
    return controls > max(_MAX_STRAY_CONTROLS, len(text) * _MAX_CONTROL_SHARE)


def _read_utf8(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise DocumentRefusedError(_UNREADABLE) from exc
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        if b"\x00" in raw:
            raise DocumentRefusedError(_NOT_WHAT_IT_SAYS) from exc
        raise DocumentRefusedError(_NOT_UTF8) from exc
    if _looks_binary(raw, text):
        raise DocumentRefusedError(_NOT_WHAT_IT_SAYS)
    cleaned = clean_text(text).strip()
    if not cleaned:
        raise DocumentRefusedError(_EMPTY)
    return cleaned


def _markdown(path: Path) -> ExtractedText:
    return ExtractedText(format="md", pages=(_read_utf8(path),))


def _plain_text(path: Path) -> ExtractedText:
    return ExtractedText(format="txt", pages=(_read_utf8(path),))


def _pdf_child_command(path: Path) -> Sequence[str]:
    """The child that reads a PDF: this interpreter, isolated, running this module."""
    return [sys.executable, "-I", "-m", "server.memory.document_extract", str(path)]


def _is_pdf(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return _PDF_MAGIC in handle.read(_PDF_MAGIC_WINDOW)
    except OSError as exc:
        raise DocumentRefusedError(_UNREADABLE) from exc


def _pdf(path: Path) -> ExtractedText:
    if not _is_pdf(path):
        raise DocumentRefusedError(_NOT_WHAT_IT_SAYS)
    try:
        done = subprocess.run(  # noqa: S603 - a fixed command; the path is an argument, never a shell
            _pdf_child_command(path),
            capture_output=True,
            timeout=EXTRACT_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise DocumentRefusedError(_TOO_SLOW) from exc
    if done.returncode in _EXIT_REASONS:
        raise DocumentRefusedError(_EXIT_REASONS[done.returncode])
    if done.returncode != 0:
        raise DocumentRefusedError(_UNREADABLE)
    try:
        pages = json.loads(done.stdout.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise DocumentRefusedError(_UNREADABLE) from exc
    if not isinstance(pages, list) or not all(isinstance(page, str) for page in pages):
        raise DocumentRefusedError(_UNREADABLE)
    return ExtractedText(format="pdf", pages=tuple(clean_text(page).strip() for page in pages))


#: The closed table of formats: a lower-case extension to its extractor.
EXTRACTORS: Final[Mapping[str, Extractor]] = {".md": _markdown, ".txt": _plain_text, ".pdf": _pdf}


def extract_text(path: Path) -> ExtractedText:
    """Read one file's text by its extension.

    Args:
        path: A file the owner chose.

    Returns:
        Its text, page by page.

    Raises:
        DocumentRefusedError: With its closed reason: a format outside the table, a file over
            ``MAX_FILE_BYTES``, a file whose bytes are not what its extension says, a text not
            in UTF-8 or empty, a PDF without text, encrypted, over ``MAX_PAGES``, carrying
            active content (``pdf_inspect``), unreadable or slower than ``EXTRACT_TIMEOUT_S``.
    """
    extractor = EXTRACTORS.get(path.suffix.lower())
    if extractor is None:
        raise DocumentRefusedError(_UNKNOWN_FORMAT)
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise DocumentRefusedError(_UNREADABLE) from exc
    if size > MAX_FILE_BYTES:
        raise DocumentRefusedError(_TOO_BIG)
    return extractor(path)


def _child(path: Path) -> int:
    """Read *path* as a PDF and write its pages' text as JSON; return the exit code."""
    from pypdf import PdfReader, overwrite_configuration  # noqa: PLC0415 - only the child parses

    overwrite_configuration(
        zlib_maximum_output_length=_MAX_DECOMPRESSED_BYTES,
        maximum_declared_stream_length=_MAX_DECOMPRESSED_BYTES,
    )
    from server.memory.pdf_inspect import holds_active_content, holds_codes  # noqa: PLC0415

    reader = PdfReader(path)
    if reader.is_encrypted:
        return _EXIT_NO_TEXT
    if len(reader.pages) > MAX_PAGES:
        return _EXIT_TOO_MANY_PAGES
    if holds_active_content(reader) or holds_codes(reader):
        return _EXIT_ACTIVE
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
    if not any(pages):
        return _EXIT_NO_TEXT
    sys.stdout.buffer.write(json.dumps(pages).encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(_child(Path(sys.argv[1])))
