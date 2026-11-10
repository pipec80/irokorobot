"""Recall through the real voice routes (Plan 0078 Task 9, ADR 0028 decisions 4, 5 and 8).

Face detection, speech and the local model are doubles; the identity store, the policy, the audit,
the recall units and their search are real. Every value is an invented canary.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
import io
import json
import logging
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
import wave

import cv2
import httpx
from httpx import ASGITransport, AsyncClient
import numpy as np
from pydantic import SecretStr
import pytest
from server.cognition import controller as controller_module, face_authentication as face_auth
from server.cognition.owner_authentication import owner_unlock_service
from server.cognition.response_plan import NO_MEMORY, RECALL_LOGGED_TEXT
from server.conversation_log import CONVERSATION_LOGGER_NAME, set_enabled
from server.main import app
from server.memory import continuity, recall_answer, recall_search, recall_store
from server.memory.biometric_consent import grant_face_consent
from server.memory.conversation_types import RecordedTurn, TurnVerdict
from server.personal_setup import PersonalSetupInput, PersonalSetupResult, apply_personal_setup
from server.resources import AppResources
from server.routers import transcribe as transcribe_module
from server.settings import settings
from server.vision.faces import DetectedFace, enroll_face

from server import db, llm, llm_streaming, stt, tts

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_FRAME = cv2.imencode(".jpg", np.zeros((10, 10, 3), dtype=np.uint8))[1].tobytes()
_OWNER_FACE = np.eye(512, dtype=np.float32)[0]
_STRONG = "¿Qué te conté del cerro?"
_WEAK = "¿Te acuerdas de Mozart?"
_GENERIC = "Hola, ¿cómo estás?"
_ANSWER = "Sí, me contaste que fuiste al cerro con Zeta."
_REFUSAL = "Todavía no puedo confirmar quién eres para contarte lo que sé de ti."
_RECALL_AUDIT = (
    "SELECT COUNT(*) FROM authorization_audit_events "
    "WHERE action = 'read_personal_conversation_memory'"
)


def _wav() -> bytes:
    t = np.linspace(0.0, 3.0, 48_000, endpoint=False)
    samples = (8_000 * np.sin(2 * np.pi * 220 * t)).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(samples.tobytes())
    return buffer.getvalue()


def _files(*, with_frame: bool = True) -> dict[str, tuple[str, bytes, str]]:
    files = {"audio": ("a.wav", _wav(), "audio/wav")}
    if with_frame:
        files["frame"] = ("frame.jpg", _FRAME, "image/jpeg")
    return files


@pytest.fixture
async def household(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[PersonalSetupResult]:
    """A face-enrolled owner with one recalled sentence: «fuimos al cerro con Zeta»."""
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "recall-routes.db")
    monkeypatch.setattr(settings, "face_authentication_enabled", True)
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "recall_enabled", True)
    continuity.reset()
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    result = await apply_personal_setup(
        PersonalSetupInput(owner_name="Canary", child_names=("Hija Uno",), pin=SecretStr("482173"))
    )
    await grant_face_consent(result.owner_entity_id)
    await enroll_face(result.owner_entity_id, _OWNER_FACE, label="Canary")
    await _remember(result.owner_entity_id, "fuimos al cerro con Zeta")
    yield result
    continuity.reset()
    await db.close_db()
    db._conn = None


async def _remember(owner: int, heard: str) -> None:
    said = datetime.now(UTC) - timedelta(days=1)
    async with db.transaction() as conn:
        cursor = await conn.execute(
            "INSERT INTO conversation_records (owner_entity_id, started_at, last_turn_at, "
            "closed_at, expires_at) VALUES (?, 't', 't', 't', ?)",
            (owner, (datetime.now(UTC) + timedelta(days=30)).isoformat()),
        )
        record_id = int(cursor.lastrowid or 0)
        await cursor.close()
        turn = RecordedTurn(
            at=said, heard=heard, said="ok", voice=TurnVerdict.VERIFIED, correlation_id=uuid4()
        )
        await recall_store.insert_turn_unit(
            conn, record_id=record_id, owner_entity_id=owner, turn=turn
        )


@asynccontextmanager
async def _client() -> AsyncGenerator[AsyncClient]:
    async with AsyncClient() as http_client:
        app.state.resources = AppResources(
            http_client=http_client, owner_unlock_service=owner_unlock_service
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client


def _see_the_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    detected = DetectedFace(embedding=_OWNER_FACE, score=0.9, width=200.0)
    monkeypatch.setattr(face_auth, "_detect_faces_default", AsyncMock(return_value=[detected]))


def _hear(monkeypatch: pytest.MonkeyPatch, *sentences: str) -> None:
    monkeypatch.setattr(stt, "transcribe", AsyncMock(side_effect=list(sentences)))
    monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("AAAA", 42)))


def _models(monkeypatch: pytest.MonkeyPatch) -> tuple[list[str], AsyncMock]:
    """Script the generic model (both routes), the recall wording, and an absent embedder."""
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
        recall_search, "ollama_embed", AsyncMock(side_effect=httpx.ConnectError("offline"))
    )
    wording = AsyncMock(return_value=_ANSWER)
    monkeypatch.setattr(recall_answer, "ollama_chat", wording)
    return prompts, wording


def _spoken(response: httpx.Response, route: str) -> str:
    if route == "/transcribe":
        return str(response.json()["llm_response"])
    events = [json.loads(line) for line in response.text.splitlines() if line]
    return " ".join(str(event["text"]) for event in events if event["type"] == "audio")


async def _audit_rows() -> int:
    cursor = await db.get_conn().execute(_RECALL_AUDIT)
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    return int(row[0])


_ROUTES = ["/transcribe", "/transcribe/stream"]


@pytest.mark.parametrize(
    "memory_enabled, recall_enabled, expected",
    [(True, False, False), (False, True, False), (True, True, True)],
    ids=["recall-off", "memory-off", "both-on"],
)
def test_the_recall_answerer_is_none_unless_both_switches_are_on(
    monkeypatch: pytest.MonkeyPatch, memory_enabled: bool, recall_enabled: bool, expected: bool
) -> None:
    monkeypatch.setattr(settings, "memory_enabled", memory_enabled)
    monkeypatch.setattr(settings, "recall_enabled", recall_enabled)

    answerer = transcribe_module._recall_answerer(httpx.AsyncClient())

    assert (answerer is not None) is expected


@pytest.mark.parametrize("route", _ROUTES)
async def test_a_strong_cue_with_hits_answers_from_them(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, _STRONG)
    prompts, wording = _models(monkeypatch)

    async with _client() as client:
        response = await client.post(route, files=_files())

    assert response.status_code == 200
    assert _spoken(response, route) == _ANSWER
    assert prompts == []  # the generic model was never asked
    wording.assert_awaited_once()
    assert await _audit_rows() == 1


@pytest.mark.parametrize("route", _ROUTES)
async def test_a_strong_cue_without_hits_says_it_does_not_remember(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "¿Qué te conté de la playa?")
    prompts, wording = _models(monkeypatch)

    async with _client() as client:
        response = await client.post(route, files=_files())

    assert _spoken(response, route) == NO_MEMORY
    assert prompts == []
    wording.assert_not_awaited()


@pytest.mark.parametrize("route", _ROUTES)
async def test_a_stranger_strong_cue_hears_the_refusal_and_a_weak_cue_converses(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    _hear(monkeypatch, _STRONG, _WEAK)
    prompts, wording = _models(monkeypatch)

    async with _client() as client:
        strong = await client.post(route, files=_files(with_frame=False))
        weak = await client.post(route, files=_files(with_frame=False))

    assert _spoken(strong, route) == _REFUSAL
    assert "Zeta" not in strong.text
    assert _spoken(weak, route) == "Hola."
    assert len(prompts) == 1
    wording.assert_not_awaited()
    assert await _audit_rows() == 0


@pytest.mark.parametrize("route", _ROUTES)
async def test_the_recall_answer_is_not_written_to_continuity(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    pairs = Mock(return_value=True)
    monkeypatch.setattr(continuity, "record_pair", pairs)
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, _STRONG)
    _models(monkeypatch)

    async with _client() as client:
        response = await client.post(route, files=_files())

    assert _spoken(response, route) == _ANSWER
    pairs.assert_not_called()


@pytest.mark.parametrize("route", _ROUTES)
@pytest.mark.parametrize("message", ["¿Qué te conté ayer?", _STRONG, _GENERIC])
async def test_with_recall_disabled_every_route_is_byte_identical(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, route: str, message: str
) -> None:
    """With the switch off nothing of Plan 0078 runs: the turn is the one of main."""
    monkeypatch.setattr(settings, "recall_enabled", False)
    untouchable = Mock(side_effect=AssertionError("recall code ran with the switch off"))
    monkeypatch.setattr(controller_module, "classify_recall_cue", untouchable)
    monkeypatch.setattr(transcribe_module, "recall_reply", untouchable)
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, message)
    prompts, wording = _models(monkeypatch)

    async with _client() as client:
        response = await client.post(route, files=_files())

    assert response.status_code == 200
    assert _spoken(response, route) == "Hola."
    assert len(prompts) == 1
    untouchable.assert_not_called()
    wording.assert_not_awaited()
    assert await _audit_rows() == 0


@pytest.mark.parametrize("route", _ROUTES)
async def test_a_generic_turn_has_the_same_prompt_with_recall_on_and_off(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, _GENERIC, _GENERIC)
    prompts, _ = _models(monkeypatch)

    async with _client() as client:
        await client.post(route, files=_files())
        continuity.reset()
        monkeypatch.setattr(settings, "recall_enabled", False)
        await client.post(route, files=_files())

    on, off = prompts
    assert on == off
    assert "cerro" not in on


@pytest.mark.parametrize("route", _ROUTES)
async def test_the_opt_in_log_shows_the_marker(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    messages: list[str] = []

    class Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            messages.append(record.getMessage())

    conversation = logging.getLogger(CONVERSATION_LOGGER_NAME)
    collector = Collector(level=logging.DEBUG)
    conversation.addHandler(collector)
    was_disabled = conversation.disabled
    set_enabled(True)
    try:
        _see_the_owner(monkeypatch)
        _hear(monkeypatch, _STRONG)
        _models(monkeypatch)
        async with _client() as client:
            response = await client.post(route, files=_files())
    finally:
        conversation.removeHandler(collector)
        conversation.disabled = was_disabled

    assert response.status_code == 200
    spoken = [message for message in messages if message.startswith("Spoken")]
    assert spoken == [f"Spoken: {RECALL_LOGGED_TEXT}"]
    assert not any("Zeta" in message for message in messages)


_BEACH_STORY = "fui a la playa con Zeta"
_NOT_RECORDED = "No tengo registrado cuándo fue."


@pytest.mark.parametrize("route", _ROUTES)
async def test_a_when_question_answers_with_the_day_it_was_told_and_asks_no_model(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    """Plan 0080 D-8 and D-9: «¿cuándo fui…?» is not the told day, «¿cuándo te conté…?» is."""
    await _remember(household.owner_entity_id, _BEACH_STORY)
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "¿Cuándo fui a la playa?", "¿Cuándo te conté de la playa?")
    prompts, wording = _models(monkeypatch)

    async with _client() as client:
        happened = await client.post(route, files=_files())
        told = await client.post(route, files=_files())

    assert _spoken(happened, route) == (
        f"{_NOT_RECORDED} Sí recuerdo que ayer me contaste esto: {_BEACH_STORY}"
    )
    assert _spoken(told, route) == f"Ayer me contaste esto: {_BEACH_STORY}"
    assert prompts == []  # the generic model was never asked
    wording.assert_not_awaited()  # nor the recall wording: the answer is a table
    assert await _audit_rows() == 2


@pytest.mark.parametrize("route", _ROUTES)
@pytest.mark.parametrize("question", ["¿Cuándo fui a la playa?", "¿Cuándo te conté de la playa?"])
async def test_a_when_question_with_nothing_told_says_it_does_not_remember(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, route: str, question: str
) -> None:
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, question)
    prompts, wording = _models(monkeypatch)

    async with _client() as client:
        response = await client.post(route, files=_files())

    assert _spoken(response, route) == NO_MEMORY
    assert prompts == []
    wording.assert_not_awaited()


@pytest.mark.parametrize("route", _ROUTES)
@pytest.mark.parametrize(
    "question", ["¿Cuándo fue el mundial de 2010?", "Cuando fui a la playa me quemé"]
)
async def test_a_trap_is_ordinary_conversation_and_reads_no_diary(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, route: str, question: str
) -> None:
    await _remember(household.owner_entity_id, _BEACH_STORY)
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, question)
    prompts, wording = _models(monkeypatch)

    async with _client() as client:
        response = await client.post(route, files=_files())

    assert _spoken(response, route) == "Hola."
    assert len(prompts) == 1
    wording.assert_not_awaited()
    assert await _audit_rows() == 0
