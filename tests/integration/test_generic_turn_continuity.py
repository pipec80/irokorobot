"""Short-term continuity through the real generic-turn routes (Plan 0061, ADR 0020).

Face detection and the speaker embedding are doubles; face matching, the identity store and the
unlock registry are real. Model replies are scripted: no real model, no recording.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
import io
import json
from pathlib import Path
from unittest.mock import AsyncMock
import wave

import cv2
from httpx import ASGITransport, AsyncClient
import numpy as np
from pydantic import SecretStr
import pytest
from server.cognition import (
    face_authentication as face_auth_module,
    speaker_authentication as speaker_auth_module,
)
from server.cognition.identity import PersonRecord
from server.cognition.identity_sessions import IdentitySessionRegistry
from server.cognition.owner_authentication import OwnerUnlockService, owner_unlock_service
from server.dependencies import get_owner_unlock_service
from server.exceptions import LLMError
from server.main import app
from server.memory.biometric_consent import grant_face_consent
from server.memory.candidate_types import CandidateChannel
from server.memory.entity_labels import get_person_label
from server.memory.household_authorization import get_active_role
from server.memory.owner_credentials import get_active_owner_pin_credential
from server.personal_setup import PersonalSetupInput, PersonalSetupResult, apply_personal_setup
from server.resources import AppResources
from server.routers import transcribe as transcribe_module
from server.settings import settings
from server.vision.faces import DetectedFace, enroll_face

from server import db, llm, llm_streaming, stt, tts

_PIN = "482173"
_OWNER_NAME = "Canary"
_CHILD_QUESTION = "¿Quiénes son mis hijos?"
_FRAME = cv2.imencode(".jpg", np.zeros((10, 10, 3), dtype=np.uint8))[1].tobytes()
_OWNER_FACE = np.eye(512, dtype=np.float32)[0]
_STRANGER_FACE = np.eye(512, dtype=np.float32)[1]


def _detected(embedding: np.ndarray) -> DetectedFace:
    return DetectedFace(embedding=embedding, score=0.9, width=200.0)


def _tone_wav(seconds: float = 3.0) -> bytes:
    t = np.linspace(0.0, seconds, int(16_000 * seconds), endpoint=False)
    samples = (8_000 * np.sin(2 * np.pi * 220 * t)).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(samples.tobytes())
    return buffer.getvalue()


def _files(*, with_frame: bool = True) -> dict[str, tuple[str, bytes, str]]:
    files = {"audio": ("a.wav", _tone_wav(), "audio/wav")}
    if with_frame:
        files["frame"] = ("frame.jpg", _FRAME, "image/jpeg")
    return files


@pytest.fixture
async def household(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[PersonalSetupResult]:
    """A real database with one enrolled owner whose face is consented."""
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "generic-continuity.db")
    monkeypatch.setattr(settings, "face_authentication_enabled", True)
    monkeypatch.setattr(settings, "speaker_authentication_enabled", True)
    monkeypatch.setattr(settings, "memory_enabled", True)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    result = await apply_personal_setup(
        PersonalSetupInput(
            owner_name=_OWNER_NAME, child_names=("Hija Uno", "Hija Dos"), pin=SecretStr(_PIN)
        )
    )
    await grant_face_consent(result.owner_entity_id)
    await enroll_face(result.owner_entity_id, _OWNER_FACE, label=_OWNER_NAME)
    yield result
    await db.close_db()
    db._conn = None


async def _read_person_record(person_entity_id: int) -> PersonRecord | None:
    label = await get_person_label(entity_id=person_entity_id)
    if label is None:
        return None
    return PersonRecord(
        person_id=label.entity_id, display_name=label.display_name, entity_type="person"
    )


def _service() -> OwnerUnlockService:
    registry = IdentitySessionRegistry(
        lookup_person=lambda _pid: None, clock=lambda: datetime.now(UTC), ttl=timedelta(seconds=60)
    )
    return OwnerUnlockService(
        clock=lambda: datetime.now(UTC),
        registry=registry,
        read_credential=get_active_owner_pin_credential,
        read_role=get_active_role,
        read_person=_read_person_record,
    )


@asynccontextmanager
async def _client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient() as http_client:
        app.state.resources = AppResources(
            http_client=http_client, owner_unlock_service=owner_unlock_service
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client


def _detect(monkeypatch: pytest.MonkeyPatch, *faces: np.ndarray) -> None:
    monkeypatch.setattr(
        face_auth_module,
        "_detect_faces_default",
        AsyncMock(return_value=[_detected(face) for face in faces]),
    )


def _speak(monkeypatch: pytest.MonkeyPatch, *sentences: str) -> None:
    """Script what STT hears on each successive request, and silence the TTS."""
    monkeypatch.setattr(stt, "transcribe", AsyncMock(side_effect=list(sentences)))
    monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("AAAA", 42)))


def _model(monkeypatch: pytest.MonkeyPatch, *replies: str) -> AsyncMock:
    """Script the classic model's replies; return the mock to read the histories it got."""
    generate = AsyncMock(side_effect=[(reply, "neutral") for reply in replies])
    monkeypatch.setattr(llm, "generate_response", generate)
    return generate


