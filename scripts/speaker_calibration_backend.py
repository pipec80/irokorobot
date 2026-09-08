"""Frozen SpeechBrain ECAPA speaker-embedding backend for Plan 0047 (Task 3).

This module is the only place the study loads a real model. It freezes the
backend, model, immutable revision, CPU device, offline-safe copy strategy and
PCM int16 -> float preprocessing exactly as the Plan 0047 "Frozen readiness
contract" (blocks 1-2, 5-6). ``_MODEL_SOURCE`` and ``_MODEL_REVISION`` are the
one sanctioned exception to the "no hardcoded model" rule: the whole point of
the study is a frozen, reproducible backend, so they are never routed through
``server.settings`` and never made configurable.

``run_cli`` in ``scripts.speaker_calibration`` reaches this module by a deferred
import, so ``validate`` / ``analyze`` / ``cleanup`` never import ``torch``.

Audio contract for every WAV this module touches: WAV, 16 000 Hz, mono, signed
int16. No cloud inference (ADR-0004). This study never enrols a production
voiceprint and never makes ``VOICE`` trusted identity evidence.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
import time
from typing import Any, Final
import wave

import numpy as np

from scripts.speaker_calibration import _checked_embedding, percentile
from scripts.speaker_calibration_corpus import validate_wav_bytes

logger = logging.getLogger(__name__)

# Frozen study identifiers (Plan 0047 block 1). Immutable, never configurable,
# never via server.settings. The revision is a public Hugging Face commit SHA.
_MODEL_SOURCE: Final = "speechbrain/spkrec-ecapa-voxceleb"
_MODEL_REVISION: Final = "0f99f2d0ebe89ac095bcc5903c4dd8f72b367286"  # pragma: allowlist secret
_MODEL_CACHE_DIR: Final = Path("project-history/calibration/speaker/model-cache")

_SAMPLE_RATE: Final = 16_000
_INT16_FULL_SCALE: Final = 32768.0
_LATENCY_WARMUP: Final = 3
_LATENCY_SAMPLES: Final = 30
_LATENCY_WAV_SECONDS: Final = 3


class SpeechBrainEcapaBackend:
    """Frozen ECAPA-TDNN speaker-embedding backend (SpeechBrain 1.1.1).

    Wraps one already-constructed ``EncoderClassifier`` and turns a validated
    WAV (16 000 Hz, mono, signed int16) into one finite 192-d embedding. Build
    the encoder with :func:`load_frozen_encoder`; this class never downloads.
    """

    def __init__(self, encoder: Any) -> None:  # noqa: ANN401 -- speechbrain has no stubs
        """Store the constructed ``EncoderClassifier`` (or a typed test fake)."""
        self._encoder = encoder

    @property
    def model_id(self) -> str:
        """Return the frozen model identifier and its pinned revision."""
        return f"{_MODEL_SOURCE}@{_MODEL_REVISION}"

    def embed_wav(self, wav_bytes: bytes) -> np.ndarray:
        """Embed WAV audio (16 000 Hz, mono, signed int16) into a 192-d vector.

        Args:
            wav_bytes: Raw WAV bytes — 16 000 Hz, mono, signed int16.

        Returns:
            A 1-D ``np.ndarray`` of exactly 192 finite floats.

        Raises:
            ValueError: If the bytes break the audio contract, or the model
                returns a non-finite, wrong-length or all-zero vector.
        """
        validate_wav_bytes(wav_bytes)
        wave_f32 = _pcm16_wav_to_float32(wav_bytes)
        return _encode_one(self._encoder, wave_f32)


def _pcm16_wav_to_float32(wav_bytes: bytes) -> np.ndarray:
    """Decode a contract WAV (16 000 Hz, mono, signed int16) to float32.

    Args:
        wav_bytes: Raw WAV bytes — 16 000 Hz, mono, signed int16. Assumed
            already validated by :func:`validate_wav_bytes`.

    Returns:
        A writable 1-D float32 array equal to ``samples / 32768.0`` in
        ``[-1.0, 1.0)``. No resample, no gain, no widening beyond float32.
    """
    with wave.open(io.BytesIO(wav_bytes), "rb") as handle:
        frames = handle.readframes(handle.getnframes())
    samples = np.frombuffer(frames, dtype=np.int16)
    return samples.astype(np.float32) / _INT16_FULL_SCALE


def _encode_one(encoder: Any, wave_f32: np.ndarray) -> np.ndarray:  # noqa: ANN401 -- no stubs
    """Run one frozen forward pass on a pre-decoded float32 waveform.

    Args:
        encoder: A constructed ``EncoderClassifier`` (or typed test fake).
        wave_f32: 1-D float32 samples in ``[-1.0, 1.0)`` at 16 000 Hz.

    Returns:
        A 1-D ``np.ndarray`` of exactly 192 finite floats.

    Raises:
        ValueError: If the model output is non-finite, wrong-length or all-zero.
    """
    import torch  # noqa: PLC0415 -- deferred so non-embed CLI actions never import torch

    tensor = torch.from_numpy(wave_f32).unsqueeze(0)  # (1, n_samples) float32 CPU
    out = encoder.encode_batch(wavs=tensor, wav_lens=None, normalize=False)
    vector = out.squeeze().detach().cpu().numpy()  # (1, 1, 192) -> (192,)
    return _checked_embedding(vector)


def load_frozen_encoder(*, allow_network: bool) -> Any:  # noqa: ANN401 -- speechbrain has no stubs
    """Construct the frozen ``EncoderClassifier`` on CPU at the pinned revision.

    Args:
        allow_network: ``False`` for the normal offline-after-cache path;
            ``True`` only for the one-time cache warm-up in ``model-contract``.

    Returns:
        A constructed ``EncoderClassifier`` bound to the CPU device.
    """
    from speechbrain.inference.speaker import (  # noqa: PLC0415 -- deferred heavy import
        EncoderClassifier,
    )
    from speechbrain.utils.fetching import (  # noqa: PLC0415 -- deferred heavy import
        FetchConfig,
        LocalStrategy,
    )

    _MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return EncoderClassifier.from_hparams(
        source=_MODEL_SOURCE,
        savedir=str(_MODEL_CACHE_DIR),
        run_opts={"device": "cpu"},
        local_strategy=LocalStrategy.COPY,  # SYMLINK breaks on Windows without Dev Mode
        fetch_config=FetchConfig(revision=_MODEL_REVISION, allow_network=allow_network),
    )


def _assert_resolved_revision() -> str:
    """Prove the pinned revision is the one actually cached, offline.

    Returns:
        The resolved snapshot path (contains ``/snapshots/<revision>/``).

    Raises:
        ValueError: If the cached ``hyperparams.yaml`` did not resolve under the
            pinned revision's snapshot directory.
    """
    from huggingface_hub import hf_hub_download  # noqa: PLC0415 -- deferred heavy import

    resolved = hf_hub_download(
        _MODEL_SOURCE, "hyperparams.yaml", revision=_MODEL_REVISION, local_files_only=True
    )
    marker = f"/snapshots/{_MODEL_REVISION}/"
    if marker not in Path(resolved).as_posix():
        raise ValueError(f"resolved revision path {resolved!r} is not under {marker!r}")
    return resolved


def _sine_wav_bytes(*, seconds: int, freq_hz: float = 220.0) -> bytes:
    """Generate a non-biometric sine tone as contract WAV bytes.

    Args:
        seconds: Tone length in seconds.
        freq_hz: Tone frequency — a plain sine wave, never a voice.

    Returns:
        WAV bytes — 16 000 Hz, mono, signed int16.
    """
    step = np.arange(_SAMPLE_RATE * seconds, dtype=np.float32) / _SAMPLE_RATE
    samples = (np.sin(2.0 * np.pi * freq_hz * step) * 16_000.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(_SAMPLE_RATE)
        handle.writeframes(samples.tobytes())
    return buf.getvalue()


def run_model_contract() -> int:
    """Warm the pinned-revision cache and prove the frozen contract holds.

    Downloads the pinned revision into the gitignored cache, asserts the
    resolved revision equals :data:`_MODEL_REVISION`, then embeds one generated
    non-biometric sine tone and logs its shape, dtype, dimension and finiteness.
    No microphone, no household audio, not timed.

    Returns:
        ``0`` on complete success, ``1`` otherwise.
    """
    logger.info("warming frozen model cache: %s @ %s", _MODEL_SOURCE, _MODEL_REVISION)
    load_frozen_encoder(allow_network=True)
    resolved = _assert_resolved_revision()
    logger.info("resolved revision OK under %s", resolved)
    encoder = _load_offline_or_note_limitation()
    vector = SpeechBrainEcapaBackend(encoder).embed_wav(
        _sine_wav_bytes(seconds=_LATENCY_WAV_SECONDS)
    )
    logger.info(
        "sine-tone embedding: shape=%s dtype=%s dim=%d all_finite=%s",
        vector.shape,
        vector.dtype,
        vector.shape[0],
        bool(np.all(np.isfinite(vector))),
    )
    return 0


def _load_offline_or_note_limitation() -> Any:  # noqa: ANN401 -- speechbrain has no stubs
    """Load the encoder offline; fall back to online with a recorded limitation.

    Returns:
        A constructed ``EncoderClassifier``.
    """
    try:
        return load_frozen_encoder(allow_network=False)
    except Exception:  # any offline-load fault is a recorded, non-fatal limitation (block 2)
        logger.warning(
            "offline-only load limitation: the pinned revision loads online but not with "
            "allow_network=False; the revision is still fully pinned (Plan 0047 block 2)"
        )
        return load_frozen_encoder(allow_network=True)


def run_latency_protocol() -> dict[str, float]:
    """Execute the frozen latency protocol once (Plan 0047 block 5).

    One already-loaded encoder; one in-process 3 s synthetic WAV decoded and
    validated outside the timed region; 3 discarded warm-ups; 30 sequential
    timed embeddings; p50/p95 by nearest-rank. No concurrent load, no download.

    Returns:
        Sanitized timings in milliseconds: ``p50_ms``, ``p95_ms``, ``min_ms``,
        ``max_ms`` and the sample count ``n``. No audio, no paths.
    """
    encoder = load_frozen_encoder(allow_network=False)
    wav_bytes = _sine_wav_bytes(seconds=_LATENCY_WAV_SECONDS)
    validate_wav_bytes(wav_bytes)  # outside the timed region
    wave_f32 = _pcm16_wav_to_float32(wav_bytes)  # outside the timed region
    for _ in range(_LATENCY_WARMUP):
        _encode_one(encoder, wave_f32)
    timings_ms: list[float] = []
    for _ in range(_LATENCY_SAMPLES):
        start = time.perf_counter()
        _encode_one(encoder, wave_f32)
        timings_ms.append((time.perf_counter() - start) * 1_000.0)
    return {
        "p50_ms": percentile(timings_ms, 0.5),
        "p95_ms": percentile(timings_ms, 0.95),
        "min_ms": min(timings_ms),
        "max_ms": max(timings_ms),
        "n": float(_LATENCY_SAMPLES),
    }
