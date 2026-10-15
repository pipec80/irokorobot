"""The spoken offer and answer through the real voice routes (ADR 0021 decision 9, Plan 0063).

Face detection and the speaker embedding are doubles; face matching, the voice centroid, the
policy, the audit and the database are real. Audio is generated in code, never a recording, and
every name is a canary.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
import io
import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
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
from server.cognition.owner_authentication import owner_unlock_service
from server.exceptions import TTSError
from server.main import app
from server.memory import candidates
from server.memory.biometric_consent import grant_face_consent, revoke_face_consent
from server.memory.candidate_dialogue import (
    ANSWER_REJECTED_PHRASE,
    ANSWER_SAVED_PHRASE,
    compose_offer,
)
from server.memory.candidate_types import CandidateChannel, CandidateStatus, ProposedCandidate
from server.memory.predicate_registry import resolve_predicate
from server.memory.relational_v4 import get_active_literal_facts
from server.memory.voice_consent import grant_voice_consent, revoke_voice_consent
from server.personal_setup import PersonalSetupInput, PersonalSetupResult, apply_personal_setup
from server.resources import AppResources
from server.settings import settings
from server.vision.faces import DetectedFace, enroll_face
from server.voice.speaker_embedding import model_id
from server.voice.voiceprints import enroll_voiceprint

from server import db, llm, llm_streaming, pipeline, stt, tts

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_OWNER_NAME = "Canary"
_PIN = "482173"
_FRAME = cv2.imencode(".jpg", np.zeros((10, 10, 3), dtype=np.uint8))[1].tobytes()
_OFFER = compose_offer("likes", "el mate")
_REPLY = "Hola, qué gusto."
_ANSWER = "Sí, autorizo guardar el mate"


def _axis(size: int, axis: int) -> np.ndarray:
    vector = np.zeros(size, dtype=np.float32)
    vector[axis] = 1.0
    return vector


_OWNER_FACE = _axis(512, 0)
_STRANGER_FACE = _axis(512, 1)
_OWNER_VOICE = _axis(192, 0)
_OTHER_VOICE = _axis(192, 10)


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


@pytest.fixture
async def household(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[PersonalSetupResult]:
    """One owner with an enrolled, consented face and voice, and the candidate switch on."""
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "memory-dialogue.db")
    monkeypatch.setattr(settings, "face_authentication_enabled", True)
    monkeypatch.setattr(settings, "speaker_authentication_enabled", True)
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    result = await apply_personal_setup(
        PersonalSetupInput(owner_name=_OWNER_NAME, child_names=(), pin=SecretStr(_PIN))
    )
    await grant_face_consent(result.owner_entity_id)
    await enroll_face(result.owner_entity_id, _OWNER_FACE, label=_OWNER_NAME)
    await grant_voice_consent(result.owner_entity_id)
    for axis in range(3):
        await enroll_voiceprint(result.owner_entity_id, _axis(192, axis), "owner", model_id())
    yield result
    await db.close_db()
    db._conn = None


@asynccontextmanager
async def _client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient() as http_client:
        app.state.resources = AppResources(
            http_client=http_client, owner_unlock_service=owner_unlock_service
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client


def _files() -> dict[str, tuple[str, bytes, str]]:
    return {
        "audio": ("a.wav", _tone_wav(), "audio/wav"),
        "frame": ("frame.jpg", _FRAME, "image/jpeg"),
    }


def _scene(
    monkeypatch: pytest.MonkeyPatch,
    *heard: str,
    faces: tuple[np.ndarray, ...] = (_OWNER_FACE,),
    voice: np.ndarray = _OWNER_VOICE,
) -> AsyncMock:
    """Script the faces, the voice, what STT hears and the model's reply; return the TTS spy."""
    monkeypatch.setattr(
        face_auth_module,
        "_detect_faces_default",
        AsyncMock(return_value=[DetectedFace(embedding=f, score=0.9, width=200.0) for f in faces]),
    )
    monkeypatch.setattr(speaker_auth_module, "embed_wav", AsyncMock(return_value=voice))
    monkeypatch.setattr(stt, "transcribe", AsyncMock(side_effect=list(heard)))
    monkeypatch.setattr(llm, "generate_response", AsyncMock(return_value=(_REPLY, "neutral")))
    synthesize = AsyncMock(return_value=("AAAA", 42))
    monkeypatch.setattr(tts, "synthesize", synthesize)
    return synthesize


