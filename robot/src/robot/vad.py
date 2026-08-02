"""Voice activity detection engines: Silero VAD (neural) and RMS (fallback).

Audio contract: int16 PCM chunks at 16000 Hz, mono.
"""

import logging
from pathlib import Path
from typing import Protocol

import numpy as np

from robot.settings import settings

logger = logging.getLogger(__name__)

_SAMPLE_RATE = 16_000
_SILERO_CHUNK_SAMPLES = 512  # 32 ms at 16kHz — fixed input size required by the model
_SILERO_CONTEXT_SAMPLES = 64  # trailing samples the model prepends to the next chunk
_SILERO_STATE_SHAPE = (2, 1, 128)  # LSTM-style recurrent state carried between calls
_SILERO_OUTPUT_COUNT = 2  # speech probability and recurrent state
_DEFAULT_SPEECH_PROBABILITY_THRESHOLD = 0.5  # Silero's documented default cutoff


class VoiceActivityDetector(Protocol):
    """Common interface for onset/voice detection engines."""

    def detect(self, chunk: np.ndarray) -> bool:
        """Return True if the chunk contains speech.

        Args:
            chunk: Flat int16 PCM samples, mono, 16000 Hz.

        Returns:
            True if the engine judges the chunk to contain speech.
        """
        ...


def _compute_rms(chunk: np.ndarray) -> float:
    """Compute root mean square energy of an audio chunk."""
    return float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))


class RmsVAD:
    """Energy-threshold VAD — the pre-R1 engine, kept as a degradation fallback."""

    def __init__(self, threshold_rms: float | None = None) -> None:
        """Initialize with an RMS threshold.

        Args:
            threshold_rms: Onset threshold. Defaults to
                ``settings.vad_silence_threshold_rms``.
        """
        self._threshold = (
            threshold_rms if threshold_rms is not None else settings.vad_silence_threshold_rms
        )

    def detect(self, chunk: np.ndarray) -> bool:
        """Return True if chunk energy exceeds the configured threshold."""
        return _compute_rms(chunk) > self._threshold


class SileroVAD:
    """Neural VAD using the Silero v5 ONNX model (~2 MB, MIT license).

    Keeps recurrent state and a small context window between calls, so
    chunks must arrive in order from a single utterance capture session.
    """

    def __init__(
        self, model_path: Path, threshold: float = _DEFAULT_SPEECH_PROBABILITY_THRESHOLD
    ) -> None:
        """Load the ONNX model and reset recurrent state.

        Args:
            model_path: Path to the local silero_vad.onnx file (see
                ``scripts/fetch_silero_vad_model.py``).
            threshold: Speech probability cutoff, 0-1.

        Raises:
            Exception: If onnxruntime is missing or the model fails to load.
                Callers (``create_vad``) must treat this as a degrade signal.
        """
        import onnxruntime  # noqa: PLC0415 — heavy import, paid only when Silero is selected

        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self._session = onnxruntime.InferenceSession(
            str(model_path), sess_options=opts, providers=["CPUExecutionProvider"]
        )
        self._threshold = threshold
        self._state = np.zeros(_SILERO_STATE_SHAPE, dtype=np.float32)
        self._context = np.zeros((1, _SILERO_CONTEXT_SAMPLES), dtype=np.float32)

    def detect(self, chunk: np.ndarray) -> bool:
        """Return True if the model's speech probability exceeds the threshold."""
        if chunk.shape[-1] != _SILERO_CHUNK_SAMPLES:
            raise ValueError(
                f"SileroVAD requires {_SILERO_CHUNK_SAMPLES}-sample chunks, got {chunk.shape[-1]}"
            )
        samples = chunk.astype(np.float32).reshape(1, -1) / 32768.0
        model_input = np.concatenate([self._context, samples], axis=1)
        outputs = self._session.run(
            None,
            {
                "input": model_input,
                "state": self._state,
                "sr": np.array(_SAMPLE_RATE, dtype=np.int64),
            },
        )
        if len(outputs) < _SILERO_OUTPUT_COUNT:
            raise RuntimeError("Silero VAD returned fewer than two outputs")
        probability, state = outputs[:_SILERO_OUTPUT_COUNT]
        if not isinstance(probability, np.ndarray) or not isinstance(state, np.ndarray):
            raise TypeError("Silero VAD outputs must be NumPy arrays")
        self._state = state
        self._context = model_input[:, -_SILERO_CONTEXT_SAMPLES:]
        return float(probability.item()) > self._threshold


def create_vad(engine: str) -> VoiceActivityDetector:
    """Build the configured VAD engine, degrading to RMS on failure.

    Args:
        engine: "silero" or "rms" (from ``settings.vad_engine``).

    Returns:
        A ready-to-use VAD engine. Silero load failures (missing dependency
        or model file) degrade to RmsVAD with a warning — never raises.
    """
    if engine != "silero":
        return RmsVAD()
    try:
        return SileroVAD(Path(settings.vad_model_path))
    except Exception as exc:
        logger.warning("Silero VAD unavailable (%s) — falling back to RMS", exc)
        return RmsVAD()
