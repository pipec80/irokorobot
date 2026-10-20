"""Unit tests for robot.audio_capture — sounddevice mocked, RMS engine forced."""

import hashlib
import io
from types import TracebackType
import wave

import numpy as np
from pydantic import ValidationError
import pytest
from robot.settings import Settings, settings

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
    policy = audio_capture.SegmentationPolicy.from_settings()
    _, _, expected_reads = audio_capture._policy_chunks(policy, 1.0)
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
    preroll_samples = audio_capture.CHUNK_FRAMES * 2
    assert samples[:preroll_samples].max() == 0  # pre-roll is the silent chunks before onset
    assert samples.max() == 30_000  # the loud onset itself is captured too


def _wav_samples(wav: bytes) -> np.ndarray:
    """Decode WAV bytes (16 kHz mono int16) back to a sample array."""
    with wave.open(io.BytesIO(wav)) as wf:
        return np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)


@pytest.fixture
def _short_vad_timings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Normal close after 2 silent chunks (64 ms), no pre-roll, to keep streams tiny."""
    monkeypatch.setattr(settings, "vad_preroll_ms", 0)
    monkeypatch.setattr(settings, "vad_silence_ms", 64)


class _FakePatternStream(_FakeSpeechStream):
    """Stand-in for sd.InputStream with an explicit loud/silent chunk pattern."""

    def __init__(self, pattern: list[int]) -> None:
        super().__init__(silent_before=0, speech_chunks=0, silent_after=0)
        self._pattern = pattern


_REPLY_CLOSE_MS = 160  # 5 chunks of 32 ms


@pytest.mark.unit
@pytest.mark.usefixtures("_short_vad_timings")
async def test_reply_capture_keeps_a_pause_inside_the_speech_in_one_clip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A gap longer than the normal close but shorter than the reply close stays one clip."""
    pattern = [30_000] * 3 + [0] * 3 + [30_000] * 3 + [0] * 20
    monkeypatch.setattr(
        audio_capture.sd, "InputStream", lambda **_kwargs: _FakePatternStream(pattern)
    )

    result = await audio_capture.capture_utterance(close_silence_ms=_REPLY_CLOSE_MS)

    samples = _wav_samples(result)
    chunks = samples.reshape(-1, audio_capture.CHUNK_FRAMES)
    loud = (chunks.max(axis=1) == 30_000).sum()
    assert loud == 6  # both speech parts, one clip
    assert len(chunks) == 3 + 3 + 3 + 2  # speech, the inner pause, speech, normal-length tail


@pytest.mark.unit
@pytest.mark.usefixtures("_short_vad_timings")
async def test_reply_capture_uploads_no_more_trailing_silence_than_a_normal_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The longer reply close must not make the uploaded clip longer than a normal one."""
    pattern = [30_000] * 3 + [0] * 20
    monkeypatch.setattr(
        audio_capture.sd, "InputStream", lambda **_kwargs: _FakePatternStream(pattern)
    )
    normal = await audio_capture.capture_utterance()
    monkeypatch.setattr(
        audio_capture.sd, "InputStream", lambda **_kwargs: _FakePatternStream(pattern)
    )

    reply = await audio_capture.capture_utterance(close_silence_ms=_REPLY_CLOSE_MS)

    assert normal != b""
    assert len(_wav_samples(reply)) == len(_wav_samples(normal))


@pytest.mark.unit
async def test_reply_capture_without_speech_returns_empty_after_the_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Silence for the whole wait gives b"" and stops reading at the wait budget."""
    fake = _FakeSilentStream()
    monkeypatch.setattr(audio_capture.sd, "InputStream", lambda **_kwargs: fake)

    result = await audio_capture.capture_utterance(max_wait_s=1.0, close_silence_ms=_REPLY_CLOSE_MS)

    assert result == b""
    policy = audio_capture.SegmentationPolicy.from_settings(_REPLY_CLOSE_MS)
    _, _, expected_reads = audio_capture._policy_chunks(policy, 1.0)
    assert fake.reads == expected_reads


