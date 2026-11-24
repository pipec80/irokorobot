"""Extracting a document's text, one adapter per format (Plan 0088 Task B2, D-9).

The PDF adapter runs in a child process (an external process, hence `integration`). Every file is
an invented canary written into a temporary folder; the bench's PDF is the tracked fixture.
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import TYPE_CHECKING

import cv2
import numpy as np
from PIL import Image
from pypdf import PdfWriter
from pypdf.annotations import Link
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, TextStringObject
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


# --- what a file really is, and what a PDF may not carry (Pipec, 2026-11-24) -------------------

_ACTIVE = "Este PDF trae enlaces, firmas, códigos QR o de barras, adjuntos o acciones; no lo abro."
_NOT_WHAT_IT_SAYS = "Ese archivo no es lo que dice su extensión; no lo abro."


def _text_pdf() -> PdfWriter:
    """The bench's text-layer guide as a writer, to add active content to."""
    return PdfWriter(clone_from=_FIXTURES / "guia-cuidados-rodilla.pdf")


def _saved(writer: PdfWriter, path: Path) -> Path:
    with path.open("wb") as handle:
        writer.write(handle)
    return path


@pytest.mark.parametrize(
    "name, content",
    [
        ("carta.pdf", b"#!/bin/sh\nrm -rf /\n"),
        ("nota.txt", b"MZ\x90\x00\x03\x00binario"),
        ("x.md", b"\x00\x00\x00"),
    ],
)
def test_a_file_that_is_not_what_its_extension_says_is_refused(
    tmp_path: Path, name: str, content: bytes
) -> None:
    path = tmp_path / name
    path.write_bytes(content)

    with pytest.raises(DocumentRefusedError) as raised:
        extract_text(path)
    assert raised.value.reason == _NOT_WHAT_IT_SAYS


def test_invisible_and_control_characters_never_reach_the_text(tmp_path: Path) -> None:
    path = tmp_path / "nota.md"
    path.write_bytes("zz\u202euno\u200b dos\x1b[31m tres\x07".encode())

    (page,) = extract_text(path).pages

    assert page == "zzuno dos[31m tres"


def test_a_pdf_with_javascript_is_refused(tmp_path: Path) -> None:
    writer = _text_pdf()
    writer._root_object[NameObject("/OpenAction")] = DictionaryObject(
        {
            NameObject("/S"): NameObject("/JavaScript"),
            NameObject("/JS"): TextStringObject("app.alert(1)"),
        }
    )

    with pytest.raises(DocumentRefusedError) as raised:
        extract_text(_saved(writer, tmp_path / "js.pdf"))
    assert raised.value.reason == _ACTIVE


def test_a_pdf_with_an_attachment_is_refused(tmp_path: Path) -> None:
    writer = _text_pdf()
    writer.add_attachment("script.bat", b"del /q *")

    with pytest.raises(DocumentRefusedError) as raised:
        extract_text(_saved(writer, tmp_path / "adjunto.pdf"))
    assert raised.value.reason == _ACTIVE


def test_a_pdf_with_a_link_is_refused(tmp_path: Path) -> None:
    writer = _text_pdf()
    writer.add_annotation(0, Link(rect=(50, 50, 200, 80), url="http://zz.invalid/x"))

    with pytest.raises(DocumentRefusedError) as raised:
        extract_text(_saved(writer, tmp_path / "enlace.pdf"))
    assert raised.value.reason == _ACTIVE


def test_a_pdf_with_a_signature_field_is_refused(tmp_path: Path) -> None:
    writer = _text_pdf()
    field = DictionaryObject(
        {NameObject("/FT"): NameObject("/Sig"), NameObject("/T"): TextStringObject("firma")}
    )
    writer._root_object[NameObject("/AcroForm")] = DictionaryObject(
        {NameObject("/Fields"): ArrayObject([writer._add_object(field)])}
    )

    with pytest.raises(DocumentRefusedError) as raised:
        extract_text(_saved(writer, tmp_path / "firmado.pdf"))
    assert raised.value.reason == _ACTIVE


def _image_pdf(image: np.ndarray, path: Path) -> Path:
    Image.fromarray(image).convert("RGB").save(path, "PDF")
    return path


def test_a_pdf_with_a_qr_code_is_refused(tmp_path: Path) -> None:
    qr = cv2.QRCodeEncoder.create().encode("http://zz.invalid/script")
    big = cv2.resize(qr, (qr.shape[1] * 8, qr.shape[0] * 8), interpolation=cv2.INTER_NEAREST)
    padded = cv2.copyMakeBorder(big, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255)
    writer = _text_pdf()
    writer.append(_image_pdf(padded, tmp_path / "qr-only.pdf"))

    with pytest.raises(DocumentRefusedError) as raised:
        extract_text(_saved(writer, tmp_path / "qr.pdf"))
    assert raised.value.reason == _ACTIVE


def test_the_bench_pdf_carries_nothing_active() -> None:
    assert len(extract_text(_FIXTURES / "guia-cuidados-rodilla.pdf").pages) == 3


def test_a_pdf_with_too_many_images_to_inspect_is_refused(tmp_path: Path) -> None:
    """Security review: images are decoded to look for codes, so their number is bounded."""
    from pypdf import PdfReader  # noqa: PLC0415
    from server.memory import pdf_inspect  # noqa: PLC0415

    blank = np.full((60, 60), 255, dtype=np.uint8)
    writer = _text_pdf()
    for index in range(3):
        writer.append(_image_pdf(blank, tmp_path / f"blank{index}.pdf"))
    path = _saved(writer, tmp_path / "imagenes.pdf")

    assert not pdf_inspect.holds_codes(PdfReader(path))
    assert pdf_inspect.holds_codes(PdfReader(path), max_images=2)


def test_an_image_over_the_declared_pixel_budget_is_refused_before_any_decode(
    tmp_path: Path,
) -> None:
    from pypdf import PdfReader  # noqa: PLC0415
    from server.memory import pdf_inspect  # noqa: PLC0415

    writer = _text_pdf()
    writer.append(_image_pdf(np.full((60, 60), 255, dtype=np.uint8), tmp_path / "blank.pdf"))
    path = _saved(writer, tmp_path / "grande.pdf")

    assert not pdf_inspect.holds_codes(PdfReader(path))
    assert pdf_inspect.holds_codes(PdfReader(path), max_pixels=60 * 60 - 1)
