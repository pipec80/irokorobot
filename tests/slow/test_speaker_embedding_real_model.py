"""One real-model check (Plan 0053, Task 3) — skipped when the frozen
revision is not cached offline on this machine. Synthetic audio only; never a
human recording."""

import io
import wave

import numpy as np
import pytest
from server.settings import settings
from server.voice.speaker_embedding import embed_wav, model_id

pytestmark = pytest.mark.slow


def _tone(seconds: float = 3.0, amplitude: int = 8_000) -> bytes:
    """Build a deterministic synthetic 'utterance' — never a human recording.

    Same construction as `tests/unit/test_speaker_embedding.py`'s helper —
    the plan's own Task 3 Step 6 snippet calls `_tone()` without defining it
    in this file; reproduced here rather than imported, so this slow test
    stays self-contained.

    Returns:
        WAV bytes — 16 000 Hz, mono, signed int16, matching the audio
        contract that `embed_wav` requires.
    """
    t = np.linspace(0.0, seconds, int(16_000 * seconds), endpoint=False)
    samples = (amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(samples.tobytes())
    return buffer.getvalue()


def _revision_is_cached_offline() -> bool:
    """Probe the standard HF cache for the pinned revision only — never a
    reason to swallow a REAL failure below.

    Round 2 of A2: an earlier draft caught bare `SpeakerBackendError` around
    the whole `embed_wav` call and skipped on any of it — but
    `SpeakerBackendError` is also `_embed_sync`'s catch-all for a genuinely
    corrupt cache, a broken `torch`/`speechbrain` install, or a real
    inference regression. That would have reported "not installed" for a
    real bug. This probe answers only "is the pinned revision cached
    offline?" — the ONE legitimate skip condition — using the exact same
    lookup `_load_encoder`'s own `overwrite=True` path performs.

    Round 3: the first version of this probe still caught bare `Exception`,
    which is the same mistake one level down — a config error (e.g. a
    malformed `HF_HOME`) or a permissions error would also report as
    "not cached" and silently skip instead of failing loud. Narrowed to the
    exact type `hf_hub_download(local_files_only=True)` raises for a
    genuinely absent local revision, confirmed by actually calling it
    against an unresolvable revision with the installed `huggingface_hub`:
    `huggingface_hub.errors.LocalEntryNotFoundError`.
    """
    from huggingface_hub import hf_hub_download  # noqa: PLC0415 -- deferred heavy import
    from huggingface_hub.errors import LocalEntryNotFoundError  # noqa: PLC0415 -- deferred

    try:
        hf_hub_download(
            settings.speaker_model,
            "hyperparams.yaml",
            revision=settings.speaker_model_revision,
            local_files_only=True,
        )
    except LocalEntryNotFoundError:
        return False
    return True


def test_a_genuinely_unresolvable_revision_is_a_legitimate_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round 3: proves the ONE case this probe is meant to swallow, using a
    revision guaranteed not to be cached (an all-zero SHA)."""
    monkeypatch.setattr(settings, "speaker_model_revision", "0" * 40)
    assert _revision_is_cached_offline() is False


def test_an_unexpected_error_is_not_swallowed_as_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round 3: a config or permissions error must fail this test loudly,
    never silently report as 'not cached, skip'."""

    def _explode(*_args: object, **_kwargs: object) -> None:
        raise OSError("permission denied reading HF_HOME")

    monkeypatch.setattr("huggingface_hub.hf_hub_download", _explode)
    with pytest.raises(OSError, match="permission denied"):
        _revision_is_cached_offline()


async def test_the_real_encoder_returns_the_frozen_shape() -> None:
    if not _revision_is_cached_offline():
        pytest.skip("frozen speaker model revision not cached offline on this machine")
    # No try/except past this point: if the revision IS cached and this
    # still raises, that is a real regression and the test must fail, not
    # skip — the exact gap the round-2 review found.
    vector = await embed_wav(_tone())
    assert vector.shape == (192,)
    assert "@" in model_id()
