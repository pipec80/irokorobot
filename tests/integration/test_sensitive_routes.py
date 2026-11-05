"""The sensitive read and the secret guard through the real routes (Plan 0079 Task 8, ADR 0029).

Face detection, speech and the local model are doubles; the identity store, the policy, the audit,
the stored values and the conversation record are real. Every value is an invented canary.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
import io
import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock
import wave

import cv2
from httpx import ASGITransport, AsyncClient
import numpy as np
from pydantic import SecretStr
import pytest
from server.cognition import face_authentication as face_auth_module
from server.cognition.owner_authentication import owner_unlock_service
from server.cognition.response_plan import (
    NOT_ALONE,
    SECRET_RECORDED_TEXT,
    SECRET_REFUSAL,
    SENSITIVE_RECORDED_TEXT,
    ResponsePlan,
)
from server.main import app
from server.memory import continuity
from server.memory.biometric_consent import grant_face_consent
from server.memory.canonical_writer import WriteChannel, write_literal
from server.memory.conversation_consent import grant_conversation_consent
from server.personal_setup import PersonalSetupInput, PersonalSetupResult, apply_personal_setup
from server.resources import AppResources
from server.routers import transcribe as transcribe_module
from server.settings import settings
from server.vision.faces import DetectedFace, enroll_face

from server import db, llm, llm_streaming, stt, tts

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator
    from pathlib import Path

    import httpx

pytestmark = pytest.mark.integration

_FRAME = cv2.imencode(".jpg", np.zeros((10, 10, 3), dtype=np.uint8))[1].tobytes()
_OWNER_FACE = np.eye(512, dtype=np.float32)[0]
_STRANGER_FACE = np.eye(512, dtype=np.float32)[1]
_BIRTHDAY_QUESTION = "¿Cuándo es mi cumpleaños?"
_BIRTHDAY_ANSWER = "Tu cumpleaños es el 3 de marzo."
_GENERIC = "Hola, ¿cómo estás?"
_DATE_QUESTION = "¿Qué fecha es hoy?"
_STATED = "Mi clave es 4821"
_ASKED = "¿Cuál es mi clave?"
_STATED_AND_ASKED = "¿Cuándo es mi cumpleaños? Mi clave es 4821"
_VOICE_ROUTES = ["/transcribe", "/transcribe/stream"]
_ALL_ROUTES = [*_VOICE_ROUTES, "/chat", "/vision/respond"]
_READ_AUDIT = (
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
    """A face-enrolled owner whose birthday is stored; every switch of Plan 0079 on."""
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "sensitive-routes.db")
    monkeypatch.setattr(settings, "face_authentication_enabled", True)
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "conversation_record_enabled", True)
    monkeypatch.setattr(settings, "sensitive_read_enabled", True)
    continuity.reset()
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    result = await apply_personal_setup(
        PersonalSetupInput(owner_name="Canary", child_names=(), pin=SecretStr("482173"))
    )
    await grant_face_consent(result.owner_entity_id)
    await enroll_face(result.owner_entity_id, _OWNER_FACE, label="Canary")
    await write_literal(
        owner_entity_id=result.owner_entity_id,
        subject_entity_id=result.owner_entity_id,
        predicate="birth_date",
        value="1990-03-03",
        channel=WriteChannel.IMPORT_FILE,
        confirmed_at="2026-11-05T09:00:00.000000+00:00",
    )
    yield result
    continuity.reset()
    await db.close_db()
    db._conn = None


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    capture = AsyncMock()
    monkeypatch.setattr(transcribe_module, "capture_turn", capture)
    return capture


@asynccontextmanager
async def _client() -> AsyncGenerator[AsyncClient]:
    async with AsyncClient() as http_client:
        app.state.resources = AppResources(
            http_client=http_client, owner_unlock_service=owner_unlock_service
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client


def _see(monkeypatch: pytest.MonkeyPatch, *faces: np.ndarray) -> None:
    detected = [DetectedFace(embedding=face, score=0.9, width=200.0) for face in faces]
    monkeypatch.setattr(face_auth_module, "_detect_faces_default", AsyncMock(return_value=detected))


def _hear(monkeypatch: pytest.MonkeyPatch, *sentences: str) -> None:
    monkeypatch.setattr(stt, "transcribe", AsyncMock(side_effect=list(sentences)))
    monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("AAAA", 42)))


def _model(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Script the generic model on every route; return the prompts it was asked with."""
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
    return prompts


