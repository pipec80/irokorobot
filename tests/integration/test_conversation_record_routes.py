"""The voice routes record every spoken reply (Plan 0076 Task 7, ADR 0027).

``capture_turn`` is replaced by a double: these tests pin what each route hands it (what was
heard, what was said, the speaker) and when. Face detection is a double; models are scripted.
Every value is an invented canary.
"""

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
import io
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4
import wave

import cv2
from httpx import ASGITransport, AsyncClient
import numpy as np
from pydantic import SecretStr
import pytest
from server.cognition import face_authentication as face_auth_module
from server.cognition.identity import ActivePersonStatus
from server.cognition.owner_authentication import owner_unlock_service
from server.exceptions import LLMError, UnclearSpeechError
from server.main import app
from server.memory.biometric_consent import grant_face_consent
from server.personal_setup import PersonalSetupInput, PersonalSetupResult, apply_personal_setup
from server.resources import AppResources
from server.routers import transcribe as transcribe_module
from server.settings import settings
from server.vision.faces import DetectedFace, enroll_face

from server import db, llm, llm_streaming, stt, tts

pytestmark = pytest.mark.integration

_PIN = "482173"
_FRAME = cv2.imencode(".jpg", np.zeros((10, 10, 3), dtype=np.uint8))[1].tobytes()
_OWNER_FACE = np.eye(512, dtype=np.float32)[0]
_HEARD = "Hola, Zeta, ¿cómo estás?"


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
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "record-routes.db")
    monkeypatch.setattr(settings, "face_authentication_enabled", True)
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "conversation_record_enabled", True)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    result = await apply_personal_setup(
        PersonalSetupInput(owner_name="Canary", child_names=(), pin=SecretStr(_PIN))
    )
    await grant_face_consent(result.owner_entity_id)
    await enroll_face(result.owner_entity_id, _OWNER_FACE, label="Canary")
    yield result
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


def _see_the_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    detected = DetectedFace(embedding=_OWNER_FACE, score=0.9, width=200.0)
    monkeypatch.setattr(
        face_auth_module, "_detect_faces_default", AsyncMock(return_value=[detected])
    )


def _hear(monkeypatch: pytest.MonkeyPatch, sentence: str = _HEARD) -> None:
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value=sentence))
    monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("AAAA", 42)))


def _classic_reply(monkeypatch: pytest.MonkeyPatch, reply: str = "Muy bien.") -> None:
    monkeypatch.setattr(llm, "_generate_ollama", AsyncMock(return_value=(reply, "neutral")))


def _stream_reply(monkeypatch: pytest.MonkeyPatch, reply: str = "Muy bien.") -> None:
    async def stream(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        yield reply

    monkeypatch.setattr(llm_streaming, "ollama_chat_stream", stream)


@pytest.mark.parametrize(
    "memory_enabled, record_enabled, expected",
    [(True, False, False), (False, True, False), (True, True, True)],
    ids=["record-off", "memory-off", "both-on"],
)
def test_turn_recorder_is_none_unless_both_switches_are_on(
    monkeypatch: pytest.MonkeyPatch, memory_enabled: bool, record_enabled: bool, expected: bool
) -> None:
    monkeypatch.setattr(settings, "memory_enabled", memory_enabled)
    monkeypatch.setattr(settings, "conversation_record_enabled", record_enabled)
    event = transcribe_module._voice_event_from_transcript("hola")

    recorder = transcribe_module._turn_recorder(AsyncMock(), event=event, wav_bytes=b"RIFF-canary")

    assert (recorder is not None) is expected


@pytest.mark.parametrize("route", ["/transcribe", "/transcribe/stream"])
async def test_a_generic_turn_records_what_was_heard_said_and_the_speaker(
    household: PersonalSetupResult,
    captured: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    route: str,
) -> None:
    _see_the_owner(monkeypatch)
    _hear(monkeypatch)
    _classic_reply(monkeypatch)
    _stream_reply(monkeypatch)

    async with _client() as client:
        response = await client.post(route, files=_files())

    assert response.status_code == 200
    captured.assert_awaited_once()
    heard, said, actor = captured.await_args_list[-1].args
    assert (heard, said) == (_HEARD, "Muy bien.")
    assert actor is not None
    assert actor.status is ActivePersonStatus.IDENTIFIED
    assert actor.person_id == household.owner_entity_id
    assert captured.await_args_list[-1].kwargs["wav_bytes"]


@pytest.mark.parametrize("route", ["/transcribe", "/transcribe/stream"])
async def test_a_stranger_turn_is_recorded_with_an_unidentified_speaker(
    household: PersonalSetupResult,
    captured: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    route: str,
) -> None:
    _hear(monkeypatch)
    _classic_reply(monkeypatch)
    _stream_reply(monkeypatch)

    async with _client() as client:
        response = await client.post(route, files=_files(with_frame=False))

    assert response.status_code == 200
    _heard, _said, actor = captured.await_args_list[-1].args
    assert actor is not None
    assert actor.status is not ActivePersonStatus.IDENTIFIED


@pytest.mark.parametrize("route", ["/transcribe", "/transcribe/stream"])
async def test_a_deterministic_turn_keeps_the_speaker_the_controller_resolved(
    household: PersonalSetupResult,
    captured: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    route: str,
) -> None:
    """Found on hardware: the owner's verified words answered by a fixed reply reach the record."""
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "Hoy tengo que ir a buscar a mis hijos al colegio, Zeta.")

    async with _client() as client:
        response = await client.post(route, files=_files())

    assert response.status_code == 200
    _heard, _said, actor = captured.await_args_list[-1].args
    assert actor is not None
    assert actor.status is ActivePersonStatus.IDENTIFIED
    assert actor.person_id == household.owner_entity_id


