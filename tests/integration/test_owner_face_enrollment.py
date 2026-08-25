"""Integration tests for the authenticated owner face enroll/revoke endpoints.

Covers the Plan 0029 Task 4 north star: the ONLY way to register a face for
owner authentication is a loopback-only endpoint that requires a fresh
PIN-consumed token and always enrolls the token's own owner — never a
third party, never without a valid, unconsumed grant. A companion revoke
endpoint purges the consent and every stored face profile. None of this
touches the already-quarantined public `POST /vision/enroll`.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import cv2
from httpx import ASGITransport, AsyncClient
import numpy as np
from pydantic import SecretStr
import pytest
from server.cognition.identity import PersonRecord
from server.cognition.identity_sessions import IdentitySessionRegistry
from server.cognition.owner_authentication import OwnerUnlockService
from server.exceptions import EnrollmentRejectedError
from server.main import app
from server.memory.declarative import upsert_entity
from server.memory.entity_labels import get_person_label
from server.memory.household_authorization import get_active_role
from server.memory.owner_credentials import get_active_owner_pin_credential
from server.personal_setup import PersonalSetupInput, PersonalSetupResult, apply_personal_setup
from server.routers import auth as auth_module
from server.settings import settings

from server import db, vision

_PIN = "482173"
_OWNER_NAME = "Pipec"
_FAKE_JPEG = cv2.imencode(".jpg", np.zeros((10, 10, 3), dtype=np.uint8))[1].tobytes()


@pytest.fixture
async def face_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[PersonalSetupResult]:
    """Open a fresh temp DB with an owner/child/PIN personal setup applied."""
    db_path = tmp_path / "owner-face-enrollment.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    result = await apply_personal_setup(
        PersonalSetupInput(
            owner_name=_OWNER_NAME,
            child_names=("Maximo",),
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
        raise AssertionError("unlock must not be reachable from a face endpoint")


@asynccontextmanager
async def _loopback_client() -> AsyncIterator[AsyncClient]:
    """Yield a client whose ASGI scope reports a loopback origin."""
    transport = ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@asynccontextmanager
async def _remote_client() -> AsyncIterator[AsyncClient]:
    """Yield a client whose ASGI scope reports a non-loopback origin."""
    transport = ASGITransport(app=app, client=("203.0.113.5", 12345))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _enroll_files() -> dict[str, tuple[str, bytes, str]]:
    """Build the multipart files payload for one enroll request."""
    return {"image": ("frame.jpg", _FAKE_JPEG, "image/jpeg")}


async def _fake_enroll_person(*, name: str, image: bytes) -> vision.EnrollOutcome:
    """Stand in for the real detector: reuse the label's entity and enroll a stub embedding."""
    del image
    entity_id = await upsert_entity(name=name, type="person")
    profile_id = await vision.enroll_face(entity_id, np.zeros(512, dtype=np.float32), label=name)
    return vision.EnrollOutcome(name=name, entity_id=entity_id, profile_id=profile_id)


