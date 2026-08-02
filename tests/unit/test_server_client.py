"""Unit tests for robot.server_client — httpx mocked via MockTransport."""

from collections.abc import Generator

import httpx
import pytest
from robot.exceptions import NoSpeechError, ServerError

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
