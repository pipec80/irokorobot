"""Slow contract tests for the frozen SpeechBrain ECAPA speaker backend.

Opt-in (`uv run pytest -m slow`). They need the pinned model cached locally —
run `just speaker-calibration model-contract` once first; otherwise every test
here skips. They never assert speaker-identity quality on a synthetic tone,
only shape, finiteness, determinism and offline-after-cache behaviour.

Audio contract for every WAV here: WAV, 16 000 Hz, mono, signed int16.
"""

from __future__ import annotations

import numpy as np
import pytest

from scripts.speaker_calibration_backend import (
    _MODEL_REVISION,
    SpeechBrainEcapaBackend as _Backend,
    _sine_wav_bytes,
    load_frozen_encoder,
)

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def frozen_backend() -> _Backend:
    """Return a backend on the offline-loaded frozen encoder, or skip."""
    try:
        encoder = load_frozen_encoder(allow_network=False)
    except Exception as exc:  # cold cache is a skip, never a suite failure
        pytest.skip(
            f"frozen model not cached; run `just speaker-calibration model-contract`: {exc}"
        )
    return _Backend(encoder)


def test_embed_returns_finite_192d_vector(frozen_backend: _Backend) -> None:
    vector = frozen_backend.embed_wav(_sine_wav_bytes(seconds=3))

    assert vector.shape == (192,)
    assert np.all(np.isfinite(vector))


def test_embed_is_repeatable(frozen_backend: _Backend) -> None:
    wav = _sine_wav_bytes(seconds=3)

    first = frozen_backend.embed_wav(wav)
    second = frozen_backend.embed_wav(wav)

    np.testing.assert_allclose(first, second, rtol=0.0, atol=1e-5)


def test_model_id_pins_the_frozen_revision(frozen_backend: _Backend) -> None:
    assert _MODEL_REVISION in frozen_backend.model_id


def test_offline_load_after_cache_needs_no_network() -> None:
    """`allow_network=False` must succeed once the cache is warm."""
    load_frozen_encoder(allow_network=False)