async def _candidate(owner: int) -> int:
    result = await candidates.insert_candidate(
        ProposedCandidate(predicate="likes", value_text="el mate", value_key="mate"),
        subject_person_id=owner,
        asserted_by_person_id=owner,
        channel=CandidateChannel.VOICE_CLASSIC,
        correlation_id=uuid4(),
        now=datetime.now(UTC) - timedelta(minutes=5),
    )
    assert result.candidate_id is not None
    return result.candidate_id


async def _status(candidate_id: int) -> CandidateStatus:
    stored = await candidates.get_candidate(candidate_id)
    assert stored is not None
    return stored.status


async def _audit_rows() -> list[tuple[str, str]]:
    cursor = await db.get_conn().execute(
        "SELECT action, decision FROM authorization_audit_events "
        "WHERE action LIKE '%personal%memory%' ORDER BY id"
    )
    rows = [(str(row[0]), str(row[1])) for row in await cursor.fetchall()]
    await cursor.close()
    return rows


async def _likes(owner: int) -> list[object]:
    definition = resolve_predicate("likes")
    assert definition is not None
    return list(await get_active_literal_facts(subject_entity_id=owner, definition=definition))


async def test_the_classic_route_offers_after_the_reply_and_the_answer_saves_it(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = household.owner_entity_id
    candidate_id = await _candidate(owner)
    synthesize = _scene(monkeypatch, "hola", _ANSWER)

    async with _client() as client:
        offered = await client.post("/transcribe", files=_files())
        answered = await client.post("/transcribe", files=_files())

    assert offered.status_code == answered.status_code == 200
    assert offered.json()["llm_response"] == _REPLY
    assert offered.json()["identity_source"] is None  # a generic turn stays a generic turn
    assert synthesize.await_args_list[0].args == (f"{_REPLY} {_OFFER}",)
    assert answered.json()["llm_response"] == ANSWER_SAVED_PHRASE
    assert answered.json()["identity_source"] == "face_voice"
    assert await _status(candidate_id) is CandidateStatus.CONFIRMED
    assert len(await _likes(owner)) == 1
    assert await _audit_rows() == [
        ("read_personal_conversation_memory", "allowed"),
        ("confirm_personal_memory", "allowed"),
    ]


async def test_the_streaming_route_offers_as_one_more_silent_audio_event(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = household.owner_entity_id
    candidate_id = await _candidate(owner)
    synthesize = _scene(monkeypatch, "hola")

    async def stream(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        yield _REPLY

    monkeypatch.setattr(llm_streaming, "generate_response_stream", stream)

    async with _client() as client:
        response = await client.post("/transcribe/stream", files=_files())

    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["type"] for event in events] == [
        "text_heard",
        "emotion",
        "audio",
        "audio",
        "done",
    ]
    assert events[3]["text"] == ""
    assert synthesize.await_args_list[-1].args == (_OFFER,)
    assert await _status(candidate_id) is CandidateStatus.OFFERED


async def test_no_is_said_and_audited_and_the_value_is_gone(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = household.owner_entity_id
    candidate_id = await _candidate(owner)
    _scene(monkeypatch, "hola", "No autorizo guardar el mate")

    async with _client() as client:
        await client.post("/transcribe", files=_files())
        answered = await client.post("/transcribe", files=_files())

    assert answered.json()["llm_response"] == ANSWER_REJECTED_PHRASE
    assert await _status(candidate_id) is CandidateStatus.REJECTED
    assert await _likes(owner) == []


async def test_another_voice_with_the_owner_face_is_offered_nothing_and_answers_nothing(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = household.owner_entity_id
    candidate_id = await _candidate(owner)
    synthesize = _scene(monkeypatch, "hola", _ANSWER, voice=_OTHER_VOICE)

    async with _client() as client:
        offered = await client.post("/transcribe", files=_files())
        answered = await client.post("/transcribe", files=_files())

    assert synthesize.await_args_list[0].args == (_REPLY,)
    assert offered.json()["llm_response"] == _REPLY
    assert answered.json()["llm_response"] == _REPLY
    assert await _status(candidate_id) is CandidateStatus.PROPOSED
    assert await _audit_rows() == []


async def test_a_second_face_in_frame_is_offered_nothing(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate_id = await _candidate(household.owner_entity_id)
    synthesize = _scene(monkeypatch, "hola", faces=(_OWNER_FACE, _STRANGER_FACE))

    async with _client() as client:
        response = await client.post("/transcribe", files=_files())

    assert response.json()["llm_response"] == _REPLY
    assert synthesize.await_args_list[0].args == (_REPLY,)
    assert await _status(candidate_id) is CandidateStatus.PROPOSED


async def test_an_answer_with_no_offer_outstanding_is_an_ordinary_turn(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing is confirmed; the ordinary turn it becomes may itself carry the offer."""
    candidate_id = await _candidate(household.owner_entity_id)
    synthesize = _scene(monkeypatch, _ANSWER)

    async with _client() as client:
        response = await client.post("/transcribe", files=_files())

    assert response.json()["llm_response"] == _REPLY
    assert synthesize.await_args_list[0].args == (f"{_REPLY} {_OFFER}",)
    assert await _status(candidate_id) is CandidateStatus.OFFERED
    assert await _audit_rows() == [("read_personal_conversation_memory", "allowed")]


async def test_the_switch_off_offers_nothing_and_answers_nothing(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = household.owner_entity_id
    candidate_id = await _candidate(owner)
    assert await candidates.mark_offered(
        candidate_id, owner, correlation_id=uuid4(), now=datetime.now(UTC)
    )
    monkeypatch.setattr(settings, "memory_candidates_enabled", False)
    synthesize = _scene(monkeypatch, "hola", _ANSWER)

    async with _client() as client:
        first = await client.post("/transcribe", files=_files())
        second = await client.post("/transcribe", files=_files())

    assert synthesize.await_args_list[0].args == (_REPLY,)
    assert first.json()["llm_response"] == second.json()["llm_response"] == _REPLY
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
    assert await _status(candidate_id) is CandidateStatus.OFFERED


async def test_chat_never_answers_a_memory_offer(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = household.owner_entity_id
    candidate_id = await _candidate(owner)
    assert await candidates.mark_offered(
        candidate_id, owner, correlation_id=uuid4(), now=datetime.now(UTC)
    )
    _scene(monkeypatch)

    async with _client() as client:
        response = await client.post("/chat", json={"message": _ANSWER, "conversation_id": "web"})

    assert response.status_code == 200
    assert response.json()["response"] == _REPLY
    assert await _status(candidate_id) is CandidateStatus.OFFERED


async def test_the_classic_spoken_log_never_carries_the_offer(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _candidate(household.owner_entity_id)
    _scene(monkeypatch, "hola")
    spoken = Mock()
    monkeypatch.setattr(pipeline, "log_spoken", spoken)

    async with _client() as client:
        await client.post("/transcribe", files=_files())

    assert [call.args[0] for call in spoken.call_args_list] == [_REPLY]


async def test_a_failing_combined_synthesis_still_speaks_the_reply(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _candidate(household.owner_entity_id)
    synthesize = _scene(monkeypatch, "hola")
    synthesize.side_effect = [TTSError("piper down"), ("AAAA", 42)]

    async with _client() as client:
        response = await client.post("/transcribe", files=_files())

    assert response.status_code == 200
    assert response.json()["llm_response"] == _REPLY
    assert [call.args for call in synthesize.await_args_list] == [
        (f"{_REPLY} {_OFFER}",),
        (_REPLY,),
    ]


async def test_a_fall_through_answer_is_the_ordinary_turn_on_the_wire(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another voice saying the answer gets exactly what «hola» gets, field by field."""
    owner = household.owner_entity_id
    candidate_id = await _candidate(owner)
    assert await candidates.mark_offered(
        candidate_id, owner, correlation_id=uuid4(), now=datetime.now(UTC)
    )
    _scene(monkeypatch, "hola", _ANSWER, voice=_OTHER_VOICE)

    async with _client() as client:
        ordinary = (await client.post("/transcribe", files=_files())).json()
        answer = (await client.post("/transcribe", files=_files())).json()

    timing = {"stt_ms", "llm_ms", "tts_ms", "total_ms", "text_heard"}
    assert {k: v for k, v in answer.items() if k not in timing} == {
        k: v for k, v in ordinary.items() if k not in timing
    }
    assert await _status(candidate_id) is CandidateStatus.OFFERED


async def test_the_streaming_route_answers_too(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = household.owner_entity_id
    candidate_id = await _candidate(owner)
    assert await candidates.mark_offered(
        candidate_id, owner, correlation_id=uuid4(), now=datetime.now(UTC)
    )
    _scene(monkeypatch, _ANSWER)

    async with _client() as client:
        response = await client.post("/transcribe/stream", files=_files())

    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["text"] for event in events if event["type"] == "audio"] == [ANSWER_SAVED_PHRASE]
    assert await _status(candidate_id) is CandidateStatus.CONFIRMED


async def test_a_voice_consent_revoked_after_the_offer_answers_nothing(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = household.owner_entity_id
    candidate_id = await _candidate(owner)
    _scene(monkeypatch, "hola", _ANSWER)

    async with _client() as client:
        await client.post("/transcribe", files=_files())
        await revoke_voice_consent(owner)
        answered = await client.post("/transcribe", files=_files())

    assert answered.json()["llm_response"] == _REPLY
    assert await _status(candidate_id) is CandidateStatus.OFFERED
    assert await _audit_rows() == [("read_personal_conversation_memory", "allowed")]


async def test_a_face_consent_revoked_before_the_turn_offers_nothing(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = household.owner_entity_id
    candidate_id = await _candidate(owner)
    await revoke_face_consent(owner)
    synthesize = _scene(monkeypatch, "hola")

    async with _client() as client:
        await client.post("/transcribe", files=_files())

    assert synthesize.await_args_list[0].args == (_REPLY,)
    assert await _status(candidate_id) is CandidateStatus.PROPOSED
    assert await _audit_rows() == []


async def test_vision_never_answers_a_memory_offer(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = household.owner_entity_id
    candidate_id = await _candidate(owner)
    assert await candidates.mark_offered(
        candidate_id, owner, correlation_id=uuid4(), now=datetime.now(UTC)
    )
    _scene(monkeypatch)
    monkeypatch.setattr(settings, "vision_enabled", True)

    async with _client() as client:
        response = await client.post(
            "/vision/respond",
            files={"image": ("frame.jpg", _FRAME, "image/jpeg")},
            data={"text": _ANSWER},
        )

    assert response.status_code == 200
    assert await _status(candidate_id) is CandidateStatus.OFFERED


async def test_chat_never_offers_a_waiting_candidate(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate_id = await _candidate(household.owner_entity_id)
    _scene(monkeypatch)

    async with _client() as client:
        response = await client.post("/chat", json={"message": "hola", "conversation_id": "web"})

    assert response.json()["response"] == _REPLY
    assert await _status(candidate_id) is CandidateStatus.PROPOSED
