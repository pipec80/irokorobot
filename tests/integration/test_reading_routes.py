"""«Iroko, lee esto» and «sí, guárdalo» through the real voice routes (Plan 0088 Task B9, D-17).

Face detection, speech and the VLM are doubles; the identity store, the policy, the slot and the
document store are real. Every value is an invented canary; the frame is a blank JPEG whose bytes
must reach neither the database nor a log.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
from server.cognition.response_plan import (
    NOTHING_TO_READ,
    READ_OFFER,
    READ_SECRET,
    READING_KEPT,
    READING_RECORDED_TEXT,
)
from server.memory import document_store
from server.memory.conversation_consent import grant_conversation_consent
from server.memory.reading_offer import READING_SLOT
from server.routers import transcribe as transcribe_module
from server.settings import settings

from server import db
from tests.integration.test_document_routes import _models, household
from tests.integration.test_recall_routes import (
    _FRAME,
    _client,
    _files,
    _hear,
    _see_the_owner,
    _spoken,
)

if TYPE_CHECKING:
    from pathlib import Path

    from server.personal_setup import PersonalSetupResult

pytestmark = pytest.mark.integration

_CARD = "Leche descremada qqcardqq"
_ROUTES = ["/transcribe", "/transcribe/stream"]
__all__ = ["household"]  # the fixture, imported so this module can use it


@pytest.fixture
async def reading(
    household: tuple[PersonalSetupResult, int], monkeypatch: pytest.MonkeyPatch
) -> tuple[PersonalSetupResult, AsyncMock]:
    monkeypatch.setattr(settings, "vision_enabled", True)
    read = AsyncMock(return_value=_CARD)
    monkeypatch.setattr(transcribe_module, "read_text", read)
    READING_SLOT.clear()
    return household[0], read


async def _camera_titles(owner: int) -> list[str]:
    return [
        s.title
        for s in await document_store.sources_of(owner_entity_id=owner)
        if s.format == "camera"
    ]


@pytest.mark.parametrize("route", _ROUTES)
async def test_the_card_is_read_then_kept_on_the_next_turn(
    reading: tuple[PersonalSetupResult, AsyncMock], monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    result, read = reading
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "Iroko, lee esto", "Sí, guárdalo")
    prompts = _models(monkeypatch)

    async with _client() as client:
        first = await client.post(route, files=_files())
        second = await client.post(route, files=_files())

    assert _spoken(first, route) == f"{_CARD} {READ_OFFER}"
    assert _spoken(second, route) == READING_KEPT
    assert read.await_args is not None
    assert read.await_args.args[1] == _FRAME
    assert prompts == []
    titles = await _camera_titles(result.owner_entity_id)
    assert len(titles) == 1
    assert titles[0].startswith("Nota del ")


async def test_a_keep_after_questions_about_the_paper_keeps_it(
    reading: tuple[PersonalSetupResult, AsyncMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR 0041 decision 6: «sí, guárdalo» keeps the paper right after questions about it."""
    result, _ = reading
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "lee esto", "¿De qué se trata?", "¿Qué dice el papel?", "Sí, guárdalo")
    _models(monkeypatch)

    async with _client() as client:
        responses = [await client.post("/transcribe", files=_files()) for _ in range(4)]

    assert _spoken(responses[3], "/transcribe") == READING_KEPT
    assert len(await _camera_titles(result.owner_entity_id)) == 1


