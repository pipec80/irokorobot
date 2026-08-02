"""Unit tests for robot.audio_capture — sounddevice mocked, RMS engine forced."""

import io
from types import TracebackType
import wave

import numpy as np
import pytest
from robot.settings import settings

from robot import audio_capture


@pytest.fixture(autouse=True)
def _force_rms_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the RMS engine — tests must not depend on a vendored ONNX model."""
    monkeypatch.setattr(settings, "vad_engine", "rms")


class _FakeSilentStream:
    """Stand-in for sd.InputStream that only ever yields silence."""

    def __init__(self, **_kwargs: object) -> None:
        self.reads = 0

    def __enter__(self) -> "_FakeSilentStream":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        return False

    def read(self, frames: int) -> tuple[np.ndarray, bool]:
        self.reads += 1
        return np.zeros((frames, 1), dtype=np.int16), False


class _FakeSpeechStream:
    """Stand-in for sd.InputStream: N silent chunks, then loud, then silent."""

    def __init__(self, silent_before: int, speech_chunks: int, silent_after: int) -> None:
        self._pattern = [0] * silent_before + [30_000] * speech_chunks + [0] * silent_after
        self._idx = 0

    def __enter__(self) -> "_FakeSpeechStream":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        return False

    def read(self, frames: int) -> tuple[np.ndarray, bool]:
        value = self._pattern[min(self._idx, len(self._pattern) - 1)]
        self._idx += 1
        return np.full((frames, 1), value, dtype=np.int16), False


@pytest.mark.unit
async def test_capture_utterance_times_out_and_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no speech onset, capture must give up after max_wait_s (P0-3)."""
    fake = _FakeSilentStream()
    monkeypatch.setattr(audio_capture.sd, "InputStream", lambda **_kwargs: fake)

    result = await audio_capture.capture_utterance(max_wait_s=1.0)

    assert result == b""
    _, _, expected_reads = audio_capture._compute_chunk_budget(1.0)
    assert fake.reads == expected_reads


@pytest.mark.unit
async def test_capture_utterance_includes_preroll(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pre-roll chunks captured before onset must be prepended to the utterance (R1)."""
    monkeypatch.setattr(settings, "vad_preroll_ms", 64)  # 2 chunks of 32 ms
    monkeypatch.setattr(settings, "vad_silence_ms", 64)  # close after 2 silent chunks
    fake = _FakeSpeechStream(silent_before=5, speech_chunks=3, silent_after=3)
    monkeypatch.setattr(audio_capture.sd, "InputStream", lambda **_kwargs: fake)

    result = await audio_capture.capture_utterance(max_wait_s=30.0)

    assert result != b""
    with wave.open(io.BytesIO(result)) as wf:
        raw = wf.readframes(wf.getnframes())
    samples = np.frombuffer(raw, dtype=np.int16)
    preroll_samples = audio_capture._CHUNK_FRAMES * 2
    assert samples[:preroll_samples].max() == 0  # pre-roll is the silent chunks before onset
    assert samples.max() == 30_000  # the loud onset itself is captured too
