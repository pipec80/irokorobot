"""Speech-to-text using faster-whisper.

Audio contract: WAV · 16000 Hz · mono · int16.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import io
import logging

from faster_whisper import WhisperModel
from faster_whisper.transcribe import VadOptions

from server.exceptions import TranscriptionError
from server.settings import settings

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)
_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    """Return the singleton WhisperModel, loading it on first call."""
    global _model  # noqa: PLW0603
    if _model is None:
        logger.info("Loading Whisper model: %s", settings.whisper_model)
        # local_files_only=True avoids a HuggingFace version-check HTTP request on every
        # server startup. This is a local-first homelab — no guaranteed internet access.
        # To update the model: delete the HF cache (~/.cache/huggingface/hub/) and restart
        # once with internet, then it re-caches and reverts to offline mode automatically.
        try:
            _model = WhisperModel(
                settings.whisper_model,
                device=settings.whisper_device,
                compute_type=settings.whisper_compute_type,
                local_files_only=True,
            )
        except Exception:
            logger.info("Model not in cache — downloading from HuggingFace (one-time)")
            _model = WhisperModel(
                settings.whisper_model,
                device=settings.whisper_device,
                compute_type=settings.whisper_compute_type,
            )
    return _model


def _merge_hotwords(base: str | None, extra: list[str] | None) -> str | None:
    """Merge static hotwords from settings with dynamic entity names.

    Args:
        base: Space-separated hotwords from ``settings.whisper_hotwords``.
        extra: Names learned by the memory layer (may be empty or None).

    Returns:
        Combined hotwords string, or ``None`` when both inputs are empty.
    """
    tokens: list[str] = base.split() if base else []
    seen = {t.casefold() for t in tokens}
    for raw in extra or []:
        name = raw.strip()
        if name and name.casefold() not in seen:
            tokens.append(name)
            seen.add(name.casefold())
    return " ".join(tokens) or None


def _transcribe_sync(audio: bytes, hotwords: str | None) -> str:
    """Run Whisper inference synchronously (blocking).

    Args:
        audio: Raw WAV bytes at 16kHz mono int16.
        hotwords: Merged hotwords string biasing the decoder toward known
            proper nouns, or ``None``.

    Returns:
        Transcribed text string.

    Raises:
        TranscriptionError: If audio cannot be processed.
        ValueError: If audio is empty.
    """
    if not audio:
        raise ValueError("Audio bytes are empty")
    try:
        model = _get_model()
        vad_params = VadOptions(min_silence_duration_ms=settings.whisper_vad_min_silence_ms)
        segments, info = model.transcribe(
            io.BytesIO(audio),
            language=settings.whisper_language,
            beam_size=settings.whisper_beam_size,
            initial_prompt=settings.whisper_initial_prompt,
            hotwords=hotwords,
            condition_on_previous_text=False,
            hallucination_silence_threshold=settings.whisper_hallucination_silence_threshold,
            vad_filter=True,
            vad_parameters=vad_params,
        )
        logger.info(
            "Language detected: %s (%.0f%%) — audio duration: %.1fs → %.1fs after VAD",
            info.language,
            info.language_probability * 100,
            info.duration,
            info.duration_after_vad,
        )
        parts: list[str] = []
        for seg in segments:
            logger.debug(
                "Segment [%.1fs→%.1fs] logprob=%.2f no_speech=%.2f temp=%.1f (%d chars)",
                seg.start,
                seg.end,
                seg.avg_logprob,
                seg.no_speech_prob,
                seg.temperature or 0.0,
                len(seg.text.strip()),
            )
            parts.append(seg.text.strip())
        return " ".join(parts)
    except Exception as exc:
        raise TranscriptionError("Whisper inference failed") from exc


def preload() -> None:
    """Load Whisper model into memory.

    Call at application startup to avoid cold-start latency on the first request.
    """
    _get_model()


async def transcribe(audio: bytes, *, extra_hotwords: list[str] | None = None) -> str:
    """Transcribe audio bytes to text.

    Args:
        audio: Raw WAV bytes at 16kHz mono int16.
        extra_hotwords: Optional names (from the memory layer) merged with
            ``settings.whisper_hotwords`` to bias decoding toward proper
            nouns the robot already knows.

    Returns:
        Transcribed text string.

    Raises:
        TranscriptionError: If audio cannot be processed.
        ValueError: If audio is empty.
    """
    hotwords = _merge_hotwords(settings.whisper_hotwords, extra_hotwords)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _transcribe_sync, audio, hotwords)