def _histories(generate: AsyncMock) -> list[list[str] | None]:
    return [
        None if call.kwargs["history"] is None else [t.content for t in call.kwargs["history"]]
        for call in generate.await_args_list
    ]


@pytest.mark.integration
async def test_the_owner_face_gives_a_voice_turn_continuity_without_voice_or_grant(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    embed = AsyncMock()
    monkeypatch.setattr(speaker_auth_module, "embed_wav", embed)
    _detect(monkeypatch, _OWNER_FACE)
    _speak(monkeypatch, "Me llamo Canario", "¿Cómo me llamo?")
    generate = _model(monkeypatch, "Mucho gusto, Canario.", "Te llamas Canario.")

    async with _client() as client:
        first = await client.post("/transcribe", files=_files())
        second = await client.post("/transcribe", files=_files())

    assert first.status_code == second.status_code == 200
    assert _histories(generate) == [
        [],
        ["Me llamo Canario", "Mucho gusto, Canario."],
    ]
    for body in (first.json(), second.json()):
        assert body["identity_source"] is None
        assert body["authentication_consumed"] is False
    embed.assert_not_awaited()


@pytest.mark.integration
async def test_a_second_face_suspends_the_session_and_the_owner_resumes_it(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    _speak(monkeypatch, "Mi clave es COBALTO", "¿Cuál es la clave?", "¿Cuál era mi clave?")
    generate = _model(monkeypatch, "Anotado.", "No lo sé.", "COBALTO.")

    async with _client() as client:
        _detect(monkeypatch, _OWNER_FACE)
        await client.post("/transcribe", files=_files())
        _detect(monkeypatch, _OWNER_FACE, _STRANGER_FACE)
        suspended = await client.post("/transcribe", files=_files())
        _detect(monkeypatch, _OWNER_FACE)
        resumed = await client.post("/transcribe", files=_files())

    assert suspended.status_code == resumed.status_code == 200
    assert _histories(generate) == [
        [],
        None,
        ["Mi clave es COBALTO", "Anotado."],
    ]


@pytest.mark.integration
async def test_a_turn_without_frame_or_token_is_stateless_and_leaves_the_session(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    _speak(monkeypatch, "Hola", "¿Quién eres?", "Seguimos")
    generate = _model(monkeypatch, "Hola.", "Soy Iroko.", "Claro.")

    async with _client() as client:
        _detect(monkeypatch, _OWNER_FACE)
        await client.post("/transcribe", files=_files())
        await client.post("/transcribe", files=_files(with_frame=False))
        await client.post("/transcribe", files=_files())

    assert _histories(generate) == [[], None, ["Hola", "Hola."]]


@pytest.mark.integration
async def test_the_streaming_route_reads_and_writes_the_same_session(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    _detect(monkeypatch, _OWNER_FACE)
    _speak(monkeypatch, "Me llamo Canario", "¿Cómo me llamo?")
    seen: list[list[str] | None] = []

    async def stream(*_args: object, **kwargs: object) -> AsyncIterator[str]:
        history = kwargs["history"]
        seen.append(None if history is None else [t.content for t in history])  # type: ignore[attr-defined]  # ConversationTurn items
        yield "Mucho gusto."

    monkeypatch.setattr(llm_streaming, "generate_response_stream", stream)

    async with _client() as client:
        first = await client.post("/transcribe/stream", files=_files())
        second = await client.post("/transcribe/stream", files=_files())

    for response in (first, second):
        events = [json.loads(line) for line in response.text.splitlines() if line]
        assert events[-1]["type"] == "done"
        assert events[-1].get("identity_source") is None
    assert seen == [[], ["Me llamo Canario", "Mucho gusto."]]


@pytest.mark.integration
async def test_a_chat_token_gives_continuity_across_public_conversation_ids_and_is_never_spent(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    headers = {"X-Iroko-Identity-Token": unlock.token}
    generate = _model(monkeypatch, "Anotado.", "COBALTO.", "Sigo aquí.")

    async with _client() as client:
        replies = [
            await client.post(
                "/chat", headers=headers, json={"message": text, "conversation_id": conversation}
            )
            for text, conversation in (
                ("Mi clave es COBALTO", "web-a"),
                ("¿Cuál era mi clave?", "web-b"),
                ("¿Sigues ahí?", "web-c"),
            )
        ]

    assert [reply.status_code for reply in replies] == [200, 200, 200]
    assert [reply.json()["authentication_consumed"] for reply in replies] == [False] * 3
    assert _histories(generate) == [
        [],
        ["Mi clave es COBALTO", "Anotado."],
        ["Mi clave es COBALTO", "Anotado.", "¿Cuál era mi clave?", "COBALTO."],
    ]


@pytest.mark.integration
async def test_a_protected_answer_spends_the_token_and_never_enters_the_session(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    first_unlock = await service.unlock(_PIN)
    assert first_unlock is not None
    generate = _model(monkeypatch, "Anotado.", "Aquí sigo.", "Bienvenido.")

    async with _client() as client:
        await client.post(
            "/chat",
            headers={"X-Iroko-Identity-Token": first_unlock.token},
            json={"message": "Mi clave es COBALTO", "conversation_id": "web"},
        )
        protected = await client.post(
            "/chat",
            headers={"X-Iroko-Identity-Token": first_unlock.token},
            json={"message": _CHILD_QUESTION, "conversation_id": "web"},
        )
        spent = await client.post(
            "/chat",
            headers={"X-Iroko-Identity-Token": first_unlock.token},
            json={"message": "¿Sigues ahí?", "conversation_id": "web"},
        )
        second_unlock = await service.unlock(_PIN)
        assert second_unlock is not None
        resumed = await client.post(
            "/chat",
            headers={"X-Iroko-Identity-Token": second_unlock.token},
            json={"message": "Ya volví", "conversation_id": "web"},
        )

    assert protected.json()["authentication_consumed"] is True
    assert "Hija Uno" in protected.json()["response"]
    assert spent.status_code == resumed.status_code == 200
    # The spent token names nobody: that turn suspends. The new unlock resumes the same
    # session, which holds the first exchange and nothing of the protected answer.
    assert _histories(generate) == [[], None, ["Mi clave es COBALTO", "Anotado."]]


@pytest.mark.integration
async def test_a_visual_dialogue_turn_neither_reads_nor_writes_the_session(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR 0020 §1: `/vision/respond` keeps the public unknown, so it leaves the session alone."""
    monkeypatch.setattr(settings, "vision_enabled", True)
    _detect(monkeypatch, _OWNER_FACE)
    _speak(monkeypatch, "Mi clave es COBALTO", "¿Qué decía mi clave?")
    generate = _model(monkeypatch, "Anotado.", "Hola.", "COBALTO.")

    async with _client() as client:
        await client.post("/transcribe", files=_files())
        visual = await client.post(
            "/vision/respond",
            files={"image": ("frame.jpg", _FRAME, "image/jpeg")},
            data={"text": "Hola, Iroko"},
        )
        resumed = await client.post("/transcribe", files=_files())

    assert visual.status_code == resumed.status_code == 200
    # The visual turn received no history and wrote nothing: the owner's next turn still finds
    # exactly the first exchange, not the visual one.
    assert _histories(generate) == [[], None, ["Mi clave es COBALTO", "Anotado."]]


# --- candidate proposals through the real routes (Plan 0062, ADR 0021 §10) -------------------


@pytest.fixture
def proposals(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Switch candidates on and replace the background proposal with a spy."""
    spy = AsyncMock()
    monkeypatch.setattr(transcribe_module, "propose_candidates", spy)
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
    return spy


@pytest.mark.integration
async def test_a_face_identified_classic_turn_proposes_with_its_own_clip_and_event(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, proposals: AsyncMock
) -> None:
    _detect(monkeypatch, _OWNER_FACE)
    _speak(monkeypatch, "Me gusta el mate")
    _model(monkeypatch, "Qué bueno.")

    async with _client() as client:
        response = await client.post("/transcribe", files=_files())

    assert response.status_code == 200
    proposals.assert_awaited_once()
    call = proposals.await_args
    assert call is not None
    _client_arg, message, actor = call.args
    assert message == "Me gusta el mate"
    assert actor.person_id == household.owner_entity_id
    assert {item.source.value for item in actor.evidence} == {"face"}
    assert call.kwargs["wav_bytes"] == _tone_wav()
    assert call.kwargs["channel"] is CandidateChannel.VOICE_CLASSIC
    assert call.kwargs["event"].payload.message == "Me gusta el mate"
    assert "Qué bueno." not in str(call)


@pytest.mark.integration
async def test_a_face_identified_streaming_turn_proposes_on_the_stream_channel(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, proposals: AsyncMock
) -> None:
    _detect(monkeypatch, _OWNER_FACE)
    _speak(monkeypatch, "Me gusta el mate")

    async def stream(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        yield "Qué bueno."

    monkeypatch.setattr(llm_streaming, "generate_response_stream", stream)

    async with _client() as client:
        response = await client.post("/transcribe/stream", files=_files())

    assert response.status_code == 200
    proposals.assert_awaited_once()
    call = proposals.await_args
    assert call is not None
    assert call.kwargs["channel"] is CandidateChannel.VOICE_STREAM
    assert call.kwargs["wav_bytes"] == _tone_wav()


@pytest.mark.integration
async def test_no_proposal_without_a_face_with_a_token_from_chat_or_with_the_switch_off(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, proposals: AsyncMock
) -> None:
    service = _service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    headers = {"X-Iroko-Identity-Token": unlock.token}
    _speak(monkeypatch, "Me gusta el mate", "Me gusta el mate", "Me gusta el mate")
    _model(monkeypatch, "Uno.", "Dos.", "Tres.", "Cuatro.", "Cinco.")

    async with _client() as client:
        # no frame: the speaker is unknown
        await client.post("/transcribe", files=_files(with_frame=False))
        # a token only: a PIN grant proves the PIN, not the speaker
        await client.post("/transcribe", files=_files(with_frame=False), headers=headers)
        # /chat has no audio, so it never proposes
        await client.post(
            "/chat",
            headers=headers,
            json={"message": "Me gusta el mate", "conversation_id": "web"},
        )
        # the face is there, the kill-switch is off
        _detect(monkeypatch, _OWNER_FACE)
        monkeypatch.setattr(settings, "memory_candidates_enabled", False)
        await client.post("/transcribe", files=_files())

    proposals.assert_not_awaited()


@pytest.mark.integration
async def test_no_proposal_from_a_visual_dialogue_turn_or_a_fallback_reply(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, proposals: AsyncMock
) -> None:
    monkeypatch.setattr(settings, "vision_enabled", True)
    _detect(monkeypatch, _OWNER_FACE)
    _speak(monkeypatch, "Me gusta el mate")
    monkeypatch.setattr(llm, "generate_response", AsyncMock(side_effect=LLMError("down")))

    async with _client() as client:
        visual = await client.post(
            "/vision/respond",
            files={"image": ("frame.jpg", _FRAME, "image/jpeg")},
            data={"text": "Me gusta el mate"},
        )
        fallback = await client.post("/transcribe", files=_files())

    assert visual.status_code == fallback.status_code == 200
    proposals.assert_not_awaited()
