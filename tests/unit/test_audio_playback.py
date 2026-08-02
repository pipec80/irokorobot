"""Unit tests for robot.audio_playback — sounddevice is mocked."""

import io
import wave

import numpy as np
import pytest
from robot.exceptions import AudioPlaybackError

from robot import audio_playback


def _make_wav(sample_rate: int, n_frames: int) -> bytes:
    """Build a mono int16 WAV of zeros at the given sample rate."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(np.zeros(n_frames, dtype=np.int16).tobytes())
    return buf.getvalue()


@pytest.mark.unit
async def test_play_wav_uses_header_sample_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Playback must honor the WAV header rate, never assume 16 kHz."""
    played: dict[str, object] = {}

    def _fake_play(audio: np.ndarray, samplerate: int) -> None:
        played["rate"] = samplerate
        played["frames"] = len(audio)

    monkeypatch.setattr(audio_playback.sd, "play", _fake_play)
    monkeypatch.setattr(audio_playback.sd, "wait", lambda: None)

    await audio_playback.play_wav(_make_wav(sample_rate=22_050, n_frames=2205))

    assert played["rate"] == 22_050
    assert played["frames"] == 2205


@pytest.mark.unit
async def test_play_wav_empty_bytes_raises_value_error() -> None:
    with pytest.raises(ValueError, match="empty"):
        await audio_playback.play_wav(b"")


@pytest.mark.unit
async def test_play_wav_wraps_device_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any sounddevice failure must surface as AudioPlaybackError."""

    def _broken_play(audio: np.ndarray, samplerate: int) -> None:
        raise RuntimeError("no output device")

    monkeypatch.setattr(audio_playback.sd, "play", _broken_play)
    monkeypatch.setattr(audio_playback.sd, "wait", lambda: None)

    with pytest.raises(AudioPlaybackError):
        await audio_playback.play_wav(_make_wav(sample_rate=16_000, n_frames=160))
