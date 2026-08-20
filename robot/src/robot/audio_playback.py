"""WAV playback through the default audio output device.

Audio contract: WAV · 16000 Hz · mono · int16. The sample rate is read
from the WAV header rather than assumed, so playback stays correct even
if the server ever emits a different rate.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from concurrent.futures import ThreadPoolExecutor
import contextlib
import io
import logging
import wave

import numpy as np
import numpy.typing as npt
import sounddevice as sd

from robot.exceptions import AudioPlaybackError

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=1)


def _play_sync(wav_bytes: bytes) -> None:
    """Decode and play WAV bytes, blocking until playback completes.

    Args:
        wav_bytes: WAV audio — sample rate and channels read from the header.
    """
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        sample_rate = wf.getframerate()
        channels = wf.getnchannels()
        frames = wf.readframes(wf.getnframes())
    audio: npt.NDArray[np.int16] = np.frombuffer(frames, dtype=np.int16)
    if channels > 1:
        audio = audio.reshape(-1, channels)
    logger.debug("Playing %d frames at %d Hz", len(audio), sample_rate)
    sd.play(audio, samplerate=sample_rate)
    sd.wait()


async def play_wav(wav_bytes: bytes) -> None:
    """Play WAV audio without blocking the event loop.

    Runs the blocking sounddevice calls in a thread executor. Returns only
    when playback has finished — callers rely on this to enforce half-duplex
    (never capture while speaking).

    Args:
        wav_bytes: WAV audio at 16kHz mono int16 per the audio contract;
            the header rate is honored if it ever differs.

    Raises:
        AudioPlaybackError: If decoding or the output device fails.
        ValueError: If wav_bytes is empty.
    """
    if not wav_bytes:
        raise ValueError("Audio bytes are empty")
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(_executor, _play_sync, wav_bytes)
    except Exception as exc:
        raise AudioPlaybackError("Audio playback failed") from exc


async def _consume(
    queue: asyncio.Queue[bytes | None],
    on_chunk_start: Callable[[int], None] | None,
) -> None:
    """Play every queued chunk in order, reporting each playback start.

    Args:
        queue: Chunks produced by the background reader, terminated by a
            ``None`` sentinel.
        on_chunk_start: Called with the one-based chunk index immediately
            before that chunk's ``play_wav`` call, if given.
    """
    index = 0
    while (chunk := await queue.get()) is not None:
        index += 1
        if on_chunk_start is not None:
            on_chunk_start(index)
        await play_wav(chunk)


async def play_wav_stream(
    chunks: AsyncIterator[bytes],
    *,
    on_chunk_start: Callable[[int], None] | None = None,
) -> None:
    """Play a stream of WAV chunks sequentially, draining before returning (R3).

    A background task pulls chunks from ``chunks`` into a queue while this
    coroutine plays them one at a time via ``play_wav`` — so the next chunk
    can already be arriving over the network while the previous one plays.
    Returns only once every chunk has been played (or the stream/playback
    fails), preserving the same half-duplex guarantee as ``play_wav``: the
    caller must not reopen the microphone before this coroutine returns.

    Args:
        chunks: Async iterator of WAV audio chunks, each at 16kHz mono int16
            per the audio contract (e.g. one chunk per synthesized sentence).
        on_chunk_start: Optional callback invoked with the one-based chunk
            index immediately before that chunk starts playing.

    Raises:
        AudioPlaybackError: If decoding or the output device fails for any chunk.
        Exception: Whatever ``chunks`` itself raises (e.g. a server/network
            or stream-validation error) — re-raised after every already
            -received chunk has played.
    """
    queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    async def _producer() -> None:
        try:
            async for chunk in chunks:
                await queue.put(chunk)
        finally:
            queue.put_nowait(None)  # sentinel: unblocks the consumer even on error

    producer_task = asyncio.create_task(_producer())
    try:
        await _consume(queue, on_chunk_start)
    finally:
        producer_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await producer_task
