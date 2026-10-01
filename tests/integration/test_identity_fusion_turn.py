"""Face, voice and PIN through the real /transcribe routes (Plan 0054, ADR 0016).

Detection and the speaker embedding are doubles; face matching, the voice centroid and the
database are real. Audio is generated in code — never a human recording.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
import io
import json
from pathlib import Path
from typing import NamedTuple
from unittest.mock import AsyncMock
import wave

import aiosqlite
import cv2
from httpx import ASGITransport, AsyncClient
import numpy as np
from pydantic import SecretStr
import pytest
from server.cognition import (
    face_authentication as face_auth_module,
    speaker_authentication as speaker_auth_module,
)
from server.cognition.identity import HouseholdRole, PersonRecord
from server.cognition.identity_sessions import IdentitySessionRegistry
from server.cognition.owner_authentication import OwnerUnlockService, owner_unlock_service
from server.dependencies import get_owner_unlock_service
from server.main import app
from server.memory.biometric_consent import grant_face_consent
from server.memory.declarative import upsert_entity
from server.memory.entity_labels import get_person_label
from server.memory.household_authorization import assign_household_role, get_active_role
from server.memory.owner_credentials import get_active_owner_pin_credential
from server.memory.policy_gated_v4_reader import PolicyGatedV4Reader
from server.memory.relational_v4 import get_active_entity_relations
from server.memory.voice_consent import grant_voice_consent
from server.personal_setup import PersonalSetupInput, PersonalSetupResult, apply_personal_setup
from server.resources import AppResources
from server.routers import transcribe as transcribe_router
from server.settings import settings
from server.vision.faces import DetectedFace, enroll_face
from server.voice.speaker_embedding import SpeakerBackendError, model_id
from server.voice.voiceprints import enroll_voiceprint

from server import db, stt, tts

_CHILD_ANSWER = "Tus hijos son Joaquín y Martina."
_CHILD_QUESTION = "¿Quiénes son mis hijos?"
_PIN = "482173"
_OWNER_NAME = "Pipec"
_FRAME = cv2.imencode(".jpg", np.zeros((10, 10, 3), dtype=np.uint8))[1].tobytes()


def _axis(size: int, axis: int) -> np.ndarray:
    vector = np.zeros(size, dtype=np.float32)
    vector[axis] = 1.0
    return vector


_OWNER_FACE = _axis(512, 0)
_STRANGER_FACE = _axis(512, 1)
_MATCHING_VOICE = _axis(192, 0)  # distance ~0.42 to the centroid of axes 0..2
_OTHER_VOICE = _axis(192, 10)  # orthogonal: distance 1.0


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


@pytest.fixture
async def fusion_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[PersonalSetupResult]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "identity-fusion.db")
    monkeypatch.setattr(settings, "face_authentication_enabled", True)
    monkeypatch.setattr(settings, "speaker_authentication_enabled", True)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    result = await apply_personal_setup(
        PersonalSetupInput(
            owner_name=_OWNER_NAME, child_names=("Joaquín", "Martina"), pin=SecretStr(_PIN)
        )
    )
    await grant_face_consent(result.owner_entity_id)
    await enroll_face(result.owner_entity_id, _OWNER_FACE, label=_OWNER_NAME)
    await grant_voice_consent(result.owner_entity_id)
    for axis in range(3):
        await enroll_voiceprint(result.owner_entity_id, _axis(192, axis), "owner", model_id())
    yield result
    await db.close_db()
    db._conn = None


def _detect(monkeypatch: pytest.MonkeyPatch, faces: list[DetectedFace]) -> AsyncMock:
    mock = AsyncMock(return_value=faces)
    monkeypatch.setattr(face_auth_module, "_detect_faces_default", mock)
    return mock


def _embed(monkeypatch: pytest.MonkeyPatch, result: object) -> AsyncMock:
    mock = (
        AsyncMock(side_effect=result)
        if isinstance(result, Exception)
        else AsyncMock(return_value=result)
    )
    monkeypatch.setattr(speaker_auth_module, "embed_wav", mock)
    return mock


def _mock_stt_tts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value=_CHILD_QUESTION))
    monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("AAAA", 42)))


def _files(*, with_frame: bool = True) -> dict[str, tuple[str, bytes, str]]:
    files = {"audio": ("a.wav", _tone_wav(), "audio/wav")}
    if with_frame:
        files["frame"] = ("frame.jpg", _FRAME, "image/jpeg")
    return files


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
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.mark.integration
async def test_owner_face_and_matching_voice_answer_at_strong_assurance(
    fusion_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    _detect(monkeypatch, [_detected(_OWNER_FACE)])
    embed = _embed(monkeypatch, _MATCHING_VOICE)
    _mock_stt_tts(monkeypatch)

    async with _client() as client:
        response = await client.post("/transcribe", files=_files())

    body = response.json()
    assert response.status_code == 200
    assert body["llm_response"] == _CHILD_ANSWER
    assert body["identity_source"] == "face_voice"
    assert body["authentication_consumed"] is False
    embed.assert_awaited_once()


@pytest.mark.integration
async def test_owner_face_with_a_different_voice_still_answers_at_basic(
    fusion_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default path: a photograph plus another speaker opens ordinary private data."""
    _detect(monkeypatch, [_detected(_OWNER_FACE)])
    _embed(monkeypatch, _OTHER_VOICE)
    _mock_stt_tts(monkeypatch)

    async with _client() as client:
        response = await client.post("/transcribe", files=_files())

    body = response.json()
    assert body["llm_response"] == _CHILD_ANSWER
    assert body["identity_source"] == "face"


