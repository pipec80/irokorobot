"""Frozen CPU speaker-embedding adapter (Plan 0053, PC-3B).

The only place the runtime loads a speaker model. Reproduces Plan 0047's frozen
contract exactly — SpeechBrain 1.1.1 EncoderClassifier, the pinned revision,
CPU, `samples / 32768.0` preprocessing, 192-d output — but reads the model
identity from `settings` instead of hardcoding it, because runtime code may not
hardcode a model name. Every heavy import is deferred, so a server with
`SPEAKER_AUTHENTICATION_ENABLED=false` never imports torch.

Inference is CPU-bound (measured p50 431 / p95 536 ms per real clip, Plan
0047) and runs in a dedicated bounded executor, exactly like
`vision/faces.py`'s face detection — never inline on the async event loop,
which this process shares with every other concurrent request
(`UVICORN_WORKERS=1`, ADR-0010).

Audio contract: WAV, 16 000 Hz, mono, signed int16. No cloud inference
(ADR-0004). A returned vector is untrusted identity evidence, never
authorization.
"""

from concurrent.futures import ThreadPoolExecutor
from functools import partial
import io
import logging
import time
from typing import Any, Final
import wave

import numpy as np

from server.audio_contract import validate_wav_contract
from server.exceptions import AudioContractError
from server.request_context import run_in_executor_with_context
from server.settings import settings

logger = logging.getLogger(__name__)

_INT16_FULL_SCALE: Final = 32768.0
_EMBEDDING_DIM: Final = 192
_SAMPLE_RATE: Final = 16_000
# Mean absolute sample value below which the clip is treated as silence. A
# contract-perfect silent WAV embeds like any other and would otherwise be
# compared against the centroid (Review Focus 1).
_MIN_MEAN_ABS_AMPLITUDE: Final = 200.0

# CPU speaker inference is not thread-safe per encoder instance and would
# block the event loop if run inline — serialize it on its own bounded pool,
# exactly like `vision/faces.py`'s `_executor`. A dedicated pool, not the
# loop's default: the STT/TTS/face paths each already have their own.
_executor = ThreadPoolExecutor(max_workers=1)

# No `ANN401` noqa here: that rule fires on a dynamically-typed function
# parameter or return annotation, not on a bare module-level variable — an
# unused noqa trips `RUF100`. `vision/faces.py:36`'s equivalent
# (`_analyzer: Any = None`) carries none either; mirror it exactly.
# `Any`: speechbrain ships no type stubs, so the encoder has no importable type.
_encoder: Any | None = None
# `time.monotonic()` of the last failed model load, or `None`. While it is
# younger than `settings.speaker_model_retry_cooldown_s` the loader refuses to
# retry, so a broken model is not re-read from disk on every protected turn.
_load_failed_at: float | None = None


class SpeakerBackendError(Exception):
    """The speaker backend could not produce an embedding.

    Every exception in `server.exceptions` (including `VisionError`, this
    module's closest sibling) inherits directly from `Exception` — there is
    no shared `ServerError` base in this codebase to subclass.
    """


def model_id() -> str:
    """Return the configured frozen ``model@revision`` identifier."""
    return f"{settings.speaker_model}@{settings.speaker_model_revision}"


def has_voiced_energy(wav_bytes: bytes) -> bool:
    """Return whether the clip carries more than background-level energy.

    Pure and CPU-light (one NumPy pass over already-decoded samples) — stays
    synchronous and is never dispatched to the executor, unlike `embed_wav`.

    Args:
        wav_bytes: Raw WAV bytes — 16 000 Hz, mono, signed int16.

    Returns:
        `False` for a clip whose mean absolute amplitude is at or below the
        silence floor (which must never be verified against a voiceprint),
        or that fails to decode at all — see `_safe_decode`.
    """
    samples = _safe_decode(wav_bytes)
    if samples is None:
        return False
    # Remove the mean first: a flat DC offset is not speech but has a large mean |x|.
    centered = samples - float(np.mean(samples))
    return bool(np.mean(np.abs(centered)) > _MIN_MEAN_ABS_AMPLITUDE / _INT16_FULL_SCALE)


