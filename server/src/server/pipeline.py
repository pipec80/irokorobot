"""Shared STT/TTS orchestration helpers used by HTTP media adapters.

Audio contract: WAV · 16000 Hz · mono · int16.
"""

import logging
import time

from fastapi import HTTPException

from server import stt, tts
from server.exceptions import BrainMemoryError, TranscriptionError, TTSError
from server.memory.declarative import list_entity_names
from server.settings import settings

logger = logging.getLogger(__name__)


async def _entity_hotwords() -> list[str]:
    """Return known entity names to bias Whisper decoding.

    Proper nouns are what the STT garbles most; the names the robot already
    learned are the ones most likely to be spoken again. A down DB degrades
    to no extra hotwords — never to a failed transcription.

    Returns:
        Entity names, or an empty list when memory is off or unavailable.
    """
    if not settings.memory_enabled:
        return []
    try:
        return await list_entity_names()
    except BrainMemoryError as exc:
        logger.warning("Entity hotwords unavailable — transcribing without: %s", exc)
        return []


def _elapsed_ms(start: float) -> int:
    """Return milliseconds elapsed since a ``time.perf_counter()`` reading."""
    return round((time.perf_counter() - start) * 1000)


def _log_pipeline_timing(stt_ms: int, llm_ms: int, tts_ms: int, total_ms: int) -> None:
    """Log one INFO line per pipeline request with per-stage latency."""
    logger.info("Pipeline: stt=%dms llm=%dms tts=%dms total=%dms", stt_ms, llm_ms, tts_ms, total_ms)


async def _run_stt(audio_bytes: bytes, hotwords: list[str]) -> tuple[str, int]:
    """Transcribe audio and measure elapsed time.

    Args:
        audio_bytes: Raw WAV bytes — 16kHz, mono, int16.
        hotwords: Known entity names to bias Whisper decoding.

    Returns:
        Tuple of (transcribed text, elapsed milliseconds).

    Raises:
        HTTPException 500: If STT fails.
    """
    start = time.perf_counter()
    try:
        text = await stt.transcribe(audio_bytes, extra_hotwords=hotwords)
    except (TranscriptionError, ValueError) as exc:
        logger.error("STT failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Transcription failed") from exc
    logger.info("STT heard: %r", text)
    return text, _elapsed_ms(start)


async def _run_tts(text: str) -> tuple[str, int, int]:
    """Synthesize speech and measure elapsed time.

    Args:
        text: Text to speak.

    Returns:
        Tuple of (base64 WAV audio, TTS-reported synthesis ms, elapsed ms).

    Raises:
        HTTPException 500: If TTS fails.
    """
    start = time.perf_counter()
    try:
        audio_base64, duration_ms = await tts.synthesize(text)
    except (TTSError, ValueError) as exc:
        logger.error("TTS failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Speech synthesis failed") from exc
    logger.info("TTS synthesized: %d ms audio, %d chars in", duration_ms, len(text))
    return audio_base64, duration_ms, _elapsed_ms(start)
