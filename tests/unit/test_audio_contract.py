"""Unit tests for the audio contract: WAV 16kHz mono int16.

Covers pure-function helpers that produce or transform audio bytes:
- robot.audio_capture._encode_wav
- robot.vad._compute_rms
- server.tts._append_silence
"""

import io
import wave

import numpy as np
import pytest
from robot.audio_capture import AudioConfig, _encode_wav
from robot.vad import _compute_rms
from server.tts import _append_silence, _resample_to_contract


def _read_wav(data: bytes) -> tuple[int, int, int, int]:
    """Return (sample_rate, channels, sampwidth, nframes) from WAV bytes."""
    with wave.open(io.BytesIO(data), "rb") as wf:
        return wf.getframerate(), wf.getnchannels(), wf.getsampwidth(), wf.getnframes()


@pytest.mark.unit
def test_encode_wav_produces_correct_format() -> None:
    """Encoded WAV must be 16kHz mono int16, per the audio contract."""
    config = AudioConfig()
    frames = [np.zeros(1600, dtype=np.int16) for _ in range(3)]
    wav_bytes = _encode_wav(frames, config)

    rate, channels, sampwidth, nframes = _read_wav(wav_bytes)
    assert rate == 16_000
    assert channels == 1
    assert sampwidth == 2  # int16 = 2 bytes
    assert nframes == 4800  # 3 chunks x 1600 samples


@pytest.mark.unit
def test_encode_wav_with_single_frame() -> None:
    config = AudioConfig()
    frames = [np.arange(100, dtype=np.int16)]
    wav_bytes = _encode_wav(frames, config)

    rate, channels, _, nframes = _read_wav(wav_bytes)
    assert rate == 16_000
    assert channels == 1
    assert nframes == 100


@pytest.mark.unit
def test_audio_config_defaults_match_contract() -> None:
    config = AudioConfig()
    assert config.sample_rate == 16_000
    assert config.channels == 1
    assert config.dtype == "int16"


@pytest.mark.unit
def test_compute_rms_of_silence_is_zero() -> None:
    silence = np.zeros(1600, dtype=np.int16)
    assert _compute_rms(silence) == 0.0


@pytest.mark.unit
def test_compute_rms_of_constant_signal() -> None:
    """RMS of a constant signal should equal the absolute value of the constant."""
    const_signal = np.full(1000, 500, dtype=np.int16)
    assert _compute_rms(const_signal) == pytest.approx(500.0)


@pytest.mark.unit
def test_compute_rms_is_positive_for_noise() -> None:
    rng = np.random.default_rng(seed=42)
    noise = rng.integers(-1000, 1000, size=1600, dtype=np.int16)
    assert _compute_rms(noise) > 0


@pytest.mark.unit
def test_append_silence_preserves_format_and_adds_frames() -> None:
    """Appending silence must keep 16kHz mono int16 and extend nframes exactly."""
    # Build a minimal valid WAV of 1000 frames
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16_000)
        wf.writeframes(np.zeros(1000, dtype=np.int16).tobytes())
    wav_in = buf.getvalue()

    silence_frames = 6400  # 400 ms at 16kHz
    wav_out = _append_silence(wav_in, silence_frames)

    rate, channels, sampwidth, nframes = _read_wav(wav_out)
    assert rate == 16_000
    assert channels == 1
    assert sampwidth == 2
    assert nframes == 1000 + silence_frames


def _make_wav(sample_rate: int, seconds: float) -> bytes:
    """Build a mono int16 WAV with a 440 Hz tone at the given sample rate."""
    t = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)
    samples = (np.sin(2 * np.pi * 440 * t) * 10_000).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())
    return buf.getvalue()


@pytest.mark.unit
def test_resample_to_contract_converts_22050_to_16000() -> None:
    """Piper-native 22 050 Hz output must be resampled to the 16 kHz contract."""
    wav_22k = _make_wav(sample_rate=22_050, seconds=0.5)

    result = _resample_to_contract(wav_22k)

    rate, channels, sampwidth, nframes = _read_wav(result)
    assert rate == 16_000
    assert channels == 1
    assert sampwidth == 2
    # Duration must be preserved (±5 ms tolerance)
    assert abs(nframes / rate - 0.5) < 0.005


@pytest.mark.unit
def test_resample_to_contract_passthrough_at_16000() -> None:
    """A WAV already at 16 kHz must be returned byte-identical."""
    wav_16k = _make_wav(sample_rate=16_000, seconds=0.25)

    assert _resample_to_contract(wav_16k) == wav_16k


@pytest.mark.unit
def test_append_silence_tail_samples_are_zero() -> None:
    """The appended tail must be exact silence (all zero samples)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16_000)
        wf.writeframes(np.full(500, 1234, dtype=np.int16).tobytes())
    wav_in = buf.getvalue()

    silence_frames = 100
    wav_out = _append_silence(wav_in, silence_frames)

    with wave.open(io.BytesIO(wav_out), "rb") as wf:
        raw = wf.readframes(wf.getnframes())
    samples = np.frombuffer(raw, dtype=np.int16)
    assert (samples[-silence_frames:] == 0).all()
    assert (samples[:500] == 1234).all()
