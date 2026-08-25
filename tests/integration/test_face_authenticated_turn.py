"""End-to-end acceptance tests for in-request face authentication (Plan 0029).

Covers the Task 5 north star: a protected question answered with a webcam
frame attached — and no `X-Iroko-Identity-Token` header at all — resolves
the owner and gets the protected answer, through the real classic
`/transcribe` and `/transcribe/stream` routes. Mirrors
`tests/integration/test_owner_authenticated_turn.py`'s north-star scenario
and fixtures, adding a synthetic enrolled face (never a real image or model)
and monkeypatching only the face-DETECTION boundary — real `match_face`
still runs against the temp DB, exactly like `tests/integration/test_faces.py`.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from unittest.mock import AsyncMock

import cv2
from httpx import ASGITransport, AsyncClient, Response
import numpy as np
from pydantic import SecretStr
import pytest
from server.cognition import face_authentication as face_auth_module
from server.cognition.identity import PersonRecord
from server.cognition.identity_sessions import IdentitySessionRegistry
from server.cognition.owner_authentication import (
    OwnerRequestResolver,
    OwnerUnlockResult,
    OwnerUnlockService,
)
from server.main import app
from server.memory.biometric_consent import grant_face_consent
from server.memory.entity_labels import get_person_label
from server.memory.household_authorization import get_active_role
from server.memory.owner_credentials import get_active_owner_pin_credential
from server.memory.policy_gated_v4_reader import PolicyGatedV4Reader
from server.personal_setup import PersonalSetupInput, PersonalSetupResult, apply_personal_setup
from server.routers import transcribe as transcribe_module
from server.settings import settings
from server.text_turn import TextTurnResult
from server.vision.faces import DetectedFace, enroll_face

from server import db, stt, tts

_CHILD_ANSWER = "Tus hijos son Máximo y Dominga."
_CHILD_QUESTION = "¿Quiénes son mis hijos?"
_GENERIC_QUESTION = "¿qué día es hoy?"
_PIN = "482173"
_OWNER_NAME = "Pipec"
_FRAME_BYTES = cv2.imencode(".jpg", np.zeros((10, 10, 3), dtype=np.uint8))[1].tobytes()


def _unit_vector(axis: int) -> np.ndarray:
    """Return a 512-d unit vector along *axis* — a synthetic 'face' embedding."""
    vector = np.zeros(512, dtype=np.float32)
    vector[axis] = 1.0
    return vector


_OWNER_EMBEDDING = _unit_vector(0)
_STRANGER_EMBEDDING = _unit_vector(1)


def _detected(embedding: np.ndarray) -> DetectedFace:
    """Build one detected face with a synthetic embedding — no real detector."""
    return DetectedFace(embedding=embedding, score=0.9, width=200.0)


@pytest.fixture
async def face_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[PersonalSetupResult]:
    """Open a fresh temp DB with the north-star owner/children/PIN setup applied."""
    db_path = tmp_path / "face-authenticated-turn.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    result = await apply_personal_setup(
        PersonalSetupInput(
            owner_name=_OWNER_NAME,
            child_names=("Máximo", "Dominga"),
            pin=SecretStr(_PIN),
        )
    )
    yield result
    await db.close_db()
    db._conn = None


async def _enroll_owner_face(owner_entity_id: int) -> None:
    """Grant biometric consent and enroll the owner's synthetic embedding."""
    await grant_face_consent(owner_entity_id)
    await enroll_face(owner_entity_id, _OWNER_EMBEDDING, label=_OWNER_NAME)


def _mock_detect(monkeypatch: pytest.MonkeyPatch, faces: list[DetectedFace]) -> AsyncMock:
    """Stub only the face-DETECTION boundary — real match_face runs against the DB."""
    mock = AsyncMock(return_value=faces)
    monkeypatch.setattr(face_auth_module, "_detect_faces_default", mock)
    return mock


async def _read_person_record(person_entity_id: int) -> PersonRecord | None:
    """Adapt the safe entity-label lookup for a test-owned unlock service."""
    label = await get_person_label(entity_id=person_entity_id)
    if label is None:
        return None
    return PersonRecord(
        person_id=label.entity_id, display_name=label.display_name, entity_type="person"
    )


