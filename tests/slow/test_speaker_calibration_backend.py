"""Slow contract tests for the frozen SpeechBrain ECAPA speaker backend.

Opt-in (`uv run pytest -m slow`). They need the pinned model cached locally —
run `just speaker-calibration model-contract` once first; otherwise every test
here skips. They never assert speaker-identity quality on a synthetic tone,
only shape, finiteness, determinism and offline-after-cache behaviour.

Audio contract for every WAV here: WAV, 16 000 Hz, mono, signed int16.
"""

from __future__ import annotations

import socket

import numpy as np
import pytest

from scripts.speaker_calibration_backend import (
    _MODEL_CACHE_DIR,
    _MODEL_REVISION,
    SpeechBrainEcapaBackend as _Backend,
    _sine_wav_bytes,
    frozen_model_identity,
    load_frozen_encoder,
)

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def frozen_backend() -> _Backend:
    """Return a backend on the offline-loaded frozen encoder.

    Only a cold cache skips. Once the model is cached, a load failure (an import
    error, a revision regression) is a real failure, never a silent skip.
    """
    if not (_MODEL_CACHE_DIR / "embedding_model.ckpt").is_file():
        pytest.skip("frozen model not cached; run `just speaker-calibration model-contract`")
    return _Backend(load_frozen_encoder(allow_network=False))


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


def test_offline_load_after_cache_needs_no_network(
    frozen_backend: _Backend, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`allow_network=False` must succeed once the cache is warm - with no socket at all."""
    attempts: list[object] = []

    def _no_network(_self: socket.socket, address: object) -> None:
        attempts.append(address)
        raise ConnectionRefusedError("network blocked by the test")

    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setattr(socket.socket, "connect", _no_network)

    encoder = load_frozen_encoder(allow_network=False)

    assert encoder is not None
    assert attempts == []


def test_frozen_model_identity_names_the_pinned_revision_offline(
    frozen_backend: _Backend, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "HF_HUB_OFFLINE", "1"
    )  # what the CLI forces for every action but the warm-up

    model_id, package_version = frozen_model_identity()

    assert model_id.endswith(_MODEL_REVISION)
    assert package_version.startswith("speechbrain ")
