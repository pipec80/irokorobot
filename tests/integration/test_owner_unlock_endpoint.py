"""Integration tests for the loopback-only local owner unlock endpoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
import logging

from httpx import ASGITransport, AsyncClient
import pytest
from server.cognition.owner_authentication import (
    OwnerUnlockRateLimitedError,
    OwnerUnlockResult,
)
from server.main import app
from server.routers import auth


class _FakeService:
    """Minimal injected service double for endpoint-level tests."""

    def __init__(
        self, *, result: OwnerUnlockResult | None = None, raises: Exception | None = None
    ) -> None:
        self._result = result
        self._raises = raises
        self.received_pin: str | None = None

    async def unlock(self, pin: str) -> OwnerUnlockResult | None:
        self.received_pin = pin
        if self._raises is not None:
            raise self._raises
        return self._result


def _result() -> OwnerUnlockResult:
    return OwnerUnlockResult(
        token="opaque-token",  # noqa: S106 — fixture value, not a real credential
        expires_at=datetime(2026, 8, 21, 10, 1, tzinfo=UTC),
    )


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


@pytest.mark.integration
async def test_loopback_with_valid_pin_returns_only_token_and_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A loopback caller with a correct PIN receives exactly token and expiry."""
    fake = _FakeService(result=_result())
    monkeypatch.setattr(auth, "owner_unlock_service", fake)

    async with _loopback_client() as client:
        response = await client.post("/auth/owner/unlock", json={"pin": "482173"})

    assert response.status_code == 200
    assert set(response.json()) == {"token", "expires_at"}
    assert response.json()["token"] == "opaque-token"  # noqa: S105 — fixture value
    assert fake.received_pin == "482173"


@pytest.mark.integration
async def test_loopback_with_invalid_pin_returns_401_without_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An invalid PIN and a missing profile both return the same 401 body."""
    fake = _FakeService(result=None)
    monkeypatch.setattr(auth, "owner_unlock_service", fake)

    async with _loopback_client() as client:
        response = await client.post("/auth/owner/unlock", json={"pin": "000000"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Owner authentication failed"}


@pytest.mark.integration
async def test_rate_limit_returns_429_without_attempt_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An active local rate limit maps to 429 with a generic body."""
    fake = _FakeService(raises=OwnerUnlockRateLimitedError(retry_after_seconds=60))
    monkeypatch.setattr(auth, "owner_unlock_service", fake)

    async with _loopback_client() as client:
        response = await client.post("/auth/owner/unlock", json={"pin": "482173"})

    assert response.status_code == 429
    assert response.json() == {"detail": "Too many attempts"}


@pytest.mark.integration
async def test_non_loopback_client_is_rejected_before_pin_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-loopback caller is rejected with 403 without reaching the service."""
    fake = _FakeService(result=_result())
    monkeypatch.setattr(auth, "owner_unlock_service", fake)

    async with _remote_client() as client:
        response = await client.post("/auth/owner/unlock", json={"pin": "482173"})

    assert response.status_code == 403
    assert response.json() == {"detail": "Local access only"}
    assert fake.received_pin is None


@pytest.mark.integration
async def test_request_forbids_extra_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unexpected field in the unlock request is rejected, not ignored."""
    fake = _FakeService(result=_result())
    monkeypatch.setattr(auth, "owner_unlock_service", fake)

    async with _loopback_client() as client:
        response = await client.post("/auth/owner/unlock", json={"pin": "482173", "person_id": 1})

    assert response.status_code == 422
    assert fake.received_pin is None


@pytest.mark.integration
async def test_openapi_exposes_no_person_role_or_session_fields() -> None:
    """The published schema never hints at a person selector or persistent session."""
    async with _loopback_client() as client:
        response = await client.get("/openapi.json")

    schemas = response.json()["components"]["schemas"]
    unlock_request = schemas["OwnerUnlockRequest"]
    unlock_response = schemas["OwnerUnlockResponse"]
    assert set(unlock_request["properties"]) == {"pin"}
    assert set(unlock_response["properties"]) == {"token", "expires_at"}