def meets_verification_duration(wav_bytes: bytes) -> bool:
    """Return whether the clip is long enough to attempt verification at all.

    A code reviewer's finding (A6): `speaker_min_enrollment_s` bounds
    enrolment only. Without a separate floor here, a short but loud clip
    passes `has_voiced_energy` and gets embedded regardless — territory
    Plan 0047 never measured (its shortest real clips were 3-5 s).

    Args:
        wav_bytes: Raw WAV bytes — 16 000 Hz, mono, signed int16.

    Returns:
        `False` when the clip is shorter than
        `settings.speaker_min_verification_s`, or fails to decode at all.
    """
    samples = _safe_decode(wav_bytes)
    if samples is None:
        return False
    return len(samples) / _SAMPLE_RATE >= settings.speaker_min_verification_s


async def embed_wav(wav_bytes: bytes) -> np.ndarray:
    """Embed one contract WAV into a 192-d speaker vector on CPU.

    The audio-contract check runs inline (microseconds, pure Python) so a
    malformed WAV fails fast without consuming an executor slot; the actual
    CPU-bound inference runs on `_executor` via
    `run_in_executor_with_context`, off the event loop.

    Args:
        wav_bytes: Raw WAV bytes — 16 000 Hz, mono, signed int16.

    Returns:
        A 1-D `np.ndarray` of exactly 192 finite floats.

    Raises:
        AudioContractError: If the bytes break the audio contract, including
            a header that passes `validate_wav_contract` but whose data chunk
            fails to decode (that validator checks the header only, never
            the full payload — a code reviewer's finding, round 2 of A4) or
            decodes to a byte count `np.frombuffer` cannot reshape into
            int16 samples (round 3: a truncated data chunk raises `ValueError`
            here, not `wave.Error` — both are caught).
        SpeakerBackendError: If the model cannot be loaded, its cached files
            do not match the pinned revision, or it returns a non-finite,
            wrong-length or all-zero vector.
    """
    validate_wav_contract(wav_bytes, max_duration_s=settings.max_audio_duration_s)
    try:
        wave_f32 = _decode(wav_bytes)
    except (wave.Error, ValueError) as exc:
        raise AudioContractError("Audio failed to decode past its header") from exc
    return await run_in_executor_with_context(_executor, partial(_embed_sync, wave_f32))


def _embed_sync(wave_f32: np.ndarray) -> np.ndarray:
    """Run the frozen forward pass on the executor thread — never call directly."""
    try:
        encoder = _load_encoder()
        import torch  # noqa: PLC0415 -- deferred so the flag-off path never imports torch

        tensor = torch.from_numpy(wave_f32).unsqueeze(0)
        with torch.inference_mode():
            output = encoder.encode_batch(wavs=tensor, wav_lens=None, normalize=False)
        vector = np.asarray(output.squeeze().detach().cpu().numpy(), dtype=np.float32)
    except Exception as exc:
        # (Review Focus 4) can raise almost anything: a hyperpyyaml parse
        # error, a torch deserialization error, or something neither names.
        # The Global Constraint is "every failure produces `unknown`; no path
        # raises to the caller" — a narrower tuple risks exactly the escape
        # that constraint forbids, so this is the one deliberate broad catch
        # in the plan, immediately re-typed into `SpeakerBackendError`.
        raise SpeakerBackendError("Speaker backend unavailable") from exc
    if vector.shape != (_EMBEDDING_DIM,) or not np.isfinite(vector).all() or not vector.any():
        raise SpeakerBackendError(f"Speaker backend returned an unusable vector {vector.shape}")
    return vector


