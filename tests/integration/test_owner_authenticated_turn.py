"""End-to-end acceptance tests for the one-use owner-authenticated turn.

Covers the Plan 0026 north-star scenario through the real classic `/chat`
and `/transcribe` routes: a valid local unlock answers the confirmed child
question exactly once; absent, expired, replayed, and malformed tokens deny
without disclosure and without reaching v4 storage.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient
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
    db_path = tmp_path / "owner-authenticated-turn.db"
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


@pytest.mark.integration
async def test_chat_with_valid_token_answers_and_consumes_the_grant(
    acceptance_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fresh unlock, used once, returns exactly the confirmed child names."""
    service = _service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None

    async with _client() as client:
        response = await client.post(
            "/chat",
            headers={"X-Iroko-Identity-Token": unlock.token},
            json={"message": _CHILD_QUESTION, "conversation_id": "acceptance-owner"},
        )

    assert response.status_code == 200
    assert response.json()["response"] == _CHILD_ANSWER
    assert response.json()["authentication_consumed"] is True


@pytest.mark.integration
async def test_chat_replayed_token_denies_without_disclosure(
    acceptance_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second use of an already-consumed token must not reveal any name."""
    service = _service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None

    async with _client() as client:
        first = await client.post(
            "/chat",
            headers={"X-Iroko-Identity-Token": unlock.token},
            json={"message": _CHILD_QUESTION, "conversation_id": "acceptance-owner"},
        )
        second = await client.post(
            "/chat",
            headers={"X-Iroko-Identity-Token": unlock.token},
            json={"message": _CHILD_QUESTION, "conversation_id": "acceptance-owner"},
        )

    assert first.json()["response"] == _CHILD_ANSWER
    assert second.status_code == 200
    assert second.json()["authentication_consumed"] is False
    assert "Máximo" not in second.json()["response"]
    assert "Dominga" not in second.json()["response"]


@pytest.mark.integration
async def test_allowed_read_audit_trace_contains_no_names_pin_or_token(
    acceptance_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The safe audit trail never carries the disclosed names, PIN, or token."""
    service = _service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None

    async with _client() as client:
        await client.post(
            "/chat",
            headers={"X-Iroko-Identity-Token": unlock.token},
            json={"message": _CHILD_QUESTION, "conversation_id": "acceptance-owner"},
        )

    cursor = await db.get_conn().execute(
        "SELECT actor_entity_id, target_entity_id, action, data_categories, decision, "
        "policy_id, reason, correlation_id FROM authorization_audit_events"
    )
    rows = await cursor.fetchall()
    await cursor.close()
    assert rows
    joined = repr(rows)
    assert _PIN not in joined
    assert unlock.token not in joined
    assert "Máximo" not in joined
    assert "Dominga" not in joined


@pytest.mark.integration
async def test_transcribe_with_valid_token_speaks_the_exact_child_answer(
    acceptance_db: None, monkeypatch: pytest.MonkeyPatch, silence_wav_bytes: bytes
) -> None:
    """Classic voice with a fresh token speaks exactly the confirmed answer."""
    service = _service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value=_CHILD_QUESTION))
    tts_mock = AsyncMock(return_value=("AAAA", 42))
    monkeypatch.setattr(tts, "synthesize", tts_mock)

    async with _client() as client:
        response = await client.post(
            "/transcribe",
            headers={"X-Iroko-Identity-Token": unlock.token},
            files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
        )

    assert response.status_code == 200
    assert response.json()["llm_response"] == _CHILD_ANSWER
    assert response.json()["authentication_consumed"] is True
    tts_mock.assert_awaited_once_with(_CHILD_ANSWER)


@pytest.mark.integration
@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-Iroko-Identity-Token": "not-a-real-token"},
    ],
    ids=["absent", "malformed"],
)
async def test_transcribe_absent_or_malformed_token_denies_without_reading_v4(
    acceptance_db: None,
    monkeypatch: pytest.MonkeyPatch,
    silence_wav_bytes: bytes,
    headers: dict[str, str],
) -> None:
    """No usable token must never reach v4 storage or disclose the names."""
    service = _service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value=_CHILD_QUESTION))
    tts_mock = AsyncMock(return_value=("AAAA", 42))
    monkeypatch.setattr(tts, "synthesize", tts_mock)
    reader_spy = AsyncMock(wraps=PolicyGatedV4Reader.read_active_relations)
    monkeypatch.setattr(PolicyGatedV4Reader, "read_active_relations", reader_spy)

    async with _client() as client:
        response = await client.post(
            "/transcribe",
            headers=headers,
            files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
        )

    assert response.status_code == 200
    assert response.json()["authentication_consumed"] is False
    assert "Máximo" not in response.json()["llm_response"]
    assert "Dominga" not in response.json()["llm_response"]
    reader_spy.assert_not_awaited()


@pytest.mark.integration
async def test_transcribe_expired_token_denies_without_reading_v4(
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

    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value=_CHILD_QUESTION))
    monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("AAAA", 42)))
    reader_spy = AsyncMock(wraps=PolicyGatedV4Reader.read_active_relations)
    monkeypatch.setattr(PolicyGatedV4Reader, "read_active_relations", reader_spy)

    async with _client() as client:
        response = await client.post(
            "/transcribe",
            headers={"X-Iroko-Identity-Token": unlock.token},
            files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
        )

    assert response.status_code == 200
    assert response.json()["authentication_consumed"] is False
    reader_spy.assert_not_awaited()


@pytest.mark.integration
async def test_transcribe_replayed_token_denies_without_reading_v4(
    acceptance_db: None, monkeypatch: pytest.MonkeyPatch, silence_wav_bytes: bytes
) -> None:
    """Reusing an already-consumed token must deny exactly like an absent one."""
    service = _service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value=_CHILD_QUESTION))
    monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("AAAA", 42)))

    async with _client() as client:
        first = await client.post(
            "/transcribe",
            headers={"X-Iroko-Identity-Token": unlock.token},
            files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
        )
        reader_spy = AsyncMock(wraps=PolicyGatedV4Reader.read_active_relations)
        monkeypatch.setattr(PolicyGatedV4Reader, "read_active_relations", reader_spy)
        second = await client.post(
            "/transcribe",
            headers={"X-Iroko-Identity-Token": unlock.token},
            files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
        )

    assert first.json()["authentication_consumed"] is True
    assert second.json()["authentication_consumed"] is False
    reader_spy.assert_not_awaited()
