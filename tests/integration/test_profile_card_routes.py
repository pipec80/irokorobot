"""The profile card through the real routes (Plan 0074, ADR 0026 decision 3).

Face detection is a double; the identity store, the policy, the audit and the V4 repository are
real. Model replies are scripted: no real model, no recording. Every value is an invented canary.
"""

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
import io
import json
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
from server.cognition.identity import PersonRecord
from server.cognition.identity_sessions import IdentitySessionRegistry
from server.cognition.owner_authentication import OwnerUnlockService, owner_unlock_service
from server.dependencies import get_owner_unlock_service
from server.main import app
from server.memory.biometric_consent import grant_face_consent
from server.memory.entity_labels import get_person_label
from server.memory.household_authorization import get_active_role
from server.memory.owner_credentials import get_active_owner_pin_credential
from server.memory.predicate_registry import resolve_predicate
from server.memory.profile_card import CARD_HEADER
from server.memory.relational_v4 import assert_literal_fact
from server.personal_setup import PersonalSetupInput, PersonalSetupResult, apply_personal_setup
from server.resources import AppResources
from server.routers import transcribe as transcribe_module
from server.settings import settings
from server.vision.faces import DetectedFace, enroll_face

from server import db, llm, llm_streaming, stt, tts

_PIN = "482173"
_OWNER_NAME = "Canary"
_CARD_NAME = "Zeta"
_TASTE = "mate"
_FRAME = cv2.imencode(".jpg", np.zeros((10, 10, 3), dtype=np.uint8))[1].tobytes()
_OWNER_FACE = np.eye(512, dtype=np.float32)[0]
_AUDIT_COUNT = (
    "SELECT COUNT(*) FROM authorization_audit_events "
    "WHERE action = 'read_personal_conversation_memory'"
)

pytestmark = pytest.mark.integration


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


async def _own(owner_id: int, alias: str, value: str) -> None:
    definition = resolve_predicate(alias)
    assert definition is not None
    await assert_literal_fact(
        subject_entity_id=owner_id,
        definition=definition,
        value=value,
        visibility="personal",
        sensitivity="normal",
    )


@pytest.fixture
async def household(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[PersonalSetupResult]:
    """A real database: a face-enrolled owner whose card holds a name and a taste."""
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "profile-card-routes.db")
    monkeypatch.setattr(settings, "face_authentication_enabled", True)
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "profile_card_enabled", True)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    result = await apply_personal_setup(
        PersonalSetupInput(owner_name=_OWNER_NAME, child_names=("Hija Uno",), pin=SecretStr(_PIN))
    )
    await grant_face_consent(result.owner_entity_id)
    await enroll_face(result.owner_entity_id, _OWNER_FACE, label=_OWNER_NAME)
    await _own(result.owner_entity_id, "preferred_name", _CARD_NAME)
    await _own(result.owner_entity_id, "likes", _TASTE)
    yield result
    await db.close_db()
    db._conn = None


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


def _hear(monkeypatch: pytest.MonkeyPatch, *sentences: str) -> None:
    monkeypatch.setattr(stt, "transcribe", AsyncMock(side_effect=list(sentences)))
    monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("AAAA", 42)))


