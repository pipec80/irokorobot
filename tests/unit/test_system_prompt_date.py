"""Unit tests for the current-date block in the system prompt."""

from __future__ import annotations

from datetime import date

import pytest
from server.characters import build_system_prompt, current_date_es, get_character


@pytest.mark.unit
def test_current_date_es_formats_spanish_prose() -> None:
    """2026-07-14 is a Tuesday → 'martes 14 de julio de 2026'."""
    assert current_date_es(date(2026, 7, 14)) == "martes 14 de julio de 2026"


@pytest.mark.unit
def test_system_prompt_contains_todays_date() -> None:
    """Observed live 2026-07-14: without the date the model invented
    'tu cumpleaños es justo hoy'. The prompt must state the real date."""
    prompt = build_system_prompt(get_character("iroko"), None)

    assert "FECHA ACTUAL" in prompt
    assert current_date_es() in prompt
