"""Unit tests for the frozen runtime speaker-embedding adapter (Plan 0053,
Task 3). No real model: a typed fake encoder stands in, so CI never downloads
or loads torch weights."""

import asyncio
import io
import threading
import time
import wave

import numpy as np
import pytest
from server.exceptions import AudioContractError
from server.voice import speaker_embedding
from server.voice.speaker_embedding import SpeakerBackendError


@pytest.fixture(scope="module", autouse=True)
def _warm_torch() -> None:
    """Import torch once, outside every timed test window.

    `embed_wav` imports torch lazily inside its executor thread, and the timeout tests
    wait only 0.2 s. Without this, the first test of a cold process paid the import inside
    that window and failed depending on which tests shared the xdist worker.
    """
    pytest.importorskip("torch")


def _wav(samples: np.ndarray, *, rate: int = 16_000, channels: int = 1) -> bytes:
    """Build a WAV container around *samples* (int16)."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(samples.astype(np.int16).tobytes())
    return buffer.getvalue()


def _tone(seconds: float = 3.0, amplitude: int = 8_000) -> bytes:
    """Build a deterministic synthetic 'utterance' — never a human recording."""
    t = np.linspace(0.0, seconds, int(16_000 * seconds), endpoint=False)
    return _wav((amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.int16))


class _FakeOutput:
    """Mirrors the tensor shape the real encoder returns."""

    def __init__(self, vector: np.ndarray) -> None:
        self._vector = vector

    def squeeze(self) -> "_FakeOutput":
        return self

    def detach(self) -> "_FakeOutput":
        return self

    def cpu(self) -> "_FakeOutput":
        return self

    def numpy(self) -> np.ndarray:
        return self._vector


class _FakeEncoder:
    """Stands in for speechbrain's EncoderClassifier."""

    def __init__(self, vector: np.ndarray | None = None) -> None:
        self.calls = 0
        self._vector = np.ones(192, dtype=np.float32) if vector is None else vector

    def encode_batch(
        self,
        wavs: object,  # noqa: ARG002 -- fake ignores the tensor
        wav_lens: object = None,  # noqa: ARG002
        normalize: bool = False,  # noqa: ARG002
    ) -> object:
        self.calls += 1
        return _FakeOutput(self._vector)


