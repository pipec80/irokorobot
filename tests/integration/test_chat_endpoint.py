"""Integration tests for the local text-only chat endpoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import ANY, AsyncMock, Mock

from httpx import ASGITransport, AsyncClient
import pytest
from server.cognition.owner_authentication import owner_unlock_service
from server.main import app
from server.memory import working
from server.resources import AppResources
from server.routers import chat
from server.settings import settings
from server.text_turn import TextTurnResult

from server import text_turn


@asynccontextmanager
async def _client() -> AsyncIterator[AsyncClient]:
    """Yield an async client without running application lifespan.

    Plan 0039: routers depend on `request.app.state.resources`
    (`ResourcesDep`), which the real lifespan sets — assign a lightweight
    `AppResources` here since that lifespan never runs in this helper.
    """
    async with AsyncClient() as http_client:
        app.state.resources = AppResources(
            http_client=http_client, owner_unlock_service=owner_unlock_service
        )
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
        "authentication_consumed": False,
    }
    process.assert_awaited_once_with(ANY, "Hello", "web-primary")


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
async def test_chat_rejects_http_consent_field() -> None:
    """Public chat must not accept an untrusted consent assertion from HTTP."""
    async with _client() as client:
        response = await client.post(
            "/chat",
            json={
                "message": "Hello",
                "conversation_id": "web-primary",
                "consent": "granted",
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
        "authentication_consumed",
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_chat_answers_current_date_without_calling_legacy_text_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The chat adapter should expose the deterministic date result unchanged."""
    process = AsyncMock(return_value=TextTurnResult("legacy", "joy", 42, False))
    monkeypatch.setattr(chat, "process_text_turn", process)
    monkeypatch.setattr(chat, "_today", lambda: date(2026, 8, 12))

    async with _client() as client:
        response = await client.post(
            "/chat",
            json={"message": "¿Qué fecha es hoy?", "conversation_id": "web-primary"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "response": "Hoy es 2026-08-12.",
        "emotion": "neutral",
        "duration_ms": 0,
        "conversation_id": "web-primary",
        "authentication_consumed": False,
    }
    process.assert_not_awaited()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_chat_blocks_private_household_question_before_legacy_text_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Public chat must not expose a family query to legacy memory or generation."""
    process = AsyncMock(return_value=TextTurnResult("legacy", "joy", 42, False))
    audit = AsyncMock()
    monkeypatch.setattr(chat, "process_text_turn", process)
    monkeypatch.setattr(chat, "record_authorization_decision", audit)

    async with _client() as client:
        response = await client.post(
            "/chat",
            json={"message": "¿Cómo se llaman mis hijos?", "conversation_id": "web-primary"},
        )

    assert response.status_code == 200
    assert response.json()["response"] == (
        "No puedo acceder a información familiar privada sin una autorización comprobada."
    )
    process.assert_not_awaited()
    audit.assert_awaited_once()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_chat_composes_tools_but_unknown_actor_never_reaches_v4_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Public family text stays denied before a composed B2 tool can read values."""
    process = AsyncMock(return_value=TextTurnResult("legacy", "joy", 42, False))
    audit = AsyncMock()
    reader = Mock()
    tools = Mock()
    tools.get_children = AsyncMock()
    tools.count_children = AsyncMock()
    reader_factory = Mock(return_value=reader)
    tools_factory = Mock(return_value=tools)
    monkeypatch.setattr(chat, "process_text_turn", process)
    monkeypatch.setattr(chat, "record_authorization_decision", audit)
    monkeypatch.setattr(chat, "PolicyGatedV4Reader", reader_factory)
    monkeypatch.setattr(chat, "HouseholdKnowledgeTools", tools_factory)

    async with _client() as client:
        response = await client.post(
            "/chat",
            json={"message": "¿Cuántos hijos tengo?", "conversation_id": "web-primary"},
        )

    assert response.status_code == 200
    assert response.json()["response"] == (
        "No puedo acceder a información familiar privada sin una autorización comprobada."
    )
    reader_factory.assert_called_once_with()
    tools_factory.assert_called_once_with(reader=reader)
    tools.get_children.assert_not_awaited()
    tools.count_children.assert_not_awaited()
    assert reader.mock_calls == []
    process.assert_not_awaited()
    audit.assert_awaited_once()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("vision_enabled", [True, False])
async def test_chat_scene_request_always_gets_the_fixed_unavailable_plan(
    monkeypatch: pytest.MonkeyPatch, vision_enabled: bool
) -> None:
    """Chat has no camera round-trip — a scene request never reaches vision."""
    process = AsyncMock(return_value=TextTurnResult("legacy", "joy", 42, False))
    monkeypatch.setattr(chat, "process_text_turn", process)
    monkeypatch.setattr(settings, "vision_enabled", vision_enabled)

    async with _client() as client:
        response = await client.post(
            "/chat",
            json={"message": "¿Qué ves?", "conversation_id": "web-primary"},
        )

    assert response.status_code == 200
    assert response.json()["response"] == "Ahora mismo no puedo mirar desde este canal."
    process.assert_not_awaited()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_chat_active_identity_denies_without_fresh_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chat's public actor is always unknown, so identity stays unconfirmed."""
    process = AsyncMock(return_value=TextTurnResult("legacy", "joy", 42, False))
    monkeypatch.setattr(chat, "process_text_turn", process)

    async with _client() as client:
        response = await client.post(
            "/chat",
            json={"message": "¿Quién soy?", "conversation_id": "web-primary"},
        )

    assert response.status_code == 200
    assert response.json()["response"] == "Todavía no puedo confirmar quién sos."
    process.assert_not_awaited()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_chat_biometric_enrollment_is_rejected_without_camera_or_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unequivocal enrollment cue is rejected without camera, model, or legacy text."""
    process = AsyncMock(return_value=TextTurnResult("legacy", "joy", 42, False))
    monkeypatch.setattr(chat, "process_text_turn", process)

    async with _client() as client:
        response = await client.post(
            "/chat",
            json={
                "message": "Aprende mi cara, soy PersonaDePrueba",
                "conversation_id": "web-primary",
            },
        )

    assert response.status_code == 200
    assert response.json()["response"] == (
        "Todavía no puedo registrar rostros: hace falta administración local y consentimiento."
    )
    process.assert_not_awaited()
