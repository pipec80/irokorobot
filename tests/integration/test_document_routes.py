"""The owner's documents through the real voice routes (Plan 0088 Task B8, D-14, D-18, D-19).

Face detection, speech, the embedder and the local model are doubles; the identity store, the
policy, the audit, the documents and their search are real. The embedder is offline, so words alone
search: the questions name the canary code «ZZK41» the section holds (ADR 0040 decision 3). Every
value is an invented canary.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import httpx
from pydantic import SecretStr
import pytest
from server.cognition.response_plan import DOCUMENT_RECORDED_TEXT, NO_MEMORY, NOT_IN_DOCUMENTS
from server.memory import continuity, document_answer, document_search, document_store
from server.memory.biometric_consent import grant_face_consent
from server.memory.conversation_consent import grant_conversation_consent
from server.memory.deletion_register import Deletion, DeletionKind, forget
from server.memory.document_store import NewSection, NewSource
from server.personal_setup import PersonalSetupInput, PersonalSetupResult, apply_personal_setup
from server.routers import transcribe as transcribe_module
from server.settings import settings
from server.vision.faces import enroll_face

from server import db, llm, llm_streaming
from tests.integration.test_recall_routes import (
    _OWNER_FACE,
    _REFUSAL,
    _client,
    _files,
    _hear,
    _see_the_owner,
    _spoken,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_CANARY = "zzcanaryzz el repuesto ZZK41 se gira hacia la izquierda"
_ASK = "¿Qué dice el manual de la lavadora sobre el repuesto ZZK41?"
_STRONG_NOTHING = "Según mis documentos, ¿qué dice del repuesto QQX77?"
_GENERAL = "¿Qué dice la guía de Santiago sobre el metro?"
_RECALL = "¿Qué te conté del repuesto ZZK41?"
_WORDED = "El repuesto ZZK41 se gira hacia la izquierda."
_ROUTES = ["/transcribe", "/transcribe/stream"]
_DOCUMENT_AUDIT = (
    "SELECT COUNT(*) FROM authorization_audit_events WHERE action = 'read_personal_document'"
)


@pytest.fixture
async def household(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[PersonalSetupResult, int]]:
    """A face-enrolled owner with one document holding the canary."""
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "documents-routes.db")
    monkeypatch.setattr(settings, "face_authentication_enabled", True)
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "recall_enabled", True)
    monkeypatch.setattr(settings, "documents_enabled", True)
    continuity.reset()
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    result = await apply_personal_setup(
        PersonalSetupInput(owner_name="Canary", child_names=(), pin=SecretStr("482173"))
    )
    await grant_face_consent(result.owner_entity_id)
    await enroll_face(result.owner_entity_id, _OWNER_FACE, label="Canary")
    source = NewSource(
        owner_entity_id=result.owner_entity_id,
        title="Manual de la lavadora",
        file_sha256="b" * 64,
        format="md",
        level="normal",
        channel="admin_local",
        loaded_at="2026-11-23T12:00:00.000000+00:00",
        loaded_by_entity_id=result.owner_entity_id,
    )
    async with db.transaction() as conn:
        source_id = await document_store.insert_source(
            conn, source=source, sections=[NewSection(0, "Repuestos", _CANARY)]
        )
    yield result, source_id
    continuity.reset()
    await db.close_db()
    db._conn = None


def _models(monkeypatch: pytest.MonkeyPatch) -> tuple[list[str], AsyncMock]:
    prompts: list[str] = []

    async def generate(_client: object, system_prompt: str, _messages: object) -> tuple[str, str]:
        prompts.append(system_prompt)
        return "Hola.", "neutral"

    async def stream(
        _client: object, messages: list[dict[str, str]], **_kwargs: object
    ) -> AsyncIterator[str]:
        prompts.append(messages[0]["content"])
        yield "Hola."

    monkeypatch.setattr(llm, "_generate_ollama", generate)
    monkeypatch.setattr(llm_streaming, "ollama_chat_stream", stream)
    monkeypatch.setattr(
        document_search, "ollama_embed", AsyncMock(side_effect=httpx.ConnectError("offline"))
    )
    monkeypatch.setattr(
        "server.memory.recall_search.ollama_embed",
        AsyncMock(side_effect=httpx.ConnectError("offline")),
    )
    wording = AsyncMock(return_value=_WORDED)
    monkeypatch.setattr(document_answer, "ollama_chat", wording)
    return prompts, wording


async def _count(sql: str) -> int:
    cursor = await db.get_conn().execute(sql)
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    return int(row[0])


@pytest.mark.parametrize(
    "memory_enabled, documents_enabled, expected",
    [(True, False, False), (False, True, False), (True, True, True)],
    ids=["documents-off", "memory-off", "both-on"],
)
def test_the_document_answerer_is_none_unless_both_switches_are_on(
    monkeypatch: pytest.MonkeyPatch, memory_enabled: bool, documents_enabled: bool, expected: bool
) -> None:
    monkeypatch.setattr(settings, "memory_enabled", memory_enabled)
    monkeypatch.setattr(settings, "documents_enabled", documents_enabled)

    answerer = transcribe_module._document_answerer(httpx.AsyncClient(), AsyncMock())

    assert (answerer is not None) is expected


@pytest.mark.parametrize("route", _ROUTES)
async def test_a_document_question_names_its_document_and_asks_no_generic_model(
    household: tuple[PersonalSetupResult, int], monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, _ASK)
    prompts, wording = _models(monkeypatch)

    async with _client() as client:
        response = await client.post(route, files=_files())

    assert _spoken(response, route) == f"Según Manual de la lavadora: {_WORDED}"
    assert prompts == []
    wording.assert_awaited_once()
    assert await _count(_DOCUMENT_AUDIT) == 1


@pytest.mark.parametrize("route", _ROUTES)
async def test_nothing_found_a_general_question_and_a_stranger(
    household: tuple[PersonalSetupResult, int], monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, _STRONG_NOTHING, _GENERAL)
    prompts, wording = _models(monkeypatch)

    async with _client() as client:
        nothing = await client.post(route, files=_files())
        general = await client.post(route, files=_files())

    assert _spoken(nothing, route) == NOT_IN_DOCUMENTS
    assert _spoken(general, route) == "Hola."
    assert len(prompts) == 1
    wording.assert_not_awaited()


@pytest.mark.parametrize("route", _ROUTES)
async def test_no_face_hears_the_denial_and_nothing_is_read(
    household: tuple[PersonalSetupResult, int], monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    _hear(monkeypatch, "Según mis documentos, ¿qué dice del repuesto ZZK41?")
    _models(monkeypatch)

    async with _client() as client:
        response = await client.post(route, files=_files(with_frame=False))

    assert _spoken(response, route) == _REFUSAL
    assert "zzcanaryzz" not in response.text
    assert await _count(_DOCUMENT_AUDIT) == 0


async def test_a_recall_question_never_answers_from_a_document(
    household: tuple[PersonalSetupResult, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, _RECALL)
    _models(monkeypatch)

    async with _client() as client:
        response = await client.post("/transcribe", files=_files())

    assert _spoken(response, "/transcribe") == NO_MEMORY
    assert await _count(_DOCUMENT_AUDIT) == 0


async def test_the_record_keeps_the_marker_and_forgetting_leaves_no_byte(
    household: tuple[PersonalSetupResult, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    result, source_id = household
    monkeypatch.setattr(settings, "conversation_record_enabled", True)
    await grant_conversation_consent(
        result.owner_entity_id, notice_version="v1", now=datetime.now(UTC)
    )
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, _ASK)
    _models(monkeypatch)

    async with _client() as client:
        response = await client.post("/transcribe", files=_files())
    assert "ZZK41" in _spoken(response, "/transcribe")

    cursor = await db.get_conn().execute("SELECT said FROM conversation_turns")
    said = [str(row[0]) for row in await cursor.fetchall()]
    await cursor.close()
    assert said == [DOCUMENT_RECORDED_TEXT]
    assert await _count("SELECT COUNT(*) FROM recall_units") == 0

    await forget([Deletion(DeletionKind.DOCUMENT, source_id)], now=datetime.now(UTC))
    await db.close_db()
    db._conn = None

    database = settings.brain_db_path
    for path in (database, database.with_name(f"{database.name}-wal")):
        if path.exists():
            assert b"zzcanaryzz" not in path.read_bytes()
    await db.open_db()
