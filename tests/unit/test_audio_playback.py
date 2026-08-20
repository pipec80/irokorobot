"""Unit tests for robot.audio_playback — sounddevice is mocked."""

from collections.abc import AsyncIterator
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


async def _chunks(*items: bytes) -> AsyncIterator[bytes]:
    for item in items:
        yield item


@pytest.mark.unit
async def test_play_wav_stream_reports_chunk_start_before_each_play(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """on_chunk_start must fire immediately before each play_wav, one-based."""
    calls: list[str] = []

    async def _fake_play_wav(_wav_bytes: bytes) -> None:
        calls.append("play")

    monkeypatch.setattr(audio_playback, "play_wav", _fake_play_wav)
    seen: list[int] = []

    def _on_chunk_start(index: int) -> None:
        seen.append(index)
        calls.append(f"start-{index}")

    await audio_playback.play_wav_stream(_chunks(b"a", b"b"), on_chunk_start=_on_chunk_start)

    assert seen == [1, 2]
    assert calls == ["start-1", "play", "start-2", "play"]


@pytest.mark.unit
async def test_play_wav_stream_without_callback_still_plays_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """on_chunk_start is optional — omitting it must not break playback."""
    play_mock_calls: list[bytes] = []

    async def _fake_play_wav(wav_bytes: bytes) -> None:
        play_mock_calls.append(wav_bytes)

    monkeypatch.setattr(audio_playback, "play_wav", _fake_play_wav)

    await audio_playback.play_wav_stream(_chunks(b"a", b"b"))

    assert play_mock_calls == [b"a", b"b"]