class _Reply:
    """What a route answered, normalized across the four wire shapes."""

    def __init__(self, route: str, response: httpx.Response) -> None:
        self.status_code = response.status_code
        self.route = route
        self.body: dict[str, object] = {}
        self.events: list[dict[str, object]] = []
        if route == "/transcribe/stream":
            self.events = [json.loads(line) for line in response.text.splitlines() if line]
        else:
            self.body = response.json()

    @property
    def spoken(self) -> str:
        if self.route == "/transcribe/stream":
            return " ".join(str(e["text"]) for e in self.events if e["type"] == "audio")
        key = "response" if self.route == "/chat" else "llm_response"
        return str(self.body[key])

    @property
    def shape(self) -> list[str]:
        """The wire fields: the body keys, or the event types and the `done` keys."""
        if self.route == "/transcribe/stream":
            done = next(e for e in self.events if e["type"] == "done")
            return [str(e["type"]) for e in self.events] + sorted(done)
        return sorted(self.body)


async def _post(
    client: AsyncClient, route: str, message: str, *, with_frame: bool = True
) -> _Reply:
    match route:
        case "/chat":
            response = await client.post("/chat", json={"message": message, "conversation_id": "w"})
        case "/vision/respond":
            response = await client.post(
                route,
                files={"image": ("frame.jpg", _FRAME, "image/jpeg")},
                data={"text": message},
            )
        case _:
            response = await client.post(route, files=_files(with_frame=with_frame))
    return _Reply(route, response)


def _hear_for(monkeypatch: pytest.MonkeyPatch, route: str, message: str) -> None:
    if route in _VOICE_ROUTES:
        _hear(monkeypatch, message)
    else:
        _hear(monkeypatch)  # the TTS only: /chat and /vision/respond take the text directly


async def _count(sql: str) -> int:
    cursor = await db.get_conn().execute(sql)
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    return int(row[0])


@pytest.mark.parametrize(
    "memory_enabled, sensitive_enabled, expected",
    [(True, False, False), (False, True, False), (True, True, True)],
    ids=["read-off", "memory-off", "both-on"],
)
def test_the_reader_is_built_only_with_both_switches(
    monkeypatch: pytest.MonkeyPatch, memory_enabled: bool, sensitive_enabled: bool, expected: bool
) -> None:
    monkeypatch.setattr(settings, "memory_enabled", memory_enabled)
    monkeypatch.setattr(settings, "sensitive_read_enabled", sensitive_enabled)

    reader = transcribe_module._sensitive_reader(Mock(), Mock())

    assert (reader is not None) is expected


@pytest.mark.parametrize("route", _VOICE_ROUTES)
@pytest.mark.parametrize("message", [_BIRTHDAY_QUESTION, _GENERIC])
async def test_with_the_switch_off_every_read_route_is_byte_identical(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, route: str, message: str
) -> None:
    """Switch off, a sensitive question is the generic turn of main: same model call, same wire."""
    monkeypatch.setattr(settings, "sensitive_read_enabled", False)
    untouchable = Mock(side_effect=AssertionError("sensitive code ran with the switch off"))
    monkeypatch.setattr(transcribe_module, "sensitive_reply", untouchable)
    _see(monkeypatch, _OWNER_FACE)
    _hear(monkeypatch, message, _GENERIC)
    prompts = _model(monkeypatch)

    async with _client() as client:
        asked = await _post(client, route, message)
        reference = await _post(client, route, _GENERIC)

    assert asked.status_code == 200
    assert asked.spoken == reference.spoken == "Hola."
    assert asked.shape == reference.shape
    assert len(prompts) == 2
    untouchable.assert_not_called()
    assert await _count(_READ_AUDIT) == 0


