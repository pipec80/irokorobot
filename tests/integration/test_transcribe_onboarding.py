"""Integration tests for onboarding behavior through POST /transcribe."""

from collections.abc import Generator
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
import pytest
from server.exceptions import BrainMemoryError
from server.memory import working
from server.onboarding import OnboardingSlot
from server.routers import transcribe as transcribe_module
from server.schemas import MemoryContext
from server.settings import settings

from server import llm, pipeline, stt, text_turn, tts


@pytest.fixture(autouse=True)
def _mock_memory_pipeline(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Enable memory with mocked model boundaries for each onboarding test."""
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value="hola robot"))
    monkeypatch.setattr(llm, "generate_response", AsyncMock(return_value=("hola humano", "joy")))
    monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("AAAA", 42)))
    monkeypatch.setattr(pipeline, "list_entity_names", AsyncMock(return_value=[]))
    monkeypatch.setattr(transcribe_module, "consolidate_turn", AsyncMock())
    monkeypatch.setattr(text_turn, "_onboarding_done", False)
    yield
    working.clear(settings.voice_conversation_id)


@pytest.mark.integration
def test_onboarding_check_failure_degrades_to_stateless(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An onboarding DB failure should not prevent a response."""
    monkeypatch.setattr(text_turn, "build_context", AsyncMock(return_value=MemoryContext()))
    monkeypatch.setattr(
        text_turn,
        "_needs_onboarding",
        AsyncMock(side_effect=BrainMemoryError("DB not open")),
    )

    response = client.post(
        "/transcribe",
        files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
    )

    assert response.status_code == 200
    assert response.json()["llm_response"] == "hola humano"


@pytest.mark.integration
def test_onboarding_slot_reaches_llm(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The next persistent checklist slot should reach shared generation."""
    llm_mock = AsyncMock(return_value=("¿cómo te llamás?", "neutral"))
    slot = OnboardingSlot(key="nombre", question_hint="su nombre")
    monkeypatch.setattr(llm, "generate_response", llm_mock)
    monkeypatch.setattr(text_turn, "build_context", AsyncMock(return_value=MemoryContext()))
    monkeypatch.setattr(text_turn, "_needs_onboarding", AsyncMock(return_value=True))
    monkeypatch.setattr(text_turn, "next_missing_slot", AsyncMock(return_value=slot))
    monkeypatch.setattr(text_turn.meta, "get_flag", AsyncMock(return_value=None))

    response = client.post(
        "/transcribe",
        files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
    )

    assert response.status_code == 200
    assert llm_mock.await_args_list[-1].kwargs["onboarding"] is True
    assert llm_mock.await_args_list[-1].kwargs["onboarding_slot"] == slot


@pytest.mark.integration
def test_exhausted_checklist_completes_onboarding(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No missing slot should persist completion and end the interview."""
    llm_mock = AsyncMock(return_value=("¡listo!", "joy"))
    set_flag = AsyncMock()
    monkeypatch.setattr(llm, "generate_response", llm_mock)
    monkeypatch.setattr(text_turn, "build_context", AsyncMock(return_value=MemoryContext()))
    monkeypatch.setattr(text_turn, "_needs_onboarding", AsyncMock(return_value=True))
    monkeypatch.setattr(text_turn, "next_missing_slot", AsyncMock(return_value=None))
    monkeypatch.setattr(text_turn.meta, "get_flag", AsyncMock(return_value="Felipe"))
    monkeypatch.setattr(text_turn.meta, "set_flag", set_flag)

    response = client.post(
        "/transcribe",
        files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
    )

    assert response.status_code == 200
    set_flag.assert_awaited_once_with("onboarding_complete", "true")
    assert llm_mock.await_args_list[-1].kwargs["onboarding"] is False
