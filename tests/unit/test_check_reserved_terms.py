"""Guard for locally reserved private terms (scripts/check_reserved_terms.py).

Uses invented terms only: the real list lives in a gitignored local file.
"""

from pathlib import Path

import pytest

from scripts.check_reserved_terms import (
    build_matcher,
    load_reserved_terms,
    main,
    offending_lines,
)


@pytest.mark.unit
def test_matcher_flags_whole_words_case_sensitively() -> None:
    """Only exact, whole-word occurrences count; case and word parts do not."""
    matcher = build_matcher(["Zeph", "quorvax 12"])
    assert matcher is not None

    text = "Hola Zeph\nzeph en minúscula\nZephyr no cuenta\nel quorvax 12 sí\n"

    assert offending_lines(text, matcher) == [1, 4]


@pytest.mark.unit
def test_an_empty_list_builds_no_matcher() -> None:
    """No reserved terms means there is nothing to block."""
    assert build_matcher([]) is None


@pytest.mark.integration
def test_main_blocks_a_reserved_term_and_passes_without_a_local_list(tmp_path: Path) -> None:
    """A listed term fails the check; a missing list (CI, fresh clone) passes."""
    terms = tmp_path / "terms.txt"
    terms.write_text("# comentario\nZeph\n", encoding="utf-8")
    dirty = tmp_path / "dirty.md"
    dirty.write_text("Zeph vive aquí\n", encoding="utf-8")
    clean = tmp_path / "clean.md"
    clean.write_text("nada privado\n", encoding="utf-8")

    assert load_reserved_terms(terms) == ["Zeph"]
    assert main([str(dirty), "--terms-file", str(terms)]) == 1
    assert main([str(clean), "--terms-file", str(terms)]) == 0
    assert main([str(dirty), "--terms-file", str(tmp_path / "missing.txt")]) == 0
