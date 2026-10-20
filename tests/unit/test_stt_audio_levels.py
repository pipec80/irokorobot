"""Capture levels and the conversion to the audio contract (Plan 0069 Task 4).

Synthetic signals only. Audio contract: WAV · 16000 Hz · mono · int16.
"""

import numpy as np
import pytest

from scripts.stt_audio_levels import LevelReport, level_report, level_verdicts, to_contract

_RATE = 16_000
_FULL_SCALE = 32768.0


def _sine(rms_dbfs: float, seconds: float, rate: int = _RATE, hz: float = 440.0) -> np.ndarray:
    """A float sine whose RMS is *rms_dbfs* (peak 3 dB higher)."""
    t = np.arange(int(seconds * rate)) / rate
    amplitude = np.sqrt(2) * 10 ** (rms_dbfs / 20)
    return amplitude * np.sin(2 * np.pi * hz * t)


def _int16(signal: np.ndarray) -> np.ndarray:
    return np.round(signal * _FULL_SCALE).clip(-32768, 32767).astype(np.int16)


@pytest.mark.unit
def test_a_sine_reports_its_peak() -> None:
    report = level_report(_int16(_sine(-9.0103, 1.0)))  # peak -6.0 dBFS

    assert report.peak_dbfs == pytest.approx(-6.0, abs=0.1)
    assert report.snr_db == pytest.approx(0.0, abs=0.5)  # steady tone: speech equals floor
    assert report.clipped_fraction == 0.0


@pytest.mark.unit
def test_digital_silence_reports_nothing_instead_of_minus_infinity() -> None:
    report = level_report(np.zeros(_RATE, dtype=np.int16))

    assert report == LevelReport(
        peak_dbfs=None, speech_rms_dbfs=None, floor_dbfs=None, snr_db=None, clipped_fraction=0.0
    )


@pytest.mark.unit
def test_a_full_scale_square_wave_is_clipped() -> None:
    square = np.where(np.arange(_RATE) % 40 < 20, 32767, -32768).astype(np.int16)

    assert level_report(square).clipped_fraction >= 0.99
    assert level_verdicts(level_report(square))["clipping"] == "clipped"


@pytest.mark.unit
def test_speech_over_a_floor_reports_floor_and_snr() -> None:
    floor = _sine(-60.0, 4.0, hz=120.0)
    speech = _sine(-20.0, 1.0)
    signal = np.concatenate([floor[:16_000], speech, floor[16_000:48_000], floor[:16_000]])

    report = level_report(_int16(signal))

    assert report.floor_dbfs == pytest.approx(-60.0, abs=1.0)
    assert report.speech_rms_dbfs == pytest.approx(-20.0, abs=1.0)
    assert report.snr_db == pytest.approx(40.0, abs=1.0)


@pytest.mark.unit
def test_verdicts_follow_the_targets() -> None:
    good = LevelReport(
        peak_dbfs=-6.0, speech_rms_dbfs=-25.0, floor_dbfs=-60.0, snr_db=35.0, clipped_fraction=0.0
    )
    quiet = LevelReport(
        peak_dbfs=-30.0, speech_rms_dbfs=-45.0, floor_dbfs=-60.0, snr_db=15.0, clipped_fraction=0.0
    )
    hot = LevelReport(
        peak_dbfs=-0.5, speech_rms_dbfs=-12.0, floor_dbfs=-50.0, snr_db=38.0, clipped_fraction=0.0
    )

    assert level_verdicts(good) == {"peak": "ok", "speech": "ok", "floor": "ok", "clipping": "ok"}
    assert level_verdicts(quiet) == {
        "peak": "low",
        "speech": "low",
        "floor": "low",
        "clipping": "ok",
    }
    assert level_verdicts(hot)["peak"] == "high"
    assert level_verdicts(hot)["speech"] == "high"


@pytest.mark.unit
@pytest.mark.parametrize("source_rate", [48_000, 44_100])
def test_to_contract_downsamples_stereo_and_keeps_the_tone(source_rate: int) -> None:
    tone = _sine(-20.0, 1.0, rate=source_rate, hz=1000.0).astype(np.float32)
    stereo = np.stack([tone, tone], axis=1)

    out = to_contract(stereo, source_rate, channels=2)

    assert out.dtype == np.int16
    assert len(out) == _RATE
    middle = out[2000:-2000].astype(np.float64) / _FULL_SCALE
    rms_dbfs = 20 * np.log10(np.sqrt(np.mean(middle**2)))
    assert rms_dbfs == pytest.approx(-20.0, abs=0.5)


@pytest.mark.unit
def test_to_contract_rejects_a_mismatched_channel_count() -> None:
    with pytest.raises(ValueError, match="channels"):
        to_contract(np.zeros((480, 3), dtype=np.float32), 48_000, channels=2)