@pytest.mark.unit
@pytest.mark.usefixtures("_short_vad_timings")
@pytest.mark.parametrize("close_ms", [64, 32], ids=["equal-to-normal", "shorter-than-normal"])
async def test_close_not_longer_than_the_normal_close_is_not_trimmed(
    monkeypatch: pytest.MonkeyPatch, close_ms: int
) -> None:
    """A close <= vad_silence_ms trims nothing and equals a normal capture with that close."""
    pattern = [30_000] * 3 + [0] * 20
    monkeypatch.setattr(
        audio_capture.sd, "InputStream", lambda **_kwargs: _FakePatternStream(pattern)
    )
    overridden = await audio_capture.capture_utterance(close_silence_ms=close_ms)
    monkeypatch.setattr(settings, "vad_silence_ms", close_ms)
    monkeypatch.setattr(
        audio_capture.sd, "InputStream", lambda **_kwargs: _FakePatternStream(pattern)
    )

    normal_with_that_close = await audio_capture.capture_utterance()

    silent_tail_chunks = audio_capture._ms_to_chunks(close_ms)
    assert overridden != b""
    assert overridden == normal_with_that_close
    assert len(_wav_samples(overridden)) == (3 + silent_tail_chunks) * audio_capture.CHUNK_FRAMES


@pytest.mark.unit
@pytest.mark.usefixtures("_short_vad_timings")
async def test_capture_without_an_override_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """close_silence_ms=None is the omitted keyword: same clip, normal close and no trim."""
    pattern = [30_000] * 3 + [0] * 3 + [30_000] * 3 + [0] * 20
    monkeypatch.setattr(
        audio_capture.sd, "InputStream", lambda **_kwargs: _FakePatternStream(pattern)
    )
    omitted = await audio_capture.capture_utterance()
    monkeypatch.setattr(
        audio_capture.sd, "InputStream", lambda **_kwargs: _FakePatternStream(pattern)
    )

    explicit_none = await audio_capture.capture_utterance(close_silence_ms=None)

    assert explicit_none == omitted
    assert len(_wav_samples(omitted)) == (3 + 2) * audio_capture.CHUNK_FRAMES  # closed in the gap
    assert audio_capture.SegmentationPolicy.from_settings() == (
        audio_capture.SegmentationPolicy.from_settings(None)
    )


# Plan 0069 Task 3: the same segmentation over any chunk source, and an upload tail.
# The two digests were taken from `capture_utterance` before this change (pre-roll 400 ms,
# close 800 ms, reply close 1600 ms) on this pattern: a 1.12 s pause splits a normal capture
# and stays inside a reply capture.
_PIN_PATTERN = [0] * 20 + [30_000] * 30 + [0] * 35 + [30_000] * 20 + [0] * 60
_PIN_NORMAL_SHA256 = "79c88a3c6c234885b1111d2b6cf25e89c00920936047dd3110c621c6cc6b419b"
_PIN_REPLY_SHA256 = "c5fa2b7ef826f9278356fd6b87ef990b83096d5bd04b6a0f99e915f8e586bf46"


class _ListSource:
    """A chunk source over a fixed loud/silent pattern; silence once it runs out."""

    def __init__(self, pattern: list[int]) -> None:
        self._pattern = pattern
        self.reads = 0

    def read(self, frames: int) -> tuple[np.ndarray, bool]:
        value = self._pattern[self.reads] if self.reads < len(self._pattern) else 0
        self.reads += 1
        return np.full((frames, 1), value, dtype=np.int16), False


class _LoudVad:
    """A scripted VAD: a chunk is speech when it is not silent."""

    def detect(self, chunk: np.ndarray) -> bool:
        return bool(np.abs(chunk).max() > 0)


@pytest.fixture
def _today_timings(monkeypatch: pytest.MonkeyPatch) -> None:
    """The shipped defaults, whatever a local .env says."""
    monkeypatch.setattr(settings, "vad_preroll_ms", 400)
    monkeypatch.setattr(settings, "vad_silence_ms", 800)
    monkeypatch.setattr(settings, "vad_upload_tail_ms", None)


