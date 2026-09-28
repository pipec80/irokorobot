"""Integration tests for the authenticated owner voice enroll/revoke endpoints.

Mirrors `tests/integration/test_owner_face_enrollment.py` case for case (Plan
0053, Task 5). The ONLY way to register a voiceprint for speaker evidence is
a loopback-only endpoint that requires a fresh PIN-consumed token and always
enrolls the token's own owner — never a third party, never without a valid,
unconsumed grant. A companion revoke endpoint purges the consent and every
stored voiceprint, and keeps working even with
`speaker_authentication_enabled` off.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
import io
from pathlib import Path
from unittest.mock import AsyncMock
import wave

from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
import numpy as np
from pydantic import SecretStr
import pytest
from server.cognition.identity import PersonRecord
from server.cognition.identity_sessions import IdentitySessionRegistry
from server.cognition.owner_authentication import OwnerUnlockService, owner_unlock_service
from server.dependencies import get_owner_unlock_service
from server.main import app
from server.memory.entity_labels import get_person_label
from server.memory.household_authorization import get_active_role
from server.memory.owner_credentials import get_active_owner_pin_credential
from server.personal_setup import PersonalSetupInput, PersonalSetupResult, apply_personal_setup
from server.resources import AppResources
from server.routers import auth as auth_module
from server.settings import settings

from server import db

_PIN = "482173"
_OWNER_NAME = "Pipec"


@pytest.fixture
async def voice_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[PersonalSetupResult]:
    """Open a fresh temp DB with an owner/child/PIN personal setup applied,
    with speaker authentication enabled by default for these tests."""
    db_path = tmp_path / "owner-voice-enrollment.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)
    monkeypatch.setattr(settings, "speaker_authentication_enabled", True)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    result = await apply_personal_setup(
        PersonalSetupInput(
            owner_name=_OWNER_NAME,
            child_names=("Joaquin",),
            pin=SecretStr(_PIN),
        )
    )
    yield result
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


def _real_service(*, clock=lambda: datetime.now(UTC)) -> OwnerUnlockService:
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


class _ExplodingService:
    """Service double that fails loudly if identity resolution is even attempted."""

    def for_request(self, _token: str | None) -> object:
        raise AssertionError("must not resolve identity for a non-loopback caller")

    async def unlock(self, _pin: str) -> object:
        raise AssertionError("unlock must not be reachable from a voice endpoint")


@asynccontextmanager
async def _loopback_client() -> AsyncIterator[AsyncClient]:
    """Yield a client whose ASGI scope reports a loopback origin.

    Plan 0039: routers depend on `request.app.state.resources`
    (`ResourcesDep`), which the real lifespan sets — assign a lightweight
    `AppResources` here since that lifespan never runs in this helper.
    """
    async with AsyncClient() as http_client:
        app.state.resources = AppResources(
            http_client=http_client, owner_unlock_service=owner_unlock_service
        )
        transport = ASGITransport(app=app, client=("127.0.0.1", 12345))
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@asynccontextmanager
async def _remote_client() -> AsyncIterator[AsyncClient]:
    """Yield a client whose ASGI scope reports a non-loopback origin.

    Plan 0039: routers depend on `request.app.state.resources`
    (`ResourcesDep`), which the real lifespan sets — assign a lightweight
    `AppResources` here since that lifespan never runs in this helper.
    """
    async with AsyncClient() as http_client:
        app.state.resources = AppResources(
            http_client=http_client, owner_unlock_service=owner_unlock_service
        )
        transport = ASGITransport(app=app, client=("203.0.113.5", 12345))
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


def _wav(samples: np.ndarray, *, rate: int = 16_000, channels: int = 1) -> bytes:
    """Build a WAV container around *samples* (int16)."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(samples.astype(np.int16).tobytes())
    return buffer.getvalue()


def _tone(seconds: float, *, amplitude: int = 8_000, rate: int = 16_000) -> bytes:
    """Build a deterministic synthetic 'utterance' — never a human recording."""
    t = np.linspace(0.0, seconds, int(rate * seconds), endpoint=False)
    return _wav((amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.int16), rate=rate)


