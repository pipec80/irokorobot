"""The pending-topic follow-up through the two real voice routes (Plan 0084 Task 6).

Face detection, speech-to-text, the model and the TTS are doubles; the store, the policy, the audit,
the identity store and the routes are real. A topic is stored due yesterday. Canaries only.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
import io
import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock
from uuid import UUID, uuid4
import wave

import cv2
from httpx import ASGITransport, AsyncClient
import numpy as np
from pydantic import SecretStr
import pytest
from server.cognition import face_authentication as face_auth_module
from server.cognition.owner_authentication import owner_unlock_service
from server.main import app
from server.memory import pending_store
from server.memory.biometric_consent import grant_face_consent
from server.memory.candidate_dialogue import PendingOffer
from server.personal_setup import PersonalSetupInput, PersonalSetupResult, apply_personal_setup
from server.resources import AppResources
from server.routers import transcribe as transcribe_module
from server.settings import settings
from server.vision.faces import DetectedFace, enroll_face

from server import db, llm, llm_streaming, stt, text_turn, tts

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from server.memory.pending_store import PendingSensitivity

pytestmark = pytest.mark.integration

_FRAME = cv2.imencode(".jpg", np.zeros((10, 10, 3), dtype=np.uint8))[1].tobytes()
_OWNER_FACE = np.eye(512, dtype=np.float32)[0]
_STRANGER_FACE = np.eye(512, dtype=np.float32)[1]
_REPLY = "Hola, qué gusto verte."
_SENTENCE = "¿Cómo te fue ayer con el banco?"
_OFFER = "Antes me dijiste que te gusta el mate."
_T = "2026-11-03T10:00:00.000000+00:00"
# Thursday 2026-11-12, noon in Santiago.
_NOW = datetime(2026, 11, 12, 15, tzinfo=UTC)
_TODAY = date(2026, 11, 12)
_DONE_KEYS = {
    "type",
    "stt_ms",
    "llm_ms",
    "tts_ms",
    "total_ms",
    "authentication_consumed",
    "identity_source",
    "expects_short_reply",
}


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


def _files() -> dict[str, tuple[str, bytes, str]]:
    return {
        "audio": ("a.wav", _tone_wav(), "audio/wav"),
        "frame": ("frame.jpg", _FRAME, "image/jpeg"),
    }


@pytest.fixture
async def household(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[PersonalSetupResult]:
    """A real database, an enrolled owner with a consented face, the switches on."""
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "pending-routes.db")
    monkeypatch.setattr(settings, "face_authentication_enabled", True)
    monkeypatch.setattr(settings, "speaker_authentication_enabled", False)
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "conversation_record_enabled", True)
    monkeypatch.setattr(settings, "pending_topics_enabled", True)
    monkeypatch.setattr(settings, "memory_candidates_enabled", False)
    monkeypatch.setattr(settings, "household_timezone", "America/Santiago")
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    result = await apply_personal_setup(
        PersonalSetupInput(owner_name="Canary", child_names=(), pin=SecretStr("482173"))
    )
    await grant_face_consent(result.owner_entity_id)
    await enroll_face(result.owner_entity_id, _OWNER_FACE, label="Canary")
    # One instant for the whole test, so a run across local midnight never flaps (Task 8 review).
    monkeypatch.setattr(transcribe_module, "utc_now", lambda: _NOW)
    yield result
    await db.close_db()
    db._conn = None


async def _topic_due_yesterday(
    owner_id: int, topic: str = "el banco", *, sensitivity: PendingSensitivity = "normal"
) -> int:
    today = _TODAY
    cursor = await db.get_conn().execute(
        "INSERT INTO conversation_records (owner_entity_id, started_at, last_turn_at, closed_at, "
        "expires_at) VALUES (?, ?, ?, ?, ?)",
        (owner_id, _T, _T, _T, "2099-01-01T00:00:00.000000+00:00"),
    )
    record_id = int(cursor.lastrowid or 0)
    await cursor.close()
    await db.get_conn().commit()
    async with db.transaction() as conn:
        topic_id = await pending_store.insert_unnamed(
            conn,
            owner_entity_id=owner_id,
            record_id=record_id,
            correlation_id=uuid4(),
            said_day=today - timedelta(days=2),
            due_day=today - timedelta(days=1),
            heard="zzheardzz",
            sensitivity=sensitivity,
            now=_NOW - timedelta(days=2),
        )
    assert await pending_store.set_topic(topic_id, topic)
    return topic_id


async def _state(topic_id: int) -> str:
    cursor = await db.get_conn().execute(
        "SELECT state FROM pending_topics WHERE id = ?", (topic_id,)
    )
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    return str(row[0])


@asynccontextmanager
async def _client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient() as http_client:
        app.state.resources = AppResources(
            http_client=http_client, owner_unlock_service=owner_unlock_service
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client


def _faces(monkeypatch: pytest.MonkeyPatch, *faces: np.ndarray) -> None:
    monkeypatch.setattr(
        face_auth_module,
        "_detect_faces_default",
        AsyncMock(
            return_value=[DetectedFace(embedding=face, score=0.9, width=200.0) for face in faces]
        ),
    )


def _doubles(monkeypatch: pytest.MonkeyPatch, *, turns: int = 2) -> AsyncMock:
    """Script the speech, the classic and the streaming model; return the TTS spy."""
    monkeypatch.setattr(stt, "transcribe", AsyncMock(side_effect=["Hola."] * turns))
    monkeypatch.setattr(
        llm, "generate_response", AsyncMock(side_effect=[(_REPLY, "neutral")] * turns)
    )

    async def generate_stream(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        yield _REPLY

    monkeypatch.setattr(llm_streaming, "generate_response_stream", generate_stream)
    synthesize = AsyncMock(return_value=("AAAA", 42))
    monkeypatch.setattr(tts, "synthesize", synthesize)
    return synthesize


def _said(synthesize: AsyncMock) -> list[str]:
    return [call.args[0] for call in synthesize.await_args_list]


async def _stream(client: AsyncClient) -> list[dict[str, object]]:
    response = await client.post("/transcribe/stream", files=_files())
    assert response.status_code == 200
    return [json.loads(line) for line in response.text.splitlines() if line]


async def test_the_classic_route_says_it_once(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    topic_id = await _topic_due_yesterday(household.owner_entity_id)
    _faces(monkeypatch, _OWNER_FACE)
    synthesize = _doubles(monkeypatch)

    async with _client() as client:
        first = await client.post("/transcribe", files=_files())
        second = await client.post("/transcribe", files=_files())

    assert first.status_code == second.status_code == 200
    assert first.json()["llm_response"] == _REPLY
    assert _said(synthesize) == [f"{_REPLY} {_SENTENCE}", _REPLY]
    assert await _state(topic_id) == "asked"


async def test_the_stream_says_it_once_and_done_gains_no_field(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    topic_id = await _topic_due_yesterday(household.owner_entity_id)
    _faces(monkeypatch, _OWNER_FACE)
    synthesize = _doubles(monkeypatch)

    async with _client() as client:
        first = await _stream(client)
        second = await _stream(client)

    assert [event["type"] for event in first] == ["text_heard", "emotion", "audio", "audio", "done"]
    assert first[3]["text"] == ""
    assert set(first[-1]) == _DONE_KEYS
    assert [event["type"] for event in second].count("audio") == 1
    assert _said(synthesize) == [_REPLY, _SENTENCE, _REPLY]
    assert await _state(topic_id) == "asked"


@pytest.mark.parametrize("route", ["classic", "stream"])
async def test_a_guest_in_view_hears_nothing(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    topic_id = await _topic_due_yesterday(household.owner_entity_id)
    _faces(monkeypatch, _OWNER_FACE, _STRANGER_FACE)
    synthesize = _doubles(monkeypatch, turns=1)

    async with _client() as client:
        if route == "classic":
            response = await client.post("/transcribe", files=_files())
            assert response.status_code == 200
        else:
            await _stream(client)

    assert _said(synthesize) == [_REPLY]
    assert await _state(topic_id) == "open"


async def test_an_open_offer_wins_and_the_topic_stays_open(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    topic_id = await _topic_due_yesterday(household.owner_entity_id)
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
    _faces(monkeypatch, _OWNER_FACE)
    synthesize = _doubles(monkeypatch, turns=1)
    offer = PendingOffer(
        candidate_id=1,
        subject_person_id=household.owner_entity_id,
        phrase=_OFFER,
        actor=None,  # type: ignore[arg-type]  # the commit is a double; the actor is not read
        correlation_id=UUID(int=1),
    )
    monkeypatch.setattr(transcribe_module, "prepare_offer", AsyncMock(return_value=offer))
    monkeypatch.setattr(text_turn, "commit_offer", AsyncMock(return_value=_OFFER))

    async with _client() as client:
        response = await client.post("/transcribe", files=_files())

    assert response.status_code == 200
    assert _said(synthesize) == [f"{_REPLY} {_OFFER}"]
    assert await _state(topic_id) == "open"


@pytest.mark.parametrize("route", ["classic", "stream"])
async def test_with_the_switch_off_every_route_is_byte_identical(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    topic_id = await _topic_due_yesterday(household.owner_entity_id)
    monkeypatch.setattr(settings, "pending_topics_enabled", False)
    _faces(monkeypatch, _OWNER_FACE)
    synthesize = _doubles(monkeypatch, turns=1)
    preparer = AsyncMock()
    monkeypatch.setattr(transcribe_module, "prepare_follow_up", preparer)
    reads = {name: AsyncMock() for name in ("due_topic", "asked_today", "mark_asked")}
    for name, spy in reads.items():
        monkeypatch.setattr(f"server.memory.pending_follow_up.{name}", spy)

    async with _client() as client:
        if route == "classic":
            body = (await client.post("/transcribe", files=_files())).json()
            assert body["llm_response"] == _REPLY
        else:
            events = await _stream(client)
            assert [event["type"] for event in events] == ["text_heard", "emotion", "audio", "done"]

    assert _said(synthesize) == [_REPLY]
    preparer.assert_not_awaited()
    for spy in reads.values():
        spy.assert_not_awaited()
    assert await _state(topic_id) == "open"


async def _close_the_alta() -> None:
    await db.get_conn().execute(
        "INSERT INTO commissioning_records (installation_id, started_at, interviewer_label, "
        "interviewer_role, confirmation_mode, disk_encryption, pool_version, closed_at) "
        "VALUES (?, ?, 'Canary Builder', 'builder', 'builder_is_owner', 'unknown', 1, ?)",
        ("00000000-0000-0000-0000-000000000084", _T, _T),
    )
    await db.get_conn().commit()


@pytest.mark.parametrize("closed", [True, False], ids=["alta-closed", "alta-open"])
async def test_a_health_topic_needs_the_closed_alta_on_the_route(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, closed: bool
) -> None:
    topic_id = await _topic_due_yesterday(
        household.owner_entity_id, "el médico", sensitivity="medical"
    )
    if closed:
        await _close_the_alta()
    _faces(monkeypatch, _OWNER_FACE)
    synthesize = _doubles(monkeypatch, turns=1)

    async with _client() as client:
        assert (await client.post("/transcribe", files=_files())).status_code == 200

    if closed:
        assert _said(synthesize) == [f"{_REPLY} ¿Cómo te fue ayer con el médico?"]
        assert await _state(topic_id) == "asked"
    else:
        assert _said(synthesize) == [_REPLY]
        assert await _state(topic_id) == "open"


async def test_a_health_topic_is_never_said_with_a_guest_in_view(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    topic_id = await _topic_due_yesterday(
        household.owner_entity_id, "el médico", sensitivity="medical"
    )
    await _close_the_alta()
    _faces(monkeypatch, _OWNER_FACE, _STRANGER_FACE)
    synthesize = _doubles(monkeypatch, turns=1)

    async with _client() as client:
        await _stream(client)

    assert _said(synthesize) == [_REPLY]
    assert await _state(topic_id) == "open"


async def test_the_next_model_turn_hears_the_question_and_this_one_never_reads_it(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-12 and the prompt guard on the real route: the model reads no topic when it speaks."""
    await _topic_due_yesterday(household.owner_entity_id)
    _faces(monkeypatch, _OWNER_FACE)
    _doubles(monkeypatch)

    async with _client() as client:
        await client.post("/transcribe", files=_files())
        await client.post("/transcribe", files=_files())

    first, second = llm.generate_response.await_args_list  # type: ignore[attr-defined]  # an AsyncMock
    assert "banco" not in repr(first.args) + repr(first.kwargs)
    history = [turn.content for turn in second.kwargs["history"]]
    assert history == ["Hola.", f"{_REPLY} {_SENTENCE}"]
