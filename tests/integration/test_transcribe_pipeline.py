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
def test_transcribe_uses_distinct_internal_scopes_per_request(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unresolved voice requests use isolated internal scopes and consolidation."""
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

    responses = [
        client.post(
            "/transcribe",
            files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
        )
        for _ in range(2)
    ]

    scopes = [call.args[1] for call in process.await_args_list]
    assert [response.status_code for response in responses] == [200, 200]
    assert len(scopes) == 2
    assert all(scope.startswith("interaction:") for scope in scopes)
    assert scopes[0] != scopes[1]
    assert all(scope not in response.text for scope in scopes for response in responses)
    assert tts_mock.await_count == 2
    assert consolidate.await_count == 2
    assert all(response.json()["llm_response"] == "shared reply" for response in responses)