def _classic_prompts(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Capture the system prompt of every classic model call."""
    prompts: list[str] = []

    async def generate(_client: object, system_prompt: str, _messages: object) -> tuple[str, str]:
        prompts.append(system_prompt)
        return "Hola.", "neutral"

    monkeypatch.setattr(llm, "_generate_ollama", generate)
    return prompts


def _stream_prompts(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Capture the system prompt of every streamed model call."""
    prompts: list[str] = []

    async def stream(
        _client: object, messages: list[dict[str, str]], **_kwargs: object
    ) -> AsyncIterator[str]:
        prompts.append(messages[0]["content"])
        yield "Hola."

    monkeypatch.setattr(llm_streaming, "ollama_chat_stream", stream)
    return prompts


async def _audit_rows() -> int:
    cursor = await db.get_conn().execute(_AUDIT_COUNT)
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    return int(row[0])


@pytest.mark.parametrize(
    "memory_enabled, card_enabled, expected_provider",
    [(True, False, False), (False, True, False), (True, True, True)],
    ids=["card-off", "memory-off", "both-on"],
)
def test_profile_card_provider_is_none_unless_both_switches_are_on(
    monkeypatch: pytest.MonkeyPatch,
    memory_enabled: bool,
    card_enabled: bool,
    expected_provider: bool,
) -> None:
    monkeypatch.setattr(settings, "memory_enabled", memory_enabled)
    monkeypatch.setattr(settings, "profile_card_enabled", card_enabled)

    provider = transcribe_module._profile_card_provider(uuid4())

    assert (provider is not None) is expected_provider


async def test_the_classic_route_puts_the_owners_card_in_the_prompt_with_one_audit_row(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "Hola, ¿cómo estás?")
    prompts = _classic_prompts(monkeypatch)

    async with _client() as client:
        response = await client.post("/transcribe", files=_files())

    assert response.status_code == 200
    (prompt,) = prompts
    assert CARD_HEADER in prompt
    assert f'Nombre: "{_CARD_NAME}"' in prompt
    assert f'"{_TASTE}"' in prompt
    assert _OWNER_NAME not in prompt  # the display name is not the card
    assert await _audit_rows() == 1


async def test_with_the_card_switch_off_the_prompt_is_the_one_of_a_stranger(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "profile_card_enabled", False)
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "Hola, ¿cómo estás?", "Hola, ¿cómo estás?")
    prompts = _classic_prompts(monkeypatch)

    async with _client() as client:
        owner = await client.post("/transcribe", files=_files())
        stranger = await client.post("/transcribe", files=_files(with_frame=False))

    assert owner.status_code == stranger.status_code == 200
    owner_prompt, stranger_prompt = prompts
    assert owner_prompt == stranger_prompt
    assert CARD_HEADER not in owner_prompt
    assert await _audit_rows() == 0


async def test_an_unknown_speaker_gets_no_card_and_no_audit_row(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    _hear(monkeypatch, "Hola, ¿cómo estás?")
    prompts = _classic_prompts(monkeypatch)

    async with _client() as client:
        response = await client.post("/transcribe", files=_files(with_frame=False))

    assert response.status_code == 200
    (prompt,) = prompts
    assert CARD_HEADER not in prompt
    assert _TASTE not in prompt
    assert await _audit_rows() == 0


async def test_the_streaming_route_has_the_same_card_and_the_same_silences(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    _hear(monkeypatch, "Hola, ¿cómo estás?", "Hola, ¿cómo estás?", "Hola, ¿cómo estás?")
    prompts = _stream_prompts(monkeypatch)

    async with _client() as client:
        _see_the_owner(monkeypatch)
        owner = await client.post("/transcribe/stream", files=_files())
        stranger = await client.post("/transcribe/stream", files=_files(with_frame=False))
        monkeypatch.setattr(settings, "profile_card_enabled", False)
        switched_off = await client.post("/transcribe/stream", files=_files())

    for response in (owner, stranger, switched_off):
        events = [json.loads(line) for line in response.text.splitlines() if line]
        assert events[-1]["type"] == "done"
    owner_prompt, stranger_prompt, off_prompt = prompts
    assert CARD_HEADER in owner_prompt
    assert f'Nombre: "{_CARD_NAME}"' in owner_prompt
    assert CARD_HEADER not in stranger_prompt
    assert off_prompt == stranger_prompt
    assert await _audit_rows() == 1


async def test_chat_and_the_visual_dialogue_never_read_the_card(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = IdentitySessionRegistry(
        lookup_person=lambda _pid: None, clock=lambda: datetime.now(UTC), ttl=timedelta(seconds=60)
    )

    async def person(person_entity_id: int) -> PersonRecord | None:
        label = await get_person_label(entity_id=person_entity_id)
        return (
            None
            if label is None
            else PersonRecord(
                person_id=label.entity_id, display_name=label.display_name, entity_type="person"
            )
        )

    service = OwnerUnlockService(
        clock=lambda: datetime.now(UTC),
        registry=registry,
        read_credential=get_active_owner_pin_credential,
        read_role=get_active_role,
        read_person=person,
    )
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    monkeypatch.setattr(settings, "vision_enabled", True)
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "Hola, Iroko")
    prompts = _classic_prompts(monkeypatch)

    async with _client() as client:
        chat = await client.post(
            "/chat",
            headers={"X-Iroko-Identity-Token": unlock.token},
            json={"message": "Hola, ¿cómo estás?", "conversation_id": "web"},
        )
        visual = await client.post(
            "/vision/respond",
            files={"image": ("frame.jpg", _FRAME, "image/jpeg")},
            data={"text": "Hola, Iroko"},
        )

    assert chat.status_code == visual.status_code == 200
    assert prompts
    for prompt in prompts:
        assert CARD_HEADER not in prompt
        assert _TASTE not in prompt
    assert await _audit_rows() == 0
