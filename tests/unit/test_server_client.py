"""Unit tests for robot.server_client — httpx mocked via MockTransport."""

from collections.abc import Generator
from datetime import UTC, datetime
import json

import httpx
import pytest
from robot.exceptions import NoSpeechError, ServerError
from robot.stream_events import DoneEvent

from robot import server_client


@pytest.fixture(autouse=True)
def _reset_shared_client() -> Generator[None, None, None]:
    """Drop the module-level pooled client so each test builds its own."""
    server_client._client = None
    yield
    server_client._client = None


@pytest.mark.unit
async def test_transcribe_empty_bytes_raises_value_error() -> None:
    with pytest.raises(ValueError, match="empty"):
        await server_client.transcribe(b"")


@pytest.mark.unit
async def test_transcribe_parses_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful server response must map to a TranscribeResult dataclass."""

    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/transcribe"
        assert request.method == "POST"
        return httpx.Response(
            200,
            json={
                "text_heard": "hola",
                "llm_response": "qué tal",
                "audio_base64": "AAAA",
                "duration_ms": 123,
                "emotion": "joy",
            },
        )

    transport = httpx.MockTransport(_handler)
    original = httpx.AsyncClient

    def _patched_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(server_client.httpx, "AsyncClient", _patched_client)

    result = await server_client.transcribe(b"fake-wav-bytes")
    assert result.text_heard == "hola"
    assert result.llm_response == "qué tal"
    assert result.audio_base64 == "AAAA"
    assert result.duration_ms == 123
    assert result.emotion == "joy"


@pytest.mark.unit
async def test_transcribe_tolerates_new_response_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The API contract allows ADDING fields — the robot must not crash.

    Regression guard for R2 (per-stage latency metrics will add fields).
    """

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "text_heard": "hola",
                "llm_response": "qué tal",
                "audio_base64": "AAAA",
                "duration_ms": 123,
                "emotion": "joy",
                "stt_ms": 900,  # future additive field
                "llm_ms": 15000,
            },
        )

    transport = httpx.MockTransport(_handler)
    original = httpx.AsyncClient

    def _patched_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(server_client.httpx, "AsyncClient", _patched_client)

    result = await server_client.transcribe(b"fake-wav")
    assert result.text_heard == "hola"
    assert result.duration_ms == 123


@pytest.mark.unit
async def test_transcribe_server_error_raises_server_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-2xx responses must raise ServerError with the status code."""

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    transport = httpx.MockTransport(_handler)
    original = httpx.AsyncClient

    def _patched_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(server_client.httpx, "AsyncClient", _patched_client)

    with pytest.raises(ServerError, match="500"):
        await server_client.transcribe(b"fake-wav")


@pytest.mark.unit
async def test_transcribe_422_raises_no_speech_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP 422 (no speech detected) must raise NoSpeechError, not ServerError."""

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": "No speech detected in audio"})

    transport = httpx.MockTransport(_handler)
    original = httpx.AsyncClient

    def _patched_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(server_client.httpx, "AsyncClient", _patched_client)

    with pytest.raises(NoSpeechError):
        await server_client.transcribe(b"noise-only-wav")


@pytest.mark.unit
async def test_transcribe_network_error_raises_server_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Connection failures must raise ServerError, not leak httpx exceptions."""

    def _handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable")

    transport = httpx.MockTransport(_handler)
    original = httpx.AsyncClient

    def _patched_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(server_client.httpx, "AsyncClient", _patched_client)

    with pytest.raises(ServerError, match="Could not reach"):
        await server_client.transcribe(b"fake-wav")


@pytest.mark.unit
async def test_check_vision_enabled_reads_health_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /health's vision_enabled field must be surfaced as a plain bool."""

    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        assert request.method == "GET"
        return httpx.Response(200, json={"status": "ok", "vision_enabled": True})

    transport = httpx.MockTransport(_handler)
    original = httpx.AsyncClient

    def _patched_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(server_client.httpx, "AsyncClient", _patched_client)

    assert await server_client.check_vision_enabled() is True


@pytest.mark.unit
async def test_check_vision_enabled_defaults_false_when_field_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An older server without the field must not be treated as vision-enabled."""

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(_handler)
    original = httpx.AsyncClient

    def _patched_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(server_client.httpx, "AsyncClient", _patched_client)

    assert await server_client.check_vision_enabled() is False


@pytest.mark.unit
async def test_check_vision_enabled_network_error_raises_server_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dead server at startup must raise ServerError, not crash with httpx internals."""

    def _handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable")

    transport = httpx.MockTransport(_handler)
    original = httpx.AsyncClient

    def _patched_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(server_client.httpx, "AsyncClient", _patched_client)

    with pytest.raises(ServerError, match="Could not reach"):
        await server_client.check_vision_enabled()


