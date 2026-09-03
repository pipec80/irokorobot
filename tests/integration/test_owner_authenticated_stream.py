"""Streaming parity acceptance tests for the one-use owner-authenticated turn.

Plan 0027 Task 3. Mirrors tests/integration/test_owner_authenticated_turn.py's
north-star scenario through the real POST /transcribe/stream NDJSON route
instead of classic /transcribe: a valid local unlock answers the confirmed
child question exactly once, with the terminal `done` event reporting
`authentication_consumed=true`; absent, expired, replayed, and malformed
tokens deny without disclosure and without reaching v4 storage. A generic
turn with a valid token must not consume the grant.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient, Response
from pydantic import SecretStr
import pytest
from server.cognition.identity import PersonRecord
from server.cognition.identity_sessions import IdentitySessionRegistry
from server.cognition.owner_authentication import OwnerUnlockService
from server.dependencies import get_owner_unlock_service
from server.main import app
from server.memory.entity_labels import get_person_label
from server.memory.household_authorization import get_active_role
from server.memory.owner_credentials import get_active_owner_pin_credential
from server.memory.policy_gated_v4_reader import PolicyGatedV4Reader
from server.personal_setup import PersonalSetupInput, apply_personal_setup
from server.settings import settings

from server import db, stt, tts

_CHILD_ANSWER = "Tus hijos son Máximo y Dominga."
_CHILD_QUESTION = "¿Quiénes son mis hijos?"
_PIN = "482173"


@pytest.fixture
async def acceptance_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Open a fresh temp DB with the north-star owner/children/PIN setup applied."""
    db_path = tmp_path / "owner-authenticated-stream.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    await apply_personal_setup(
        PersonalSetupInput(
            owner_name="Pipec",
            child_names=("Máximo", "Dominga"),
            pin=SecretStr(_PIN),
        )
    )
    yield
    await db.close_db()
    db._conn = None


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


async def _post_stream(
    client: AsyncClient, *, token: str | None, silence_wav_bytes: bytes
) -> Response:
    headers = {"X-Iroko-Identity-Token": token} if token else {}
    return await client.post(
        "/transcribe/stream",
        headers=headers,
        files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
    )


@pytest.mark.integration
async def test_stream_with_valid_token_speaks_the_exact_child_answer_once(
    acceptance_db: None, monkeypatch: pytest.MonkeyPatch, silence_wav_bytes: bytes
) -> None:
    """A fresh unlock, used once, streams exactly the confirmed child names."""
    service = _service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    _mock_stt_tts(monkeypatch, text=_CHILD_QUESTION)

    async with _client() as client:
        response = await _post_stream(
            client, token=unlock.token, silence_wav_bytes=silence_wav_bytes
        )

    assert response.status_code == 200
    events = _parse_ndjson(response)
    assert [event["type"] for event in events] == ["text_heard", "emotion", "audio", "done"]
    audio_events = [event for event in events if event["type"] == "audio"]
    assert audio_events[0]["text"] == _CHILD_ANSWER
    assert events[-1]["authentication_consumed"] is True


@pytest.mark.integration
async def test_stream_replayed_token_denies_without_disclosure(
    acceptance_db: None, monkeypatch: pytest.MonkeyPatch, silence_wav_bytes: bytes
) -> None:
    """Reusing an already-consumed token must deny exactly like an absent one."""
    service = _service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    _mock_stt_tts(monkeypatch, text=_CHILD_QUESTION)

    async with _client() as client:
        first = await _post_stream(client, token=unlock.token, silence_wav_bytes=silence_wav_bytes)
        reader_spy = AsyncMock(wraps=PolicyGatedV4Reader.read_active_relations)
        monkeypatch.setattr(PolicyGatedV4Reader, "read_active_relations", reader_spy)
        second = await _post_stream(client, token=unlock.token, silence_wav_bytes=silence_wav_bytes)

    first_events = _parse_ndjson(first)
    second_events = _parse_ndjson(second)
    assert first_events[-1]["authentication_consumed"] is True
    assert second_events[-1]["authentication_consumed"] is False
    joined = repr(second_events)
    assert "Máximo" not in joined
    assert "Dominga" not in joined
    reader_spy.assert_not_awaited()


@pytest.mark.integration
@pytest.mark.parametrize(
    "token",
    [None, "not-a-real-token"],
    ids=["absent", "malformed"],
)
async def test_stream_absent_or_malformed_token_denies_without_reading_v4(
    acceptance_db: None,
    monkeypatch: pytest.MonkeyPatch,
    silence_wav_bytes: bytes,
    token: str | None,
) -> None:
    """No usable token must never reach v4 storage or disclose the names."""
    service = _service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    _mock_stt_tts(monkeypatch, text=_CHILD_QUESTION)
    reader_spy = AsyncMock(wraps=PolicyGatedV4Reader.read_active_relations)
    monkeypatch.setattr(PolicyGatedV4Reader, "read_active_relations", reader_spy)

    async with _client() as client:
        response = await _post_stream(client, token=token, silence_wav_bytes=silence_wav_bytes)

    assert response.status_code == 200
    events = _parse_ndjson(response)
    assert events[-1]["authentication_consumed"] is False
    joined = repr(events)
    assert "Máximo" not in joined
    assert "Dominga" not in joined
    reader_spy.assert_not_awaited()


@pytest.mark.integration
async def test_stream_expired_token_denies_without_reading_v4(
    acceptance_db: None, monkeypatch: pytest.MonkeyPatch, silence_wav_bytes: bytes
) -> None:
    """A token past its 60-second TTL must deny exactly like an absent one."""
    now = datetime.now(UTC)

    def clock() -> datetime:
        return now

    service = _service(clock=clock)
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    now = now + timedelta(seconds=61)
    _mock_stt_tts(monkeypatch, text=_CHILD_QUESTION)
    reader_spy = AsyncMock(wraps=PolicyGatedV4Reader.read_active_relations)
    monkeypatch.setattr(PolicyGatedV4Reader, "read_active_relations", reader_spy)

    async with _client() as client:
        response = await _post_stream(
            client, token=unlock.token, silence_wav_bytes=silence_wav_bytes
        )

    assert response.status_code == 200
    events = _parse_ndjson(response)
    assert events[-1]["authentication_consumed"] is False
    reader_spy.assert_not_awaited()


@pytest.mark.integration
async def test_stream_generic_turn_with_valid_token_does_not_consume_it(
    acceptance_db: None, monkeypatch: pytest.MonkeyPatch, silence_wav_bytes: bytes
) -> None:
    """A generic question must not resolve the actor, so the grant stays usable."""
    service = _service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None

    async with _client() as client:
        _mock_stt_tts(monkeypatch, text="¿qué día es hoy?")
        generic = await _post_stream(
            client, token=unlock.token, silence_wav_bytes=silence_wav_bytes
        )

        generic_events = _parse_ndjson(generic)
        assert generic_events[-1]["authentication_consumed"] is False

        _mock_stt_tts(monkeypatch, text=_CHILD_QUESTION)
        protected = await _post_stream(
            client, token=unlock.token, silence_wav_bytes=silence_wav_bytes
        )

    protected_events = _parse_ndjson(protected)
    audio_events = [event for event in protected_events if event["type"] == "audio"]
    assert audio_events[0]["text"] == _CHILD_ANSWER
    assert protected_events[-1]["authentication_consumed"] is True
