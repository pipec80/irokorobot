"""Text-to-speech using Piper TTS.

Audio contract: WAV · 16000 Hz · mono · int16.
"""

import base64
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import io
import logging
import struct
import time
import wave

import numpy as np
from piper import PiperVoice, SynthesisConfig
import soxr

from server.exceptions import TTSError
from server.request_context import run_in_executor_with_context
from server.settings import settings

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=1)
_voice: PiperVoice | None = None
_TAIL_SILENCE_MS = 400
_TARGET_SAMPLE_RATE = 16_000
_INT16_SCALE = 32768.0


def _get_voice() -> PiperVoice:
    """Return the singleton PiperVoice, loading it on first call."""
    global _voice  # noqa: PLW0603
    if _voice is None:
        model_path = settings.models_dir / "piper" / f"{settings.piper_voice}.onnx"
        logger.info("Loading Piper voice: %s (cuda=%s)", model_path, settings.piper_use_cuda)
        _voice = PiperVoice.load(str(model_path), use_cuda=settings.piper_use_cuda)
    return _voice


def _append_silence(wav_bytes: bytes, frames: int) -> bytes:
    """Return wav_bytes with `frames` zero-value samples appended.

    Args:
        wav_bytes: WAV at 16kHz mono int16.
        frames: Number of silent int16 samples to append.

    Returns:
        WAV bytes with silence tail — same format: 16kHz mono int16.
    """
    buf = io.BytesIO(wav_bytes)
    with wave.open(buf, "rb") as src:
        params = src.getparams()
        audio_data = src.readframes(src.getnframes())
    silence = struct.pack(f"<{frames}h", *([0] * frames))
    out = io.BytesIO()
    with wave.open(out, "wb") as dst:
        dst.setparams(params)
        dst.writeframes(audio_data + silence)
    return out.getvalue()


def _resample_to_contract(wav_bytes: bytes) -> bytes:
    """Resample a mono int16 WAV to the 16 kHz audio contract if needed.

    Piper voices emit at model-native rates (e.g. 22 050 Hz for medium
    quality); the API contract promises 16 kHz, so the output is resampled
    here with soxr (high-quality bandlimited resampler).

    Args:
        wav_bytes: WAV at any sample rate — mono int16.

    Returns:
        WAV bytes at 16 kHz mono int16. Unchanged if already 16 kHz.
    """
    with wave.open(io.BytesIO(wav_bytes), "rb") as src:
        source_rate = src.getframerate()
        frames = src.readframes(src.getnframes())
    if source_rate == _TARGET_SAMPLE_RATE:
        return wav_bytes

    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / _INT16_SCALE
    resampled = soxr.resample(audio, source_rate, _TARGET_SAMPLE_RATE)
    pcm = np.clip(resampled * _INT16_SCALE, -_INT16_SCALE, _INT16_SCALE - 1).astype(np.int16)

    out = io.BytesIO()
    with wave.open(out, "wb") as dst:
        dst.setnchannels(1)
        dst.setsampwidth(2)  # int16 = 2 bytes
        dst.setframerate(_TARGET_SAMPLE_RATE)
        dst.writeframes(pcm.tobytes())
    logger.debug("Resampled TTS output: %d Hz -> %d Hz", source_rate, _TARGET_SAMPLE_RATE)
    return out.getvalue()


def _synthesize_sync(text: str) -> tuple[bytes, int]:
    """Run Piper TTS synchronously (blocking).

    Args:
        text: Text to synthesize.

    Returns:
        Tuple of (wav_bytes, duration_ms). WAV at 16kHz mono int16.

    Raises:
        TTSError: If Piper synthesis fails.
        ValueError: If text is empty.
    """
    if not text:
        raise ValueError("Text is empty")
    try:
        voice = _get_voice()
        config = SynthesisConfig(
            length_scale=1.0 / settings.piper_speed,
            noise_scale=settings.piper_noise_scale,
            noise_w_scale=settings.piper_noise_w_scale,
        )
        start = time.monotonic()
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            voice.synthesize_wav(text, wf, syn_config=config)
        duration_ms = int((time.monotonic() - start) * 1000)
        # Honor the audio contract: Piper emits at model-native rates, the API
        # promises 16 kHz — resample before anything else touches the bytes.
        wav_bytes = _resample_to_contract(buf.getvalue())
        # Piper clips the final phoneme — append silence so playback completes cleanly.
        silence_frames = int(_TARGET_SAMPLE_RATE * _TAIL_SILENCE_MS / 1000)
        wav_with_tail = _append_silence(wav_bytes, silence_frames)
        return wav_with_tail, duration_ms
    except Exception as exc:
        raise TTSError("Piper synthesis failed") from exc


def preload() -> None:
    """Load Piper voice model into memory.

    Call at application startup to avoid cold-start latency on the first request.
    """
    _get_voice()


def is_loaded() -> bool:
    """Return whether the Piper voice is currently loaded (Plan 0040).

    Side-effect-free — never triggers a load. Used by `GET /ready` to
    report readiness without paying for a real model load in that probe.
    """
    return _voice is not None


async def synthesize(text: str) -> tuple[str, int]:
    """Synthesize text to base64-encoded WAV audio.

    Args:
        text: Text to synthesize.

    Returns:
        Tuple of (audio_base64, duration_ms). WAV at 16kHz mono int16.

    Raises:
        TTSError: If Piper synthesis fails.
        ValueError: If text is empty.
    """
    wav_bytes, duration_ms = await run_in_executor_with_context(
        _executor, partial(_synthesize_sync, text)
    )
    audio_base64 = base64.b64encode(wav_bytes).decode("ascii")
    return audio_base64, duration_ms