def _patch_transport(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    """Route the shared httpx client through a mocked transport."""
    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def _patched_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(server_client.httpx, "AsyncClient", _patched_client)


@pytest.mark.unit
async def test_unlock_owner_sends_pin_only_to_the_local_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The PIN must go to POST /auth/owner/unlock and nowhere else."""

    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/auth/owner/unlock"
        assert request.method == "POST"
        assert json.loads(request.content) == {"pin": "482173"}
        return httpx.Response(
            200, json={"token": "opaque-token", "expires_at": "2026-08-21T10:01:00+00:00"}
        )

    _patch_transport(monkeypatch, _handler)

    result = await server_client.unlock_owner("482173")

    assert result.token == "opaque-token"  # noqa: S105 — fixture value
    assert result.expires_at == datetime(2026, 8, 21, 10, 1, tzinfo=UTC)


@pytest.mark.unit
async def test_unlock_owner_maps_401_to_server_error_without_echoing_pin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An invalid PIN must raise ServerError, never leaking the candidate PIN."""

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Owner authentication failed"})

    _patch_transport(monkeypatch, _handler)

    with pytest.raises(ServerError) as exc_info:
        await server_client.unlock_owner("000000")
    assert "000000" not in str(exc_info.value)


@pytest.mark.unit
async def test_unlock_owner_maps_429_to_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """An active local rate limit must surface as a safe ServerError."""

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"detail": "Too many attempts"})

    _patch_transport(monkeypatch, _handler)

    with pytest.raises(ServerError, match="429"):
        await server_client.unlock_owner("482173")


@pytest.mark.unit
async def test_unlock_owner_network_error_raises_server_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dead server must raise ServerError, not leak httpx internals."""

    def _handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable")

    _patch_transport(monkeypatch, _handler)

    with pytest.raises(ServerError, match="Could not reach"):
        await server_client.unlock_owner("482173")


@pytest.mark.unit
async def test_transcribe_adds_identity_header_only_when_token_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The identity header must be sent only when a token was supplied."""
    seen_headers: list[httpx.Headers] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(request.headers)
        return httpx.Response(
            200,
            json={
                "text_heard": "hola",
                "llm_response": "qué tal",
                "audio_base64": "AAAA",
                "duration_ms": 123,
                "emotion": "joy",
            },
        )

    _patch_transport(monkeypatch, _handler)

    await server_client.transcribe(b"wav", identity_token="opaque-token")  # noqa: S106
    await server_client.transcribe(b"wav")

    assert seen_headers[0]["X-Iroko-Identity-Token"] == "opaque-token"
    assert "X-Iroko-Identity-Token" not in seen_headers[1]


def _done_line(*, authentication_consumed: bool | None = None) -> str:
    """Build one raw NDJSON `done` line, optionally omitting the new field."""
    payload: dict[str, object] = {
        "type": "done",
        "stt_ms": 1,
        "llm_ms": 2,
        "tts_ms": 3,
        "total_ms": 6,
    }
    if authentication_consumed is not None:
        payload["authentication_consumed"] = authentication_consumed
    return json.dumps(payload)


@pytest.mark.unit
async def test_transcribe_stream_omits_header_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No token supplied must never send the identity header (Plan 0027)."""
    seen_headers: list[httpx.Headers] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(request.headers)
        return httpx.Response(200, text=_done_line() + "\n")

    _patch_transport(monkeypatch, _handler)

    async for _event in server_client.transcribe_stream(b"wav"):
        pass

    assert "X-Iroko-Identity-Token" not in seen_headers[0]


@pytest.mark.unit
async def test_transcribe_stream_sends_identity_header_exactly_once_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A supplied token must be sent exactly once, on the streaming request itself."""
    seen_headers: list[httpx.Headers] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(request.headers)
        return httpx.Response(200, text=_done_line() + "\n")

    _patch_transport(monkeypatch, _handler)

    async for _event in server_client.transcribe_stream(b"wav", identity_token="opaque-token"):  # noqa: S106
        pass

    assert len(seen_headers) == 1
    assert seen_headers[0]["X-Iroko-Identity-Token"] == "opaque-token"


@pytest.mark.unit
async def test_transcribe_stream_done_tolerates_missing_consumed_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An older server's done payload (no such key) must still parse and default false."""

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_done_line() + "\n")

    _patch_transport(monkeypatch, _handler)

    events = [event async for event in server_client.transcribe_stream(b"wav")]

    assert len(events) == 1
    done = events[0]
    assert isinstance(done, DoneEvent)
    assert done.authentication_consumed is False


@pytest.mark.unit
async def test_transcribe_stream_done_parses_consumed_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fresh owner grant consumed this turn must surface as True."""

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_done_line(authentication_consumed=True) + "\n")

    _patch_transport(monkeypatch, _handler)

    events = [event async for event in server_client.transcribe_stream(b"wav")]

    done = events[0]
    assert isinstance(done, DoneEvent)
    assert done.authentication_consumed is True


@pytest.mark.unit
async def test_transcribe_parses_authentication_consumed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A consumed grant must surface as `authentication_consumed = True`."""

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "text_heard": "hola",
                "llm_response": "qué tal",
                "audio_base64": "AAAA",
                "duration_ms": 123,
                "emotion": "joy",
                "authentication_consumed": True,
            },
        )

    _patch_transport(monkeypatch, _handler)

    result = await server_client.transcribe(b"wav", identity_token="opaque-token")  # noqa: S106

    assert result.authentication_consumed is True


@pytest.mark.unit
async def test_transcribe_defaults_authentication_consumed_false_on_older_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An older server without the field must not crash or claim consumption."""

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "text_heard": "hola",
                "llm_response": "qué tal",
                "audio_base64": "AAAA",
                "duration_ms": 123,
                "emotion": "joy",
            },
        )

    _patch_transport(monkeypatch, _handler)

    result = await server_client.transcribe(b"wav")

    assert result.authentication_consumed is False