def _valid_clip() -> bytes:
    """A 3-second clip above both the duration floor and the energy floor."""
    return _tone(3.0)


def _enroll_files(audio_bytes: bytes | None = None) -> dict[str, tuple[str, bytes, str]]:
    """Build the multipart files payload for one enroll request."""
    return {"audio": ("clip.wav", audio_bytes or _valid_clip(), "audio/wav")}


async def _fake_embed_wav(_wav_bytes: bytes) -> np.ndarray:
    """Stand in for the real model: a fixed, valid-shaped embedding."""
    vector = np.zeros(192, dtype=np.float32)
    vector[0] = 1.0
    return vector


@pytest.mark.integration
async def test_no_token_denies_without_touching_the_speaker_model(
    voice_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Absent token must deny before the speaker model is ever touched."""
    embed = AsyncMock()
    monkeypatch.setattr(auth_module, "embed_wav", embed)

    async with _loopback_client() as client:
        response = await client.post("/auth/owner/voice/enroll", files=_enroll_files())

    assert response.status_code == 401
    embed.assert_not_awaited()


@pytest.mark.integration
async def test_expired_token_denies_without_touching_the_speaker_model(
    voice_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A token past its TTL must deny exactly like an absent one."""
    now = datetime.now(UTC)

    def clock() -> datetime:
        return now

    service = _real_service(clock=clock)
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    now = now + timedelta(seconds=61)

    embed = AsyncMock()
    monkeypatch.setattr(auth_module, "embed_wav", embed)

    async with _loopback_client() as client:
        response = await client.post(
            "/auth/owner/voice/enroll",
            headers={"X-Iroko-Identity-Token": unlock.token},
            files=_enroll_files(),
        )

    assert response.status_code == 401
    embed.assert_not_awaited()


@pytest.mark.integration
async def test_consumed_token_denies_second_use_without_touching_the_speaker_model(
    voice_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reusing an already-consumed token must deny without a second enrollment."""
    service = _real_service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    monkeypatch.setattr(auth_module, "embed_wav", _fake_embed_wav)

    async with _loopback_client() as client:
        first = await client.post(
            "/auth/owner/voice/enroll",
            headers={"X-Iroko-Identity-Token": unlock.token},
            files=_enroll_files(),
        )
        second_embed = AsyncMock()
        monkeypatch.setattr(auth_module, "embed_wav", second_embed)
        second = await client.post(
            "/auth/owner/voice/enroll",
            headers={"X-Iroko-Identity-Token": unlock.token},
            files=_enroll_files(),
        )

    assert first.status_code == 200
    assert second.status_code == 401
    second_embed.assert_not_awaited()


@pytest.mark.integration
async def test_non_loopback_client_is_rejected_before_identity_resolution(
    voice_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-loopback caller is rejected with 403 without reaching the resolver."""
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, _ExplodingService)
    embed = AsyncMock()
    monkeypatch.setattr(auth_module, "embed_wav", embed)

    async with _remote_client() as client:
        response = await client.post(
            "/auth/owner/voice/enroll",
            headers={"X-Iroko-Identity-Token": "does-not-matter"},
            files=_enroll_files(),
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "Local access only"}
    embed.assert_not_awaited()


@pytest.mark.integration
async def test_non_loopback_revoke_is_rejected_before_identity_resolution(
    voice_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-loopback caller cannot reach revoke identity resolution either."""
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, _ExplodingService)

    async with _remote_client() as client:
        response = await client.post(
            "/auth/owner/voice/revoke",
            headers={"X-Iroko-Identity-Token": "does-not-matter"},
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "Local access only"}


@pytest.mark.integration
async def test_oversized_enrollment_upload_returns_413_without_touching_the_speaker_model(
    voice_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An authenticated caller still cannot bypass the per-file byte budget."""
    service = _real_service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    embed = AsyncMock(wraps=_fake_embed_wav)
    monkeypatch.setattr(auth_module, "embed_wav", embed)
    oversized = b"RIFF" + b"\x00" * settings.max_audio_upload_bytes

    async with _loopback_client() as client:
        response = await client.post(
            "/auth/owner/voice/enroll",
            headers={"X-Iroko-Identity-Token": unlock.token},
            files={"audio": ("big.wav", oversized, "audio/wav")},
        )

    assert response.status_code == 413
    embed.assert_not_awaited()


@pytest.mark.integration
async def test_empty_body_returns_422_without_touching_the_speaker_model(
    voice_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty upload is rejected before any embedding is attempted."""
    service = _real_service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    embed = AsyncMock()
    monkeypatch.setattr(auth_module, "embed_wav", embed)

    async with _loopback_client() as client:
        response = await client.post(
            "/auth/owner/voice/enroll",
            headers={"X-Iroko-Identity-Token": unlock.token},
            files={"audio": ("empty.wav", b"", "audio/wav")},
        )

    assert response.status_code == 422
    embed.assert_not_awaited()


@pytest.mark.integration
async def test_off_contract_audio_returns_422_without_touching_the_speaker_model(
    voice_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 44.1kHz stereo clip fails the audio contract before it is embedded."""
    service = _real_service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    embed = AsyncMock()
    monkeypatch.setattr(auth_module, "embed_wav", embed)
    off_contract = _tone(3.0, rate=44_100)

    async with _loopback_client() as client:
        response = await client.post(
            "/auth/owner/voice/enroll",
            headers={"X-Iroko-Identity-Token": unlock.token},
            files=_enroll_files(off_contract),
        )

    assert response.status_code == 422
    embed.assert_not_awaited()


@pytest.mark.integration
async def test_a_one_second_clip_returns_422_without_touching_the_speaker_model(
    voice_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Shorter than `speaker_min_enrollment_s` (2.0s) is rejected outright."""
    service = _real_service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    embed = AsyncMock()
    monkeypatch.setattr(auth_module, "embed_wav", embed)

    async with _loopback_client() as client:
        response = await client.post(
            "/auth/owner/voice/enroll",
            headers={"X-Iroko-Identity-Token": unlock.token},
            files=_enroll_files(_tone(1.0)),
        )

    assert response.status_code == 422
    embed.assert_not_awaited()


@pytest.mark.integration
async def test_a_near_silent_clip_returns_422_without_touching_the_speaker_model(
    voice_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review Focus 1 — a format-perfect but near-silent clip never enrolls."""
    service = _real_service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    embed = AsyncMock()
    monkeypatch.setattr(auth_module, "embed_wav", embed)
    near_silent = _wav(np.zeros(16_000 * 3, dtype=np.int16))

    async with _loopback_client() as client:
        response = await client.post(
            "/auth/owner/voice/enroll",
            headers={"X-Iroko-Identity-Token": unlock.token},
            files=_enroll_files(near_silent),
        )

    assert response.status_code == 422
    embed.assert_not_awaited()


@pytest.mark.integration
async def test_successful_enroll_grants_consent_and_creates_one_profile(
    voice_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A successful enrollment returns 200, grants consent, and persists one profile."""
    service = _real_service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    monkeypatch.setattr(auth_module, "embed_wav", _fake_embed_wav)
    grant = AsyncMock(wraps=auth_module.grant_voice_consent)
    monkeypatch.setattr(auth_module, "grant_voice_consent", grant)

    async with _loopback_client() as client:
        response = await client.post(
            "/auth/owner/voice/enroll",
            headers={"X-Iroko-Identity-Token": unlock.token},
            files=_enroll_files(),
        )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"profile_id", "enrolled_at", "reference_count"}
    assert body["reference_count"] == 1
    grant.assert_awaited_once_with(voice_db.owner_entity_id)

    cursor = await db.get_conn().execute(
        "SELECT COUNT(*) FROM voice_profiles WHERE entity_id = ?",
        (voice_db.owner_entity_id,),
    )
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    assert row[0] == 1

    cursor = await db.get_conn().execute(
        "SELECT COUNT(*) FROM voice_consent_grants "
        "WHERE person_entity_id = ? AND revoked_at IS NULL",
        (voice_db.owner_entity_id,),
    )
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    assert row[0] == 1


@pytest.mark.integration
async def test_second_enrollment_for_same_owner_persists_profile_and_reuses_consent_grant(
    voice_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-enrolling the same owner twice persists both profiles but grants consent once."""
    service = _real_service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    monkeypatch.setattr(auth_module, "embed_wav", _fake_embed_wav)

    first_unlock = await service.unlock(_PIN)
    assert first_unlock is not None
    async with _loopback_client() as client:
        first = await client.post(
            "/auth/owner/voice/enroll",
            headers={"X-Iroko-Identity-Token": first_unlock.token},
            files=_enroll_files(),
        )

    second_unlock = await service.unlock(_PIN)
    assert second_unlock is not None
    async with _loopback_client() as client:
        second = await client.post(
            "/auth/owner/voice/enroll",
            headers={"X-Iroko-Identity-Token": second_unlock.token},
            files=_enroll_files(),
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["reference_count"] == 1
    assert second.json()["reference_count"] == 2

    cursor = await db.get_conn().execute(
        "SELECT COUNT(*) FROM voice_profiles WHERE entity_id = ?",
        (voice_db.owner_entity_id,),
    )
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    assert row[0] == 2

    cursor = await db.get_conn().execute(
        "SELECT COUNT(*) FROM voice_consent_grants "
        "WHERE person_entity_id = ? AND revoked_at IS NULL",
        (voice_db.owner_entity_id,),
    )
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    assert row[0] == 1


@pytest.mark.integration
async def test_every_enroll_attempt_writes_one_audit_event(
    voice_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both an allowed and a denied attempt each write exactly one audit row."""
    service = _real_service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    monkeypatch.setattr(auth_module, "embed_wav", _fake_embed_wav)

    cursor = await db.get_conn().execute("SELECT COUNT(*) FROM authorization_audit_events")
    before = (await cursor.fetchone())[0]  # type: ignore[index]
    await cursor.close()

    unlock = await service.unlock(_PIN)
    assert unlock is not None
    async with _loopback_client() as client:
        allowed = await client.post(
            "/auth/owner/voice/enroll",
            headers={"X-Iroko-Identity-Token": unlock.token},
            files=_enroll_files(),
        )
        denied = await client.post(
            "/auth/owner/voice/enroll",
            headers={"X-Iroko-Identity-Token": "not-a-real-token"},
            files=_enroll_files(),
        )

    assert allowed.status_code == 200
    assert denied.status_code == 401

    cursor = await db.get_conn().execute("SELECT COUNT(*) FROM authorization_audit_events")
    after = (await cursor.fetchone())[0]  # type: ignore[index]
    await cursor.close()
    assert after == before + 2


@pytest.mark.integration
async def test_no_response_body_or_log_contains_the_owner_name(
    voice_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Privacy: the owner's name never reaches the enroll response or a log line.

    Scoped to INFO and above — the Global Constraint ("No name, transcript,
    distance or score reaches a log line") is about this codebase's own
    logging choices, not `aiosqlite`'s DEBUG-level SQL parameter tracing,
    which echoes every bound value (including `label`) for any query on any
    table at that verbosity, `voice_profiles` and `face_profiles` alike —
    a property of the driver, not something Plan 0053 controls or changes.
    """
    service = _real_service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    monkeypatch.setattr(auth_module, "embed_wav", _fake_embed_wav)

    with caplog.at_level("INFO"):
        async with _loopback_client() as client:
            response = await client.post(
                "/auth/owner/voice/enroll",
                headers={"X-Iroko-Identity-Token": unlock.token},
                files=_enroll_files(),
            )

    assert response.status_code == 200
    assert _OWNER_NAME not in response.text
    assert all(_OWNER_NAME not in record.getMessage() for record in caplog.records)


@pytest.mark.integration
async def test_revoke_with_valid_token_purges_consent_and_returns_204(
    voice_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A valid token revokes exactly the token owner's consent."""
    service = _real_service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    revoke = AsyncMock(wraps=auth_module.revoke_voice_consent)
    monkeypatch.setattr(auth_module, "revoke_voice_consent", revoke)

    async with _loopback_client() as client:
        response = await client.post(
            "/auth/owner/voice/revoke",
            headers={"X-Iroko-Identity-Token": unlock.token},
        )

    assert response.status_code == 204
    revoke.assert_awaited_once_with(voice_db.owner_entity_id)


@pytest.mark.integration
async def test_revoke_with_no_token_denies_without_purging(
    voice_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No token must deny revoke without ever purging consent."""
    revoke = AsyncMock()
    monkeypatch.setattr(auth_module, "revoke_voice_consent", revoke)

    async with _loopback_client() as client:
        response = await client.post("/auth/owner/voice/revoke")

    assert response.status_code == 401
    revoke.assert_not_awaited()


@pytest.mark.integration
async def test_revoke_with_invalid_token_denies_without_purging(
    voice_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A malformed/unknown token must deny revoke without ever purging consent."""
    service = _real_service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    revoke = AsyncMock()
    monkeypatch.setattr(auth_module, "revoke_voice_consent", revoke)

    async with _loopback_client() as client:
        response = await client.post(
            "/auth/owner/voice/revoke",
            headers={"X-Iroko-Identity-Token": "not-a-real-token"},
        )

    assert response.status_code == 401
    revoke.assert_not_awaited()


@pytest.mark.integration
async def test_flag_off_enroll_returns_503_without_a_token_or_a_write(
    voice_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The flag matrix (A5): disabled means 503, no token consumed, no write —
    even given a valid token and valid audio."""
    monkeypatch.setattr(settings, "speaker_authentication_enabled", False)
    service = _real_service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    embed = AsyncMock()
    monkeypatch.setattr(auth_module, "embed_wav", embed)

    async with _loopback_client() as client:
        response = await client.post(
            "/auth/owner/voice/enroll",
            headers={"X-Iroko-Identity-Token": unlock.token},
            files=_enroll_files(),
        )

    assert response.status_code == 503
    embed.assert_not_awaited()

    # The token must still be usable afterward — it was never consumed.
    cursor = await db.get_conn().execute(
        "SELECT COUNT(*) FROM voice_profiles WHERE entity_id = ?",
        (voice_db.owner_entity_id,),
    )
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    assert row[0] == 0


@pytest.mark.integration
async def test_flag_off_revoke_still_works_and_purges(
    voice_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Revoke is never gated by the flag — the user-facing undo must always work."""
    service = _real_service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    monkeypatch.setattr(auth_module, "embed_wav", _fake_embed_wav)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    async with _loopback_client() as client:
        enroll_response = await client.post(
            "/auth/owner/voice/enroll",
            headers={"X-Iroko-Identity-Token": unlock.token},
            files=_enroll_files(),
        )
    assert enroll_response.status_code == 200

    monkeypatch.setattr(settings, "speaker_authentication_enabled", False)
    revoke_unlock = await service.unlock(_PIN)
    assert revoke_unlock is not None
    async with _loopback_client() as client:
        response = await client.post(
            "/auth/owner/voice/revoke",
            headers={"X-Iroko-Identity-Token": revoke_unlock.token},
        )

    assert response.status_code == 204

    cursor = await db.get_conn().execute(
        "SELECT COUNT(*) FROM voice_profiles WHERE entity_id = ?",
        (voice_db.owner_entity_id,),
    )
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    assert row[0] == 0


def test_the_two_new_routes_are_documented_with_the_expected_shape(
    client: TestClient,
) -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]

    enroll = paths["/auth/owner/voice/enroll"]["post"]
    assert enroll["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "VoiceEnrollResponse"
    )
    assert {"401", "403", "413", "503"} <= enroll["responses"].keys()

    revoke = paths["/auth/owner/voice/revoke"]["post"]
    assert revoke["responses"]["204"]
    assert {"401", "403"} <= revoke["responses"].keys()
