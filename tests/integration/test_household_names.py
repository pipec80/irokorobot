"""The household's stored names reach the controller on the identified routes (Plan 0077)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock

import pytest
from server.memory.declarative import upsert_entity
from server.memory.entity_labels import read_household_names
from server.routers import chat, transcribe as transcribe_module
from server.settings import settings
from server.text_turn import TextTurnResult

from server import db
from tests.integration.test_chat_endpoint import _client

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path


@pytest.fixture
async def household(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "names.db")
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield
    await db.close_db()
    db._conn = None


@pytest.mark.integration
async def test_the_reader_returns_the_names_and_aliases(household: None) -> None:
    await upsert_entity(name="Zeta", type="person", aliases=["Zetita"])
    await upsert_entity(name="Tomasito", type="other", aliases=["Tomi"])

    assert {"Zeta", "Zetita", "Tomasito", "Tomi"} <= await read_household_names()


@pytest.mark.integration
async def test_malformed_aliases_mean_no_names_and_never_log_the_value(
    household: None, caplog: pytest.LogCaptureFixture
) -> None:
    pet = await upsert_entity(name="Tomasito", type="other", aliases=["Tomi"])
    async with db.transaction() as conn:
        await conn.execute("UPDATE entities SET aliases = ? WHERE id = ?", ("{zumo", pet))

    with caplog.at_level(logging.DEBUG, logger="server"):
        assert await read_household_names() == frozenset()

    assert "BrainMemoryError" in caplog.text
    assert "zumo" not in caplog.text


@pytest.mark.integration
async def test_a_closed_store_means_no_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "_conn", None)

    assert await read_household_names() == frozenset()


@pytest.mark.integration
def test_the_voice_route_hands_the_reader_to_the_controller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spy = Mock(wraps=transcribe_module.CognitiveController)
    monkeypatch.setattr(transcribe_module, "CognitiveController", spy)
    monkeypatch.setattr(settings, "memory_enabled", True)

    transcribe_module._voice_controller(Mock(), request_identity=Mock())

    assert spy.call_args.kwargs["household_names"] is read_household_names


@pytest.mark.integration
def test_with_memory_off_the_voice_route_reads_no_names(monkeypatch: pytest.MonkeyPatch) -> None:
    """The database is not open: a read per turn would only log a warning per turn."""
    spy = Mock(wraps=transcribe_module.CognitiveController)
    monkeypatch.setattr(transcribe_module, "CognitiveController", spy)
    monkeypatch.setattr(settings, "memory_enabled", False)

    transcribe_module._voice_controller(Mock(), request_identity=Mock())

    assert spy.call_args.kwargs["household_names"] is None


@pytest.mark.integration
def test_a_voice_route_without_identity_reads_no_names(monkeypatch: pytest.MonkeyPatch) -> None:
    spy = Mock(wraps=transcribe_module.CognitiveController)
    monkeypatch.setattr(transcribe_module, "CognitiveController", spy)

    transcribe_module._voice_controller(Mock())

    assert "household_names" not in spy.call_args.kwargs


@pytest.mark.integration
def test_the_chat_route_imports_the_same_reader() -> None:
    assert chat.read_household_names is read_household_names


@pytest.mark.integration
async def test_a_visitor_on_chat_reaches_the_model_with_a_stored_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = AsyncMock(return_value=TextTurnResult("legacy", "joy", 42, False))
    names = AsyncMock(return_value=frozenset({"Zeta"}))
    monkeypatch.setattr(chat, "process_text_turn", process)
    monkeypatch.setattr(chat, "read_household_names", names)
    monkeypatch.setattr(settings, "memory_enabled", True)

    async with _client() as client:
        response = await client.post(
            "/chat", json={"message": "¿Cuándo nació Zeta?", "conversation_id": "web-primary"}
        )

    assert response.json()["response"] == "legacy"
    process.assert_awaited_once()
    names.assert_awaited_once()
