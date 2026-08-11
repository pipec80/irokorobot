"""Integration tests for the local text-only chat endpoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock

from httpx import ASGITransport, AsyncClient
import pytest
from server.main import app
from server.memory import working
from server.routers import chat
from server.settings import settings
from server.text_turn import TextTurnResult

from server import text_turn


@asynccontextmanager
async def _client() -> AsyncIterator[AsyncClient]:
    """Yield an async client without running application lifespan."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture(autouse=True)
def _clear_working_memory() -> None:
    """Reset process-local conversation buffers before each test."""
    working._buffers.clear()
    working._emotion_buffers.clear()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_chat_returns_exact_contract_and_calls_service_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid request should map one service result to the public contract."""
    process = AsyncMock(return_value=TextTurnResult("Reply", "joy", 42, False))
    monkeypatch.setattr(chat, "process_text_turn", process)

    async with _client() as client:
        response = await client.post(
            "/chat",
            json={"message": "Hello", "conversation_id": "web-primary"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "response": "Reply",
        "emotion": "joy",
        "duration_ms": 42,
        "conversation_id": "web-primary",
    }
    process.assert_awaited_once_with("Hello", "web-primary")


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message,conversation_id",
    [
        ("   ", "web-primary"),
        ("Hello", ""),
        ("Hello", "a" * 65),
        ("Hello", "-leading"),
        ("Hello", "contains space"),
        ("Hello", "áccented"),
    ],
)
async def test_chat_rejects_invalid_payloads(message: str, conversation_id: str) -> None:
    """Whitespace messages and unsafe conversation IDs should return 422."""
    async with _client() as client:
        response = await client.post(
            "/chat",
            json={"message": message, "conversation_id": conversation_id},
        )

    assert response.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_chat_rejects_persistent_identity_fields() -> None:
    """Chat input must not accept a user or tenant identity."""
    async with _client() as client:
        response = await client.post(
            "/chat",
            json={
                "message": "Hello",
                "conversation_id": "web-primary",
                "user_id": "someone",
            },
        )

    assert response.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_chat_fallback_is_safe_and_does_not_touch_audio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fallback details should stay private and chat should not invoke audio."""
    process = AsyncMock(
        return_value=TextTurnResult(settings.llm_fallback_phrase, "neutral", 8, True)
    )
    stt_call = AsyncMock()
    tts_call = AsyncMock()
    monkeypatch.setattr(chat, "process_text_turn", process)
    monkeypatch.setattr("server.stt.transcribe", stt_call)
    monkeypatch.setattr("server.tts.synthesize", tts_call)

    async with _client() as client:
        response = await client.post(
            "/chat",
            json={"message": "Hello", "conversation_id": "web-primary"},
        )

    assert response.status_code == 200
    assert response.json()["response"] == settings.llm_fallback_phrase
    assert set(response.json()) == {
        "response",
        "emotion",
        "duration_ms",
        "conversation_id",
    }
    stt_call.assert_not_awaited()
    tts_call.assert_not_awaited()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_chat_openapi_uses_request_and_response_schemas() -> None:
    """OpenAPI should publish the additive typed chat operation."""
    async with _client() as client:
        response = await client.get("/openapi.json")

    operation = response.json()["paths"]["/chat"]["post"]
    request_schema = operation["requestBody"]["content"]["application/json"]["schema"]
    assert request_schema["$ref"].endswith("/ChatRequest")
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ChatResponse"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_chat_without_internal_evidence_is_one_turn_and_stateless(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Public conversation IDs must not unlock history or persistent memory."""
    build_context = AsyncMock()
    get_history = Mock()
    get_emotion = Mock()
    generate = AsyncMock(side_effect=[("A1", "joy"), ("B1", "sadness"), ("A2", "neutral")])
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(text_turn, "build_context", build_context)
    monkeypatch.setattr(text_turn.working, "get_history", get_history)
    monkeypatch.setattr(text_turn.working, "get_recent_emotion", get_emotion)
    monkeypatch.setattr(text_turn.llm, "generate_response", generate)

    async with _client() as client:
        for message, conversation_id in (
            ("A", "web-a"),
            ("B", "web-b"),
            ("A again", "web-a"),
        ):
            response = await client.post(
                "/chat",
                json={"message": message, "conversation_id": conversation_id},
            )
            assert response.status_code == 200

    build_context.assert_not_awaited()
    get_history.assert_not_called()
    get_emotion.assert_not_called()
    assert [item.kwargs["context"] for item in generate.await_args_list] == [None, None, None]
    assert [item.kwargs["history"] for item in generate.await_args_list] == [None, None, None]
    assert working._buffers == {}
    assert working._emotion_buffers == {}
