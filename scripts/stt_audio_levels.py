"""Capture levels and the conversion to the audio contract (Plan 0069 Task 4).

Pure functions over sample arrays: no microphone, no file. The targets are the ones
Plan 0069 records (an engineering proposal, not a standard): speech peaks from -12 to
-3 dBFS, speech RMS from -30 to -20 dBFS, no clipped sample, and a noise floor at
least 30 dB under the speech.

Audio contract of every array returned: 16 000 Hz, mono, int16.
"""

from __future__ import annotations

from dataclasses import dataclass
import io
import math
import wave

import numpy as np
import soxr

CONTRACT_RATE = 16_000
_FULL_SCALE = 32768.0
_CLIP_LEVEL = 32767
_FRAME_S = 0.02
_SPEECH_PERCENTILE = 90
_FLOOR_PERCENTILE = 10
_PEAK_RANGE = (-12.0, -3.0)
_SPEECH_RANGE = (-30.0, -20.0)
_MIN_SNR_DB = 30.0


@dataclass(frozen=True)
class LevelReport:
    """Levels of one take, in dBFS; ``None`` where the signal is digital silence."""

    peak_dbfs: float | None
    speech_rms_dbfs: float | None
    floor_dbfs: float | None
    snr_db: float | None
    clipped_fraction: float


def _dbfs(value: float) -> float | None:
    return 20 * math.log10(value) if value > 0 else None


def level_report(samples: np.ndarray, sample_rate: int = CONTRACT_RATE) -> LevelReport:
    """Measure the peak, the speech level, the floor and clipping of int16 samples.

    Args:
        samples: Int16 mono samples (16 kHz in the contract; any rate works).
        sample_rate: Their sample rate.

    Returns:
        The report: speech is the 90th percentile of the 20 ms frame RMS, the floor the
        10th; the SNR is their difference.
    """
    signal = samples.astype(np.float64) / _FULL_SCALE
    peak = float(np.max(np.abs(signal))) if signal.size else 0.0
    frame = max(1, int(sample_rate * _FRAME_S))
    usable = signal.size - signal.size % frame
    framed = signal[:usable].reshape(-1, frame) if usable else signal.reshape(1, -1)
    rms = np.sqrt(np.mean(framed**2, axis=1)) if framed.size else np.zeros(1)
    speech = _dbfs(float(np.percentile(rms, _SPEECH_PERCENTILE)))
    floor = _dbfs(float(np.percentile(rms, _FLOOR_PERCENTILE)))
    clipped = (
        float(np.mean(np.abs(samples.astype(np.int32)) >= _CLIP_LEVEL)) if samples.size else 0.0
    )
    return LevelReport(
        peak_dbfs=_dbfs(peak),
        speech_rms_dbfs=speech,
        floor_dbfs=floor,
        snr_db=speech - floor if speech is not None and floor is not None else None,
        clipped_fraction=clipped,
    )


def _in_range(value: float | None, low: float, high: float) -> str:
    if value is None or value < low:
        return "low"
    return "high" if value > high else "ok"


def level_verdicts(report: LevelReport) -> dict[str, str]:
    """Judge a report against the targets.

    Args:
        report: A take's levels.

    Returns:
        ``peak``, ``speech`` and ``floor`` as ``ok``/``low``/``high`` (the floor is ``low``
        when it sits less than 30 dB under the speech) and ``clipping`` as ``ok`` or
        ``clipped``.
    """
    snr = report.snr_db
    return {
        "peak": _in_range(report.peak_dbfs, *_PEAK_RANGE),
        "speech": _in_range(report.speech_rms_dbfs, *_SPEECH_RANGE),
        "floor": "ok" if snr is not None and snr >= _MIN_SNR_DB else "low",
        "clipping": "clipped" if report.clipped_fraction > 0 else "ok",
    }


def to_contract(samples: np.ndarray, source_rate: int, channels: int) -> np.ndarray:
    """Turn a native capture into the audio contract.

    Args:
        samples: Float (-1..1) or int16 samples, shape ``(n,)`` or ``(n, channels)``.
        source_rate: The rate the device delivered (for example 44 100 or 48 000).
        channels: The channel count the stream opened with.

    Returns:
        Int16 samples, 16 000 Hz, mono: channels averaged, then resampled with ``soxr``.

    Raises:
        ValueError: If the array does not have *channels* channels.
    """
    shaped = samples.reshape(-1, 1) if samples.ndim == 1 else samples
    if shaped.shape[1] != channels:
        raise ValueError(f"expected {channels} channels, got {shaped.shape[1]}")
    floats = shaped.astype(np.float64)
    if np.issubdtype(samples.dtype, np.integer):
        floats /= _FULL_SCALE
    mono = floats.mean(axis=1).astype(np.float32)
    if source_rate != CONTRACT_RATE:
        mono = soxr.resample(mono, source_rate, CONTRACT_RATE, quality="HQ")
    return np.round(np.clip(mono, -1.0, 1.0) * 32767).astype(np.int16)


def wav_bytes(samples: np.ndarray) -> bytes:
    """Encode int16 samples as WAV bytes — 16 000 Hz, mono, int16.

    Args:
        samples: Int16 mono samples at 16 kHz.

    Returns:
        The WAV file's bytes in the audio contract's format.
    """
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(CONTRACT_RATE)
        handle.writeframes(samples.astype(np.int16).tobytes())
    return buffer.getvalue()