def _silent_tail_chunks(wav: bytes) -> int:
    chunks = _wav_samples(wav).reshape(-1, audio_capture.CHUNK_FRAMES)
    loud = np.flatnonzero(chunks.max(axis=1) > 0)
    return len(chunks) - 1 - int(loud[-1])


@pytest.mark.unit
@pytest.mark.usefixtures("_today_timings")
@pytest.mark.parametrize(
    "close_ms, digest",
    [(None, _PIN_NORMAL_SHA256), (1600, _PIN_REPLY_SHA256)],
    ids=["normal", "reply"],
)
async def test_segment_utterance_gives_todays_bytes_by_default(
    close_ms: int | None, digest: str
) -> None:
    policy = audio_capture.SegmentationPolicy.from_settings(close_ms)

    clip = await audio_capture.segment_utterance(_ListSource(_PIN_PATTERN), _LoudVad(), policy)

    assert hashlib.sha256(clip).hexdigest() == digest


@pytest.mark.unit
@pytest.mark.usefixtures("_today_timings")
@pytest.mark.parametrize("close_ms", [None, 1600], ids=["normal", "reply"])
async def test_capture_utterance_still_gives_todays_bytes(
    monkeypatch: pytest.MonkeyPatch, close_ms: int | None
) -> None:
    monkeypatch.setattr(audio_capture, "create_vad", lambda _engine: _LoudVad())
    monkeypatch.setattr(
        audio_capture.sd, "InputStream", lambda **_kwargs: _FakePatternStream(_PIN_PATTERN)
    )

    clip = await audio_capture.capture_utterance(close_silence_ms=close_ms)

    expected = _PIN_NORMAL_SHA256 if close_ms is None else _PIN_REPLY_SHA256
    assert hashlib.sha256(clip).hexdigest() == expected


@pytest.mark.unit
@pytest.mark.parametrize("close_ms", [800, 1600], ids=["normal", "reply"])
async def test_a_short_upload_tail_keeps_only_that_much_silence(close_ms: int) -> None:
    policy = audio_capture.SegmentationPolicy(
        preroll_ms=400, close_silence_ms=close_ms, upload_tail_ms=300
    )
    pattern = [0] * 20 + [30_000] * 30 + [0] * 80

    clip = await audio_capture.segment_utterance(_ListSource(pattern), _LoudVad(), policy)

    assert _silent_tail_chunks(clip) == round(0.3 / 0.032)


@pytest.mark.unit
async def test_a_tail_longer_than_the_collected_silence_cuts_nothing() -> None:
    pattern = [0] * 20 + [30_000] * 30 + [0] * 80
    longer = audio_capture.SegmentationPolicy(
        preroll_ms=400, close_silence_ms=800, upload_tail_ms=1000
    )

    clip = await audio_capture.segment_utterance(_ListSource(pattern), _LoudVad(), longer)

    assert _silent_tail_chunks(clip) == audio_capture._ms_to_chunks(800)


@pytest.mark.unit
async def test_a_silent_source_gives_no_clip_after_the_wait() -> None:
    source = _ListSource([])
    policy = audio_capture.SegmentationPolicy(
        preroll_ms=400, close_silence_ms=800, upload_tail_ms=800
    )

    clip = await audio_capture.segment_utterance(source, _LoudVad(), policy, max_wait_s=1.0)

    assert clip == b""
    assert source.reads == round(1.0 / 0.032)


@pytest.mark.unit
def test_the_upload_tail_defaults_to_the_closing_silence_and_refuses_under_300_ms() -> None:
    assert Settings(_env_file=None).vad_upload_tail_ms is None  # type: ignore[call-arg]  # code default
    with pytest.raises(ValidationError):
        Settings(_env_file=None, vad_upload_tail_ms=200)  # type: ignore[call-arg]  # init kwargs
