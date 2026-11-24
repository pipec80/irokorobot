"""Extracting a document's text, one adapter per format (Plan 0088 Task B2, D-9).

The PDF adapter runs in a child process (an external process, hence `integration`). Every file is
an invented canary written into a temporary folder; the bench's PDF is the tracked fixture.
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import TYPE_CHECKING

from pypdf import PdfWriter
import pytest
from server.memory import document_extract
from server.memory.document_extract import DocumentRefusedError, extract_text

if TYPE_CHECKING:
    from collections.abc import Sequence

pytestmark = pytest.mark.integration

_FIXTURES = Path(__file__).parents[1] / "fixtures" / "documents"
_UNKNOWN_FORMAT = "Ese formato todavía no lo leo."
_NO_TEXT = "Este PDF no tiene texto que pueda leer."


def _blank_pdf(path: Path, pages: int, *, password: str | None = None) -> Path:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    if password is not None:
        writer.encrypt(password)
    with path.open("wb") as handle:
        writer.write(handle)
    return path


def test_markdown_and_text_are_read_as_utf8_with_or_without_a_bom(tmp_path: Path) -> None:
    md = tmp_path / "canario.md"
    md.write_bytes("﻿# Título canario\n\nzzuno ñandú".encode())
    txt = tmp_path / "canario.TXT"
    txt.write_bytes(b"zzdos\n\nzztres")

    assert extract_text(md).format == "md"
    assert extract_text(md).pages == ("# Título canario\n\nzzuno ñandú",)
    assert extract_text(txt).format == "txt"


def test_a_text_in_latin1_is_refused_with_its_reason(tmp_path: Path) -> None:
    path = tmp_path / "latin.txt"
    path.write_bytes("ñandú canario".encode("latin-1"))

    with pytest.raises(DocumentRefusedError) as raised:
        extract_text(path)
    assert "UTF-8" in raised.value.reason


def test_a_format_outside_the_table_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "carta.docx"
    path.write_bytes(b"PK\x03\x04")

    with pytest.raises(DocumentRefusedError) as raised:
        extract_text(path)
    assert raised.value.reason == _UNKNOWN_FORMAT


def test_a_text_layer_pdf_gives_its_pages_text() -> None:
    extracted = extract_text(_FIXTURES / "guia-cuidados-rodilla.pdf")

    assert extracted.format == "pdf"
    assert len(extracted.pages) == 3
    assert "cada ocho horas" in extracted.pages[1]
    assert "después" in extracted.pages[1]


def test_a_pdf_without_text_is_refused(tmp_path: Path) -> None:
    with pytest.raises(DocumentRefusedError) as raised:
        extract_text(_blank_pdf(tmp_path / "escaneado.pdf", 2))
    assert raised.value.reason == _NO_TEXT


def test_an_encrypted_pdf_is_refused(tmp_path: Path) -> None:
    with pytest.raises(DocumentRefusedError) as raised:
        extract_text(_blank_pdf(tmp_path / "cerrado.pdf", 1, password="zzcanaryzz"))  # noqa: S106
    assert raised.value.reason == _NO_TEXT


def test_a_pdf_over_the_page_cap_is_refused(tmp_path: Path) -> None:
    path = _blank_pdf(tmp_path / "largo.pdf", document_extract.MAX_PAGES + 1)

    with pytest.raises(DocumentRefusedError) as raised:
        extract_text(path)
    assert "200 páginas" in raised.value.reason


def test_a_file_over_the_size_cap_is_refused_before_it_is_read(tmp_path: Path) -> None:
    path = tmp_path / "grande.md"
    path.write_bytes(b"x" * (document_extract.MAX_FILE_BYTES + 1))

    with pytest.raises(DocumentRefusedError) as raised:
        extract_text(path)
    assert "10 MB" in raised.value.reason


def test_a_parser_that_hangs_is_killed_at_the_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def hanging(_path: Path) -> Sequence[str]:
        return [sys.executable, "-c", "import time; time.sleep(30)"]

    monkeypatch.setattr(document_extract, "_pdf_child_command", hanging)
    monkeypatch.setattr(document_extract, "EXTRACT_TIMEOUT_S", 1.0)

    with pytest.raises(DocumentRefusedError) as raised:
        extract_text(_FIXTURES / "guia-cuidados-rodilla.pdf")
    assert "tardó demasiado" in raised.value.reason


def test_a_crashing_child_is_refused_with_its_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def crashing(_path: Path) -> Sequence[str]:
        return [sys.executable, "-c", "raise SystemExit(9)"]

    monkeypatch.setattr(document_extract, "_pdf_child_command", crashing)

    with pytest.raises(DocumentRefusedError) as raised:
        extract_text(_FIXTURES / "guia-cuidados-rodilla.pdf")
    assert raised.value.reason == "No pude leer ese archivo."


def test_an_unreadable_file_is_refused_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "bloqueado.md"
    path.write_bytes(b"# zz")

    def locked(_self: Path) -> bytes:
        raise PermissionError("locked")

    monkeypatch.setattr(Path, "read_bytes", locked)
    with pytest.raises(DocumentRefusedError):
        extract_text(path)