@pytest.mark.parametrize("route", [*_VOICE_ROUTES, "/chat"])
async def test_with_memory_off_a_secret_is_byte_identical(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    """Memory off, a secret turn is an ordinary conversation: the model answers it."""
    monkeypatch.setattr(settings, "memory_enabled", False)
    _see(monkeypatch, _OWNER_FACE)
    _hear_for(monkeypatch, route, _STATED)
    prompts = _model(monkeypatch)

    async with _client() as client:
        reply = await _post(client, route, _STATED)

    assert reply.status_code == 200
    assert reply.spoken == "Hola."
    assert len(prompts) == 1


@pytest.mark.parametrize("route", _ALL_ROUTES)
@pytest.mark.parametrize("message", [_STATED, _ASKED, _STATED_AND_ASKED])
async def test_a_stated_secret_on_each_route(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, route: str, message: str
) -> None:
    _see(monkeypatch, _OWNER_FACE)
    _hear_for(monkeypatch, route, message)
    prompts = _model(monkeypatch)

    async with _client() as client:
        reply = await _post(client, route, message)

    assert reply.status_code == 200
    assert reply.spoken == SECRET_REFUSAL
    assert prompts == []
    assert await _count(_READ_AUDIT) == 0


@pytest.mark.parametrize("route", _VOICE_ROUTES)
@pytest.mark.parametrize("message", [_STATED, _STATED_AND_ASKED])
async def test_a_secret_turn_is_recorded_with_the_marker_and_no_unit(
    household: PersonalSetupResult,
    monkeypatch: pytest.MonkeyPatch,
    route: str,
    message: str,
) -> None:
    """The real capture: the words never reach the record, the unit table or the candidates."""
    monkeypatch.setattr(settings, "recall_enabled", True)
    await grant_conversation_consent(
        household.owner_entity_id, notice_version="v1", now=datetime.now(UTC)
    )
    _see(monkeypatch, _OWNER_FACE)
    _hear(monkeypatch, message)
    _model(monkeypatch)

    async with _client() as client:
        reply = await _post(client, route, message)

    assert reply.spoken == SECRET_REFUSAL
    cursor = await db.get_conn().execute("SELECT turns FROM conversation_records")
    rows = await cursor.fetchall()
    await cursor.close()
    stored = json.dumps([row[0] for row in rows], ensure_ascii=False)
    assert SECRET_RECORDED_TEXT in stored
    assert "4821" not in stored
    assert await _count("SELECT COUNT(*) FROM recall_units") == 0
    assert await _count("SELECT COUNT(*) FROM memory_candidates") == 0
    cursor = await db.get_conn().execute(
        "SELECT json_extract(turns, '$[0].voice') FROM conversation_records"
    )
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    assert row[0] == "not_checked"


@pytest.mark.parametrize("route", _VOICE_ROUTES)
async def test_a_secret_turn_hands_the_marker_to_the_recorder(
    household: PersonalSetupResult,
    captured: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    route: str,
) -> None:
    _see(monkeypatch, _OWNER_FACE)
    _hear(monkeypatch, _STATED)
    _model(monkeypatch)

    async with _client() as client:
        await _post(client, route, _STATED)

    heard, said, actor = captured.await_args_list[-1].args
    assert (heard, said) == (SECRET_RECORDED_TEXT, SECRET_REFUSAL)
    assert actor is None


@pytest.mark.parametrize("route", _ALL_ROUTES)
async def test_the_secret_guard_runs_with_the_record_off(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    monkeypatch.setattr(settings, "conversation_record_enabled", False)
    monkeypatch.setattr(settings, "sensitive_read_enabled", False)
    _see(monkeypatch, _OWNER_FACE)
    _hear_for(monkeypatch, route, _STATED)
    prompts = _model(monkeypatch)

    async with _client() as client:
        reply = await _post(client, route, _STATED)

    assert reply.spoken == SECRET_REFUSAL
    assert prompts == []


async def test_the_voice_controller_without_an_identity_still_guards_secrets(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ruling 23: the secret rule serves every speaker, with or without a request identity."""
    prompts = _model(monkeypatch)
    event = transcribe_module._voice_event_from_transcript(_STATED)
    async with AsyncClient() as http_client:
        decision = await transcribe_module._voice_controller(http_client).decide(event)

    assert isinstance(decision, ResponsePlan)
    assert decision.response == SECRET_REFUSAL
    assert prompts == []


@pytest.mark.parametrize("route", _VOICE_ROUTES)
async def test_a_sensitive_answer_is_recorded_with_the_marker(
    household: PersonalSetupResult,
    captured: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    route: str,
) -> None:
    _see(monkeypatch, _OWNER_FACE)
    _hear(monkeypatch, _BIRTHDAY_QUESTION)
    prompts = _model(monkeypatch)

    async with _client() as client:
        reply = await _post(client, route, _BIRTHDAY_QUESTION)

    assert reply.spoken == _BIRTHDAY_ANSWER
    assert prompts == []
    heard, said, actor = captured.await_args_list[-1].args
    assert (heard, said) == (_BIRTHDAY_QUESTION, SENSITIVE_RECORDED_TEXT)
    assert actor is not None
    assert actor.person_id == household.owner_entity_id
    assert await _count(_READ_AUDIT) == 1


@pytest.mark.parametrize("route", _VOICE_ROUTES)
async def test_a_two_face_frame_hears_not_alone(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    _see(monkeypatch, _OWNER_FACE, _STRANGER_FACE)
    _hear(monkeypatch, _BIRTHDAY_QUESTION, _DATE_QUESTION)
    _model(monkeypatch)

    async with _client() as client:
        alone = await _post(client, route, _BIRTHDAY_QUESTION)
        generic = await _post(client, route, _DATE_QUESTION)

    assert alone.spoken == NOT_ALONE
    assert _BIRTHDAY_ANSWER not in alone.spoken
    assert await _count(_READ_AUDIT) == 0
    # The wire of a deterministic reply is the one of any other fixed reply: no new field.
    if route == "/transcribe/stream":
        done_alone = next(e for e in alone.events if e["type"] == "done")
        done_generic = next(e for e in generic.events if e["type"] == "done")
        assert sorted(done_alone) == sorted(done_generic)
    else:
        assert alone.shape == generic.shape
