"""Unit tests for consolidation extraction routing and the Anthropic backend."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from server.exceptions import LLMError
from server.memory import consolidation
from server.schemas import TurnExtraction
from server.settings import settings

_FAKE_EXTRACTION = TurnExtraction(importance=0.3)


@pytest.mark.unit
async def test_extract_via_anthropic_parses_tool_use_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The forced tool_use block input must validate into TurnExtraction."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = {
        "entities": [{"name": "Luna", "type": "other"}],
        "facts": [],
        "episodic_summary": "El usuario tiene una gata llamada Luna.",
        "importance": 0.8,
    }
    fake_message = MagicMock()
    fake_message.content = [tool_block]
    fake_client = MagicMock()
    fake_client.messages.create = AsyncMock(return_value=fake_message)
    monkeypatch.setattr(consolidation, "get_anthropic_client", lambda: fake_client)

    extraction = await consolidation._extract_via_anthropic("tengo una gata", "qué lindo")

    assert extraction.entities[0].name == "Luna"
    assert extraction.importance == 0.8


@pytest.mark.unit
async def test_extract_via_anthropic_no_tool_block_raises_llmerror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text_block = MagicMock()
    text_block.type = "text"
    fake_message = MagicMock()
    fake_message.content = [text_block]
    fake_client = MagicMock()
    fake_client.messages.create = AsyncMock(return_value=fake_message)
    monkeypatch.setattr(consolidation, "get_anthropic_client", lambda: fake_client)

    with pytest.raises(LLMError, match="no tool_use"):
        await consolidation._extract_via_anthropic("hola", "hola")


@pytest.mark.unit
async def test_extract_via_ollama_uses_shared_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    """R3: _extract_via_ollama must go through the shared llm_transport.ollama_chat."""
    mock_chat = AsyncMock(
        return_value='{"entities": [], "facts": [], "episodic_summary": null, "importance": 0.3}'
    )
    monkeypatch.setattr(consolidation, "ollama_chat", mock_chat)

    extraction = await consolidation._extract_via_ollama("hola", "hola")

    assert extraction == _FAKE_EXTRACTION
    mock_chat.assert_awaited_once()
    assert mock_chat.call_args.kwargs["options"] == {"temperature": 0.1}
    assert "format_schema" in mock_chat.call_args.kwargs


@pytest.mark.unit
async def test_extract_via_ollama_malformed_json_raises_llmerror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(consolidation, "ollama_chat", AsyncMock(return_value="not json"))

    with pytest.raises(LLMError, match="invalid JSON"):
        await consolidation._extract_via_ollama("hola", "hola")


@pytest.mark.unit
async def test_extract_routes_to_anthropic_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_anthropic = AsyncMock(return_value=_FAKE_EXTRACTION)
    mock_ollama = AsyncMock(return_value=_FAKE_EXTRACTION)
    monkeypatch.setattr(consolidation, "_extract_via_anthropic", mock_anthropic)
    monkeypatch.setattr(consolidation, "_extract_via_ollama", mock_ollama)
    monkeypatch.setattr(settings, "consolidation_provider", "anthropic")

    await consolidation._extract("hola", "hola")

    mock_anthropic.assert_awaited_once()
    mock_ollama.assert_not_awaited()


@pytest.mark.unit
async def test_extract_empty_provider_inherits_llm_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CONSOLIDATION_PROVIDER='' must fall back to LLM_PROVIDER."""
    mock_anthropic = AsyncMock(return_value=_FAKE_EXTRACTION)
    mock_ollama = AsyncMock(return_value=_FAKE_EXTRACTION)
    monkeypatch.setattr(consolidation, "_extract_via_anthropic", mock_anthropic)
    monkeypatch.setattr(consolidation, "_extract_via_ollama", mock_ollama)
    monkeypatch.setattr(settings, "consolidation_provider", "")
    monkeypatch.setattr(settings, "llm_provider", "anthropic")

    await consolidation._extract("hola", "hola")

    mock_anthropic.assert_awaited_once()
    mock_ollama.assert_not_awaited()


@pytest.mark.unit
async def test_extract_retries_once_after_transient_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single transient failure must be retried, not abandoned."""
    mock_ollama = AsyncMock(side_effect=[LLMError("model loading"), _FAKE_EXTRACTION])
    sleep_mock = AsyncMock()
    monkeypatch.setattr(consolidation, "_extract_via_ollama", mock_ollama)
    monkeypatch.setattr(consolidation.asyncio, "sleep", sleep_mock)
    monkeypatch.setattr(settings, "consolidation_provider", "ollama")

    extraction = await consolidation._extract("hola", "hola")

    assert extraction == _FAKE_EXTRACTION
    assert mock_ollama.await_count == 2
    sleep_mock.assert_awaited_once()


@pytest.mark.unit
async def test_extract_gives_up_after_second_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_ollama = AsyncMock(side_effect=LLMError("still broken"))
    monkeypatch.setattr(consolidation, "_extract_via_ollama", mock_ollama)
    monkeypatch.setattr(consolidation.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(settings, "consolidation_provider", "ollama")

    with pytest.raises(LLMError):
        await consolidation._extract("hola", "hola")

    assert mock_ollama.await_count == 2
