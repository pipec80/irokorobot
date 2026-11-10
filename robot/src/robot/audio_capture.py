"""Microphone audio capture with pluggable VAD (Silero neural or RMS fallback).

Audio contract: WAV · 16000 Hz · mono · int16.
"""

import asyncio
from collections import deque
from dataclasses import dataclass
import io
import logging
from typing import Final, Protocol
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
#: Samples per chunk: 32 ms at 16 kHz, the chunk size Silero VAD requires.
CHUNK_FRAMES: Final = 512
_CHUNK_DURATION_S = CHUNK_FRAMES / _SAMPLE_RATE
_CHUNK_MS = CHUNK_FRAMES * 1000 // _SAMPLE_RATE  # 32 ms, exact (512 frames at 16 kHz)


@dataclass(frozen=True)
class AudioConfig:
    """Immutable audio format specification."""

    sample_rate: int = _SAMPLE_RATE
    channels: int = _CHANNELS
    dtype: str = _DTYPE


class ChunkSource(Protocol):
    """Anything that hands out chunks the way ``sd.InputStream.read`` does.

    The live microphone is one; a recorded take read back chunk by chunk is another
    (Plan 0069), so the same segmentation runs on both.
    """

    def read(self, frames: int) -> tuple[np.ndarray, bool]:
        """Return the next *frames* int16 samples (16 kHz, mono) and an overflow flag."""
        ...


@dataclass(frozen=True)
class SegmentationPolicy:
    """How one utterance is cut out of a chunk source (Plan 0069 D-17).

    Attributes:
        preroll_ms: Audio kept before the speech onset.
        close_silence_ms: Silence after speech that closes the utterance.
        upload_tail_ms: Silence the returned clip keeps after the speech; never more than
            was collected.
        max_utterance_ms: Longest clip, pre-roll included (Plan 0080). Once speech has
            started and the collected audio reaches it, the utterance closes right there
            and is sent as it is. ``None`` means no cap (offline callers).
    """

    preroll_ms: int
    close_silence_ms: int
    upload_tail_ms: int
    max_utterance_ms: int | None = None

    @classmethod
    def from_settings(cls, close_silence_ms: int | None = None) -> "SegmentationPolicy":
        """Build the policy the robot runs with.

        Args:
            close_silence_ms: Reply mode's closing silence, replacing ``vad_silence_ms``;
                ``None`` keeps the normal close.

        Returns:
            The policy. The tail is ``vad_upload_tail_ms``, never longer than the normal
            ``vad_silence_ms``; the length cap is ``max_utterance_s`` (below the server's
            audio limit).
        """
        return cls(
            preroll_ms=settings.vad_preroll_ms,
            close_silence_ms=settings.vad_silence_ms
            if close_silence_ms is None
            else close_silence_ms,
            upload_tail_ms=min(settings.vad_upload_tail_ms, settings.vad_silence_ms),
            max_utterance_ms=round(settings.max_utterance_s * 1000),
        )


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


def _ms_to_chunks(duration_ms: int) -> int:
    """Convert a silence duration in ms into a chunk count (at least one chunk)."""
    return max(1, round(duration_ms / 1000 / _CHUNK_DURATION_S))


def _policy_chunks(policy: SegmentationPolicy, max_wait_s: float) -> tuple[int, int, int]:
    """Convert a segmentation policy into chunk counts at the 32 ms chunk cadence.

    Args:
        policy: The segmentation policy.
        max_wait_s: Seconds to wait for speech onset.

    Returns:
        (silence_close_chunks, preroll_chunks, max_wait_chunks).
    """
    silence_close_chunks = _ms_to_chunks(policy.close_silence_ms)
    preroll_chunks = max(0, round(policy.preroll_ms / 1000 / _CHUNK_DURATION_S))
    max_wait_chunks = max(1, round(max_wait_s / _CHUNK_DURATION_S))
    return silence_close_chunks, preroll_chunks, max_wait_chunks


def _max_utterance_chunks(policy: SegmentationPolicy) -> int | None:
    """Convert the policy's length cap into a chunk count (at least one), or ``None``."""
    if policy.max_utterance_ms is None:
        return None
    return max(1, round(policy.max_utterance_ms / 1000 / _CHUNK_DURATION_S))


