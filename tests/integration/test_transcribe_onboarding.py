"""Integration tests for onboarding behavior through POST /transcribe."""

from collections.abc import Generator
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
import pytest
from server.memory import meta, working
from server.routers import transcribe as transcribe_module
from server.settings import settings

from server import llm, onboarding, pipeline, stt, tts


@pytest.fixture(autouse=True)
def _mock_memory_pipeline(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Enable memory with mocked model boundaries for each onboarding test."""
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value="hola robot"))
    monkeypatch.setattr(llm, "generate_response", AsyncMock(return_value=("hola humano", "joy")))
    monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("AAAA", 42)))
    monkeypatch.setattr(pipeline, "list_entity_names", AsyncMock(return_value=[]))
    monkeypatch.setattr(transcribe_module, "consolidate_turn", AsyncMock())
    working._buffers.clear()
    working._emotion_buffers.clear()
    yield
    working._buffers.clear()
    working._emotion_buffers.clear()


@pytest.mark.integration
def test_unidentified_transcribe_suppresses_onboarding_lookup(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0.2 must not query legacy onboarding for an unresolved voice turn."""
    lookup = AsyncMock()
    monkeypatch.setattr(onboarding, "next_missing_slot", lookup)

    response = client.post(
        "/transcribe",
        files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
    )

    assert response.status_code == 200
    assert response.json()["llm_response"] == "hola humano"
    lookup.assert_not_awaited()


@pytest.mark.integration
def test_unidentified_transcribe_passes_no_onboarding_inputs(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The unresolved public path must never start the legacy interview."""
    llm_mock = AsyncMock(return_value=("hola humano", "neutral"))
    monkeypatch.setattr(llm, "generate_response", llm_mock)

    response = client.post(
        "/transcribe",
        files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
    )

    assert response.status_code == 200
    assert llm_mock.await_args_list[-1].kwargs["onboarding"] is False
    assert llm_mock.await_args_list[-1].kwargs["onboarding_slot"] is None


@pytest.mark.integration
def test_unidentified_transcribe_does_not_complete_legacy_onboarding(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0.2 must not mutate legacy onboarding completion from a voice turn."""
    set_flag = AsyncMock()
    monkeypatch.setattr(meta, "set_flag", set_flag)

    response = client.post(
        "/transcribe",
        files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
    )

    assert response.status_code == 200
    set_flag.assert_not_awaited()