@pytest.mark.parametrize("route", ["/transcribe", "/transcribe/stream"])
async def test_a_deterministic_turn_records_its_plan_with_no_speaker(
    household: PersonalSetupResult,
    captured: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    route: str,
) -> None:
    _hear(monkeypatch, "¿Qué fecha es hoy?")
    model = AsyncMock()
    monkeypatch.setattr(llm, "_generate_ollama", model)

    async with _client() as client:
        response = await client.post(route, files=_files(with_frame=False))

    assert response.status_code == 200
    model.assert_not_awaited()
    heard, said, actor = captured.await_args_list[-1].args
    assert heard == "¿Qué fecha es hoy?"
    assert "hoy" in said.lower()
    assert actor is None


async def test_the_fallback_phrase_is_recorded(
    household: PersonalSetupResult, captured: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    _hear(monkeypatch)
    monkeypatch.setattr(llm, "_generate_ollama", AsyncMock(side_effect=LLMError("down")))

    async with _client() as client:
        response = await client.post("/transcribe", files=_files(with_frame=False))

    assert response.status_code == 200
    assert captured.await_args_list[-1].args[1] == settings.llm_fallback_phrase


async def test_an_unclear_clip_records_nothing(
    household: PersonalSetupResult, captured: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    _hear(monkeypatch, "eh")
    monkeypatch.setattr(stt, "transcribe", AsyncMock(side_effect=UnclearSpeechError("eh")))

    async with _client() as client:
        response = await client.post("/transcribe", files=_files(with_frame=False))

    assert response.status_code == 200
    captured.assert_not_awaited()


async def test_chat_records_nothing_even_with_the_switch_on(
    household: PersonalSetupResult, captured: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    _classic_reply(monkeypatch)

    async with _client() as client:
        response = await client.post(
            "/chat", json={"message": "hola", "conversation_id": f"web-{uuid4().hex[:8]}"}
        )

    assert response.status_code == 200
    captured.assert_not_awaited()


async def test_vision_respond_records_nothing_even_with_the_switch_on(
    household: PersonalSetupResult, captured: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plan 0076 D-7: the camera's second round is not part of the record."""
    monkeypatch.setattr(settings, "vision_enabled", True)
    _see_the_owner(monkeypatch)
    _hear(monkeypatch)  # scripts the TTS too: CI has no Piper voice (CI failure of 2026-10-30)
    _classic_reply(monkeypatch)

    async with _client() as client:
        response = await client.post(
            "/vision/respond",
            files={"image": ("frame.jpg", _FRAME, "image/jpeg")},
            data={"text": "Hola, Iroko"},
        )

    assert response.status_code == 200
    captured.assert_not_awaited()


async def test_with_the_switch_off_nothing_is_recorded(
    household: PersonalSetupResult, captured: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "conversation_record_enabled", False)
    _see_the_owner(monkeypatch)
    _hear(monkeypatch)
    _classic_reply(monkeypatch)

    async with _client() as client:
        response = await client.post("/transcribe", files=_files())

    assert response.status_code == 200
    captured.assert_not_awaited()