def _decode(wav_bytes: bytes) -> np.ndarray:
    """Decode a contract WAV to float32 in [-1.0, 1.0), as Plan 0047 froze it.

    Raises:
        wave.Error: If the data chunk fails to decode past the header that
            `validate_wav_contract` already checked.
        ValueError: If `wave` returns a frame buffer `np.frombuffer` cannot
            reshape into whole int16 samples — a truncated data chunk with
            an odd byte count raises this, not `wave.Error` (round 3: an
            earlier version of this module only caught `wave.Error`,
            verified empirically to be the wrong/incomplete type by actually
            calling `np.frombuffer` on an odd-length buffer). Neither
            exception is caught here; callers decide what it means for
            them (`embed_wav` re-raises typed, `_safe_decode` swallows it).
    """
    with wave.open(io.BytesIO(wav_bytes), "rb") as handle:
        frames = handle.readframes(handle.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / _INT16_FULL_SCALE


def _safe_decode(wav_bytes: bytes) -> np.ndarray | None:
    """Decode for the pure gate functions, never raising.

    `has_voiced_energy`/`meets_verification_duration` gate whether
    verification is even attempted; a clip that cannot be measured is
    treated the same as one that fails the gate (`None` -> the caller
    returns `False`) rather than adding a fourth exception type to the
    resolver's boundary for what is, here, just "cannot assess."
    """
    try:
        return _decode(wav_bytes)
    except (wave.Error, ValueError):
        return None


def _load_encoder() -> Any:  # noqa: ANN401 -- speechbrain ships no type stubs
    """Return the process-wide encoder, building it once and backing off on failure.

    Runs on the executor thread (called only from `_embed_sync`), so the
    first, slow load never blocks the event loop either. After a failed load
    no new attempt is made for `settings.speaker_model_retry_cooldown_s`
    seconds; a later attempt that succeeds clears the failure.

    Raises:
        SpeakerBackendError: If the pinned revision is not present in the
            local Hugging Face cache offline, or a load failed too recently.
    """
    global _encoder, _load_failed_at  # noqa: PLW0603 -- one process-wide model
    if _encoder is not None:
        return _encoder
    if (
        _load_failed_at is not None
        and time.monotonic() - _load_failed_at < settings.speaker_model_retry_cooldown_s
    ):
        raise SpeakerBackendError("Speaker model load failed recently; not retrying yet")
    try:
        _encoder = _build_encoder()
    except Exception:
        _load_failed_at = time.monotonic()
        raise
    _load_failed_at = None
    return _encoder


def _build_encoder() -> Any:  # noqa: ANN401 -- speechbrain ships no type stubs
    """Construct the frozen encoder, offline, on CPU.

    Raises:
        SpeakerBackendError: If the pinned revision is not present in the
            local Hugging Face cache offline.
    """
    from speechbrain.inference.speaker import EncoderClassifier  # noqa: PLC0415 -- deferred
    from speechbrain.utils.fetching import FetchConfig, LocalStrategy  # noqa: PLC0415 -- deferred

    cache_dir = settings.speaker_model_cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Loading speaker model %s (CPU, offline)", model_id())
    try:
        return EncoderClassifier.from_hparams(
            source=settings.speaker_model,
            savedir=str(cache_dir),
            run_opts={"device": "cpu"},
            local_strategy=LocalStrategy.COPY,  # SYMLINK breaks on Windows without Dev Mode
            fetch_config=FetchConfig(
                revision=settings.speaker_model_revision,
                allow_network=False,
                # `overwrite=True` is the fix for a code reviewer's Important
                # finding (A2): speechbrain's `fetch()` returns a file
                # already present at `savedir` AS-IS, with NO revision check
                # at all, whenever `overwrite`/`allow_updates` are both
                # false (verified by reading the installed
                # `speechbrain/utils/fetching.py`) — so a stale or
                # wrong-revision `savedir` would silently keep being trusted
                # forever. `overwrite=True` forces every load to re-resolve
                # through `huggingface_hub.hf_hub_download(revision=...,
                # local_files_only=True)` — the SAME offline, revision-pinned
                # lookup the Plan 0047 study itself verified with
                # `_assert_resolved_revision` — which raises if that exact
                # revision is not cached, instead of trusting `savedir`
                # blindly. It never touches the network (`allow_network`
                # stays `False`) and only re-copies into `savedir` when the
                # resolved source changed, so `_load_encoder`'s own
                # per-process memoization keeps this a one-time cost.
                overwrite=True,
            ),
        )
    except Exception as exc:
        raise SpeakerBackendError(f"Speaker model {model_id()} is not cached offline") from exc