@pytest.mark.integration
async def test_no_token_denies_without_touching_face_model(
    face_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Absent token must deny before the face model is ever touched."""
    enroll = AsyncMock()
    monkeypatch.setattr(vision, "enroll_person", enroll)

    async with _loopback_client() as client:
        response = await client.post(
            "/auth/owner/face/enroll",
            files=_enroll_files(),
        )

    assert response.status_code == 401
    enroll.assert_not_awaited()


@pytest.mark.integration
async def test_expired_token_denies_without_touching_face_model(
    face_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A token past its TTL must deny exactly like an absent one."""
    now = datetime.now(UTC)

    def clock() -> datetime:
        return now

    service = _real_service(clock=clock)
    monkeypatch.setattr(auth_module, "owner_unlock_service", service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    now = now + timedelta(seconds=61)

    enroll = AsyncMock()
    monkeypatch.setattr(vision, "enroll_person", enroll)

    async with _loopback_client() as client:
        response = await client.post(
            "/auth/owner/face/enroll",
            headers={"X-Iroko-Identity-Token": unlock.token},
            files=_enroll_files(),
        )

    assert response.status_code == 401
    enroll.assert_not_awaited()


@pytest.mark.integration
async def test_consumed_token_denies_second_use_without_touching_face_model(
    face_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reusing an already-consumed token must deny without a second enrollment."""
    service = _real_service()
    monkeypatch.setattr(auth_module, "owner_unlock_service", service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    monkeypatch.setattr(
        vision,
        "enroll_person",
        AsyncMock(side_effect=EnrollmentRejectedError("no_face", "No face found")),
    )

    async with _loopback_client() as client:
        first = await client.post(
            "/auth/owner/face/enroll",
            headers={"X-Iroko-Identity-Token": unlock.token},
            files=_enroll_files(),
        )
        second_enroll = AsyncMock()
        monkeypatch.setattr(vision, "enroll_person", second_enroll)
        second = await client.post(
            "/auth/owner/face/enroll",
            headers={"X-Iroko-Identity-Token": unlock.token},
            files=_enroll_files(),
        )

    assert first.status_code == 422
    assert second.status_code == 401
    second_enroll.assert_not_awaited()


@pytest.mark.integration
async def test_non_loopback_client_is_rejected_before_identity_resolution(
    face_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-loopback caller is rejected with 403 without reaching the resolver."""
    monkeypatch.setattr(auth_module, "owner_unlock_service", _ExplodingService())
    enroll = AsyncMock()
    monkeypatch.setattr(vision, "enroll_person", enroll)

    async with _remote_client() as client:
        response = await client.post(
            "/auth/owner/face/enroll",
            headers={"X-Iroko-Identity-Token": "does-not-matter"},
            files=_enroll_files(),
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "Local access only"}
    enroll.assert_not_awaited()


@pytest.mark.integration
async def test_non_loopback_revoke_is_rejected_before_identity_resolution(
    face_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-loopback caller cannot reach revoke identity resolution either."""
    monkeypatch.setattr(auth_module, "owner_unlock_service", _ExplodingService())

    async with _remote_client() as client:
        response = await client.post(
            "/auth/owner/face/revoke",
            headers={"X-Iroko-Identity-Token": "does-not-matter"},
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "Local access only"}


@pytest.mark.integration
async def test_multiple_faces_rejection_maps_to_422_without_persisting_consent(
    face_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A multi-face frame is rejected with its code and grants no consent."""
    service = _real_service()
    monkeypatch.setattr(auth_module, "owner_unlock_service", service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    monkeypatch.setattr(
        vision,
        "enroll_person",
        AsyncMock(side_effect=EnrollmentRejectedError("multiple_faces", "Found 2 faces")),
    )
    grant = AsyncMock()
    monkeypatch.setattr(auth_module, "grant_face_consent", grant)

    async with _loopback_client() as client:
        response = await client.post(
            "/auth/owner/face/enroll",
            headers={"X-Iroko-Identity-Token": unlock.token},
            files=_enroll_files(),
        )

    assert response.status_code == 422
    assert "multiple_faces" in response.json()["detail"]
    grant.assert_not_awaited()


@pytest.mark.integration
@pytest.mark.parametrize(
    "code",
    ["no_face", "low_quality", "face_too_small"],
)
async def test_other_rejection_codes_map_to_422_without_persisting_consent(
    face_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, code: str
) -> None:
    """Every other rejection code also maps to 422 and grants no consent."""
    service = _real_service()
    monkeypatch.setattr(auth_module, "owner_unlock_service", service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    monkeypatch.setattr(
        vision,
        "enroll_person",
        AsyncMock(side_effect=EnrollmentRejectedError(code, f"rejected: {code}")),
    )
    grant = AsyncMock()
    monkeypatch.setattr(auth_module, "grant_face_consent", grant)

    async with _loopback_client() as client:
        response = await client.post(
            "/auth/owner/face/enroll",
            headers={"X-Iroko-Identity-Token": unlock.token},
            files=_enroll_files(),
        )

    assert response.status_code == 422
    assert code in response.json()["detail"]
    grant.assert_not_awaited()


@pytest.mark.integration
async def test_successful_enroll_grants_consent_and_creates_one_profile(
    face_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A successful enrollment returns 200, grants consent, and persists one profile."""
    service = _real_service()
    monkeypatch.setattr(auth_module, "owner_unlock_service", service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    monkeypatch.setattr(vision, "enroll_person", _fake_enroll_person)
    grant = AsyncMock(wraps=auth_module.grant_face_consent)
    monkeypatch.setattr(auth_module, "grant_face_consent", grant)

    async with _loopback_client() as client:
        response = await client.post(
            "/auth/owner/face/enroll",
            headers={"X-Iroko-Identity-Token": unlock.token},
            files=_enroll_files(),
        )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"profile_id", "enrolled_at"}
    grant.assert_awaited_once_with(face_db.owner_entity_id)

    cursor = await db.get_conn().execute(
        "SELECT COUNT(*) FROM face_profiles WHERE entity_id = ?",
        (face_db.owner_entity_id,),
    )
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    assert row[0] == 1


@pytest.mark.integration
async def test_extra_name_field_is_ignored_and_owner_name_is_used(
    face_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An injected `name` form field never overrides the token owner's name."""
    service = _real_service()
    monkeypatch.setattr(auth_module, "owner_unlock_service", service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    enroll = AsyncMock(side_effect=_fake_enroll_person)
    monkeypatch.setattr(vision, "enroll_person", enroll)
    monkeypatch.setattr(auth_module, "grant_face_consent", AsyncMock())

    async with _loopback_client() as client:
        response = await client.post(
            "/auth/owner/face/enroll",
            headers={"X-Iroko-Identity-Token": unlock.token},
            files=_enroll_files(),
            data={"name": "Intruder"},
        )

    assert response.status_code == 200
    enroll.assert_awaited_once()
    enroll_call = enroll.await_args
    assert enroll_call is not None
    kwargs = enroll_call.kwargs
    assert kwargs["name"].casefold() == _OWNER_NAME.casefold()
    assert kwargs["name"] != "Intruder"


@pytest.mark.integration
async def test_revoke_with_valid_token_purges_consent_and_returns_204(
    face_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A valid token revokes exactly the token owner's consent."""
    service = _real_service()
    monkeypatch.setattr(auth_module, "owner_unlock_service", service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    revoke = AsyncMock(wraps=auth_module.revoke_face_consent)
    monkeypatch.setattr(auth_module, "revoke_face_consent", revoke)

    async with _loopback_client() as client:
        response = await client.post(
            "/auth/owner/face/revoke",
            headers={"X-Iroko-Identity-Token": unlock.token},
        )

    assert response.status_code == 204
    revoke.assert_awaited_once_with(face_db.owner_entity_id)


@pytest.mark.integration
async def test_revoke_with_no_token_denies_without_purging(
    face_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No token must deny revoke without ever purging consent."""
    revoke = AsyncMock()
    monkeypatch.setattr(auth_module, "revoke_face_consent", revoke)

    async with _loopback_client() as client:
        response = await client.post("/auth/owner/face/revoke")

    assert response.status_code == 401
    revoke.assert_not_awaited()


@pytest.mark.integration
async def test_revoke_with_invalid_token_denies_without_purging(
    face_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A malformed/unknown token must deny revoke without ever purging consent."""
    service = _real_service()
    monkeypatch.setattr(auth_module, "owner_unlock_service", service)
    revoke = AsyncMock()
    monkeypatch.setattr(auth_module, "revoke_face_consent", revoke)

    async with _loopback_client() as client:
        response = await client.post(
            "/auth/owner/face/revoke",
            headers={"X-Iroko-Identity-Token": "not-a-real-token"},
        )

    assert response.status_code == 401
    revoke.assert_not_awaited()
