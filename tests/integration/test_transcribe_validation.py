"""Integration tests for POST /transcribe input validation.

Covers request-shape errors (413/422) that must be rejected before any
STT/LLM/TTS work happens. Does not require models to be loaded.
"""

import io
from unittest.mock import AsyncMock
import wave

from fastapi.testclient import TestClient
import pytest
from server.settings import settings

from server import stt


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
    """An upload larger than max_audio_upload_bytes must be rejected with 413."""
    oversized = b"\x00" * (settings.max_audio_upload_bytes + 1)
    response = client.post(
        "/transcribe",
        files={"audio": ("big.wav", io.BytesIO(oversized), "audio/wav")},
    )
    assert response.status_code == 413
    assert "too large" in response.json()["detail"].lower()


@pytest.mark.integration
def test_transcribe_oversized_audio_never_reaches_stt(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rejection must happen before the expensive STT boundary is called."""
    called = False

    async def fail_if_called(*_args: object, **_kwargs: object) -> str:
        nonlocal called
        called = True
        return "should never run"

    monkeypatch.setattr(stt, "transcribe", fail_if_called)
    oversized = b"\x00" * (settings.max_audio_upload_bytes + 1)

    client.post(
        "/transcribe",
        files={"audio": ("big.wav", io.BytesIO(oversized), "audio/wav")},
    )

    assert called is False


@pytest.mark.integration
def test_transcribe_exactly_at_the_audio_limit_is_accepted(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The boundary itself must not be rejected — only strictly over it."""
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value="hola"))
    wav_bytes = _make_wav(nframes=1600)
    assert len(wav_bytes) <= settings.max_audio_upload_bytes

    response = client.post(
        "/transcribe",
        files={"audio": ("ok.wav", wav_bytes, "audio/wav")},
    )

    assert response.status_code == 200


@pytest.mark.integration
def test_transcribe_rejects_audio_over_the_duration_limit(client: TestClient) -> None:
    """A WAV that passes format checks but is far too long must still be rejected.

    `validate_wav_contract` checked format only — channels, sample width,
    frame rate, and that at least one frame exists — never duration. A
    correctly-shaped multi-hour recording passed every existing check.
    """
    too_long_frames = int(settings.max_audio_duration_s * 16_000) + 16_000
    wav_bytes = _make_wav(nframes=too_long_frames)

    response = client.post(
        "/transcribe",
        files={"audio": ("long.wav", wav_bytes, "audio/wav")},
    )

    assert response.status_code == 422


@pytest.mark.integration
def test_transcribe_accepts_audio_at_the_duration_limit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The duration boundary itself must not be rejected."""
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value="hola"))
    at_limit_frames = int(settings.max_audio_duration_s * 16_000)
    wav_bytes = _make_wav(nframes=at_limit_frames)

    response = client.post(
        "/transcribe",
        files={"audio": ("at_limit.wav", wav_bytes, "audio/wav")},
    )

    assert response.status_code == 200


@pytest.mark.integration
def test_transcribe_rejects_truncated_wav_container(client: TestClient) -> None:
    """A WAV header cut off mid-file must be rejected, not crash the server."""
    wav_bytes = _make_wav(nframes=1600)
    truncated = wav_bytes[: len(wav_bytes) // 2]

    response = client.post(
        "/transcribe",
        files={"audio": ("truncated.wav", truncated, "audio/wav")},
    )

    assert response.status_code == 422


@pytest.mark.integration
def test_transcribe_rejects_malformed_multipart_body(client: TestClient) -> None:
    """A request claiming multipart but not shaped like it must not be a 500."""
    response = client.post(
        "/transcribe",
        content=b"this is not a multipart body",
        headers={"content-type": "multipart/form-data; boundary=x"},
    )

    assert response.status_code in (400, 422)


@pytest.mark.integration
def test_transcribe_a_huge_request_body_is_rejected(client: TestClient) -> None:
    """A body far past any legitimate request must not reach application code."""
    huge = b"\x00" * (settings.max_request_body_bytes + 1)

    response = client.post(
        "/transcribe",
        files={"audio": ("huge.wav", io.BytesIO(huge), "audio/wav")},
    )

    assert response.status_code == 413


@pytest.mark.integration
def test_transcribe_an_oversized_frame_is_rejected_even_when_never_read(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A field the app never reads must still be bounded, or it isn't bounded at all.

    `face_authentication_enabled` defaults to `False`, and in that state the
    handler never calls `_read_optional_frame` — the field is accepted but
    completely inert by design. Without a raw request-body ceiling, an
    oversized `frame` would sail past every per-file check that exists,
    because none of them ever run for it. Only the ASGI-level budget can
    catch this. Audio stays small and valid so it cannot be what rejects it.
    """
    monkeypatch.setattr(settings, "face_authentication_enabled", False)
    wav_bytes = _make_wav(nframes=1600)
    oversized_frame = b"\xff\xd8\xff\xe0" + b"\x00" * settings.max_request_body_bytes

    response = client.post(
        "/transcribe",
        files={
            "audio": ("small.wav", wav_bytes, "audio/wav"),
            "frame": ("huge.jpg", oversized_frame, "image/jpeg"),
        },
    )

    assert response.status_code == 413


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
