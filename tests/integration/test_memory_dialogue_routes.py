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
import logging
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
from server.cognition.identity import PersonRecord
from server.cognition.identity_sessions import IdentitySessionRegistry
from server.cognition.owner_authentication import OwnerUnlockService, owner_unlock_service
from server.dependencies import get_owner_unlock_service
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
from server.memory.entity_labels import get_person_label
from server.memory.household_authorization import get_active_role
from server.memory.owner_credentials import get_active_owner_pin_credential
from server.memory.predicate_registry import resolve_predicate
from server.memory.relational_v4 import get_active_literal_facts
from server.memory.voice_consent import grant_voice_consent, revoke_voice_consent
from server.personal_setup import PersonalSetupInput, PersonalSetupResult, apply_personal_setup
from server.resources import AppResources
from server.routers import transcribe as transcribe_router
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
_SHORT_ANSWER = "Sí, autorizo."


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


def _stream_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    """Script the streaming model to say the one reply sentence."""

    async def stream(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        yield _REPLY

    monkeypatch.setattr(llm_streaming, "generate_response_stream", stream)


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


async def test_another_voice_with_the_owner_face_is_offered_nothing(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing was offered, so the candidate stays proposed and nothing is audited on either turn.

    That another voice cannot *answer* an open offer is the job of
    ``test_a_fall_through_answer_is_the_ordinary_turn_on_the_wire`` (the candidate is ``offered``
    there).
    """
    owner = household.owner_entity_id
    candidate_id = await _candidate(owner)
    synthesize = _scene(monkeypatch, "hola", _ANSWER, voice=_OTHER_VOICE)

    async with _client() as client:
        offered = await client.post("/transcribe", files=_files())
        answered = await client.post("/transcribe", files=_files())

    assert synthesize.await_args_list[0].args == (_REPLY,)
    assert offered.json()["llm_response"] == _REPLY
    assert answered.json()["llm_response"] == _REPLY
    assert offered.json()["identity_source"] is None
    assert answered.json()["identity_source"] is None
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
    assert response.json()["identity_source"] is None
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
    candidate_id = await _candidate(household.owner_entity_id)
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
    # Accepted residue (plan decision D-9): the candidate was marked offered before the
    # synthesis, and nobody can tell it was never heard.
    assert await _status(candidate_id) is CandidateStatus.OFFERED


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
    assert answer["identity_source"] is None
    assert await _status(candidate_id) is CandidateStatus.OFFERED
    assert await _audit_rows() == []


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


async def test_a_verb_alone_saves_the_offer_on_the_classic_route(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = household.owner_entity_id
    candidate_id = await _candidate(owner)
    _scene(monkeypatch, "hola", _SHORT_ANSWER)

    async with _client() as client:
        await client.post("/transcribe", files=_files())
        answered = await client.post("/transcribe", files=_files())

    assert answered.json()["llm_response"] == ANSWER_SAVED_PHRASE
    assert answered.json()["identity_source"] == "face_voice"
    assert await _status(candidate_id) is CandidateStatus.CONFIRMED
    assert len(await _likes(owner)) == 1


async def test_a_verb_alone_saves_the_offer_on_the_streaming_route(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = household.owner_entity_id
    candidate_id = await _candidate(owner)
    assert await candidates.mark_offered(
        candidate_id, owner, correlation_id=uuid4(), now=datetime.now(UTC)
    )
    _scene(monkeypatch, _SHORT_ANSWER)

    async with _client() as client:
        response = await client.post("/transcribe/stream", files=_files())

    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["text"] for event in events if event["type"] == "audio"] == [ANSWER_SAVED_PHRASE]
    assert await _status(candidate_id) is CandidateStatus.CONFIRMED


async def test_a_short_reply_request_saying_si_acepto_saves_the_offer(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plan 0067: the robot's reply turn («sí, acepto») resolves the open offer end to end."""
    owner = household.owner_entity_id
    candidate_id = await _candidate(owner)
    assert await candidates.mark_offered(
        candidate_id, owner, correlation_id=uuid4(), now=datetime.now(UTC)
    )
    _scene(monkeypatch, "Sí, acepto.")

    async with _client() as client:
        response = await client.post(
            "/transcribe/stream", files=_files(), data={"short_reply": "true"}
        )

    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["text"] for event in events if event["type"] == "audio"] == [ANSWER_SAVED_PHRASE]
    assert await _status(candidate_id) is CandidateStatus.CONFIRMED


@pytest.mark.parametrize("heard", ["Sí.", "Guárdala."])
async def test_a_short_reply_request_never_widens_the_grammar(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, heard: str
) -> None:
    """Plan 0067 D-4: the flag only chooses hotwords; a bare «sí» still resolves nothing."""
    owner = household.owner_entity_id
    candidate_id = await _candidate(owner)
    assert await candidates.mark_offered(
        candidate_id, owner, correlation_id=uuid4(), now=datetime.now(UTC)
    )
    _scene(monkeypatch, heard)
    _stream_reply(monkeypatch)

    async with _client() as client:
        response = await client.post(
            "/transcribe/stream", files=_files(), data={"short_reply": "true"}
        )

    events = [json.loads(line) for line in response.text.splitlines()]
    assert ANSWER_SAVED_PHRASE not in [event.get("text") for event in events]
    assert await _status(candidate_id) is CandidateStatus.OFFERED
    assert await _likes(owner) == []


async def test_a_short_reply_request_never_lets_another_voice_answer(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The flag changes nothing about who answers: another voice with the owner's face fails."""
    owner = household.owner_entity_id
    candidate_id = await _candidate(owner)
    assert await candidates.mark_offered(
        candidate_id, owner, correlation_id=uuid4(), now=datetime.now(UTC)
    )
    _scene(monkeypatch, "Sí, acepto.", voice=_OTHER_VOICE)
    _stream_reply(monkeypatch)

    async with _client() as client:
        response = await client.post(
            "/transcribe/stream", files=_files(), data={"short_reply": "true"}
        )

    events = [json.loads(line) for line in response.text.splitlines()]
    assert ANSWER_SAVED_PHRASE not in [event.get("text") for event in events]
    assert await _status(candidate_id) is CandidateStatus.OFFERED
    assert await _likes(owner) == []


async def test_a_refusal_alone_rejects_the_offer_on_the_streaming_route(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = household.owner_entity_id
    candidate_id = await _candidate(owner)
    assert await candidates.mark_offered(
        candidate_id, owner, correlation_id=uuid4(), now=datetime.now(UTC)
    )
    _scene(monkeypatch, "No autorizo.")

    async with _client() as client:
        response = await client.post("/transcribe/stream", files=_files())

    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["text"] for event in events if event["type"] == "audio"] == [
        ANSWER_REJECTED_PHRASE
    ]
    assert await _status(candidate_id) is CandidateStatus.REJECTED
    assert await _likes(owner) == []


async def test_a_verb_alone_with_no_offer_is_an_ordinary_stream_turn(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scene(monkeypatch, _SHORT_ANSWER)
    _stream_reply(monkeypatch)

    async with _client() as client:
        response = await client.post("/transcribe/stream", files=_files())

    events = [json.loads(line) for line in response.text.splitlines()]
    assert ANSWER_SAVED_PHRASE not in [event.get("text") for event in events]
    assert await _likes(household.owner_entity_id) == []
    assert await _audit_rows() == []


async def test_a_verb_alone_with_no_offer_is_an_ordinary_turn(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A casual «autorizo» costs the face-and-voice check and nothing else."""
    owner = household.owner_entity_id
    _scene(monkeypatch, _SHORT_ANSWER)

    async with _client() as client:
        response = await client.post("/transcribe", files=_files())

    assert response.json()["llm_response"] == _REPLY
    assert response.json()["identity_source"] is None
    assert await _likes(owner) == []
    assert await _audit_rows() == []


async def test_chat_never_answers_with_a_verb_alone(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = household.owner_entity_id
    candidate_id = await _candidate(owner)
    assert await candidates.mark_offered(
        candidate_id, owner, correlation_id=uuid4(), now=datetime.now(UTC)
    )
    _scene(monkeypatch)

    async with _client() as client:
        response = await client.post(
            "/chat", json={"message": _SHORT_ANSWER, "conversation_id": "web"}
        )

    assert response.status_code == 200
    assert response.json()["response"] == _REPLY
    assert await _status(candidate_id) is CandidateStatus.OFFERED


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


@pytest.mark.parametrize("message", [_ANSWER, _SHORT_ANSWER])
async def test_vision_never_answers_a_memory_offer(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, message: str
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
            data={"text": message},
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


async def test_a_failing_combined_synthesis_never_logs_the_value(
    household: PersonalSetupResult,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A TTS engine's message may quote the text it failed on: the offer carries the value."""
    await _candidate(household.owner_entity_id)
    synthesize = _scene(monkeypatch, "hola")
    synthesize.side_effect = [TTSError(f"cannot say: {_OFFER}"), ("AAAA", 42)]

    with caplog.at_level(logging.DEBUG):
        async with _client() as client:
            response = await client.post("/transcribe", files=_files())

    assert response.status_code == 200
    assert caplog.records
    assert not any(
        "mate" in record.getMessage() or "mate" in str(record.__dict__)
        for record in caplog.records
        if record.name != "httpx"
    )


async def test_ordinary_speech_shaped_like_an_answer_leaves_an_open_offer_alone(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The verified owner says «apruebo el examen»: a closed verb, but not the offered value."""
    owner = household.owner_entity_id
    candidate_id = await _candidate(owner)
    assert await candidates.mark_offered(
        candidate_id, owner, correlation_id=uuid4(), now=datetime.now(UTC)
    )
    _scene(monkeypatch, "apruebo el examen")

    async with _client() as client:
        response = await client.post("/transcribe", files=_files())

    assert response.status_code == 200
    assert response.json()["llm_response"] == _REPLY
    assert response.json()["identity_source"] is None
    assert await _status(candidate_id) is CandidateStatus.OFFERED
    assert await _audit_rows() == []


async def test_the_streaming_route_offers_another_voice_nothing(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate_id = await _candidate(household.owner_entity_id)
    synthesize = _scene(monkeypatch, "hola", voice=_OTHER_VOICE)
    _stream_reply(monkeypatch)

    async with _client() as client:
        response = await client.post("/transcribe/stream", files=_files())

    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["type"] for event in events] == ["text_heard", "emotion", "audio", "done"]
    assert [event["text"] for event in events if event["type"] == "audio"] == [_REPLY]
    assert [call.args for call in synthesize.await_args_list] == [(_REPLY,)]
    assert await _status(candidate_id) is CandidateStatus.PROPOSED
    assert await _audit_rows() == []


async def test_the_streaming_route_never_lets_another_voice_answer(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = household.owner_entity_id
    candidate_id = await _candidate(owner)
    assert await candidates.mark_offered(
        candidate_id, owner, correlation_id=uuid4(), now=datetime.now(UTC)
    )
    _scene(monkeypatch, _ANSWER, voice=_OTHER_VOICE)
    _stream_reply(monkeypatch)

    async with _client() as client:
        response = await client.post("/transcribe/stream", files=_files())

    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["type"] for event in events] == ["text_heard", "emotion", "audio", "done"]
    assert [event["text"] for event in events if event["type"] == "audio"] == [_REPLY]
    assert await _status(candidate_id) is CandidateStatus.OFFERED
    assert await _audit_rows() == []


async def test_a_second_face_in_frame_answers_nothing(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another face vetoes the owner's: the open offer stays open and the turn is ordinary."""
    owner = household.owner_entity_id
    candidate_id = await _candidate(owner)
    assert await candidates.mark_offered(
        candidate_id, owner, correlation_id=uuid4(), now=datetime.now(UTC)
    )
    _scene(monkeypatch, _ANSWER, faces=(_OWNER_FACE, _STRANGER_FACE))

    async with _client() as client:
        response = await client.post("/transcribe", files=_files())

    assert response.status_code == 200
    assert response.json()["llm_response"] == _REPLY
    assert response.json()["identity_source"] is None
    assert await _status(candidate_id) is CandidateStatus.OFFERED
    assert await _audit_rows() == []


@pytest.mark.parametrize(
    "setting, face_detections",
    [("memory_candidates_enabled", 1), ("memory_enabled", 0)],
    ids=["candidates-off", "memory-off"],
)
async def test_an_answer_shaped_message_with_a_switch_off_resolves_no_face_for_the_answer(
    household: PersonalSetupResult,
    monkeypatch: pytest.MonkeyPatch,
    setting: str,
    face_detections: int,
) -> None:
    """Only the generic turn's own speaker check may look at the frame, never the answerer.

    With the candidate switch off the generic turn still names its speaker (one detection,
    ADR 0020); with the store off nothing looks at the frame at all. Were the answerer bound,
    the answer would cost a second detection.
    """
    owner = household.owner_entity_id
    candidate_id = await _candidate(owner)
    assert await candidates.mark_offered(
        candidate_id, owner, correlation_id=uuid4(), now=datetime.now(UTC)
    )
    _scene(monkeypatch, _ANSWER)
    detector = AsyncMock(return_value=[DetectedFace(embedding=_OWNER_FACE, score=0.9, width=200.0)])
    monkeypatch.setattr(face_auth_module, "_detect_faces_default", detector)
    embed = AsyncMock(return_value=_OWNER_VOICE)
    monkeypatch.setattr(speaker_auth_module, "embed_wav", embed)
    monkeypatch.setattr(settings, setting, False)

    async with _client() as client:
        response = await client.post("/transcribe", files=_files())

    assert response.status_code == 200
    assert response.json()["llm_response"] == _REPLY
    assert detector.await_count == face_detections
    embed.assert_not_awaited()
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
    assert await _status(candidate_id) is CandidateStatus.OFFERED


def _unlock_service() -> OwnerUnlockService:
    """A real unlock service over the household's own PIN credential and roles."""

    async def read_person(person_entity_id: int) -> PersonRecord | None:
        label = await get_person_label(entity_id=person_entity_id)
        if label is None:
            return None
        return PersonRecord(
            person_id=label.entity_id, display_name=label.display_name, entity_type="person"
        )

    registry = IdentitySessionRegistry(
        lookup_person=lambda _pid: None, clock=lambda: datetime.now(UTC), ttl=timedelta(seconds=60)
    )
    return OwnerUnlockService(
        clock=lambda: datetime.now(UTC),
        registry=registry,
        read_credential=get_active_owner_pin_credential,
        read_role=get_active_role,
        read_person=read_person,
    )


async def test_a_token_never_answers_an_offer_and_is_never_spent_by_the_attempt(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A valid owner PIN token with no face: the answer is ordinary and the grant stays usable."""
    owner = household.owner_entity_id
    candidate_id = await _candidate(owner)
    assert await candidates.mark_offered(
        candidate_id, owner, correlation_id=uuid4(), now=datetime.now(UTC)
    )
    service = _unlock_service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    _scene(monkeypatch, _ANSWER, faces=())

    async with _client() as client:
        response = await client.post(
            "/transcribe", headers={"X-Iroko-Identity-Token": unlock.token}, files=_files()
        )

    body = response.json()
    assert response.status_code == 200
    assert body["llm_response"] == _REPLY
    assert body["authentication_consumed"] is False
    assert body["identity_source"] is None
    assert await _status(candidate_id) is CandidateStatus.OFFERED
    assert await _audit_rows() == []
    # The token is still alive and unspent: observing it again still names the owner.
    event = transcribe_router._voice_event_from_transcript("hola")
    still_there = await service.for_request(unlock.token).peek_actor(event)
    assert still_there.person_id == owner


@pytest.mark.parametrize("setting", ["memory_enabled", "memory_candidates_enabled"])
def test_either_switch_off_binds_neither_the_preparation_nor_the_answerer(
    monkeypatch: pytest.MonkeyPatch, setting: str
) -> None:
    """The candidates need the memory store: with it off an answer must not even resolve a face."""
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
    monkeypatch.setattr(settings, setting, False)

    assert transcribe_router._memory_answerer() is None
    assert transcribe_router._offer_preparer(event=Mock(), wav_bytes=b"") is None
