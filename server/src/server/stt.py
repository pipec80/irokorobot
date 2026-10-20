"""Speech-to-text using faster-whisper.

Audio contract: WAV · 16000 Hz · mono · int16.
"""

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
import io
import logging
import math
import re
import unicodedata
import wave

from faster_whisper import WhisperModel
from faster_whisper.transcribe import Segment, VadOptions
import numpy as np

from server.exceptions import TranscriptionError, UnclearSpeechError
from server.request_context import run_in_executor_with_context
from server.settings import Settings, settings

logger = logging.getLogger(__name__)

# Echo-guard heuristic (Plan 0056 D-1). A prompt shorter than this is a name or a greeting
# a user may really say, so the guard stays off; a longer one is only "echoed" when the
# transcript covers at least this share of its words (five of the default prompt's seven).
_MIN_PROMPT_WORDS = 3
_MIN_ECHO_SHARE = 0.6

#: The words of a short spoken reply («sí», «acepto», «guárdala»…), passed as extra hotwords
#: only when a request asks for them (Plan 0067 D-4). The speech layer names no memory concept.
SHORT_REPLY_HOTWORDS: tuple[str, ...] = (
    "sí",
    "no",
    "acepto",
    "autorizo",
    "apruebo",
    "guárdalo",
    "guárdala",
)

_executor = ThreadPoolExecutor(max_workers=2)
_model: WhisperModel | None = None

_SAMPLE_RATE = 16_000
_INT16_FULL_SCALE = 32768.0


@dataclass(frozen=True)
class WhisperDecodeOptions:
    """Every argument of one Whisper decode (Plan 0069 D-14 and Task 1).

    The first five fields come from today's settings; the rest are fixed in code with the
    values production uses today, so the bench can vary one field at a time on the
    production code path. A field becomes a setting only when evidence moves it (Task 12).
    Three values stay out on purpose: ``condition_on_previous_text`` is always ``False`` (a
    robot clip is one 30 s window, so there is no previous text), ``patience`` keeps its
    library default (no evidence) and ``num_workers`` stays 1 (one robot, one request).
    """

    language: str
    beam_size: int
    initial_prompt: str | None
    vad_min_silence_ms: int
    hallucination_silence_threshold: float | None
    best_of: int = 5
    temperatures: tuple[float, ...] = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
    compression_ratio_threshold: float | None = 2.4
    log_prob_threshold: float | None = -1.0
    no_speech_threshold: float | None = 0.6
    vad_filter: bool = True
    vad_threshold: float = 0.5
    vad_min_speech_ms: int = 0
    vad_speech_pad_ms: int = 400
    word_timestamps: bool = False
    input_peak_dbfs: float | None = None


@dataclass(frozen=True)
class TranscriptConfidence:
    """How sure Whisper was about one clip (Plan 0069 D-11).

    ``avg_logprob`` is the token-weighted mean of the segments' mean log-probability per
    token: one coherent figure for the clip, not a calibrated probability of being right.
    The other three are the highest values over the segments, for diagnosis only.
    """

    avg_logprob: float
    no_speech_prob: float
    compression_ratio: float
    temperature: float
    segments: int


@dataclass(frozen=True)
class Transcript:
    """What Whisper heard in one clip, with its confidence and durations.

    ``confidence`` is ``None`` when Whisper returned no segment at all.
    """

    text: str
    confidence: TranscriptConfidence | None
    clip_s: float
    after_vad_s: float


def decode_options(source: Settings) -> WhisperDecodeOptions:
    """Build the production decode options from the settings that exist today.

    Args:
        source: The server settings.

    Returns:
        Options whose code-fixed fields keep today's production values.
    """
    return WhisperDecodeOptions(
        language=source.whisper_language,
        beam_size=source.whisper_beam_size,
        initial_prompt=source.whisper_initial_prompt,
        vad_min_silence_ms=source.whisper_vad_min_silence_ms,
        hallucination_silence_threshold=source.whisper_hallucination_silence_threshold,
    )


def normalize_peak(samples: np.ndarray, target_dbfs: float) -> np.ndarray:
    """Scale float samples so their peak sits at *target_dbfs*.

    Args:
        samples: Float32 samples in [-1, 1] (16 kHz mono, decoded from an int16 WAV).
        target_dbfs: The peak level wanted, in dBFS (for example -3.0).

    Returns:
        Float32 samples, same rate and length; an all-zero input comes back unchanged.
    """
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    if peak == 0.0:
        return samples
    gain = 10 ** (target_dbfs / 20) / peak
    return (samples * gain).astype(np.float32)


