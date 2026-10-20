"""Whisper's call goes through one options structure (Plan 0069 Task 1).

The defaults reproduce today's call exactly, so the bench can vary one field at a time on
the production code path. Audio contract: WAV · 16000 Hz · mono · int16.
"""

from dataclasses import dataclass, replace
import io
import wave

from faster_whisper.transcribe import VadOptions
import numpy as np
import pytest
from server.settings import Settings

from server import stt

_SAMPLE_RATE = 16_000


def _wav(samples: np.ndarray) -> bytes:
    """Encode int16 samples as WAV bytes — 16 kHz, mono, int16."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(_SAMPLE_RATE)
        handle.writeframes(samples.astype(np.int16).tobytes())
    return buffer.getvalue()


def _tone(dbfs: float, seconds: float = 0.5) -> np.ndarray:
    """A 440 Hz int16 tone whose peak is *dbfs* below full scale."""
    t = np.arange(int(seconds * _SAMPLE_RATE)) / _SAMPLE_RATE
    peak = 32767 * 10 ** (dbfs / 20)
    return (peak * np.sin(2 * np.pi * 440 * t)).astype(np.int16)


@dataclass
class _Segment:
    text: str
    tokens: list[int]
    avg_logprob: float
    no_speech_prob: float
    compression_ratio: float
    temperature: float | None
    start: float = 0.0
    end: float = 1.0


@dataclass
class _Info:
    language: str = "es"
    language_probability: float = 1.0
    duration: float = 1.3
    duration_after_vad: float = 1.0


class _RecordingModel:
    """Stands in for WhisperModel; records what `transcribe` received."""

    def __init__(self, segments: list[_Segment]) -> None:
        self.segments = segments
        self.audio: object = None
        self.kwargs: dict[str, object] = {}

    def transcribe(self, audio: object, **kwargs: object) -> tuple[list[_Segment], _Info]:
        self.audio = audio
        self.kwargs = kwargs
        return list(self.segments), _Info()


def _segment(text: str, tokens: int, logprob: float, **overrides: float) -> _Segment:
    values = {"no_speech_prob": 0.1, "compression_ratio": 1.2, "temperature": 0.0} | overrides
    return _Segment(text, list(range(tokens)), logprob, **values)


def _defaults() -> Settings:
    """The code defaults, never a local .env."""
    return Settings(_env_file=None)  # type: ignore[call-arg]  # pydantic-settings init kwarg


def _options(**overrides: object) -> stt.WhisperDecodeOptions:
    return replace(stt.decode_options(_defaults()), **overrides)  # type: ignore[arg-type]  # field overrides


@pytest.mark.unit
def test_default_call_matches_todays_whisper_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    model = _RecordingModel([_segment("hola", 3, -0.3)])
    defaults = _defaults()
    monkeypatch.setattr(stt, "_get_model", lambda: model)
    monkeypatch.setattr(stt, "settings", defaults)

    stt._transcribe_sync(_wav(_tone(-20.0)), None)

    assert model.kwargs == {
        "language": "es",
        "beam_size": 5,
        "best_of": 5,
        "temperature": (0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
        "compression_ratio_threshold": 2.4,
        "log_prob_threshold": -1.0,
        "no_speech_threshold": 0.6,
        "initial_prompt": defaults.whisper_initial_prompt,
        "hotwords": None,
        "condition_on_previous_text": False,
        "word_timestamps": False,
        "hallucination_silence_threshold": 2.0,
        "vad_filter": True,
        "vad_parameters": VadOptions(min_silence_duration_ms=500),
    }
    vad = model.kwargs["vad_parameters"]
    assert isinstance(vad, VadOptions)
    assert (vad.threshold, vad.speech_pad_ms, vad.min_speech_duration_ms) == (0.5, 400, 0)
    assert isinstance(model.audio, io.BytesIO)


@pytest.mark.unit
def test_run_whisper_joins_text_and_weights_the_log_probability_by_tokens() -> None:
    model = _RecordingModel(
        [
            _segment(" Me gusta ", 10, -0.2, no_speech_prob=0.05, compression_ratio=1.1),
            _segment(" el helado. ", 30, -1.0, no_speech_prob=0.4, temperature=0.2),
        ]
    )

    transcript = stt.run_whisper(model, _wav(_tone(-20.0)), _options(), None)  # type: ignore[arg-type]  # a recording fake stands in for WhisperModel

    assert transcript.text == "Me gusta el helado."
    assert transcript.confidence is not None
    assert transcript.confidence.avg_logprob == pytest.approx(-0.8)
    assert transcript.confidence.no_speech_prob == pytest.approx(0.4)
    assert transcript.confidence.compression_ratio == pytest.approx(1.2)
    assert transcript.confidence.temperature == pytest.approx(0.2)
    assert transcript.confidence.segments == 2
    assert (transcript.clip_s, transcript.after_vad_s) == (1.3, 1.0)


@pytest.mark.unit
def test_run_whisper_without_segments_has_no_confidence() -> None:
    transcript = stt.run_whisper(_RecordingModel([]), _wav(_tone(-20.0)), _options(), None)  # type: ignore[arg-type]  # fake model

    assert transcript.text == ""
    assert transcript.confidence is None


@pytest.mark.unit
def test_normalize_peak_raises_a_quiet_tone_to_the_target() -> None:
    quiet = _tone(-20.0).astype(np.float32) / 32768.0

    loud = stt.normalize_peak(quiet, -3.0)

    assert loud.dtype == np.float32
    assert 20 * np.log10(np.max(np.abs(loud))) == pytest.approx(-3.0, abs=0.1)


@pytest.mark.unit
def test_normalize_peak_leaves_silence_alone() -> None:
    silence = np.zeros(1600, dtype=np.float32)

    assert np.array_equal(stt.normalize_peak(silence, -3.0), silence)


@pytest.mark.unit
def test_peak_normalization_hands_whisper_a_float_array() -> None:
    model = _RecordingModel([_segment("hola", 3, -0.3)])
    options = _options(input_peak_dbfs=-3.0)

    stt.run_whisper(model, _wav(_tone(-20.0)), options, None)  # type: ignore[arg-type]  # fake model

    assert isinstance(model.audio, np.ndarray)
    assert model.audio.dtype == np.float32
    assert 20 * np.log10(np.max(np.abs(model.audio))) == pytest.approx(-3.0, abs=0.1)
