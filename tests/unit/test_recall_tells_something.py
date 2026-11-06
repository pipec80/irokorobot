"""Unit tests for ``recall_store.tells_something`` — it follows the sensitive and memory switches.

Pure: the function only resolves a message, so no database is needed (Plan 0079, Task 5).
"""

from __future__ import annotations

import pytest
from server.memory.recall_store import tells_something
from server.settings import settings

pytestmark = pytest.mark.unit

_ADDRESS_QUESTION = "¿Cuál es mi dirección?"
_STATED_VALUE = "Mi clave es 1234."
_ORDINARY = "Hoy fui a la feria y compré tomates."


def test_tells_something_follows_the_switches(monkeypatch: pytest.MonkeyPatch) -> None:
    """A sensitive question tells nothing only with the switch on; a secret with memory on."""
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "sensitive_read_enabled", False)
    # Switch off: today's behaviour, an ordinary «¿cuál es mi dirección?» still becomes a unit.
    assert tells_something(_ADDRESS_QUESTION) is True
    # Memory on, sensitive off: a stated secret still tells nothing (the secret guard follows
    # memory only).
    assert tells_something(_STATED_VALUE) is False

    monkeypatch.setattr(settings, "sensitive_read_enabled", True)
    assert tells_something(_ADDRESS_QUESTION) is False
    assert tells_something(_STATED_VALUE) is False
    assert tells_something(_ORDINARY) is True

    monkeypatch.setattr(settings, "memory_enabled", False)
    assert tells_something(_STATED_VALUE) is True


def test_a_blank_text_tells_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Blank words never become a unit, whatever the switches."""
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "sensitive_read_enabled", True)

    assert tells_something("   ") is False