def _trim_trailing_silence(
    frames: list[np.ndarray], trailing_silent_chunks: int, upload_tail_ms: int
) -> list[np.ndarray]:
    """Cut a closed utterance back to the upload tail.

    Removing the surplus of the trailing silent chunks over the tail leaves that much
    silence. A normal close has collected exactly the closing threshold of them; a close
    at the length cap has collected few or none, and must lose no speech.

    Args:
        frames: Int16 chunks (16 kHz mono) of a closed utterance.
        trailing_silent_chunks: Silent chunks really collected at the end of *frames*.
        upload_tail_ms: Silence to keep; a tail longer than what was collected cuts nothing.

    Returns:
        The frames, same format, with at most the upload tail.
    """
    # Rounded up: a 300 ms tail is 10 chunks (320 ms), never 9 (288 ms), because the clip must keep
    # at least the silence the onset and the last word need.
    kept_chunks = max(1, -(-upload_tail_ms // _CHUNK_MS))
    surplus = trailing_silent_chunks - kept_chunks
    return frames[:-surplus] if surplus > 0 else frames


async def _capture_loop(
    stream: ChunkSource,
    vad: VoiceActivityDetector,
    silence_close_chunks: int,
    preroll_chunks: int,
    max_wait_chunks: int,
    max_utterance_chunks: int | None = None,
) -> tuple[list[np.ndarray], int]:
    """Read chunks until an utterance closes, or return ``([], 0)`` on onset timeout.

    The utterance closes on the closing silence, or, once speech has started, as soon as
    the collected chunks (pre-roll included) reach *max_utterance_chunks* (Plan 0080).

    Audio contract: the chunks are int16 samples, 16 000 Hz, mono.

    Returns:
        The collected int16 chunks (16 kHz mono) and how many silent chunks really end them.
    """
    preroll: deque[np.ndarray] = deque(maxlen=preroll_chunks)
    frames: list[np.ndarray] = []
    silence_count = 0
    speaking = False
    waited_chunks = 0

    while True:
        chunk, _ = stream.read(CHUNK_FRAMES)
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
                return [], 0
        if speaking and max_utterance_chunks is not None and len(frames) >= max_utterance_chunks:
            logger.info("Utterance reached the length cap — sending it")
            break
        await asyncio.sleep(0)

    return frames, silence_count


async def segment_utterance(
    source: ChunkSource,
    vad: VoiceActivityDetector,
    policy: SegmentationPolicy,
    *,
    max_wait_s: float = 30.0,
) -> bytes:
    """Cut one utterance out of a chunk source, exactly as the robot does live.

    Args:
        source: Int16 chunks, 16 kHz, mono (the microphone, or a recorded take).
        vad: A fresh voice-activity detector for this utterance.
        policy: Pre-roll, closing silence, upload tail and the length cap.
        max_wait_s: Maximum seconds to wait for speech onset (the cap does not change it).

    Returns:
        WAV bytes at 16kHz mono int16, never longer than the policy's length cap, or
        ``b""`` if no speech started within *max_wait_s*.
    """
    silence_close_chunks, preroll_chunks, max_wait_chunks = _policy_chunks(policy, max_wait_s)
    frames, trailing_silent = await _capture_loop(
        source,
        vad,
        silence_close_chunks,
        preroll_chunks,
        max_wait_chunks,
        _max_utterance_chunks(policy),
    )
    if not frames:
        return b""
    kept = _trim_trailing_silence(frames, trailing_silent, policy.upload_tail_ms)
    return _encode_wav(kept, AudioConfig())


async def capture_utterance(
    max_wait_s: float = 30.0, *, close_silence_ms: int | None = None
) -> bytes:
    """Capture a single spoken utterance from the microphone.

    Waits for speech onset (VAD engine from ``settings.vad_engine``), prepends
    a pre-roll buffer so the onset chunk isn't clipped, and records until
    silence returns for ``settings.vad_silence_ms``, or until the clip reaches
    ``settings.max_utterance_s`` (kept below the server's audio limit), whichever
    comes first.

    Args:
        max_wait_s: Maximum seconds to wait for speech onset. If nobody
            speaks within this window, returns empty bytes so the caller's
            loop can cycle instead of blocking forever.
        close_silence_ms: Reply mode. When given, the utterance closes after
            this much silence instead of ``settings.vad_silence_ms``, so a pause
            inside the speech stays one clip. The returned clip is then cut back
            to the upload tail, so it is never longer than a normal capture.
            ``None`` keeps the normal behavior.

    Returns:
        WAV bytes at 16kHz mono int16, or ``b""`` if no speech started
        within *max_wait_s*.

    Raises:
        AudioCaptureError: If the microphone cannot be opened.
    """
    config = AudioConfig()
    vad = create_vad(settings.vad_engine)
    policy = SegmentationPolicy.from_settings(close_silence_ms)

    logger.info("Waiting for speech...")
    try:
        with sd.InputStream(
            samplerate=config.sample_rate,
            channels=config.channels,
            dtype=config.dtype,
            blocksize=CHUNK_FRAMES,
        ) as stream:
            return await segment_utterance(stream, vad, policy, max_wait_s=max_wait_s)
    except Exception as exc:
        raise AudioCaptureError("Microphone capture failed") from exc