async def test_embed_returns_192_finite_floats(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(speaker_embedding, "_load_encoder", _FakeEncoder)
    vector = await speaker_embedding.embed_wav(_tone())
    assert vector.shape == (192,)
    assert np.isfinite(vector).all()


async def test_non_contract_wav_never_reaches_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    encoder = _FakeEncoder()
    monkeypatch.setattr(speaker_embedding, "_load_encoder", lambda: encoder)
    with pytest.raises(AudioContractError):
        await speaker_embedding.embed_wav(_wav(np.zeros(16_000), rate=44_100))
    assert encoder.calls == 0


async def test_a_broken_loader_raises_the_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Review Focus 4: corrupt or half-downloaded model files must degrade."""

    def _explode() -> object:
        raise RuntimeError("PytorchStreamReader failed reading zip archive")

    monkeypatch.setattr(speaker_embedding, "_load_encoder", _explode)
    with pytest.raises(SpeakerBackendError):
        await speaker_embedding.embed_wav(_tone())


async def test_embedding_runs_off_the_event_loop() -> None:
    """A code reviewer's Critical finding: inference must not block the loop.

    A fake encoder that blocks for 200ms (well above real inference time)
    must not delay a concurrent coroutine that yields immediately — proving
    the CPU-bound work actually left the event loop thread, not merely that
    the function is declared `async def`.
    """

    class _SlowEncoder:
        def encode_batch(
            self,
            wavs: object,  # noqa: ARG002 -- fake ignores the tensor
            wav_lens: object = None,  # noqa: ARG002
            normalize: bool = False,  # noqa: ARG002
        ) -> object:
            time.sleep(0.2)  # simulates real CPU-bound inference, off-thread
            return _FakeOutput(np.ones(192, dtype=np.float32))

    async def _tick_counter(stop: asyncio.Event) -> int:
        ticks = 0
        while not stop.is_set():
            await asyncio.sleep(0.01)
            ticks += 1
        return ticks

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(speaker_embedding, "_load_encoder", _SlowEncoder)
    stop = asyncio.Event()
    counter = asyncio.ensure_future(_tick_counter(stop))
    await speaker_embedding.embed_wav(_tone())
    stop.set()
    ticks = await counter
    monkeypatch.undo()
    # A blocked loop would let ~0 ticks fire during the 200ms sleep; a
    # genuinely off-loop executor lets several fire concurrently.
    assert ticks >= 5


def test_near_silence_has_no_voiced_energy() -> None:
    """Review Focus 1: a format-perfect silent WAV must never verify."""
    assert speaker_embedding.has_voiced_energy(_wav(np.zeros(48_000))) is False
    assert speaker_embedding.has_voiced_energy(_tone()) is True


@pytest.mark.parametrize(
    "seconds, expected",
    [
        (0.5, False),  # below the floor
        (1.5, True),  # exactly at the floor — the comparison is `>=`
        (3.0, True),  # above the floor
    ],
)
def test_the_duration_floor_at_below_and_above_the_boundary(
    monkeypatch: pytest.MonkeyPatch, seconds: float, expected: bool
) -> None:
    """Finding A6 (round 2): the floor's own boundary must be tested, not
    just one point comfortably below and one comfortably above it."""
    monkeypatch.setattr(speaker_embedding.settings, "speaker_min_verification_s", 1.5)
    assert speaker_embedding.meets_verification_duration(_tone(seconds=seconds)) is expected


def test_a_short_loud_clip_still_fails_the_duration_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding A6: energy alone is not enough — a clip below
    speaker_min_verification_s must be rejected even with plenty of energy."""
    monkeypatch.setattr(speaker_embedding.settings, "speaker_min_verification_s", 1.5)
    short_loud = _tone(seconds=0.5)
    assert speaker_embedding.has_voiced_energy(short_loud) is True
    assert speaker_embedding.meets_verification_duration(short_loud) is False


def test_a_clip_that_fails_to_decode_fails_both_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Round 2 of A4: `validate_wav_contract` checks only the header; a data
    chunk that fails to decode past it must degrade the gates to `False`,
    never raise past them."""

    def _explode(_wav_bytes: bytes) -> np.ndarray:
        raise wave.Error("truncated data chunk")

    monkeypatch.setattr(speaker_embedding, "_decode", _explode)
    assert speaker_embedding.has_voiced_energy(b"irrelevant") is False
    assert speaker_embedding.meets_verification_duration(b"irrelevant") is False


async def test_embed_wav_reports_a_late_decode_failure_as_audio_contract_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round 2 of A4: the same failure inside `embed_wav` itself must not
    escape as a raw `wave.Error` — it is re-typed to `AudioContractError`,
    the type this function's own docstring already promised."""

    def _explode(_wav_bytes: bytes) -> np.ndarray:
        raise wave.Error("truncated data chunk")

    monkeypatch.setattr(speaker_embedding, "_decode", _explode)
    with pytest.raises(AudioContractError):
        await speaker_embedding.embed_wav(_tone())


def _genuinely_truncated_wav() -> bytes:
    """Chop exactly the last byte off a real WAV's data chunk.

    Round 3: the two tests above only ever mock `_decode` to raise
    `wave.Error` — they never prove a REAL corrupted payload hits this path,
    and a real one does not raise `wave.Error` at all. `wave.open()` and
    `readframes()` tolerate a short read silently (confirmed empirically:
    they return 31999 bytes instead of the declared 32000 for a 1-second
    clip missing its last byte); the actual failure is `np.frombuffer`
    raising `ValueError: buffer size must be a multiple of element size`
    on the now-odd byte count. Both code paths need this real case, not
    just the mocked one.
    """
    return _tone()[:-1]


def test_a_genuinely_truncated_wav_fails_both_gates() -> None:
    """Round 3, the real (non-mocked) counterpart to the test above."""
    truncated = _genuinely_truncated_wav()
    assert speaker_embedding.has_voiced_energy(truncated) is False
    assert speaker_embedding.meets_verification_duration(truncated) is False


async def test_embed_wav_reports_a_real_truncation_as_audio_contract_error() -> None:
    """Round 3, the real (non-mocked) counterpart to the mocked test above."""
    with pytest.raises(AudioContractError):
        await speaker_embedding.embed_wav(_genuinely_truncated_wav())


def test_model_id_comes_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(speaker_embedding.settings, "speaker_model", "m")
    monkeypatch.setattr(speaker_embedding.settings, "speaker_model_revision", "r")
    assert speaker_embedding.model_id() == "m@r"


def test_a_constant_dc_offset_is_not_voiced_energy() -> None:
    """Review M-5: `mean(|x|)` counted a flat offset as energy; the mean must go first."""
    flat = _wav(np.full(48_000, 3_000, dtype=np.int16))
    assert speaker_embedding.has_voiced_energy(flat) is False


class _FakeClock:
    """Controllable stand-in for `time.monotonic`."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


def _fresh_loader_state(monkeypatch: pytest.MonkeyPatch) -> _FakeClock:
    clock = _FakeClock()
    monkeypatch.setattr(speaker_embedding, "_encoder", None)
    monkeypatch.setattr(speaker_embedding, "_load_failed_at", None)
    monkeypatch.setattr(speaker_embedding.time, "monotonic", clock)
    monkeypatch.setattr(speaker_embedding.settings, "speaker_model_retry_cooldown_s", 60.0)
    return clock


def test_a_failed_model_load_is_not_retried_during_the_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review M-3: a broken model must not be re-read from disk on every protected turn."""
    clock = _fresh_loader_state(monkeypatch)
    attempts = 0

    def _fail() -> object:
        nonlocal attempts
        attempts += 1
        raise SpeakerBackendError("not cached offline")

    monkeypatch.setattr(speaker_embedding, "_build_encoder", _fail)

    with pytest.raises(SpeakerBackendError):
        speaker_embedding._load_encoder()
    clock.now += 59.0
    with pytest.raises(SpeakerBackendError):
        speaker_embedding._load_encoder()

    assert attempts == 1


def test_the_load_is_retried_once_the_cooldown_has_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _fresh_loader_state(monkeypatch)
    outcomes: list[object] = [SpeakerBackendError("down"), "encoder"]

    def _build() -> object:
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(speaker_embedding, "_build_encoder", _build)

    with pytest.raises(SpeakerBackendError):
        speaker_embedding._load_encoder()
    clock.now += 61.0

    assert speaker_embedding._load_encoder() == "encoder"
    assert speaker_embedding._load_failed_at is None


def test_a_loaded_encoder_is_reused_without_rebuilding(monkeypatch: pytest.MonkeyPatch) -> None:
    _fresh_loader_state(monkeypatch)
    builds = 0

    def _build() -> object:
        nonlocal builds
        builds += 1
        return "encoder"

    monkeypatch.setattr(speaker_embedding, "_build_encoder", _build)

    assert speaker_embedding._load_encoder() == "encoder"
    assert speaker_embedding._load_encoder() == "encoder"
    assert builds == 1


class _BlockingEncoder:
    """Blocks inside `encode_batch` until released — a hung backend."""

    def __init__(self) -> None:
        self.release = threading.Event()
        self.calls = 0

    def encode_batch(
        self,
        wavs: object,  # noqa: ARG002 -- fake ignores the tensor
        wav_lens: object = None,  # noqa: ARG002
        normalize: bool = False,  # noqa: ARG002
    ) -> object:
        self.calls += 1
        self.release.wait(timeout=10)
        return _FakeOutput(np.ones(192, dtype=np.float32))


async def test_a_hung_backend_times_out_instead_of_blocking_the_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review M-3: nothing bounded how long a protected turn waited for the embedding."""
    encoder = _BlockingEncoder()
    monkeypatch.setattr(speaker_embedding, "_load_encoder", lambda: encoder)
    monkeypatch.setattr(speaker_embedding, "_embedding_stuck", False)
    monkeypatch.setattr(speaker_embedding.settings, "speaker_embed_timeout_s", 0.2)
    try:
        started = time.monotonic()
        with pytest.raises(SpeakerBackendError):
            await speaker_embedding.embed_wav(_tone())
        assert time.monotonic() - started < 2.0
    finally:
        encoder.release.set()
        await _wait_until_not_stuck()


async def test_while_a_timed_out_embedding_still_runs_new_ones_are_refused_at_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The single worker is still busy: queueing behind it would delay every turn."""
    encoder = _BlockingEncoder()
    monkeypatch.setattr(speaker_embedding, "_load_encoder", lambda: encoder)
    monkeypatch.setattr(speaker_embedding, "_embedding_stuck", False)
    monkeypatch.setattr(speaker_embedding.settings, "speaker_embed_timeout_s", 0.2)
    try:
        with pytest.raises(SpeakerBackendError):
            await speaker_embedding.embed_wav(_tone())
        started = time.monotonic()
        with pytest.raises(SpeakerBackendError):
            await speaker_embedding.embed_wav(_tone())
        assert time.monotonic() - started < 0.1
        assert encoder.calls == 1
    finally:
        encoder.release.set()
        await _wait_until_not_stuck()


async def test_embedding_recovers_once_the_abandoned_work_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    encoder = _BlockingEncoder()
    monkeypatch.setattr(speaker_embedding, "_load_encoder", lambda: encoder)
    monkeypatch.setattr(speaker_embedding, "_embedding_stuck", False)
    monkeypatch.setattr(speaker_embedding.settings, "speaker_embed_timeout_s", 0.2)
    with pytest.raises(SpeakerBackendError):
        await speaker_embedding.embed_wav(_tone())

    encoder.release.set()
    await _wait_until_not_stuck()
    monkeypatch.setattr(speaker_embedding.settings, "speaker_embed_timeout_s", 5.0)

    vector = await speaker_embedding.embed_wav(_tone())
    assert vector.shape == (192,)


async def _wait_until_not_stuck() -> None:
    """Let the abandoned executor call finish so it cannot leak into another test."""
    for _ in range(200):
        if not speaker_embedding._embedding_stuck:
            return
        await asyncio.sleep(0.01)
    pytest.fail("the abandoned embedding never finished")
