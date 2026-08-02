"""Microphone audio capture with pluggable VAD (Silero neural or RMS fallback).

Audio contract: WAV · 16000 Hz · mono · int16.
"""

import asyncio
from collections import deque
from dataclasses import dataclass
import io
import logging
import wave

import numpy as np
import sounddevice as sd

from robot.exceptions import AudioCaptureError
from robot.settings import settings
from robot.vad import VoiceActivityDetector, create_vad

logger = logging.getLogger(__name__)

_SAMPLE_RATE = 16_000
_CHANNELS = 1
_DTYPE = "int16"
_CHUNK_FRAMES = 512  # 32 ms at 16kHz — required chunk size for SileroVAD
_CHUNK_DURATION_S = _CHUNK_FRAMES / _SAMPLE_RATE


@dataclass(frozen=True)
class AudioConfig:
    """Immutable audio format specification."""

    sample_rate: int = _SAMPLE_RATE
    channels: int = _CHANNELS
    dtype: str = _DTYPE


def _encode_wav(frames: list[np.ndarray], config: AudioConfig) -> bytes:
    """Encode PCM frames to WAV bytes.

    Args:
        frames: List of int16 numpy arrays.
        config: Audio format specification.

    Returns:
        WAV bytes at 16kHz mono int16.
    """
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(config.channels)
        wf.setsampwidth(2)  # int16 = 2 bytes
        wf.setframerate(config.sample_rate)
        wf.writeframes(np.concatenate(frames).tobytes())
    return buf.getvalue()


def _compute_chunk_budget(max_wait_s: float) -> tuple[int, int, int]:
    """Convert ms/s settings into chunk counts at the 32 ms chunk cadence.

    Returns:
        (silence_close_chunks, preroll_chunks, max_wait_chunks).
    """
    silence_close_chunks = max(1, round(settings.vad_silence_ms / 1000 / _CHUNK_DURATION_S))
    preroll_chunks = max(0, round(settings.vad_preroll_ms / 1000 / _CHUNK_DURATION_S))
    max_wait_chunks = max(1, round(max_wait_s / _CHUNK_DURATION_S))
    return silence_close_chunks, preroll_chunks, max_wait_chunks


async def _capture_loop(
    stream: sd.InputStream,
    vad: VoiceActivityDetector,
    silence_close_chunks: int,
    preroll_chunks: int,
    max_wait_chunks: int,
) -> list[np.ndarray]:
    """Read chunks until an utterance closes, or return [] on onset timeout."""
    preroll: deque[np.ndarray] = deque(maxlen=preroll_chunks)
    frames: list[np.ndarray] = []
    silence_count = 0
    speaking = False
    waited_chunks = 0

    while True:
        chunk, _ = stream.read(_CHUNK_FRAMES)
        if vad.detect(chunk.reshape(-1)):
            if not speaking:
                logger.debug("Speech onset detected")
                frames.extend(preroll)
            speaking = True
            silence_count = 0
            frames.append(chunk.copy())
        elif speaking:
            frames.append(chunk.copy())
            silence_count += 1
            if silence_count >= silence_close_chunks:
                logger.debug("Silence detected — utterance complete")
                break
        else:
            preroll.append(chunk.copy())
            waited_chunks += 1
            if waited_chunks >= max_wait_chunks:
                logger.debug("No speech onset within timeout — giving up")
                return []
        await asyncio.sleep(0)

    return frames


async def capture_utterance(max_wait_s: float = 30.0) -> bytes:
    """Capture a single spoken utterance from the microphone.

    Waits for speech onset (VAD engine from ``settings.vad_engine``), prepends
    a pre-roll buffer so the onset chunk isn't clipped, and records until
    silence returns for ``settings.vad_silence_ms``.

    Args:
        max_wait_s: Maximum seconds to wait for speech onset. If nobody
            speaks within this window, returns empty bytes so the caller's
            loop can cycle instead of blocking forever.

    Returns:
        WAV bytes at 16kHz mono int16, or ``b""`` if no speech started
        within *max_wait_s*.

    Raises:
        AudioCaptureError: If the microphone cannot be opened.
    """
    config = AudioConfig()
    vad = create_vad(settings.vad_engine)
    silence_close_chunks, preroll_chunks, max_wait_chunks = _compute_chunk_budget(max_wait_s)

    logger.info("Waiting for speech...")
    try:
        with sd.InputStream(
            samplerate=config.sample_rate,
            channels=config.channels,
            dtype=config.dtype,
            blocksize=_CHUNK_FRAMES,
        ) as stream:
            frames = await _capture_loop(
                stream, vad, silence_close_chunks, preroll_chunks, max_wait_chunks
            )
    except Exception as exc:
        raise AudioCaptureError("Microphone capture failed") from exc

    if not frames:
        return b""
    return _encode_wav(frames, config)