async def test_a_keep_after_talking_of_something_else_keeps_no_paper(
    reading: tuple[PersonalSetupResult, AsyncMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review finding 3 (Pipec, 2026-11-26): once the talk left the paper, «sí, guárdalo» may
    answer a memory offer, so it no longer keeps the paper."""
    result, _ = reading
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "lee esto", "Hola, ¿cómo estás?", "Sí, guárdalo")
    _models(monkeypatch)

    async with _client() as client:
        responses = [await client.post("/transcribe", files=_files()) for _ in range(3)]

    assert _spoken(responses[2], "/transcribe") != READING_KEPT
    assert await _camera_titles(result.owner_entity_id) == []


async def test_the_whole_paper_is_kept_though_only_the_start_is_spoken(
    reading: tuple[PersonalSetupResult, AsyncMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR 0041 decision 3: 400 characters are spoken, the whole paper is held and kept."""
    result, read = reading
    read.return_value = "Linea de relleno del papel. " * 30 + "Cierre qqfinalqq."
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "lee esto", "Sí, guárdalo")
    _models(monkeypatch)

    async with _client() as client:
        first = await client.post("/transcribe", files=_files())
        await client.post("/transcribe", files=_files())

    assert "qqfinalqq" not in _spoken(first, "/transcribe")
    (source,) = [
        s
        for s in await document_store.sources_of(owner_entity_id=result.owner_entity_id)
        if s.format == "camera"
    ]
    cursor = await db.get_conn().execute(
        "SELECT group_concat(body, ' ') FROM document_sections WHERE source_id = ?", (source.id,)
    )
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    assert "qqfinalqq" in str(row[0])


async def test_a_code_beyond_the_spoken_start_still_refuses_the_paper(
    reading: tuple[PersonalSetupResult, AsyncMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    result, read = reading
    read.return_value = "Linea de relleno del papel. " * 30 + "Clave del wifi: zorro4821"
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "lee esto", "Sí, guárdalo")
    _models(monkeypatch)

    async with _client() as client:
        first = await client.post("/transcribe", files=_files())
        await client.post("/transcribe", files=_files())

    assert _spoken(first, "/transcribe") == READ_SECRET
    assert await _camera_titles(result.owner_entity_id) == []


async def test_no_face_on_the_keeping_turn_keeps_nothing(
    reading: tuple[PersonalSetupResult, AsyncMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _ = reading
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "lee esto", "Sí, guárdalo")
    _models(monkeypatch)

    async with _client() as client:
        await client.post("/transcribe", files=_files())
        await client.post("/transcribe", files=_files(with_frame=False))

    assert await _camera_titles(result.owner_entity_id) == []


async def test_no_frame_says_its_phrase(
    reading: tuple[PersonalSetupResult, AsyncMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, read = reading
    _hear(monkeypatch, "lee esto")
    _models(monkeypatch)

    async with _client() as client:
        response = await client.post("/transcribe", files=_files(with_frame=False))

    assert _spoken(response, "/transcribe") == NOTHING_TO_READ
    read.assert_not_awaited()


async def test_a_card_with_a_code_is_not_read_and_not_offered(
    reading: tuple[PersonalSetupResult, AsyncMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    result, read = reading
    read.return_value = "Clave del wifi: zorro4821"
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "lee esto", "Sí, guárdalo")
    _models(monkeypatch)

    async with _client() as client:
        first = await client.post("/transcribe", files=_files())
        await client.post("/transcribe", files=_files())

    assert _spoken(first, "/transcribe") == READ_SECRET
    assert "zorro4821" not in first.text
    assert await _camera_titles(result.owner_entity_id) == []


async def test_the_reading_is_recorded_with_its_marker_and_no_frame_byte_is_kept(
    reading: tuple[PersonalSetupResult, AsyncMock],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    result, _ = reading
    monkeypatch.setattr(settings, "conversation_record_enabled", True)
    await grant_conversation_consent(
        result.owner_entity_id, notice_version="v1", now=datetime.now(UTC)
    )
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "lee esto")
    _models(monkeypatch)

    with caplog.at_level(logging.DEBUG):
        async with _client() as client:
            await client.post("/transcribe", files=_files())

    cursor = await db.get_conn().execute("SELECT said FROM conversation_turns")
    said = [str(row[0]) for row in await cursor.fetchall()]
    await cursor.close()
    assert said == [READING_RECORDED_TEXT]
    assert "qqcardqq" not in caplog.text
    database: Path = settings.brain_db_path
    await db.get_conn().commit()
    for path in (database, database.with_name(f"{database.name}-wal")):
        if path.exists():
            data = path.read_bytes()
            assert _FRAME[4:] not in data
            assert b"qqcardqq" not in data


async def test_a_kept_note_is_embedded_at_once_so_its_words_find_it(
    reading: tuple[PersonalSetupResult, AsyncMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    """«leche» names nothing specific: without a vector the gate would refuse the kept note."""
    result, _ = reading
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "lee esto", "Sí, guárdalo")
    _models(monkeypatch)
    embed = AsyncMock(return_value=[1.0] + [0.0] * 767)
    monkeypatch.setattr("server.memory.document_index.ollama_embed", embed)

    async with _client() as client:
        await client.post("/transcribe", files=_files())
        await client.post("/transcribe", files=_files())

    assert await _camera_titles(result.owner_entity_id)
    assert await document_store.sections_without_vector(10) == []
    embed.assert_awaited()


async def test_a_reading_with_no_identified_speaker_cannot_be_kept(
    reading: tuple[PersonalSetupResult, AsyncMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review: anyone on the network could plant a reading the owner's next «sí» would keep."""
    result, _ = reading
    _hear(monkeypatch, "lee esto", "Sí, guárdalo")
    _models(monkeypatch)

    async with _client() as client:
        await client.post("/transcribe", files=_files(with_frame=True))  # no face seen
        _see_the_owner(monkeypatch)
        await client.post("/transcribe", files=_files())

    assert await _camera_titles(result.owner_entity_id) == []


async def test_a_failing_keep_says_a_fixed_phrase_and_never_fails_the_turn(
    reading: tuple[PersonalSetupResult, AsyncMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "lee esto", "Sí, guárdalo")
    _models(monkeypatch)
    monkeypatch.setattr(
        transcribe_module, "keep_reading", AsyncMock(side_effect=RuntimeError("locked"))
    )

    async with _client() as client:
        await client.post("/transcribe", files=_files())
        second = await client.post("/transcribe", files=_files())

    assert second.status_code == 200
