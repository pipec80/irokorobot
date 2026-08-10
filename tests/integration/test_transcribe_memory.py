"""Integration tests for memory behavior through POST /transcribe."""

from collections.abc import Generator
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
import pytest
from server.exceptions import BrainMemoryError, LLMError
from server.memory import working
from server.routers import transcribe as transcribe_module
from server.schemas import MemoryContext
from server.settings import settings

from server import llm, pipeline, stt, text_turn, tts


@pytest.fixture(autouse=True)
def _mock_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide successful model boundaries without loading real models."""
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value="hola robot"))
    monkeypatch.setattr(llm, "generate_response", AsyncMock(return_value=("hola humano", "joy")))
    monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("AAAA", 42)))


@pytest.fixture
def memory_on(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Enable memory and reset the voice conversation around one test."""
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(transcribe_module, "consolidate_turn", AsyncMock())
    monkeypatch.setattr(text_turn, "_onboarding_done", False)
    yield
    working.clear(settings.voice_conversation_id)


@pytest.mark.integration
@pytest.mark.usefixtures("memory_on")
def test_fallback_turn_is_not_recorded(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fallback apology should not enter working or persistent memory."""
    consolidate = AsyncMock()
    monkeypatch.setattr(llm, "generate_response", AsyncMock(side_effect=LLMError("down")))
    monkeypatch.setattr(transcribe_module, "consolidate_turn", consolidate)
    monkeypatch.setattr(pipeline, "list_entity_names", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        text_turn, "_memory_prompt_state", AsyncMock(return_value=(None, False, None, None))
    )

    response = client.post(
        "/transcribe",
        files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
    )

    assert response.status_code == 200
    consolidate.assert_not_awaited()
    assert working.get_history(settings.voice_conversation_id) == []


@pytest.mark.integration
@pytest.mark.usefixtures("memory_on")
def test_memory_failure_degrades_to_stateless(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unresolved voice turn must not attempt persistent retrieval."""
    build_context = AsyncMock(side_effect=BrainMemoryError("embeddings down"))
    monkeypatch.setattr(text_turn, "build_context", build_context)

    response = client.post(
        "/transcribe",
        files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
    )

    assert response.status_code == 200
    assert response.json()["llm_response"] == "hola humano"
    build_context.assert_not_awaited()


@pytest.mark.integration
@pytest.mark.usefixtures("memory_on")
def test_entity_names_reach_stt_as_hotwords(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Known persistent entity names should continue to bias STT."""
    stt_mock = AsyncMock(return_value="hola Dominga")
    monkeypatch.setattr(stt, "transcribe", stt_mock)
    monkeypatch.setattr(
        pipeline,
        "list_entity_names",
        AsyncMock(return_value=["Dominga", "Luna"]),
    )
    monkeypatch.setattr(
        text_turn,
        "_memory_prompt_state",
        AsyncMock(return_value=(MemoryContext(), False, None, None)),
    )

    response = client.post(
        "/transcribe",
        files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
    )

    assert response.status_code == 200
    assert stt_mock.await_args_list[-1].kwargs["extra_hotwords"] == ["Dominga", "Luna"]


@pytest.mark.integration
@pytest.mark.usefixtures("memory_on")
def test_unidentified_voice_turn_does_not_read_owner_metadata(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy owner metadata must not identify the current voice speaker."""
    llm_mock = AsyncMock(return_value=("hola Felipe", "joy"))
    monkeypatch.setattr(llm, "generate_response", llm_mock)
    monkeypatch.setattr(pipeline, "list_entity_names", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        text_turn,
        "_memory_prompt_state",
        AsyncMock(return_value=(MemoryContext(), False, None, "Felipe")),
    )

    response = client.post(
        "/transcribe",
        files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
    )

    assert response.status_code == 200
    assert llm_mock.await_args_list[-1].kwargs["owner_name"] is None


@pytest.mark.integration
@pytest.mark.usefixtures("memory_on")
def test_unidentified_voice_turn_does_not_schedule_consolidation(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A voice turn with no internal manual evidence must never persist facts."""
    consolidate = AsyncMock()
    monkeypatch.setattr(transcribe_module, "consolidate_turn", consolidate)
    monkeypatch.setattr(pipeline, "list_entity_names", AsyncMock(return_value=[]))

    response = client.post(
        "/transcribe",
        files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
    )

    assert response.status_code == 200
    consolidate.assert_not_awaited()


@pytest.mark.integration
@pytest.mark.usefixtures("memory_on")
def test_hotword_failure_degrades_gracefully(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hotword lookup failure should not prevent transcription."""
    monkeypatch.setattr(
        pipeline,
        "list_entity_names",
        AsyncMock(side_effect=BrainMemoryError("DB not open")),
    )
    monkeypatch.setattr(
        text_turn,
        "build_context",
        AsyncMock(side_effect=BrainMemoryError("DB not open")),
    )

    response = client.post(
        "/transcribe",
        files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
    )

    assert response.status_code == 200
    assert response.json()["text_heard"] == "hola robot"
