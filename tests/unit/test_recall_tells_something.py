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


def test_tells_something_follows_the_alta_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    """An alta question tells nothing only with both the sensitive and the alta switches on."""
    # «¿tienes el teléfono de mi hija?» already tells nothing today (a household question), so
    # the switch is pinned on a question that is ordinary conversation without it.
    contact = "¿Cómo me desplazo?"
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "sensitive_read_enabled", True)
    monkeypatch.setattr(settings, "alta_read_enabled", False)
    assert tells_something(contact) is True
    monkeypatch.setattr(settings, "alta_read_enabled", True)
    assert tells_something(contact) is False
    monkeypatch.setattr(settings, "sensitive_read_enabled", False)
    assert tells_something(contact) is True


@pytest.mark.parametrize(
    "message",
    [
        "Mi mejor amiga Canaria me traicionó, no quiero saber nunca más de ella.",
        "No quiero saber nunca más de Canaria.",
        "Ya no me gusta el té.",
        "Ya no me gusta el chocolate. Ahora prefiero el mate.",
    ],
)
def test_a_spoken_change_is_never_a_memory(monkeypatch: pytest.MonkeyPatch, message: str) -> None:
    """Plan 0086, hardware 2026-11-18: the archive request was indexed after the archive and
    recall then read it back («Hoy me contaste esto: … no quiero saber nunca más de ella»)."""
    monkeypatch.setattr(settings, "memory_enabled", True)

    assert tells_something(message) is False
