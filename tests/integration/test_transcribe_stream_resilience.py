"""Resilience tests for POST /transcribe/stream."""

from collections.abc import AsyncIterator
import json
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
import httpx
import pytest
from server.exceptions import TranscriptionError
from server.settings import settings

from server import llm_streaming, stt, tts


@pytest.fixture(autouse=True)
def _mock_media(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide successful STT/TTS boundaries by default."""
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value="hola robot"))
    monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("QQ==", 10)))


def _post_stream(client: TestClient, audio: bytes) -> httpx.Response:
    """Post one WAV 16kHz, mono, int16 stream request."""
    return client.post(
        "/transcribe/stream",
        files={"audio": ("a.wav", audio, "audio/wav")},
    )


def _parse_ndjson(text: str) -> list[dict[str, object]]:
    """Parse non-empty NDJSON response lines."""
    return [json.loads(line) for line in text.strip().split("\n") if line.strip()]


@pytest.mark.integration
def test_stream_stt_failure_returns_500(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """STT failure before streaming should remain a normal HTTP 500."""
    monkeypatch.setattr(
        stt,
        "transcribe",
        AsyncMock(side_effect=TranscriptionError("whisper crashed")),
    )

    response = _post_stream(client, silence_wav_bytes)

    assert response.status_code == 500


@pytest.mark.integration
def test_stream_empty_transcript_returns_422(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty transcript should be rejected before starting NDJSON."""
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value="   "))

    response = _post_stream(client, silence_wav_bytes)

    assert response.status_code == 422


@pytest.mark.integration
def test_stream_empty_audio_returns_422(client: TestClient) -> None:
    """An empty WAV upload should preserve the 422 contract."""
    assert _post_stream(client, b"").status_code == 422


@pytest.mark.integration
def test_stream_without_emotion_tag_still_speaks(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing emotion metadata should fall back before emitting audio."""
    monkeypatch.setattr(settings, "llm_provider", "ollama")

    async def fake_stream(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        for delta in ("Hola. ", "¿Cómo estás?"):
            yield delta

    monkeypatch.setattr(llm_streaming, "generate_response_stream", fake_stream)
    response = _post_stream(client, silence_wav_bytes)
    events = _parse_ndjson(response.text)

    assert response.status_code == 200
    assert events[0] == {"type": "text_heard", "value": "hola robot"}
    emotion_events = [event for event in events if event["type"] == "emotion"]
    audio_events = [event for event in events if event["type"] == "audio"]
    assert emotion_events == [{"type": "emotion", "value": "neutral"}]
    assert [event["text"] for event in audio_events] == ["Hola. ¿Cómo estás?"]
    assert events.index(emotion_events[0]) < events.index(audio_events[0])
