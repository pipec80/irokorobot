"""«¿Qué ves?» over streaming, from the turn's own frame (Plan 0089 Task 8, D-2 to D-5).

Face detection, speech and the VLM are doubles; the identity store and the record are real. The
description is an invented canary; the frame is a blank JPEG whose bytes must reach neither the
database nor a log.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
from server.cognition.response_plan import (
    READING_RECORDED_TEXT,
    SCENE_FAILED_PHRASE,
    SCENE_RECORDED_TEXT,
)
from server.exceptions import VisionError
from server.memory.conversation_consent import grant_conversation_consent
from server.memory.reading_offer import READING_SLOT
from server.routers import transcribe as transcribe_module
from server.settings import settings

from server import db
from tests.integration.test_recall_routes import (
    _FRAME,
    _client,
    _files,
    _hear,
    _models,
    _see_the_owner,
    household,
)

if TYPE_CHECKING:
    from pathlib import Path

    import httpx
    from server.personal_setup import PersonalSetupResult

pytestmark = pytest.mark.integration

_SCENE = "Una taza amarilla qqtazaqq sobre la mesa."
_UNAVAILABLE = "Ahora mismo no puedo mirar desde este canal."
__all__ = ["household"]  # the fixture, imported so this module can use it


@pytest.fixture
def scene(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Vision on, a face-authenticated route, and a VLM double that describes the canary."""
    monkeypatch.setattr(settings, "vision_enabled", True)
    monkeypatch.setattr(settings, "face_authentication_enabled", True)
    perceive = AsyncMock(return_value=_SCENE)
    monkeypatch.setattr(transcribe_module, "perceive_scene", perceive)
    READING_SLOT.clear()
    return perceive


def _events(response: httpx.Response) -> list[dict[str, object]]:
    return [json.loads(line) for line in response.text.splitlines() if line]


def _spoken(response: httpx.Response) -> str:
    return " ".join(str(e["text"]) for e in _events(response) if e["type"] == "audio")


async def _recorded() -> list[tuple[str, str]]:
    cursor = await db.get_conn().execute("SELECT heard, said FROM conversation_turns")
    rows = [(str(row[0]), str(row[1])) for row in await cursor.fetchall()]
    await cursor.close()
    return rows


async def _record_on(owner: int, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "conversation_record_enabled", True)
    await grant_conversation_consent(owner, notice_version="v1", now=datetime.now(UTC))


async def test_a_scene_is_described_from_the_turn_s_frame_and_recorded_as_a_marker(
    household: PersonalSetupResult, scene: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _record_on(household.owner_entity_id, monkeypatch)
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "¿Qué ves?")
    prompts, _wording = _models(monkeypatch)

    async with _client() as client:
        response = await client.post("/transcribe/stream", files=_files())

    assert [e["type"] for e in _events(response)] == ["text_heard", "emotion", "audio", "done"]
    assert _spoken(response) == _SCENE
    scene.assert_awaited_once()
    assert scene.await_args is not None
    assert scene.await_args.args[1] == _FRAME
    assert prompts == []  # the text model was never called
    assert await _recorded() == [("¿Qué ves?", SCENE_RECORDED_TEXT)]


async def test_a_failed_vision_call_says_so_and_is_recorded_verbatim(
    household: PersonalSetupResult, scene: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _record_on(household.owner_entity_id, monkeypatch)
    scene.side_effect = VisionError("down")
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "¿Qué ves?")
    _models(monkeypatch)

    async with _client() as client:
        response = await client.post("/transcribe/stream", files=_files())

    assert _spoken(response) == SCENE_FAILED_PHRASE
    assert await _recorded() == [("¿Qué ves?", SCENE_FAILED_PHRASE)]


@pytest.mark.parametrize("off", ["no_frame", "vision_off", "face_auth_off"])
async def test_without_a_frame_or_a_switch_the_fixed_phrase_and_no_vlm(
    household: PersonalSetupResult, scene: AsyncMock, monkeypatch: pytest.MonkeyPatch, off: str
) -> None:
    if off == "vision_off":
        monkeypatch.setattr(settings, "vision_enabled", False)
    if off == "face_auth_off":
        monkeypatch.setattr(settings, "face_authentication_enabled", False)
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "¿Qué ves?")
    _models(monkeypatch)

    async with _client() as client:
        response = await client.post(
            "/transcribe/stream", files=_files(with_frame=off != "no_frame")
        )

    assert _spoken(response) == _UNAVAILABLE
    scene.assert_not_awaited()


async def test_a_reading_still_reads_and_never_describes(
    household: PersonalSetupResult, scene: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "documents_enabled", True)
    read = AsyncMock(return_value="Leche qqcardqq")
    monkeypatch.setattr(transcribe_module, "read_text", read)
    await _record_on(household.owner_entity_id, monkeypatch)
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "¿Qué dice aquí?")
    _models(monkeypatch)

    async with _client() as client:
        await client.post("/transcribe/stream", files=_files())

    read.assert_awaited_once()
    scene.assert_not_awaited()
    assert await _recorded() == [("¿Qué dice aquí?", READING_RECORDED_TEXT)]


async def test_the_frame_and_the_description_reach_no_file_and_no_log(
    household: PersonalSetupResult,
    scene: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await _record_on(household.owner_entity_id, monkeypatch)
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "¿Qué ves?")
    _models(monkeypatch)

    with caplog.at_level(logging.DEBUG):
        async with _client() as client:
            await client.post("/transcribe/stream", files=_files())

    assert "qqtazaqq" not in caplog.text
    await db.get_conn().commit()
    database: Path = settings.brain_db_path
    for path in (database, database.with_name(f"{database.name}-wal")):
        if path.exists():
            data = path.read_bytes()
            assert _FRAME[4:] not in data
            assert b"qqtazaqq" not in data
