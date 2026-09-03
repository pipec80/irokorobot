"""Unit tests for local consolidation extraction."""

from unittest.mock import AsyncMock

import httpx
import pytest
from server.exceptions import LLMError
from server.memory import consolidation
from server.schemas import TurnExtraction
from server.settings import settings

_FAKE_EXTRACTION = TurnExtraction(importance=0.3)


@pytest.mark.unit
async def test_extract_via_ollama_uses_shared_transport(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R3: _extract_via_ollama must go through the shared llm_transport.ollama_chat."""
    mock_chat = AsyncMock(
        return_value='{"entities": [], "facts": [], "episodic_summary": null, "importance": 0.3}'
    )
    monkeypatch.setattr(consolidation, "ollama_chat", mock_chat)

    extraction = await consolidation._extract_via_ollama(http_client, "hola", "hola")

    assert extraction == _FAKE_EXTRACTION
    mock_chat.assert_awaited_once()
    assert mock_chat.call_args.kwargs["options"] == {"temperature": 0.1}
    assert "format_schema" in mock_chat.call_args.kwargs


@pytest.mark.unit
async def test_extract_via_ollama_malformed_json_raises_llmerror(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(consolidation, "ollama_chat", AsyncMock(return_value="not json"))

    with pytest.raises(LLMError, match="invalid JSON"):
        await consolidation._extract_via_ollama(http_client, "hola", "hola")


@pytest.mark.unit
async def test_extract_uses_local_backend_after_invalid_runtime_mutation(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Consolidation must not select a cloud extractor after runtime corruption."""
    local_extractor = AsyncMock(return_value=_FAKE_EXTRACTION)
    monkeypatch.setattr(consolidation, "_extract_via_ollama", local_extractor)
    monkeypatch.delattr(consolidation, "_extract_via_anthropic", raising=False)
    monkeypatch.setattr(settings, "llm_provider", "anthropic")

    extraction = await consolidation._extract(http_client, "hola", "hola")

    assert extraction == _FAKE_EXTRACTION
    local_extractor.assert_awaited_once_with(http_client, "hola", "hola")


@pytest.mark.unit
async def test_extract_retries_once_after_transient_failure(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single transient failure must be retried, not abandoned."""
    mock_ollama = AsyncMock(side_effect=[LLMError("model loading"), _FAKE_EXTRACTION])
    sleep_mock = AsyncMock()
    monkeypatch.setattr(consolidation, "_extract_via_ollama", mock_ollama)
    monkeypatch.setattr(consolidation.asyncio, "sleep", sleep_mock)

    extraction = await consolidation._extract(http_client, "hola", "hola")

    assert extraction == _FAKE_EXTRACTION
    assert mock_ollama.await_count == 2
    sleep_mock.assert_awaited_once()


@pytest.mark.unit
async def test_extract_gives_up_after_second_failure(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_ollama = AsyncMock(side_effect=LLMError("still broken"))
    monkeypatch.setattr(consolidation, "_extract_via_ollama", mock_ollama)
    monkeypatch.setattr(consolidation.asyncio, "sleep", AsyncMock())

    with pytest.raises(LLMError):
        await consolidation._extract(http_client, "hola", "hola")

    assert mock_ollama.await_count == 2