@pytest.mark.integration
async def test_a_dead_speaker_backend_does_not_fail_the_face_turn(
    fusion_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review Focus 3."""
    _detect(monkeypatch, [_detected(_OWNER_FACE)])
    _embed(monkeypatch, SpeakerBackendError("model unavailable"))
    _mock_stt_tts(monkeypatch)

    async with _client() as client:
        response = await client.post("/transcribe", files=_files())

    assert response.status_code == 200
    assert response.json()["llm_response"] == _CHILD_ANSWER
    assert response.json()["identity_source"] == "face"


@pytest.mark.integration
async def test_a_verified_voice_without_a_face_denies_and_is_never_embedded(
    fusion_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review Focus 5: a recording alone opens nothing and costs nothing."""
    embed = _embed(monkeypatch, _MATCHING_VOICE)
    _mock_stt_tts(monkeypatch)

    async with _client() as client:
        response = await client.post("/transcribe", files=_files(with_frame=False))

    body = response.json()
    assert "Joaquín" not in body["llm_response"]
    assert body["identity_source"] is None
    embed.assert_not_awaited()


@pytest.mark.integration
async def test_two_faces_with_a_valid_token_deny_and_keep_the_token(
    fusion_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review Focus 2, end to end: the veto denies, then the same token still works."""
    service = _service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    embed = _embed(monkeypatch, _MATCHING_VOICE)
    _mock_stt_tts(monkeypatch)
    headers = {"X-Iroko-Identity-Token": unlock.token}

    _detect(monkeypatch, [_detected(_OWNER_FACE), _detected(_STRANGER_FACE)])
    async with _client() as client:
        vetoed = await client.post("/transcribe", headers=headers, files=_files())
        alone = await client.post("/transcribe", headers=headers, files=_files(with_frame=False))

    assert "Joaquín" not in vetoed.json()["llm_response"]
    assert vetoed.json()["authentication_consumed"] is False
    assert alone.json()["llm_response"] == _CHILD_ANSWER
    assert alone.json()["identity_source"] == "local_unlock"
    embed.assert_not_awaited()


@pytest.mark.integration
async def test_speaker_evidence_off_leaves_the_face_at_basic_and_never_embeds(
    fusion_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "speaker_authentication_enabled", False)
    _detect(monkeypatch, [_detected(_OWNER_FACE)])
    embed = _embed(monkeypatch, _MATCHING_VOICE)
    _mock_stt_tts(monkeypatch)

    async with _client() as client:
        response = await client.post("/transcribe", files=_files())

    assert response.json()["identity_source"] == "face"
    embed.assert_not_awaited()


_DENIAL = "No puedo acceder a información familiar privada sin una autorización comprobada."
_ROUTES = ["/transcribe", "/transcribe/stream"]


class _Turn(NamedTuple):
    """What a route answered, normalized across the classic and streaming shapes."""

    status_code: int
    text: str
    identity_source: str | None
    consumed: bool
    errors: list[dict[str, object]]


async def _post_turn(
    client: AsyncClient, route: str, *, headers: dict[str, str] | None = None, frame: bool = True
) -> _Turn:
    response = await client.post(route, headers=headers, files=_files(with_frame=frame))
    if route == "/transcribe":
        body = response.json()
        return _Turn(
            response.status_code,
            body["llm_response"],
            body["identity_source"],
            body["authentication_consumed"],
            [],
        )
    events = [json.loads(line) for line in response.text.strip().split("\n") if line.strip()]
    done = [e for e in events if e["type"] == "done"]
    assert len(done) == 1
    return _Turn(
        response.status_code,
        next(e for e in events if e["type"] == "audio")["text"],
        done[0]["identity_source"],
        done[0]["authentication_consumed"],
        [e for e in events if e["type"] == "error"],
    )


def _spy_on_child_reads(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Wrap the raw V4 relation reader the controller uses, to prove it was (not) read."""
    spy = AsyncMock(wraps=get_active_entity_relations)
    monkeypatch.setattr(
        transcribe_router, "PolicyGatedV4Reader", lambda: PolicyGatedV4Reader(relation_reader=spy)
    )
    return spy


@pytest.mark.integration
@pytest.mark.parametrize("route", _ROUTES)
async def test_a_store_error_in_face_resolution_denies_instead_of_failing_the_turn(
    route: str, fusion_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review Focus 1, end to end: a generic denial, never a 500, and no private read."""
    _detect(monkeypatch, [_detected(_OWNER_FACE)])
    monkeypatch.setattr(
        face_auth_module, "get_active_role", AsyncMock(side_effect=aiosqlite.Error("db down"))
    )
    embed = _embed(monkeypatch, _MATCHING_VOICE)
    _mock_stt_tts(monkeypatch)
    reads = _spy_on_child_reads(monkeypatch)

    async with _client() as client:
        turn = await _post_turn(client, route)

    assert turn.status_code == 200
    assert turn.errors == []
    assert turn.text == _DENIAL
    assert turn.identity_source is None
    assert turn.consumed is False
    embed.assert_not_awaited()
    reads.assert_not_awaited()


@pytest.mark.integration
@pytest.mark.parametrize("route", _ROUTES)
async def test_a_store_error_in_face_resolution_still_honours_a_valid_pin(
    route: str, fusion_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The face store failing says nothing about the PIN: the token still unlocks."""
    service = _service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    _detect(monkeypatch, [_detected(_OWNER_FACE)])
    monkeypatch.setattr(
        face_auth_module, "get_active_role", AsyncMock(side_effect=aiosqlite.Error("db down"))
    )
    embed = _embed(monkeypatch, _MATCHING_VOICE)
    _mock_stt_tts(monkeypatch)

    async with _client() as client:
        turn = await _post_turn(client, route, headers={"X-Iroko-Identity-Token": unlock.token})

    assert turn.status_code == 200
    assert turn.errors == []
    assert turn.text == _CHILD_ANSWER
    assert turn.identity_source == "local_unlock"
    assert turn.consumed is True
    embed.assert_not_awaited()


@pytest.mark.integration
@pytest.mark.parametrize("route", _ROUTES)
@pytest.mark.parametrize("with_token", [True, False], ids=["token", "no-token"])
@pytest.mark.parametrize("consent", [True, False], ids=["consent", "no-consent"])
@pytest.mark.parametrize("role", [HouseholdRole.ADULT, None], ids=["adult", "no-role"])
async def test_another_enrolled_person_vetoes_against_a_real_role_row(
    route: str,
    with_token: bool,
    consent: bool,
    role: HouseholdRole | None,
    fusion_db: PersonalSetupResult,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review Focus 5: the veto holds against real rows and never spends the PIN token.

    A face matched to an enrolled person who is not the owner vetoes whatever their
    consent — and, by decision D-3, also when that person has no household role.
    """
    other_id = await upsert_entity(name="Canary Adult", type="person")
    if role is not None:
        await assign_household_role(
            person_entity_id=other_id, role=role, grantor_entity_id=fusion_db.owner_entity_id
        )
    if consent:
        await grant_face_consent(other_id)
    await enroll_face(other_id, _STRANGER_FACE, label="Canary Adult")
    service = _service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    headers: dict[str, str] | None = None
    if with_token:
        unlock = await service.unlock(_PIN)
        assert unlock is not None
        headers = {"X-Iroko-Identity-Token": unlock.token}
    _detect(monkeypatch, [_detected(_STRANGER_FACE)])
    embed = _embed(monkeypatch, _MATCHING_VOICE)
    _mock_stt_tts(monkeypatch)
    reads = _spy_on_child_reads(monkeypatch)

    async with _client() as client:
        vetoed = await _post_turn(client, route, headers=headers)
        reads.assert_not_awaited()
        embed.assert_not_awaited()
        alone = await _post_turn(client, route, headers=headers, frame=False)

    assert vetoed.status_code == 200
    assert vetoed.errors == []
    assert vetoed.text == _DENIAL
    assert vetoed.identity_source is None
    assert vetoed.consumed is False
    if with_token:
        assert alone.text == _CHILD_ANSWER
        assert alone.identity_source == "local_unlock"
        assert alone.consumed is True
    else:
        assert alone.text == _DENIAL
        assert alone.identity_source is None
        assert alone.consumed is False


@pytest.mark.integration
async def test_stream_route_reports_the_strong_source(
    fusion_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    _detect(monkeypatch, [_detected(_OWNER_FACE)])
    _embed(monkeypatch, _MATCHING_VOICE)
    _mock_stt_tts(monkeypatch)

    async with _client() as client:
        response = await client.post("/transcribe/stream", files=_files())

    events = [json.loads(line) for line in response.text.strip().split("\n") if line.strip()]
    assert events[-1]["identity_source"] == "face_voice"
    assert next(e for e in events if e["type"] == "audio")["text"] == _CHILD_ANSWER