def _service(*, clock=lambda: datetime.now(UTC)) -> OwnerUnlockService:
    """Build a fresh owner-unlock service bound to the real repositories."""
    registry = IdentitySessionRegistry(
        lookup_person=lambda _person_id: None, clock=clock, ttl=timedelta(seconds=60)
    )
    return OwnerUnlockService(
        clock=clock,
        registry=registry,
        read_credential=get_active_owner_pin_credential,
        read_role=get_active_role,
        read_person=_read_person_record,
    )


class _SpyingUnlockService:
    """Wraps a real service, spying on `resolve_actor` of every resolver it hands out."""

    def __init__(self, real: OwnerUnlockService) -> None:
        self._real = real
        self.resolvers: list[OwnerRequestResolver] = []

    def for_request(self, token: str | None) -> OwnerRequestResolver:
        resolver = self._real.for_request(token)
        resolver.resolve_actor = AsyncMock(wraps=resolver.resolve_actor)  # type: ignore[method-assign]
        self.resolvers.append(resolver)
        return resolver

    async def unlock(self, pin: str) -> OwnerUnlockResult | None:
        return await self._real.unlock(pin)


@asynccontextmanager
async def _client() -> AsyncIterator[AsyncClient]:
    """Yield an async client without running application lifespan."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _parse_ndjson(response: Response) -> list[dict[str, object]]:
    return [json.loads(line) for line in response.text.strip().split("\n") if line.strip()]


def _mock_stt_tts(monkeypatch: pytest.MonkeyPatch, *, text: str) -> None:
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value=text))
    monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("AAAA", 42)))


def _files(silence_wav_bytes: bytes, *, with_frame: bool) -> dict[str, tuple[str, bytes, str]]:
    files = {"audio": ("a.wav", silence_wav_bytes, "audio/wav")}
    if with_frame:
        files["frame"] = ("frame.jpg", _FRAME_BYTES, "image/jpeg")
    return files


# ---------------------------------------------------------------------------
# 1. Owner's frame answers a protected question — classic /transcribe
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_owner_frame_answers_protected_question_classic(
    face_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, silence_wav_bytes: bytes
) -> None:
    """A recognized owner frame, with no token at all, answers the exact child names."""
    monkeypatch.setattr(settings, "face_authentication_enabled", True)
    await _enroll_owner_face(face_db.owner_entity_id)
    _mock_detect(monkeypatch, [_detected(_OWNER_EMBEDDING)])
    _mock_stt_tts(monkeypatch, text=_CHILD_QUESTION)

    async with _client() as client:
        response = await client.post(
            "/transcribe", files=_files(silence_wav_bytes, with_frame=True)
        )

    assert response.status_code == 200
    body = response.json()
    assert body["llm_response"] == _CHILD_ANSWER
    assert body["authentication_consumed"] is True
    assert body["identity_source"] == "face"


# ---------------------------------------------------------------------------
# 2. Stranger's frame denies without disclosure or v4 reads — classic
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_stranger_frame_denies_without_reading_v4_classic(
    face_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, silence_wav_bytes: bytes
) -> None:
    """An unmatched face must deny non-disclosingly and never reach v4 storage."""
    monkeypatch.setattr(settings, "face_authentication_enabled", True)
    await _enroll_owner_face(face_db.owner_entity_id)
    _mock_detect(monkeypatch, [_detected(_STRANGER_EMBEDDING)])
    _mock_stt_tts(monkeypatch, text=_CHILD_QUESTION)
    reader_spy = AsyncMock(wraps=PolicyGatedV4Reader.read_active_relations)
    monkeypatch.setattr(PolicyGatedV4Reader, "read_active_relations", reader_spy)

    async with _client() as client:
        response = await client.post(
            "/transcribe", files=_files(silence_wav_bytes, with_frame=True)
        )

    assert response.status_code == 200
    body = response.json()
    assert body["authentication_consumed"] is False
    assert body["identity_source"] is None
    assert "Máximo" not in body["llm_response"]
    assert "Dominga" not in body["llm_response"]
    reader_spy.assert_not_awaited()


# ---------------------------------------------------------------------------
# 3. Two faces (ambiguous) denies, never reads v4, never consults PIN
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_two_faces_denies_and_never_consults_pin_classic(
    face_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, silence_wav_bytes: bytes
) -> None:
    """Two faces in frame is terminal AMBIGUOUS — never falls through to the PIN resolver."""
    monkeypatch.setattr(settings, "face_authentication_enabled", True)
    await _enroll_owner_face(face_db.owner_entity_id)
    _mock_detect(monkeypatch, [_detected(_OWNER_EMBEDDING), _detected(_STRANGER_EMBEDDING)])
    _mock_stt_tts(monkeypatch, text=_CHILD_QUESTION)
    spy_service = _SpyingUnlockService(_service())
    monkeypatch.setattr(transcribe_module, "owner_unlock_service", spy_service)
    reader_spy = AsyncMock(wraps=PolicyGatedV4Reader.read_active_relations)
    monkeypatch.setattr(PolicyGatedV4Reader, "read_active_relations", reader_spy)

    async with _client() as client:
        response = await client.post(
            "/transcribe", files=_files(silence_wav_bytes, with_frame=True)
        )

    assert response.status_code == 200
    body = response.json()
    assert body["authentication_consumed"] is False
    assert body["identity_source"] is None
    reader_spy.assert_not_awaited()
    assert len(spy_service.resolvers) == 1
    spy_service.resolvers[0].resolve_actor.assert_not_awaited()  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# 4. A generic question with a frame attached never touches face detection
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_generic_question_with_frame_never_detects_faces(
    face_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, silence_wav_bytes: bytes
) -> None:
    """A non-protected turn must never trigger face detection, even with a frame attached."""
    monkeypatch.setattr(settings, "face_authentication_enabled", True)
    await _enroll_owner_face(face_db.owner_entity_id)
    detect_mock = _mock_detect(monkeypatch, [_detected(_OWNER_EMBEDDING)])
    _mock_stt_tts(monkeypatch, text=_GENERIC_QUESTION)
    process = AsyncMock(return_value=TextTurnResult("día genérico", "joy", 7, False))
    monkeypatch.setattr(transcribe_module, "process_text_turn", process)

    async with _client() as client:
        response = await client.post(
            "/transcribe", files=_files(silence_wav_bytes, with_frame=True)
        )

    assert response.status_code == 200
    detect_mock.assert_not_awaited()


# ---------------------------------------------------------------------------
# 5. No frame at all — Plan 0026/0027 PIN behavior is unchanged
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_no_frame_preserves_existing_pin_flow(
    face_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, silence_wav_bytes: bytes
) -> None:
    """With face auth ON but no frame supplied, a valid PIN token still answers exactly."""
    monkeypatch.setattr(settings, "face_authentication_enabled", True)
    service = _service()
    monkeypatch.setattr(transcribe_module, "owner_unlock_service", service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    _mock_stt_tts(monkeypatch, text=_CHILD_QUESTION)

    async with _client() as client:
        response = await client.post(
            "/transcribe",
            headers={"X-Iroko-Identity-Token": unlock.token},
            files=_files(silence_wav_bytes, with_frame=False),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["llm_response"] == _CHILD_ANSWER
    assert body["authentication_consumed"] is True
    assert body["identity_source"] == "local_unlock"


# ---------------------------------------------------------------------------
# 6. Flag off makes an attached frame completely inert
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_flag_off_ignores_attached_frame_entirely(
    face_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, silence_wav_bytes: bytes
) -> None:
    """With FACE_AUTHENTICATION_ENABLED off (default), a frame is accepted but never inspected."""
    assert settings.face_authentication_enabled is False
    await _enroll_owner_face(face_db.owner_entity_id)
    detect_mock = _mock_detect(monkeypatch, [_detected(_OWNER_EMBEDDING)])
    _mock_stt_tts(monkeypatch, text=_CHILD_QUESTION)

    async with _client() as client:
        response = await client.post(
            "/transcribe", files=_files(silence_wav_bytes, with_frame=True)
        )

    assert response.status_code == 200
    body = response.json()
    assert body["authentication_consumed"] is False
    assert body["identity_source"] is None
    assert "Máximo" not in body["llm_response"]
    assert "Dominga" not in body["llm_response"]
    detect_mock.assert_not_awaited()


# ---------------------------------------------------------------------------
# 7. Streaming parity — allowed / denied / ambiguous through /transcribe/stream
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_owner_frame_answers_protected_question_stream(
    face_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, silence_wav_bytes: bytes
) -> None:
    """Streaming parity for scenario 1: terminal `done` reports face identity."""
    monkeypatch.setattr(settings, "face_authentication_enabled", True)
    await _enroll_owner_face(face_db.owner_entity_id)
    _mock_detect(monkeypatch, [_detected(_OWNER_EMBEDDING)])
    _mock_stt_tts(monkeypatch, text=_CHILD_QUESTION)

    async with _client() as client:
        response = await client.post(
            "/transcribe/stream", files=_files(silence_wav_bytes, with_frame=True)
        )

    assert response.status_code == 200
    events = _parse_ndjson(response)
    audio_events = [event for event in events if event["type"] == "audio"]
    assert audio_events[0]["text"] == _CHILD_ANSWER
    assert events[-1]["authentication_consumed"] is True
    assert events[-1]["identity_source"] == "face"


@pytest.mark.integration
async def test_stranger_frame_denies_without_reading_v4_stream(
    face_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, silence_wav_bytes: bytes
) -> None:
    """Streaming parity for scenario 2: terminal `done` reports denial, no v4 read."""
    monkeypatch.setattr(settings, "face_authentication_enabled", True)
    await _enroll_owner_face(face_db.owner_entity_id)
    _mock_detect(monkeypatch, [_detected(_STRANGER_EMBEDDING)])
    _mock_stt_tts(monkeypatch, text=_CHILD_QUESTION)
    reader_spy = AsyncMock(wraps=PolicyGatedV4Reader.read_active_relations)
    monkeypatch.setattr(PolicyGatedV4Reader, "read_active_relations", reader_spy)

    async with _client() as client:
        response = await client.post(
            "/transcribe/stream", files=_files(silence_wav_bytes, with_frame=True)
        )

    assert response.status_code == 200
    events = _parse_ndjson(response)
    assert events[-1]["authentication_consumed"] is False
    assert events[-1]["identity_source"] is None
    joined = repr(events)
    assert "Máximo" not in joined
    assert "Dominga" not in joined
    reader_spy.assert_not_awaited()


@pytest.mark.integration
async def test_two_faces_denies_and_never_consults_pin_stream(
    face_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, silence_wav_bytes: bytes
) -> None:
    """Streaming parity for scenario 3: ambiguous is terminal, PIN never consulted."""
    monkeypatch.setattr(settings, "face_authentication_enabled", True)
    await _enroll_owner_face(face_db.owner_entity_id)
    _mock_detect(monkeypatch, [_detected(_OWNER_EMBEDDING), _detected(_STRANGER_EMBEDDING)])
    _mock_stt_tts(monkeypatch, text=_CHILD_QUESTION)
    spy_service = _SpyingUnlockService(_service())
    monkeypatch.setattr(transcribe_module, "owner_unlock_service", spy_service)
    reader_spy = AsyncMock(wraps=PolicyGatedV4Reader.read_active_relations)
    monkeypatch.setattr(PolicyGatedV4Reader, "read_active_relations", reader_spy)

    async with _client() as client:
        response = await client.post(
            "/transcribe/stream", files=_files(silence_wav_bytes, with_frame=True)
        )

    assert response.status_code == 200
    events = _parse_ndjson(response)
    assert events[-1]["authentication_consumed"] is False
    assert events[-1]["identity_source"] is None
    reader_spy.assert_not_awaited()
    assert len(spy_service.resolvers) == 1
    spy_service.resolvers[0].resolve_actor.assert_not_awaited()  # type: ignore[attr-defined]
