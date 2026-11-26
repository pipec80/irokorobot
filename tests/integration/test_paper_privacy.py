"""Plan 0090 Task 7 (ADR 0041 decision 3): the paper lives only in its slot and a kept document.

One canary paper is read, asked about twice and kept, through the real classic route. Its words
must never reach a log, the conversation record, the short-term session or an export; once kept,
they are in the document's sections and nowhere else.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
from server.memory import continuity
from server.memory.conversation_consent import grant_conversation_consent
from server.memory.data_export import gather_export
from server.memory.export_files import render_json
from server.memory.export_model import ExportScope, ExportScopeKind
from server.memory.reading_offer import READING_SLOT
from server.routers import transcribe as transcribe_module
from server.settings import settings

from server import db
from tests.integration.test_document_routes import _models, household
from tests.integration.test_recall_routes import _client, _files, _hear, _see_the_owner

if TYPE_CHECKING:
    from server.personal_setup import PersonalSetupResult

pytestmark = pytest.mark.integration

_CANARY = "qqpapelqq"
_PAPER = f"Aviso {_CANARY}\nTotal a pagar: $7.777\nVence: 01-12-2026"
__all__ = ["household"]  # the fixture, imported so this module can use it


async def _texts_of(table: str, columns: str) -> str:
    cursor = await db.get_conn().execute(f"SELECT {columns} FROM {table}")  # noqa: S608 - fixed names
    rows = await cursor.fetchall()
    await cursor.close()
    return " ".join(str(cell) for row in rows for cell in row)


async def test_the_paper_never_leaves_its_slot_until_it_is_kept(
    household: tuple[PersonalSetupResult, int],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    owner = household[0].owner_entity_id
    monkeypatch.setattr(settings, "vision_enabled", True)
    monkeypatch.setattr(settings, "conversation_record_enabled", True)
    monkeypatch.setattr(transcribe_module, "read_text", AsyncMock(return_value=_PAPER))
    await grant_conversation_consent(owner, notice_version="v1", now=datetime.now(UTC))
    READING_SLOT.clear()
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "lee esto", "¿Cuánto tengo que pagar?", "¿De qué se trata?", "Sí, guárdalo")
    _models(monkeypatch)

    with caplog.at_level(logging.DEBUG):
        async with _client() as client:
            for _ in range(3):
                await client.post("/transcribe", files=_files())
            before_keep = render_json(
                await gather_export(
                    ExportScope(ExportScopeKind.ALL), owner_entity_id=owner, now="2026-11-26"
                )
            )
            await client.post("/transcribe", files=_files())

    assert _CANARY not in caplog.text
    assert "7.777" not in caplog.text
    assert _CANARY not in json.dumps(before_keep, ensure_ascii=False, default=str)
    assert _CANARY not in await _texts_of("conversation_turns", "heard, said")
    history = continuity.open_turn(owner).history
    assert all(_CANARY not in turn.content for turn in history)
    assert _CANARY in await _texts_of("document_sections", "body")
