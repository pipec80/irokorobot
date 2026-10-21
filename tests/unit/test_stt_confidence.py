"""The clip confidence is logged and, behind a threshold, refuses a doubtful transcript.

Plan 0069 Task 2 (D-11). Audio contract: WAV · 16000 Hz · mono · int16.
"""

from dataclasses import dataclass
import logging

import pytest
from server.exceptions import TranscriptionError, UnclearSpeechError
from server.settings import Settings

from server import stt

_PROMPT = "Conversación con un robot doméstico llamado Iroko."
_SENTINEL = "palabracentinela"


@dataclass
class _Segment:
    text: str
    avg_logprob: float
    tokens: tuple[int, ...] = (1, 2, 3)
    no_speech_prob: float = 0.1
    compression_ratio: float = 1.2
    temperature: float | None = 0.0
    start: float = 0.0
    end: float = 1.0


@dataclass
class _Info:
    language: str = "es"
    language_probability: float = 1.0
    duration: float = 1.3
    duration_after_vad: float = 1.0


class _FakeModel:
    def __init__(self, text: str, logprob: float) -> None:
        self._segment = _Segment(text, logprob)

    def transcribe(self, *_args: object, **_kwargs: object) -> tuple[list[_Segment], _Info]:
        return [self._segment], _Info()


def _confidence(logprob: float) -> stt.TranscriptConfidence:
    return stt.TranscriptConfidence(
        avg_logprob=logprob,
        no_speech_prob=0.1,
        compression_ratio=1.2,
        temperature=0.0,
        segments=1,
    )


def _use(
    monkeypatch: pytest.MonkeyPatch, text: str, logprob: float, threshold: float | None
) -> None:
    monkeypatch.setattr(stt.settings, "whisper_initial_prompt", _PROMPT)
    monkeypatch.setattr(stt, "_get_model", lambda: _FakeModel(text, logprob))
    monkeypatch.setattr(stt.settings, "whisper_unclear_logprob", threshold)


@pytest.mark.unit
def test_the_unclear_threshold_is_off_by_default() -> None:
    assert Settings(_env_file=None).whisper_unclear_logprob is None  # type: ignore[call-arg]  # code default


@pytest.mark.unit
@pytest.mark.parametrize(
    "confidence, threshold, unclear",
    [
        (_confidence(-2.0), None, False),
        (None, -1.0, False),
        (_confidence(-1.0), -1.0, False),
        (_confidence(-1.01), -1.0, True),
        (_confidence(-0.2), -1.0, False),
    ],
    ids=["no-threshold", "no-confidence", "equal", "below", "above"],
)
def test_is_unclear_only_below_a_set_threshold(
    confidence: stt.TranscriptConfidence | None, threshold: float | None, unclear: bool
) -> None:
    assert stt.is_unclear(confidence, threshold) is unclear


@pytest.mark.unit
def test_a_doubtful_transcript_raises_and_carries_its_text(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, f"me gusta el {_SENTINEL}", -1.5, -1.0)

    with pytest.raises(UnclearSpeechError) as raised:
        stt._transcribe_sync(b"\x00" * 64, None)

    assert raised.value.text == f"me gusta el {_SENTINEL}"
    assert _SENTINEL not in str(raised.value)
    assert not isinstance(raised.value, TranscriptionError | ValueError)


@pytest.mark.unit
def test_a_confident_transcript_passes_with_the_threshold_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use(monkeypatch, "me gusta el helado", -0.3, -1.0)

    assert stt._transcribe_sync(b"\x00" * 64, None) == "me gusta el helado"


@pytest.mark.unit
def test_without_a_threshold_a_doubtful_transcript_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, "me gusta el helado", -3.0, None)

    assert stt._transcribe_sync(b"\x00" * 64, None) == "me gusta el helado"


@pytest.mark.unit
def test_an_echo_is_discarded_before_the_confidence_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, _PROMPT, -3.0, -1.0)

    assert stt._transcribe_sync(b"\x00" * 64, None) == ""


@pytest.mark.unit
def test_the_confidence_record_has_numbers_and_no_text(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _use(monkeypatch, f"me gusta el {_SENTINEL}", -0.3, -1.0)

    with caplog.at_level(logging.INFO, logger="server.stt"):
        stt._transcribe_sync(b"\x00" * 64, None)

    records = [r for r in caplog.records if getattr(r, "event", None) == "stt.confidence"]
    assert len(records) == 1
    record = records[0]
    assert record.avg_logprob == pytest.approx(-0.3)  # type: ignore[attr-defined]  # log extra
    assert record.no_speech_prob == pytest.approx(0.1)  # type: ignore[attr-defined]  # log extra
    assert record.compression_ratio == pytest.approx(1.2)  # type: ignore[attr-defined]  # log extra
    assert record.temperature == pytest.approx(0.0)  # type: ignore[attr-defined]  # log extra
    assert record.segments == 1  # type: ignore[attr-defined]  # log extra
    assert record.clip_s == pytest.approx(1.3)  # type: ignore[attr-defined]  # log extra
    assert record.after_vad_s == pytest.approx(1.0)  # type: ignore[attr-defined]  # log extra
    assert record.unclear is False  # type: ignore[attr-defined]  # log extra
    assert _SENTINEL not in caplog.text


@pytest.mark.unit
async def test_the_unclear_error_crosses_the_executor_to_the_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use(monkeypatch, f"me gusta el {_SENTINEL}", -1.5, -1.0)

    with pytest.raises(UnclearSpeechError) as raised:
        await stt.transcribe(b"\x00" * 64)  # the real coroutine and thread pool, a fake model

    assert raised.value.text == f"me gusta el {_SENTINEL}"