def _wav_floats(audio: bytes) -> np.ndarray:
    """Decode WAV bytes (16 kHz, mono, int16) to float32 samples in [-1, 1].

    Raises:
        ValueError: If the WAV is not 16 kHz, mono, int16.
    """
    with wave.open(io.BytesIO(audio), "rb") as handle:
        if (handle.getframerate(), handle.getnchannels(), handle.getsampwidth()) != (
            _SAMPLE_RATE,
            1,
            2,
        ):
            raise ValueError("Audio must be WAV 16 kHz, mono, int16")
        frames = handle.readframes(handle.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / _INT16_FULL_SCALE


def _clip_confidence(segments: Sequence[Segment]) -> TranscriptConfidence | None:
    """Fold the segments' confidence into one figure for the clip (D-11)."""
    if not segments:
        return None
    weights = [max(len(seg.tokens), 1) for seg in segments]
    weighted = sum(w * seg.avg_logprob for w, seg in zip(weights, segments, strict=True))
    return TranscriptConfidence(
        avg_logprob=weighted / sum(weights),
        no_speech_prob=max(seg.no_speech_prob for seg in segments),
        compression_ratio=max(seg.compression_ratio for seg in segments),
        temperature=max(seg.temperature or 0.0 for seg in segments),
        segments=len(segments),
    )


def run_whisper(
    model: WhisperModel, audio: bytes, options: WhisperDecodeOptions, hotwords: str | None
) -> Transcript:
    """Run one Whisper decode — the only place that calls ``model.transcribe``.

    Args:
        model: A loaded Whisper model.
        audio: Raw WAV bytes at 16kHz mono int16. With ``options.input_peak_dbfs`` set they
            are decoded to float32 at 16 kHz and peak-normalized before Whisper sees them;
            otherwise the bytes go to Whisper unchanged.
        options: The decode arguments.
        hotwords: Merged hotwords string, or ``None``.

    Returns:
        The joined text, the clip's confidence and its durations before and after Whisper's
        own silence filter.
    """
    source: io.BytesIO | np.ndarray = (
        io.BytesIO(audio)
        if options.input_peak_dbfs is None
        else normalize_peak(_wav_floats(audio), options.input_peak_dbfs)
    )
    segments, info = model.transcribe(
        source,
        language=options.language,
        beam_size=options.beam_size,
        best_of=options.best_of,
        temperature=options.temperatures,
        compression_ratio_threshold=options.compression_ratio_threshold,
        log_prob_threshold=options.log_prob_threshold,
        no_speech_threshold=options.no_speech_threshold,
        initial_prompt=options.initial_prompt,
        hotwords=hotwords,
        condition_on_previous_text=False,
        word_timestamps=options.word_timestamps,
        hallucination_silence_threshold=options.hallucination_silence_threshold,
        vad_filter=options.vad_filter,
        vad_parameters=VadOptions(
            threshold=options.vad_threshold,
            min_speech_duration_ms=options.vad_min_speech_ms,
            min_silence_duration_ms=options.vad_min_silence_ms,
            speech_pad_ms=options.vad_speech_pad_ms,
        ),
    )
    logger.info(
        "Language detected: %s (%.0f%%) — audio duration: %.1fs → %.1fs after VAD",
        info.language,
        info.language_probability * 100,
        info.duration,
        info.duration_after_vad,
    )
    decoded = list(segments)
    for seg in decoded:
        logger.debug(
            "Segment [%.1fs→%.1fs] logprob=%.2f no_speech=%.2f temp=%.1f (%d chars)",
            seg.start,
            seg.end,
            seg.avg_logprob,
            seg.no_speech_prob,
            seg.temperature or 0.0,
            len(seg.text.strip()),
        )
    return Transcript(
        text=" ".join(seg.text.strip() for seg in decoded),
        confidence=_clip_confidence(decoded),
        clip_s=info.duration,
        after_vad_s=info.duration_after_vad,
    )


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


def _normalize_words(text: str) -> str:
    """Fold case, accents and punctuation so two spellings of one phrase compare equal."""
    folded = unicodedata.normalize("NFKD", text.casefold())
    unaccented = "".join(c for c in folded if not unicodedata.combining(c))
    return " ".join(re.sub(r"[\W_]+", " ", unaccented).split())


def is_prompt_echo(transcript: str, prompt: str | None) -> bool:
    """Return whether Whisper merely repeated its own initial prompt.

    On a noise clip Whisper can return the ``initial_prompt`` as if it were speech.
    This is a heuristic with a known false positive: a user who says, verbatim, at
    least 60 % of the prompt's words in a row (five of the default prompt's seven)
    is discarded too. Shorter phrases ("Iroko", "un robot doméstico") and any prompt
    of fewer than three words never trigger it.

    Args:
        transcript: Text Whisper returned.
        prompt: The ``initial_prompt`` it was given, if any.

    Returns:
        True when the transcript is a contiguous part of the prompt covering at
        least 60 % of its words, or the prompt repeated and nothing else.
    """
    if not prompt:
        return False
    reference = _normalize_words(prompt)
    reference_words = reference.split()
    if len(reference_words) < _MIN_PROMPT_WORDS:
        return False
    heard = _normalize_words(transcript)
    needed = max(_MIN_PROMPT_WORDS, math.ceil(_MIN_ECHO_SHARE * len(reference_words)))
    if len(heard.split()) < needed:
        return False
    if f" {heard} " in f" {reference} ":
        return True
    return reference in heard and not heard.replace(reference, " ").strip()


def is_unclear(confidence: TranscriptConfidence | None, threshold: float | None) -> bool:
    """Return whether a transcript is too doubtful to act on (Plan 0069 D-11).

    Args:
        confidence: The clip's confidence, or ``None`` when Whisper returned no segment.
        threshold: ``settings.whisper_unclear_logprob``; ``None`` switches the gate off.

    Returns:
        True only when a threshold is set and the clip's mean log-probability per token is
        strictly below it.
    """
    if threshold is None or confidence is None:
        return False
    return confidence.avg_logprob < threshold


def _log_confidence(transcript: Transcript, unclear: bool) -> None:
    """Log the clip's confidence numbers and the gate's verdict — never the text."""
    confidence = transcript.confidence
    if confidence is None:
        return
    logger.info(
        "STT confidence: logprob=%.3f no_speech=%.2f compression=%.2f temp=%.1f "
        "segments=%d clip=%.1fs after_vad=%.1fs unclear=%s",
        confidence.avg_logprob,
        confidence.no_speech_prob,
        confidence.compression_ratio,
        confidence.temperature,
        confidence.segments,
        transcript.clip_s,
        transcript.after_vad_s,
        unclear,
        extra={
            "event": "stt.confidence",
            "avg_logprob": round(confidence.avg_logprob, 3),
            "no_speech_prob": round(confidence.no_speech_prob, 3),
            "compression_ratio": round(confidence.compression_ratio, 3),
            "temperature": confidence.temperature,
            "segments": confidence.segments,
            "clip_s": round(transcript.clip_s, 2),
            "after_vad_s": round(transcript.after_vad_s, 2),
            "unclear": unclear,
        },
    )


def _transcribe_sync(audio: bytes, hotwords: str | None) -> str:
    """Run Whisper, discard a prompt echo and refuse a transcript Whisper doubted.

    Args:
        audio: Raw WAV bytes at 16kHz mono int16.
        hotwords: Merged hotwords string, or ``None``.

    Returns:
        Transcribed text, or ``""`` when Whisper only echoed its initial prompt.

    Raises:
        TranscriptionError: If audio cannot be processed.
        UnclearSpeechError: If the transcript is not empty and its confidence is below
            ``settings.whisper_unclear_logprob`` (off by default).
        ValueError: If audio is empty.
    """
    transcript = _whisper_transcript(audio, hotwords)
    if is_prompt_echo(transcript.text, settings.whisper_initial_prompt):
        logger.warning("Whisper returned its own initial prompt — transcript discarded")
        return ""
    unclear = bool(transcript.text.strip()) and is_unclear(
        transcript.confidence, settings.whisper_unclear_logprob
    )
    _log_confidence(transcript, unclear)
    if unclear:
        raise UnclearSpeechError(transcript.text)
    return transcript.text


def _whisper_text(audio: bytes, hotwords: str | None) -> str:
    """Run Whisper inference synchronously (blocking) and return the raw transcript.

    Args:
        audio: Raw WAV bytes at 16kHz mono int16.
        hotwords: Merged hotwords string biasing the decoder toward known
            proper nouns, or ``None``.

    Returns:
        Transcribed text string, exactly as Whisper produced it.

    Raises:
        TranscriptionError: If audio cannot be processed.
        ValueError: If audio is empty.
    """
    return _whisper_transcript(audio, hotwords).text


def _whisper_transcript(audio: bytes, hotwords: str | None) -> Transcript:
    """Run Whisper inference synchronously (blocking) with the production options.

    Args:
        audio: Raw WAV bytes at 16kHz mono int16.
        hotwords: Merged hotwords string, or ``None``.

    Returns:
        The transcript, its confidence and its durations.

    Raises:
        TranscriptionError: If audio cannot be processed.
        ValueError: If audio is empty.
    """
    if not audio:
        raise ValueError("Audio bytes are empty")
    try:
        return run_whisper(_get_model(), audio, decode_options(settings), hotwords)
    except Exception as exc:
        raise TranscriptionError("Whisper inference failed") from exc


def preload() -> None:
    """Load Whisper model into memory.

    Call at application startup to avoid cold-start latency on the first request.
    """
    _get_model()


def is_loaded() -> bool:
    """Return whether the Whisper model is currently loaded (Plan 0040).

    Side-effect-free — never triggers a load. Used by `GET /ready` to
    report readiness without paying for a real model load in that probe.
    """
    return _model is not None


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
        UnclearSpeechError: If Whisper doubted a non-empty transcript (off by default).
        ValueError: If audio is empty.
    """
    hotwords = _merge_hotwords(settings.whisper_hotwords, extra_hotwords)
    return await run_in_executor_with_context(_executor, partial(_transcribe_sync, audio, hotwords))
