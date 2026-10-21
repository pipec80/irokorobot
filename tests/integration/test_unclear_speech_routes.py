"""A transcript Whisper doubted gets a fixed «unclear» reply on both voice routes.

Plan 0069 Task 2 (D-11): the controller is never called, nothing is written, no grant is
spent, and the stream keeps reply mode only when the request was a reply. Audio contract:
WAV · 16000 Hz · mono · int16.
"""

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
import pytest
from server.cognition.identity import PersonRecord
from server.cognition.identity_sessions import IdentitySessionRegistry
from server.cognition.owner_authentication import OwnerUnlockService, owner_unlock_service
from server.cognition.response_plan import UNCLEAR_SPEECH_PHRASE
from server.dependencies import get_owner_unlock_service
from server.exceptions import UnclearSpeechError
from server.main import app
from server.memory.entity_labels import get_person_label
from server.memory.household_authorization import get_active_role
from server.memory.owner_credentials import get_active_owner_pin_credential
from server.personal_setup import PersonalSetupInput, apply_personal_setup
from server.resources import AppResources
from server.routers import transcribe as transcribe_module
from server.settings import settings

from server import db, stt, tts

_REAL_CONTROLLER = transcribe_module._voice_controller
_REAL_SCHEDULER = transcribe_module._proposal_scheduler
_DOUBTFUL = "me gusta el palabracentinela"
_PIN = "482173"
_CHILD_QUESTION = "¿Quiénes son mis hijos?"
_CHILD_ANSWER = "Tus hijos son Joaquín y Martina."


def _unclear() -> AsyncMock:
    return AsyncMock(side_effect=UnclearSpeechError(_DOUBTFUL))


def _never(*_args: object, **_kwargs: object) -> object:
    raise AssertionError("the controller and the proposal must not run on an unclear turn")


@pytest.fixture(autouse=True)
def _no_turn_machinery(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stt, "transcribe", _unclear())
    monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("QQ==", 10)))
    monkeypatch.setattr(transcribe_module, "_voice_controller", _never)
    monkeypatch.setattr(transcribe_module, "_proposal_scheduler", _never)


def _events(text: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in text.strip().split("\n") if line.strip()]


@pytest.mark.integration
def test_classic_answers_the_unclear_phrase(client: TestClient, silence_wav_bytes: bytes) -> None:
    response = client.post(
        "/transcribe", files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["llm_response"] == UNCLEAR_SPEECH_PHRASE
    assert body["text_heard"] == _DOUBTFUL
    assert body["authentication_consumed"] is False
    assert body["identity_source"] is None


@pytest.mark.integration
@pytest.mark.parametrize("short_reply", [True, False], ids=["reply-mode", "normal"])
def test_stream_answers_the_unclear_phrase_and_keeps_reply_mode_only_for_a_reply(
    client: TestClient, silence_wav_bytes: bytes, short_reply: bool
) -> None:
    response = client.post(
        "/transcribe/stream",
        files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
        data={"short_reply": str(short_reply).lower()},
    )

    assert response.status_code == 200
    events = _events(response.text)
    spoken = [str(event["text"]) for event in events if event["type"] == "audio"]
    assert spoken == [UNCLEAR_SPEECH_PHRASE]
    done = events[-1]
    assert done["type"] == "done"
    assert done["expects_short_reply"] is short_reply
    assert done["authentication_consumed"] is False


@pytest.mark.integration
def test_an_empty_transcript_is_still_a_422(
    client: TestClient, silence_wav_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value="   "))

    response = client.post(
        "/transcribe", files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")}
    )

    assert response.status_code == 422


@pytest.fixture
async def owner_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """A fresh temporary database with an owner, two invented children and a PIN."""
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "unclear.db")
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    await apply_personal_setup(
        PersonalSetupInput(
            owner_name="Pipec", child_names=("Joaquín", "Martina"), pin=SecretStr(_PIN)
        )
    )
    yield
    await db.close_db()
    db._conn = None


async def _person(person_entity_id: int) -> PersonRecord | None:
    label = await get_person_label(entity_id=person_entity_id)
    if label is None:
        return None
    return PersonRecord(
        person_id=label.entity_id, display_name=label.display_name, entity_type="person"
    )


def _service() -> OwnerUnlockService:
    clock = lambda: datetime.now(UTC)  # noqa: E731
    registry = IdentitySessionRegistry(
        lookup_person=lambda _person_id: None, clock=clock, ttl=timedelta(seconds=60)
    )
    return OwnerUnlockService(
        clock=clock,
        registry=registry,
        read_credential=get_active_owner_pin_credential,
        read_role=get_active_role,
        read_person=_person,
    )


@asynccontextmanager
async def _async_client() -> AsyncGenerator[AsyncClient]:
    async with AsyncClient() as http_client:
        app.state.resources = AppResources(
            http_client=http_client, owner_unlock_service=owner_unlock_service
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client


@pytest.mark.integration
async def test_an_unclear_turn_does_not_spend_the_owner_grant(
    owner_db: None, monkeypatch: pytest.MonkeyPatch, silence_wav_bytes: bytes
) -> None:
    service = _service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    headers = {"X-Iroko-Identity-Token": unlock.token}
    audio = {"audio": ("a.wav", silence_wav_bytes, "audio/wav")}

    async with _async_client() as client:
        unclear = await client.post("/transcribe", headers=headers, files=audio)
        # The same token, now on a clear protected question, through the real controller.
        monkeypatch.setattr(transcribe_module, "_voice_controller", _REAL_CONTROLLER)
        monkeypatch.setattr(transcribe_module, "_proposal_scheduler", _REAL_SCHEDULER)
        monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value=_CHILD_QUESTION))
        answered = await client.post("/transcribe", headers=headers, files=audio)

    assert unclear.json()["llm_response"] == UNCLEAR_SPEECH_PHRASE
    assert unclear.json()["authentication_consumed"] is False
    assert answered.json()["llm_response"] == _CHILD_ANSWER
    assert answered.json()["authentication_consumed"] is True
