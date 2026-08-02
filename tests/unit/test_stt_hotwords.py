"""Unit tests for dynamic hotword merging in the STT layer.

Whisper garbles proper nouns it has never seen ("Dominga" → "Dominguez",
observed live 2026-07-07). Names already learned by the memory layer are
merged with the static WHISPER_HOTWORDS setting to bias decoding.
"""

import pytest
from server.stt import _merge_hotwords


@pytest.mark.unit
def test_merge_both_empty_returns_none() -> None:
    assert _merge_hotwords(None, None) is None
    assert _merge_hotwords(None, []) is None


@pytest.mark.unit
def test_merge_only_base_returns_base() -> None:
    assert _merge_hotwords("Omnibot Iroko", None) == "Omnibot Iroko"


@pytest.mark.unit
def test_merge_only_extras_joins_names() -> None:
    assert _merge_hotwords(None, ["Dominga", "Máximo"]) == "Dominga Máximo"


@pytest.mark.unit
def test_merge_appends_extras_after_base() -> None:
    assert _merge_hotwords("Iroko", ["Dominga"]) == "Iroko Dominga"


@pytest.mark.unit
def test_merge_dedupes_case_insensitively() -> None:
    """A name already in the static hotwords must not repeat."""
    assert _merge_hotwords("Iroko dominga", ["Dominga", "Luna"]) == "Iroko dominga Luna"


@pytest.mark.unit
def test_merge_skips_blank_extras() -> None:
    assert _merge_hotwords(None, ["  ", "", "Luna"]) == "Luna"
