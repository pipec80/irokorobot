"""Cutting a document into sections under the embedding window (Plan 0088 Task B2, D-10).

Canary text only.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from server.memory import document_sections
from server.memory.document_extract import DocumentRefusedError, ExtractedText
from server.memory.document_sections import SECTION_MAX_CHARS, cut_sections

pytestmark = pytest.mark.unit

_MD = """# Manual canario

zzintro de la máquina.

## Filtro

zzfiltro uno.

zzfiltro dos.

### Limpieza

zzlimpieza.
"""


def test_markdown_keeps_its_heading_path() -> None:
    sections = cut_sections(ExtractedText(format="md", pages=(_MD,)), max_chars=SECTION_MAX_CHARS)

    assert [(s.position, s.heading, s.body) for s in sections] == [
        (0, "Manual canario", "zzintro de la máquina."),
        (1, "Manual canario > Filtro", "zzfiltro uno.\n\nzzfiltro dos."),
        (2, "Manual canario > Filtro > Limpieza", "zzlimpieza."),
    ]


def test_text_is_cut_at_blank_lines() -> None:
    text = ExtractedText(format="txt", pages=("zzuno\nsigue\n\n\n zzdos \n",))

    sections = cut_sections(text, max_chars=SECTION_MAX_CHARS)

    assert [s.body for s in sections] == ["zzuno sigue", "zzdos"]
    assert all(s.heading == "" for s in sections)


def test_a_pdf_is_cut_by_page() -> None:
    text = ExtractedText(format="pdf", pages=("zzpagina\nuno", "", "zzpagina dos"))

    assert [s.body for s in cut_sections(text, max_chars=SECTION_MAX_CHARS)] == [
        "zzpagina uno",
        "zzpagina dos",
    ]


def test_no_section_exceeds_the_cap_and_no_word_is_lost() -> None:
    sentence = "zzfrase canaria que se repite muchas veces."
    long_paragraph = " ".join([sentence] * 80)
    one_long_word = "z" * 130
    text = ExtractedText(format="txt", pages=(f"{long_paragraph}\n\n{one_long_word}",))

    sections = cut_sections(text, max_chars=100)

    assert all(1 <= len(s.body) <= 100 for s in sections)
    words = " ".join(s.body for s in sections).split()
    assert words.count("zzfrase") == 80
    assert "".join(w for w in words if set(w) == {"z"}) == one_long_word


def test_a_document_over_the_section_cap_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(document_sections, "MAX_SECTIONS", 2)
    text = ExtractedText(format="txt", pages=("zzuno\n\nzzdos\n\nzztres",))

    with pytest.raises(DocumentRefusedError):
        cut_sections(text, max_chars=SECTION_MAX_CHARS)


def test_the_reading_cap_and_the_note_title() -> None:
    from server.routers import transcribe  # noqa: PLC0415 - the route's helpers, tested alone

    long_text = " ".join(["palabra"] * 120)
    capped = transcribe._cap_reading(long_text)
    assert len(capped) <= 400
    assert capped.endswith("…")
    now = datetime(2026, 11, 23, 15, tzinfo=UTC)
    assert transcribe._note_title("Comprar pan y leche hoy mismo", now) == (
        "Nota del 23 de noviembre: Comprar pan y leche hoy"
    )
    assert transcribe._note_title("Pagar 3 cuentas", now) == "Nota del 23 de noviembre"
