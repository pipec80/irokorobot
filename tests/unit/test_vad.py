"""Unit tests for robot.vad: RMS engine, Silero degradation, and the factory."""

from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest
from robot.settings import settings

from robot import vad


def _silero_with_outputs(
    monkeypatch: pytest.MonkeyPatch,
    outputs: list[object],
) -> vad.SileroVAD:
    """Build a Silero test double with controlled ONNX outputs."""
    engine = vad.SileroVAD.__new__(vad.SileroVAD)
    session = Mock()
    session.run.return_value = outputs
    monkeypatch.setattr(engine, "_session", session, raising=False)
    monkeypatch.setattr(engine, "_threshold", 0.5, raising=False)
    monkeypatch.setattr(
        engine,
        "_state",
        np.zeros((2, 1, 128), dtype=np.float32),
        raising=False,
    )
    monkeypatch.setattr(
        engine,
        "_context",
        np.zeros((1, 64), dtype=np.float32),
        raising=False,
    )
    return engine


@pytest.mark.unit
def test_rms_vad_detects_loud_chunk() -> None:
    loud = np.full(512, 30_000, dtype=np.int16)
    assert vad.RmsVAD(threshold_rms=100).detect(loud) is True


@pytest.mark.unit
def test_rms_vad_ignores_silence() -> None:
    silent = np.zeros(512, dtype=np.int16)
    assert vad.RmsVAD(threshold_rms=100).detect(silent) is False


@pytest.mark.unit
def test_rms_vad_uses_settings_threshold_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "vad_silence_threshold_rms", 5)
    quiet = np.full(512, 10, dtype=np.int16)
    assert vad.RmsVAD().detect(quiet) is True


@pytest.mark.unit
def test_create_vad_rms_engine_returns_rms_vad() -> None:
    assert isinstance(vad.create_vad("rms"), vad.RmsVAD)


@pytest.mark.unit
def test_create_vad_silero_degrades_to_rms_when_model_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing/broken model must degrade to RMS, never raise (roadmap R1 requirement)."""
    monkeypatch.setattr(settings, "vad_model_path", Path("does/not/exist.onnx"))

    engine = vad.create_vad("silero")

    assert isinstance(engine, vad.RmsVAD)


@pytest.mark.unit
def test_silero_vad_rejects_wrong_chunk_size() -> None:
    """SileroVAD requires exactly 512-sample chunks — the guard runs before touching state."""
    engine = vad.SileroVAD.__new__(vad.SileroVAD)  # bypass __init__ (would load the ONNX model)

    with pytest.raises(ValueError, match="512-sample chunks"):
        engine.detect(np.zeros(256, dtype=np.int16))


@pytest.mark.unit
def test_silero_vad_accepts_typed_onnx_outputs(monkeypatch: pytest.MonkeyPatch) -> None:
    """NumPy probability and state outputs should process a 512-sample int16 chunk."""
    state = np.zeros((2, 1, 128), dtype=np.float32)
    engine = _silero_with_outputs(
        monkeypatch,
        [np.array([0.75], dtype=np.float32), state],
    )

    detected = engine.detect(np.zeros(512, dtype=np.int16))

    assert detected is True
    assert engine._state is state


@pytest.mark.unit
def test_silero_vad_rejects_unexpected_onnx_output_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-NumPy ONNX outputs should fail before scalar access."""
    state = np.zeros((2, 1, 128), dtype=np.float32)
    engine = _silero_with_outputs(monkeypatch, [["not-an-array"], state])

    with pytest.raises(TypeError, match="must be NumPy arrays"):
        engine.detect(np.zeros(512, dtype=np.int16))
