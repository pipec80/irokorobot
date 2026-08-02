"""Integration tests for POST /transcribe input validation.

Covers request-shape errors (413/422) that must be rejected before any
STT/LLM/TTS work happens. Does not require models to be loaded.
"""

import io
import wave

from fastapi.testclient import TestClient
import pytest
from server.settings import settings


@pytest.mark.integration
def test_transcribe_empty_audio_returns_422(client: TestClient) -> None:
    """An upload with zero bytes must be rejected with 422."""
    response = client.post(
        "/transcribe",
        files={"audio": ("empty.wav", b"", "audio/wav")},
    )
    assert response.status_code == 422
    assert "empty" in response.json()["detail"].lower()


@pytest.mark.integration
def test_transcribe_missing_audio_field_returns_422(client: TestClient) -> None:
    """FastAPI must reject a request without the required 'audio' field."""
    response = client.post("/transcribe")
    assert response.status_code == 422


@pytest.mark.integration
def test_transcribe_oversized_audio_returns_413(client: TestClient) -> None:
    """An upload larger than max_upload_bytes must be rejected with 413."""
    oversized = b"\x00" * (settings.max_upload_bytes + 1)
    response = client.post(
        "/transcribe",
        files={"audio": ("big.wav", io.BytesIO(oversized), "audio/wav")},
    )
    assert response.status_code == 413
    assert "too large" in response.json()["detail"].lower()


def _make_wav(
    *, channels: int = 1, sampwidth: int = 2, framerate: int = 16_000, nframes: int = 1600
) -> bytes:
    """Build a synthetic silent WAV with the given format parameters.

    Args:
        channels: Number of audio channels (contract requires 1 / mono).
        sampwidth: Sample width in bytes (contract requires 2 / int16).
        framerate: Sample rate in Hz (contract requires 16000).
        nframes: Number of silent frames to write.

    Returns:
        Raw WAV bytes built with the given (possibly contract-violating) parameters.
    """
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(framerate)
        wf.writeframes(b"\x00" * (nframes * channels * sampwidth))
    return buf.getvalue()


@pytest.mark.integration
def test_transcribe_rejects_non_wav(client: TestClient) -> None:
    """Bytes that aren't a WAV container must be rejected with 422."""
    response = client.post(
        "/transcribe",
        files={"audio": ("not_wav.wav", b"this is not a wav file at all", "audio/wav")},
    )
    assert response.status_code == 422


@pytest.mark.integration
def test_transcribe_rejects_wrong_sample_rate(client: TestClient) -> None:
    """A WAV at a sample rate other than 16kHz must be rejected with 422."""
    wav_bytes = _make_wav(framerate=44_100)
    response = client.post(
        "/transcribe",
        files={"audio": ("wrong_rate.wav", wav_bytes, "audio/wav")},
    )
    assert response.status_code == 422


@pytest.mark.integration
def test_transcribe_rejects_stereo(client: TestClient) -> None:
    """A stereo (2-channel) WAV must be rejected with 422."""
    wav_bytes = _make_wav(channels=2)
    response = client.post(
        "/transcribe",
        files={"audio": ("stereo.wav", wav_bytes, "audio/wav")},
    )
    assert response.status_code == 422


@pytest.mark.integration
def test_transcribe_rejects_non_int16(client: TestClient) -> None:
    """A WAV with a bit depth other than 16-bit must be rejected with 422."""
    wav_bytes = _make_wav(sampwidth=1)
    response = client.post(
        "/transcribe",
        files={"audio": ("8bit.wav", wav_bytes, "audio/wav")},
    )
    assert response.status_code == 422


@pytest.mark.integration
def test_transcribe_stream_rejects_non_wav(client: TestClient) -> None:
    """Bytes that aren't a WAV container must be rejected with 422 (streaming endpoint)."""
    response = client.post(
        "/transcribe/stream",
        files={"audio": ("not_wav.wav", b"this is not a wav file at all", "audio/wav")},
    )
    assert response.status_code == 422


@pytest.mark.integration
def test_transcribe_stream_rejects_wrong_sample_rate(client: TestClient) -> None:
    """A WAV at a sample rate other than 16kHz must be rejected with 422 (streaming endpoint)."""
    wav_bytes = _make_wav(framerate=44_100)
    response = client.post(
        "/transcribe/stream",
        files={"audio": ("wrong_rate.wav", wav_bytes, "audio/wav")},
    )
    assert response.status_code == 422


@pytest.mark.integration
def test_transcribe_stream_rejects_stereo(client: TestClient) -> None:
    """A stereo (2-channel) WAV must be rejected with 422 (streaming endpoint)."""
    wav_bytes = _make_wav(channels=2)
    response = client.post(
        "/transcribe/stream",
        files={"audio": ("stereo.wav", wav_bytes, "audio/wav")},
    )
    assert response.status_code == 422


@pytest.mark.integration
def test_transcribe_stream_rejects_non_int16(client: TestClient) -> None:
    """A WAV with a bit depth other than 16-bit must be rejected with 422 (streaming endpoint)."""
    wav_bytes = _make_wav(sampwidth=1)
    response = client.post(
        "/transcribe/stream",
        files={"audio": ("8bit.wav", wav_bytes, "audio/wav")},
    )
    assert response.status_code == 422
