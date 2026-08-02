"""Integration tests for POST /transcribe orchestration and error mapping."""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
import pytest
from server.exceptions import LLMError, TranscriptionError, TTSError
from server.routers import transcribe as transcribe_module
from server.settings import settings
from server.text_turn import ConsolidationScheduler, TextTurnResult

from server import llm, stt, tts


@pytest.fixture(autouse=True)
def _mock_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide successful model boundaries without loading real models."""
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value="hola robot"))
    monkeypatch.setattr(llm, "generate_response", AsyncMock(return_value=("hola humano", "joy")))
    monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("AAAA", 42)))


@pytest.mark.integration
def test_transcribe_happy_path_returns_all_fields(
    client: TestClient,
    silence_wav_bytes: bytes,
) -> None:
    """The existing response contract and non-negative timings must remain."""
    response = client.post(
        "/transcribe",
        files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
    )

    assert response.status_code == 200
    body = response.json()
    timing_fields = {key: body.pop(key) for key in ("stt_ms", "llm_ms", "tts_ms", "total_ms")}
    assert body == {
        "text_heard": "hola robot",
        "llm_response": "hola humano",
        "audio_base64": "AAAA",
        "duration_ms": 42,
        "emotion": "joy",
        "vision_requested": False,
    }
    assert all(isinstance(value, int) and value >= 0 for value in timing_fields.values())


@pytest.mark.integration
def test_transcribe_stt_failure_returns_500(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transcription backend failure should retain its 500 mapping."""
    monkeypatch.setattr(
        stt,
        "transcribe",
        AsyncMock(side_effect=TranscriptionError("whisper crashed")),
    )

    response = client.post(
        "/transcribe",
        files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
    )

    assert response.status_code == 500
    assert "transcription" in response.json()["detail"].lower()


@pytest.mark.integration
def test_transcribe_llm_failure_speaks_fallback_phrase(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An LLM failure should remain a spoken local fallback with HTTP 200."""
    monkeypatch.setattr(
        llm,
        "generate_response",
        AsyncMock(side_effect=LLMError("ollama down")),
    )

    response = client.post(
        "/transcribe",
        files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
    )

    assert response.status_code == 200
    assert response.json()["llm_response"] == settings.llm_fallback_phrase
    assert response.json()["emotion"] == "neutral"
    assert response.json()["audio_base64"] == "AAAA"


@pytest.mark.integration
def test_transcribe_tts_failure_returns_500(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A synthesis backend failure should retain its 500 mapping."""
    monkeypatch.setattr(
        tts,
        "synthesize",
        AsyncMock(side_effect=TTSError("piper crashed")),
    )

    response = client.post(
        "/transcribe",
        files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
    )

    assert response.status_code == 500
    assert "speech synthesis" in response.json()["detail"].lower()


@pytest.mark.integration
def test_transcribe_stt_value_error_returns_500(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ValueError from STT should retain the transcription 500 mapping."""
    monkeypatch.setattr(stt, "transcribe", AsyncMock(side_effect=ValueError("bad audio")))

    response = client.post(
        "/transcribe",
        files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
    )

    assert response.status_code == 500


@pytest.mark.integration
def test_transcribe_delegates_text_turn_to_shared_service(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Voice text should use the configured conversation and consolidation."""
    consolidate = AsyncMock()
    tts_mock = AsyncMock(return_value=("AAAA", 42))

    async def process_turn(
        message: str,
        conversation_id: str,
        *,
        schedule_consolidation: ConsolidationScheduler,
    ) -> TextTurnResult:
        schedule_consolidation(message, "shared reply")
        return TextTurnResult("shared reply", "joy", 7, False)

    process = AsyncMock(side_effect=process_turn)
    monkeypatch.setattr(transcribe_module, "process_text_turn", process)
    monkeypatch.setattr(transcribe_module, "consolidate_turn", consolidate)
    monkeypatch.setattr(tts, "synthesize", tts_mock)

    response = client.post(
        "/transcribe",
        files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
    )

    assert response.status_code == 200
    assert process.await_args_list[-1].args == ("hola robot", settings.voice_conversation_id)
    tts_mock.assert_awaited_once_with("shared reply")
    consolidate.assert_awaited_once_with("hola robot", "shared reply")
    assert response.json()["llm_response"] == "shared reply"