@pytest.mark.integration
async def test_logs_contain_route_and_status_but_not_pin_or_token(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Access logging must never include the request PIN or the issued token."""
    fake = _FakeService(result=_result())
    monkeypatch.setattr(auth, "owner_unlock_service", fake)

    with caplog.at_level(logging.DEBUG):
        async with _loopback_client() as client:
            await client.post("/auth/owner/unlock", json={"pin": "482173"})

    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert "482173" not in joined
    assert "opaque-token" not in joined


# --- Plan 0033: deterministic HTTP contract -------------------------------

# Sentinels distinctive enough that a substring match cannot be coincidence.
_MALFORMED_PIN = "abcdefSENTINELPINZQX"
_SHORT_PIN = "12345"
_LONG_PIN = "1234567890123"
_UNICODE_PIN = "١٢٣٤٥٦"  # Arabic-Indic digits: str.isdigit() is True, ASCII it is not


@pytest.mark.integration
@pytest.mark.parametrize(
    "pin",
    [_MALFORMED_PIN, _SHORT_PIN, _LONG_PIN, _UNICODE_PIN, ""],
    ids=["letters", "too-short", "too-long", "unicode-digits", "empty"],
)
async def test_malformed_pin_is_rejected_as_422_before_any_verification(
    pin: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A malformed PIN is a contract violation, not a wrong credential.

    Today the shape is only checked inside `verify_pin`, which raises
    `ValueError` that nothing catches — so the caller gets a 500 and the
    expensive scrypt path is entered for input that could never be valid.
    """
    fake = _FakeService(result=_result())
    monkeypatch.setattr(auth, "owner_unlock_service", fake)

    async with _loopback_client() as client:
        response = await client.post("/auth/owner/unlock", json={"pin": pin})

    assert response.status_code == 422
    assert fake.received_pin is None, "the service must never see a malformed PIN"


@pytest.mark.integration
async def test_a_rejected_pin_never_appears_in_the_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A validation error must not echo the candidate secret back."""
    monkeypatch.setattr(auth, "owner_unlock_service", _FakeService(result=_result()))

    async with _loopback_client() as client:
        response = await client.post("/auth/owner/unlock", json={"pin": _MALFORMED_PIN})

    assert _MALFORMED_PIN not in response.text


@pytest.mark.integration
async def test_a_rejected_pin_never_appears_in_the_logs(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Plan 0032's privacy rule covers credentials too."""
    monkeypatch.setattr(auth, "owner_unlock_service", _FakeService(result=_result()))

    with caplog.at_level(logging.DEBUG):
        async with _loopback_client() as client:
            await client.post("/auth/owner/unlock", json={"pin": _MALFORMED_PIN})

    assert _MALFORMED_PIN not in caplog.text


@pytest.mark.integration
async def test_a_successful_unlock_is_never_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The response body carries a usable grant; no cache may retain it."""
    monkeypatch.setattr(auth, "owner_unlock_service", _FakeService(result=_result()))

    async with _loopback_client() as client:
        response = await client.post("/auth/owner/unlock", json={"pin": "482173"})

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.integration
async def test_rate_limited_response_tells_the_caller_when_to_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 429 without Retry-After leaves a client guessing or hammering."""
    blocked = OwnerUnlockRateLimitedError(retry_after_seconds=60)
    monkeypatch.setattr(auth, "owner_unlock_service", _FakeService(raises=blocked))

    async with _loopback_client() as client:
        response = await client.post("/auth/owner/unlock", json={"pin": "482173"})

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"


@pytest.mark.integration
@pytest.mark.parametrize(
    "host",
    ["127.0.0.2", "::ffff:127.0.0.1"],
    ids=["loopback-range", "ipv4-mapped-ipv6"],
)
async def test_loopback_is_decided_by_ip_semantics_not_string_equality(
    host: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`127.0.0.2` is loopback; a string set of two literals says otherwise."""
    monkeypatch.setattr(auth, "owner_unlock_service", _FakeService(result=_result()))
    transport = ASGITransport(app=app, client=(host, 12345))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/auth/owner/unlock", json={"pin": "482173"})

    assert response.status_code == 200


@pytest.mark.integration
async def test_an_unparseable_client_address_is_forbidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the origin cannot be established, it is not local."""
    monkeypatch.setattr(auth, "owner_unlock_service", _FakeService(result=_result()))
    transport = ASGITransport(app=app, client=("not-an-ip", 12345))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/auth/owner/unlock", json={"pin": "482173"})

    assert response.status_code == 403
