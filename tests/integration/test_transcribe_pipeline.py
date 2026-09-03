"""Integration tests for POST /transcribe orchestration and error mapping."""

from datetime import date
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
import httpx
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
        "authentication_consumed": False,
        "identity_source": None,
    }
    assert all(isinstance(value, int) and value >= 0 for value in timing_fields.values())


@pytest.mark.integration
def test_transcribe_voice_date_uses_controller_without_legacy_delegate(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A spoken current-date request must use the deterministic controller route."""
    process = AsyncMock(return_value=TextTurnResult("legacy", "joy", 42, False))
    tts_mock = AsyncMock(return_value=("AAAA", 42))
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value="¿Qué fecha es hoy?"))
    monkeypatch.setattr(transcribe_module, "process_text_turn", process)
    monkeypatch.setattr(transcribe_module, "_today", lambda: date(2026, 8, 12), raising=False)
    monkeypatch.setattr(tts, "synthesize", tts_mock)

    response = client.post(
        "/transcribe",
        files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
    )

    assert response.status_code == 200
    assert response.json()["llm_response"] == "Hoy es 2026-08-12."
    assert response.json()["emotion"] == "neutral"
    assert response.json()["llm_ms"] == 0
    process.assert_not_awaited()
    tts_mock.assert_awaited_once_with("Hoy es 2026-08-12.")


@pytest.mark.integration
def test_transcribe_supervised_date_alias_avoids_llm(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Plan 0021: a reviewed STT corruption of the date request stays deterministic."""
    process = AsyncMock(return_value=TextTurnResult("legacy", "joy", 42, False))
    tts_mock = AsyncMock(return_value=("AAAA", 42))
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value="Me dice la fecha actual."))
    monkeypatch.setattr(transcribe_module, "process_text_turn", process)
    monkeypatch.setattr(transcribe_module, "_today", lambda: date(2026, 8, 17), raising=False)
    monkeypatch.setattr(tts, "synthesize", tts_mock)

    response = client.post(
        "/transcribe",
        files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
    )

    assert response.status_code == 200
    assert response.json()["llm_response"] == "Hoy es 2026-08-17."
    assert response.json()["llm_ms"] == 0
    process.assert_not_awaited()
    tts_mock.assert_awaited_once_with("Hoy es 2026-08-17.")


@pytest.mark.integration
def test_transcribe_ambiguous_date_alias_avoids_llm(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Plan 0021: a reviewed ambiguous STT corruption asks for clarification, not the LLM."""
    process = AsyncMock(return_value=TextTurnResult("legacy", "joy", 42, False))
    tts_mock = AsyncMock(return_value=("AAAA", 42))
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value="¿Qué vía es hoy?"))
    monkeypatch.setattr(transcribe_module, "process_text_turn", process)
    monkeypatch.setattr(transcribe_module, "_today", lambda: date(2026, 8, 17), raising=False)
    monkeypatch.setattr(tts, "synthesize", tts_mock)

    response = client.post(
        "/transcribe",
        files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
    )

    assert response.status_code == 200
    assert response.json()["llm_response"] == (
        "No entendí si preguntas por la fecha actual o por información personal. "
        "¿Podrías reformularlo?"
    )
    assert response.json()["llm_ms"] == 0
    process.assert_not_awaited()
    tts_mock.assert_awaited_once_with(
        "No entendí si preguntas por la fecha actual o por información personal. "
        "¿Podrías reformularlo?"
    )


@pytest.mark.integration
def test_transcribe_scene_request_unavailable_when_vision_disabled(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C7: with vision off, a scene request never asks for a frame."""
    process = AsyncMock(return_value=TextTurnResult("legacy", "joy", 42, False))
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value="¿Qué ves?"))
    monkeypatch.setattr(transcribe_module, "process_text_turn", process)
    monkeypatch.setattr(settings, "vision_enabled", False)

    response = client.post(
        "/transcribe",
        files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["llm_response"] == "Ahora mismo no puedo mirar desde este canal."
    assert body["vision_requested"] is False
    process.assert_not_awaited()


@pytest.mark.integration
@pytest.mark.parametrize("vision_enabled", [True, False])
def test_transcribe_active_identity_denies_without_fresh_evidence(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
    vision_enabled: bool,
) -> None:
    """The public classic actor is always unknown, so identity stays unconfirmed."""
    process = AsyncMock(return_value=TextTurnResult("legacy", "joy", 42, False))
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value="¿Quién soy?"))
    monkeypatch.setattr(transcribe_module, "process_text_turn", process)
    monkeypatch.setattr(settings, "vision_enabled", vision_enabled)

    response = client.post(
        "/transcribe",
        files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["llm_response"] == "Todavía no puedo confirmar quién sos."
    assert body["vision_requested"] is False
    process.assert_not_awaited()


@pytest.mark.integration
@pytest.mark.parametrize("vision_enabled", [True, False])
def test_transcribe_biometric_enrollment_rejected_without_camera_or_legacy(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
    vision_enabled: bool,
) -> None:
    """An unequivocal enrollment cue never requests a frame, even with vision on."""
    process = AsyncMock(return_value=TextTurnResult("legacy", "joy", 42, False))
    monkeypatch.setattr(
        stt, "transcribe", AsyncMock(return_value="Aprende mi cara, soy PersonaDePrueba")
    )
    monkeypatch.setattr(transcribe_module, "process_text_turn", process)
    monkeypatch.setattr(settings, "vision_enabled", vision_enabled)

    response = client.post(
        "/transcribe",
        files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["llm_response"] == (
        "Todavía no puedo registrar rostros: hace falta administración local y consentimiento."
    )
    assert body["vision_requested"] is False
    process.assert_not_awaited()


@pytest.mark.integration
def test_voice_event_from_transcript_is_fresh_and_opaque() -> None:
    """A voice transcript must become a new typed event with no caller identity."""
    first = transcribe_module._voice_event_from_transcript("hola")
    second = transcribe_module._voice_event_from_transcript("hola")

    assert first.event_type == "text.turn"
    assert first.source == "audio.transcribe"
    assert first.payload.message == "hola"
    assert first.payload.conversation_id.startswith("interaction:")
    assert first.occurred_at == first.recorded_at
    assert first.occurred_at.tzinfo is not None
    assert first.event_id != second.event_id
    assert first.correlation_id != second.correlation_id
    assert first.payload.conversation_id != second.payload.conversation_id


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
    """Unresolved voice requests use isolated internal scopes."""
    tts_mock = AsyncMock(return_value=("AAAA", 42))

    async def process_turn(
        client: httpx.AsyncClient,
        message: str,
        conversation_id: str,
        *,
        schedule_consolidation: ConsolidationScheduler,
    ) -> TextTurnResult:
        _ = client, schedule_consolidation
        return TextTurnResult("shared reply", "joy", 7, False)

    process = AsyncMock(side_effect=process_turn)
    monkeypatch.setattr(transcribe_module, "process_text_turn", process)
    monkeypatch.setattr(tts, "synthesize", tts_mock)

    responses = [
        client.post(
            "/transcribe",
            files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
        )
        for _ in range(2)
    ]

    scopes = [call.args[2] for call in process.await_args_list]
    assert [response.status_code for response in responses] == [200, 200]
    assert len(scopes) == 2
    assert all(scope.startswith("interaction:") for scope in scopes)
    assert scopes[0] != scopes[1]
    assert all(scope not in response.text for scope in scopes for response in responses)
    assert tts_mock.await_count == 2
    assert all(response.json()["llm_response"] == "shared reply" for response in responses)
