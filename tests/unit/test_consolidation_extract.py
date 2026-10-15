"""Unit tests for local consolidation extraction."""

from unittest.mock import AsyncMock

import httpx
import pytest
from server.exceptions import LLMError
from server.memory import consolidation
from server.schemas import TurnExtraction

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
async def test_a_malformed_answer_is_never_echoed_into_the_exception(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The model's output is about the household: it must not travel in an error message."""
    answer = '{"entities": "zumo de pomelo", "facts": 7}'
    monkeypatch.setattr(consolidation, "ollama_chat", AsyncMock(return_value=answer))

    with pytest.raises(LLMError) as excinfo:
        await consolidation._extract_via_ollama(http_client, "hola", "hola")

    assert str(excinfo.value) == "Extraction returned invalid JSON"
    assert "pomelo" not in repr(excinfo.value)
    assert excinfo.value.__cause__ is None
