"""speaker_calibration.py - Plan 0047 (PC-3A) speaker-evidence calibration study.

Three isolated layers, built one task at a time:

1. **Pure numeric harness** (Task 1): L2 normalization, reference centroid,
   cosine distance, deterministic threshold sweep, zero-observed-FAR selection
   and nearest-rank latency percentiles. No audio, model, network or disk.
2. **Private-corpus manifest and safe CLI** (Task 2, this task): strict sample
   schema (``scripts.speaker_calibration_models``), atomic manifest, WAV-contract
   validation, corpus-rule enforcement and aggregate-report rendering
   (``scripts.speaker_calibration_corpus``), and the seven-action CLI below.
3. **Frozen SpeechBrain embedding backend** - added by Task 3.

This study measures whether a local CPU speaker embedding can separate the
owner's live voice from consenting live impostors. It never enrols a production
voiceprint and never makes ``VOICE`` trusted identity evidence.

Audio contract for every WAV this module touches: WAV, 16 000 Hz, mono, int16.
"""

from __future__ import annotations

from pathlib import Path
import sys

# Direct execution (``python scripts/speaker_calibration.py``) puts ``scripts/``
# on ``sys.path[0]``, not the repo root, so ``from scripts.…`` imports fail.
# Under pytest the repo root is already on the path (pyproject ``pythonpath``),
# so this only matters for the frozen justfile entrypoint. Must run before any
# ``from scripts.…`` import below.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse  # after the sys.path bootstrap, by design
import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import importlib
import io
import logging
import math
import os
import time
from typing import TYPE_CHECKING
import wave

import numpy as np

from scripts.speaker_calibration_corpus import (
    append_sample_atomic,
    find_orphan_wavs,
    load_manifest,
    remove_samples_atomic,
    render_aggregate_report,
    resolve_corpus_path,
    select_samples,
    sha256_of_file,
    subject_id_problem,
    swap_into_place,
    validate_corpus,
    validate_wav_bytes,
    write_new_file_atomic,
    write_text_atomic,
)
from scripts.speaker_calibration_models import (
    CAPTURE_FLAGS,
    CLI_ACTIONS,
    CONDITIONS,
    DEFAULT_CORPUS_ROOT,
    EMBEDDING_DIM,
    EMBEDDINGS_NAME,
    IMPOSTOR_ID_PATTERN,
    LATENCY_KEY_PREFIX,
    MANIFEST_NAME,
    MODEL_CACHE_DIRNAME,
    MODEL_KEY,
    OWNER_SUBJECT_ID,
    PHRASE_IDS,
    PHRASE_TEXT,
    REPLAY_CONDITIONS,
    REPORT_NAME,
    SAMPLE_CLASSES,
    SESSION_ID_PATTERN,
    SHA_KEY_PREFIX,
    SpeakerCliOptions,
    SpeakerSample,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from scripts.speaker_calibration_models import (
        CliAction,
        SpeakerEmbeddingBackend,
        SpeakerManifest,
    )

logger = logging.getLogger(__name__)

# A full read of any frozen phrase lasts ~4-5 s; a brisk-but-complete one still
# clears ~2.8 s. Below this the VAD almost certainly closed on a mid-phrase
# pause or clipped the start, so the capture is rejected rather than stored.
_MIN_UTTERANCE_SECONDS = 2.5
# A live take far beyond a phrase read is music, a conversation or a stuck VAD.
_MAX_LIVE_UTTERANCE_SECONDS = 15.0
# 20 ms frames; speech sits well above -40 dBFS (0.01 of full scale) while empty
# room noise that merely tripped the VAD does not.
_FRAME_SAMPLES = 320
_MIN_SPEECH_FRAME_RMS = 0.01
_INT16_FULL_SCALE = 32768.0
# More than this share of samples pinned at the rails is a clipped, unusable take.
_MAX_CLIPPED_FRACTION = 0.005
_CLIP_LEVEL = 32767
_CONFIRM_WORD = "delete"
# Files ``cleanup`` may remove: the corpus artifacts by exact name or suffix. A
# directory holding anything else is not a calibration corpus and is refused.
_CLEANABLE_NAMES = frozenset({MANIFEST_NAME, EMBEDDINGS_NAME, REPORT_NAME})
_CLEANABLE_SUFFIXES = frozenset({".wav", ".tmp"})


@dataclass(frozen=True)
class SpeakerThresholdResult:
    """False-accept/false-reject counts for one candidate threshold.

    Attributes:
        threshold: The candidate cosine-distance threshold evaluated.
        false_accepts: Impostor samples with distance <= threshold.
        false_rejects: Genuine samples with distance > threshold.
        total_genuine: Total genuine samples evaluated.
        total_impostor: Total impostor samples evaluated.
    """

    threshold: float
    false_accepts: int
    false_rejects: int
    total_genuine: int
    total_impostor: int


def _as_finite_1d(vector: np.ndarray) -> np.ndarray:
    """Return *vector* as a 1-D float64 array, rejecting non-finite values.

    Raises:
        ValueError: If any component is NaN or infinite.
    """
    array = np.asarray(vector, dtype=np.float64).ravel()
    if not np.all(np.isfinite(array)):
        raise ValueError("embedding must contain only finite values")
    return array


def l2_normalize(vector: np.ndarray) -> np.ndarray:
    """Return a finite unit vector pointing the same direction as *vector*.

    Args:
        vector: A finite, non-zero embedding of any dimension.

    Returns:
        The vector scaled to euclidean norm 1.0, as float64.

    Raises:
        ValueError: If *vector* is non-finite or the zero vector.
    """
    array = _as_finite_1d(vector)
    norm = float(np.linalg.norm(array))
    if norm == 0.0:
        raise ValueError("cannot normalize the zero vector")
    return array / norm


def reference_centroid(references: Sequence[np.ndarray]) -> np.ndarray:
    """Return the normalized mean of individually normalized reference embeddings.

    Each reference is L2-normalized, the results are averaged, and the mean is
    L2-normalized again so magnitude differences between enrolment samples
    cannot skew the centroid.

    Args:
        references: One or more finite, non-zero reference embeddings, all of
            the same dimension.

    Returns:
        The unit-length centroid embedding, as float64.

    Raises:
        ValueError: If *references* is empty, dimensions differ, or any
            reference is non-finite or zero.
    """
    if len(references) == 0:
        raise ValueError("references must not be empty")
    normalized = [l2_normalize(ref) for ref in references]
    if len({vec.shape for vec in normalized}) != 1:
        raise ValueError("all references must share one embedding dimension")
    return l2_normalize(np.mean(np.vstack(normalized), axis=0))


def cosine_distance(probe: np.ndarray, reference: np.ndarray) -> float:
    """Return one-minus-cosine-similarity between two embeddings.

    Both inputs are L2-normalized internally, so the result is 0.0 for vectors
    of identical direction, 1.0 for orthogonal ones and 2.0 for opposite ones.

    Args:
        probe: A finite, non-zero embedding.
        reference: A finite, non-zero embedding of the same dimension.

    Returns:
        ``1 - dot(unit(probe), unit(reference))``.

    Raises:
        ValueError: If the dimensions differ, or either vector is non-finite
            or zero.
    """
    if _as_finite_1d(probe).shape != _as_finite_1d(reference).shape:
        raise ValueError("probe and reference must share one embedding dimension")
    return float(1.0 - np.dot(l2_normalize(probe), l2_normalize(reference)))


def sweep_speaker_thresholds(
    genuine_distances: Sequence[float],
    impostor_distances: Sequence[float],
    candidates: Sequence[float],
) -> list[SpeakerThresholdResult]:
    """Evaluate FAR and FRR at each candidate threshold.

    A sample is accepted when its distance is ``<= threshold``: an impostor at
    or below the threshold is a false accept; a genuine sample above it is a
    false reject.

    Args:
        genuine_distances: Distances for the owner's own probe samples.
        impostor_distances: Distances for live-impostor probe samples.
        candidates: Threshold values to evaluate, kept in the given order.

    Returns:
        One :class:`SpeakerThresholdResult` per candidate, in input order.

    Raises:
        ValueError: If either distance set is empty.
    """
    if len(genuine_distances) == 0 or len(impostor_distances) == 0:
        raise ValueError("genuine and impostor distance sets must not be empty")
    return [
        SpeakerThresholdResult(
            threshold=candidate,
            false_accepts=sum(1 for d in impostor_distances if d <= candidate),
            false_rejects=sum(1 for d in genuine_distances if d > candidate),
            total_genuine=len(genuine_distances),
            total_impostor=len(impostor_distances),
        )
        for candidate in candidates
    ]


def zero_far_speaker_threshold(
    genuine_distances: Sequence[float],
    impostor_distances: Sequence[float],
) -> tuple[float, float] | None:
    """Return the best zero-observed-FAR threshold and its FRR, or ``None``.

    The safe thresholds are the genuine distances strictly below the closest
    impostor distance. The largest of those minimizes false rejects; when
    several thresholds all reach the same FRR, the lowest is returned so the
    choice sits against the genuine cluster, not against the impostor edge.

    Args:
        genuine_distances: Distances for the owner's own probe samples.
        impostor_distances: Distances for live-impostor probe samples.

    Returns:
        ``(threshold, frr)`` where ``frr`` is false rejects over all genuine
        samples, or ``None`` when either set is empty or the closest sample of
        all is an impostor (the distributions overlap).
    """
    if len(genuine_distances) == 0 or len(impostor_distances) == 0:
        return None
    closest_impostor = min(impostor_distances)
    safe = [d for d in genuine_distances if d < closest_impostor]
    if not safe:
        return None
    threshold = max(safe)
    false_rejects = sum(1 for d in genuine_distances if d > threshold)
    return threshold, false_rejects / len(genuine_distances)


def percentile(values: Sequence[float], quantile: float) -> float:
    """Return the nearest-rank percentile of *values*.

    Nearest-rank: the p-quantile of ``n`` sorted values is the value at
    1-indexed rank ``ceil(p * n)``. Deterministic, no interpolation - the
    frozen latency protocol (Plan 0047 block 5) reports p50 and p95 this way.

    Args:
        values: One or more measurements.
        quantile: A fraction in ``(0, 1]`` (the study uses 0.5 and 0.95).

    Returns:
        The measurement at the nearest rank.

    Raises:
        ValueError: If *values* is empty.
    """
    if len(values) == 0:
        raise ValueError("values must not be empty")
    ordered = sorted(values)
    rank = max(1, math.ceil(quantile * len(ordered)))
    return float(ordered[rank - 1])


# --- Task 2: private-corpus CLI --------------------------------------------


def parse_cli_args(argv: Sequence[str] | None = None) -> SpeakerCliOptions:
    """Parse one explicit speaker-calibration action.

    Every value is a fixed-vocabulary token (an action name, a frozen phrase or
    condition id, a pseudonym or a path), never a free-text sentence, so no
    ``nargs='+'`` is needed for the justfile/PowerShell entrypoint.

    Args:
        argv: Argument list without the program name; defaults to ``sys.argv``.

    Returns:
        The cross-checked options. ``capture`` requires every metadata flag;
        other actions reject them. Argparse exits with code 2 on a bad combo.
    """
    parser = argparse.ArgumentParser(
        description="Plan 0047 (PC-3A) speaker-evidence calibration corpus workflow."
    )
    parser.add_argument("action", choices=CLI_ACTIONS)
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--class", dest="sample_class", choices=SAMPLE_CLASSES, default=None)
    parser.add_argument("--subject", dest="subject_id", default=None)
    parser.add_argument("--session", dest="session_id", type=_session_id, default=None)
    parser.add_argument("--phrase", dest="phrase_id", choices=PHRASE_IDS, default=None)
    parser.add_argument("--condition", choices=CONDITIONS, default=None)
    parser.add_argument("--sample", dest="sample_id", default=None)
    parser.add_argument("--purge-model-cache", action="store_true")
    args = parser.parse_args(None if argv is None else list(argv))
    _cross_check_flags(parser, args)
    return SpeakerCliOptions(
        action=args.action,
        corpus_root=args.corpus_root,
        manifest_path=args.manifest or (args.corpus_root / MANIFEST_NAME),
        output_path=args.output,
        sample_class=args.sample_class,
        subject_id=args.subject_id,
        session_id=args.session_id,
        phrase_id=args.phrase_id,
        condition=args.condition,
        sample_id=args.sample_id,
        purge_model_cache=args.purge_model_cache,
    )


def _session_id(value: str) -> str:
    """Argparse type: a session id that is safe inside a WAV file name."""
    if not SESSION_ID_PATTERN.match(value):
        raise argparse.ArgumentTypeError("session id must be 1-40 characters of a-z, 0-9 or '-'")
    return value


def _require_inside_root(
    parser: argparse.ArgumentParser, root: Path, path: Path | None, flag: str
) -> None:
    """Keep every path the tool writes inside the corpus root so ``cleanup`` covers it."""
    if path is not None and not path.resolve().is_relative_to(root.resolve()):
        parser.error(f"{flag} must stay inside --corpus-root")


def _cross_check_flags(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    _require_inside_root(parser, args.corpus_root, args.manifest, "--manifest")
    _require_inside_root(parser, args.corpus_root, args.output, "--output")
    if args.purge_model_cache and args.action != "cleanup":
        parser.error("--purge-model-cache is only valid for cleanup")
    supplied = {name for name in CAPTURE_FLAGS if getattr(args, name) is not None}
    if args.action == "capture":
        missing = sorted(set(CAPTURE_FLAGS) - supplied)
        if missing:
            parser.error(f"capture requires every metadata flag; missing {missing}")
        _check_capture_subject(parser, args)
    elif args.action == "discard":
        _check_discard_selector(parser, args, supplied)
    elif supplied:
        parser.error(f"{args.action} does not accept capture flags: {sorted(supplied)}")
    if args.sample_id is not None and args.action != "discard":
        parser.error("--sample is only valid for discard")
    if args.output is not None and args.action != "analyze":
        parser.error("--output is only valid for analyze")


def _check_discard_selector(
    parser: argparse.ArgumentParser, args: argparse.Namespace, supplied: set[str]
) -> None:
    extra = sorted(supplied - {"subject_id"})
    if extra:
        parser.error(f"discard selects by --subject or --sample only, not {extra}")
    if (args.subject_id is None) == (args.sample_id is None):
        parser.error("discard needs exactly one of --subject or --sample")
    subject = args.subject_id
    if (
        subject is not None
        and subject != OWNER_SUBJECT_ID
        and not IMPOSTOR_ID_PATTERN.match(subject)
    ):
        parser.error(f"--subject must be {OWNER_SUBJECT_ID!r} or match impostor_[a-z]+")


def _check_capture_subject(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    problem = subject_id_problem(args.sample_class, args.subject_id)
    if problem is not None:
        parser.error(f"--subject: {problem}")
    # Catch a rule the corpus validator would only flag after the recording.
    if args.sample_class == "reference" and args.condition != "quiet-near":
        parser.error("--condition: reference samples are captured at quiet-near only")
    if args.sample_class == "replay" and args.condition not in REPLAY_CONDITIONS:
        parser.error(f"--condition: replay samples use one of {REPLAY_CONDITIONS}")


def run_cli(
    options: SpeakerCliOptions,
    *,
    backend: SpeakerEmbeddingBackend | None = None,
    capture_audio: Callable[[], bytes] | None = None,
) -> int:
    """Execute one safe action and return zero only for complete success.

    Args:
        options: The parsed action and its metadata.
        backend: Embedding backend for ``embed`` (``main`` supplies the frozen
            SpeechBrain one); ``None`` makes ``embed`` fail cleanly.
        capture_audio: Microphone boundary for ``capture``; ``None`` uses the
            real robot recorder. ``validate``/``embed``/``analyze``/``cleanup``
            never touch it.

    Returns:
        ``0`` on complete success, a nonzero code otherwise. Any exception is
        logged and converted to ``1`` with no partial manifest or report.
    """
    try:
        return _dispatch(options, backend, capture_audio)
    except (ValueError, OSError) as exc:  # expected: bad corpus, missing file, capture fault
        logger.error("speaker-calibration %s failed: %s", options.action, exc)
        return 1
    except Exception:  # top-level CLI boundary: never leave a partial manifest or report
        logger.exception("speaker-calibration %s hit an unexpected error", options.action)
        return 1


def _dispatch(
    options: SpeakerCliOptions,
    backend: SpeakerEmbeddingBackend | None,
    capture_audio: Callable[[], bytes] | None,
) -> int:
    match options.action:
        case "capture":
            code = _run_capture(options, capture_audio)
        case "validate":
            code = _run_validate(options)
        case "embed":
            code = _run_embed(options, backend)
        case "analyze":
            code = _run_analyze(options)
        case "cleanup":
            code = _run_cleanup(options)
        case "discard":
            code = _run_discard(options)
        case "model-contract":
            code = _run_model_contract()
    return code


def _run_model_contract() -> int:
    """Warm the frozen model cache and assert the pinned revision (Task 3).

    Delegates to the frozen backend via a deferred import so ``validate`` /
    ``analyze`` / ``cleanup`` never import ``torch``.
    """
    from scripts.speaker_calibration_backend import (  # noqa: PLC0415 -- deferred: keeps torch out of validate/analyze/cleanup
        run_model_contract,
    )

    return run_model_contract()


def _run_capture(options: SpeakerCliOptions, capture_audio: Callable[[], bytes] | None) -> int:
    if (
        options.sample_class is None
        or options.subject_id is None
        or options.session_id is None
        or options.phrase_id is None
        or options.condition is None
    ):
        raise ValueError("capture requires full sample metadata")  # parse_cli_args enforces this
    live = capture_audio is None  # a real human is at the microphone
    wav_bytes = _capture_live(options.phrase_id) if capture_audio is None else capture_audio()
    validate_wav_bytes(wav_bytes)
    if live:
        _reject_if_too_short(wav_bytes)
        _reject_unusable_signal(wav_bytes)
    options.corpus_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    wav_name = f"{options.sample_class}-{options.session_id}-{options.phrase_id}-{stamp}.wav"
    wav_path = resolve_corpus_path(options.corpus_root, wav_name)
    write_new_file_atomic(wav_path, wav_bytes)
    try:
        sample = SpeakerSample(
            sample_id=wav_path.stem,
            subject_id=options.subject_id,
            sample_class=options.sample_class,
            session_id=options.session_id,
            phrase_id=options.phrase_id,
            condition=options.condition,
            wav_path=wav_path,
            sha256=sha256_of_file(wav_path),
        )
        append_sample_atomic(options.manifest_path, options.corpus_root, sample)
    except Exception:
        wav_path.unlink(missing_ok=True)  # never leave a private WAV the manifest does not know
        raise
    # No sample id, file name or timestamp: this log line gets pasted into chats.
    logger.info(
        "captured one %s sample (%s, %s)",
        options.sample_class,
        options.phrase_id,
        options.condition,
    )
    return 0


def _announce_capture(phrase_id: str) -> None:
    """Show the phrase to read aloud, then count down with an audible start cue.

    Console ergonomics for the person at the microphone — the caller runs this
    only for a real capture (no injected recorder), so tests stay fast.

    Args:
        phrase_id: One of the frozen phrase ids.
    """
    logger.info("---- %s ----------------------------------------", phrase_id)
    logger.info("READ ALOUD:  %s", PHRASE_TEXT[phrase_id])
    for count in (3, 2, 1):
        logger.info("   %d ...", count)
        time.sleep(1.0)
    _play_start_cue()
    logger.info("   >>> SPEAK NOW <<<")


def _reject_if_too_short(wav_bytes: bytes) -> None:
    """Reject a live capture too short to be a full phrase read.

    Args:
        wav_bytes: The just-captured WAV — 16 000 Hz, mono, signed int16.

    Raises:
        ValueError: If the utterance is under ``_MIN_UTTERANCE_SECONDS`` — the
            VAD almost certainly closed on a mid-phrase pause or clipped start,
            so nothing is written and the operator re-reads the phrase.
    """
    with wave.open(io.BytesIO(wav_bytes), "rb") as handle:
        seconds = handle.getnframes() / handle.getframerate()
    if seconds < _MIN_UTTERANCE_SECONDS:
        raise ValueError(
            f"capture is only {seconds:.1f}s (need >= {_MIN_UTTERANCE_SECONDS}s) - "
            "read the whole phrase at a steady pace, no long pauses between words"
        )


def _reject_unusable_signal(wav_bytes: bytes) -> None:
    """Reject a live capture that is overlong, clipped or has no speech-level audio.

    Args:
        wav_bytes: The just-captured WAV - 16 000 Hz, mono, signed int16.

    Raises:
        ValueError: If the take is longer than ``_MAX_LIVE_UTTERANCE_SECONDS``,
            has more than ``_MAX_CLIPPED_FRACTION`` of its samples at the rails,
            or its 95th-percentile 20 ms frame level is below speech level. Such
            a take would still yield a finite embedding and silently pollute
            FAR/FRR, so nothing is written and the phrase is read again.
    """
    with wave.open(io.BytesIO(wav_bytes), "rb") as handle:
        frames = handle.readframes(handle.getnframes())
        seconds = handle.getnframes() / handle.getframerate()
    if seconds > _MAX_LIVE_UTTERANCE_SECONDS:
        raise ValueError(
            f"capture is {seconds:.1f}s (max {_MAX_LIVE_UTTERANCE_SECONDS}s) - "
            "music, talking or a stuck microphone; read only the phrase"
        )
    samples = np.frombuffer(frames, dtype=np.int16)
    clipped = float(np.mean(np.abs(samples.astype(np.int32)) >= _CLIP_LEVEL))
    if clipped > _MAX_CLIPPED_FRACTION:
        raise ValueError("capture is clipped - lower the input gain or speak further away")
    usable = len(samples) - len(samples) % _FRAME_SAMPLES
    if usable == 0:
        raise ValueError("capture is too short to measure its level")
    framed = samples[:usable].astype(np.float64) / _INT16_FULL_SCALE
    rms = np.sqrt(np.mean(framed.reshape(-1, _FRAME_SAMPLES) ** 2, axis=1))
    if percentile(rms.tolist(), 0.95) < _MIN_SPEECH_FRAME_RMS:
        raise ValueError("capture has no speech-level audio - speak closer or louder")


def _play_start_cue() -> None:
    """Sound a short start beep; stay silent if the platform cannot."""
    try:
        import winsound  # noqa: PLC0415 -- Windows-only, real-capture path only

        winsound.Beep(1000, 250)
    except (ImportError, RuntimeError) as exc:  # no PC speaker / not Windows
        logger.debug("start cue beep unavailable: %s", exc)


def _capture_live(phrase_id: str) -> bytes:
    """Warm the recorder, announce the phrase, then capture one utterance.

    The VAD is warmed *before* the countdown so the microphone is already
    listening when the start cue fires — otherwise the phrase onset is lost
    while ``onnxruntime`` and the Silero model load.

    Args:
        phrase_id: One of the frozen phrase ids.

    Returns:
        WAV bytes - 16 000 Hz, mono, signed int16.

    Raises:
        ValueError: If no speech was captured before the timeout.
    """
    # Lazy, name-resolved import: keeps ``sounddevice`` and the robot adapter out
    # of import time, so validate/embed/analyze provably never open a microphone.
    recorder = importlib.import_module("robot.audio_capture")
    logger.info("Preparing microphone (first capture loads the VAD model)...")
    _warm_recorder()
    _announce_capture(phrase_id)
    wav: bytes = asyncio.run(recorder.capture_utterance())
    if not wav:
        raise ValueError("no speech captured before the microphone timeout")
    return wav


def _warm_recorder() -> None:
    """Preload ``onnxruntime`` and the Silero model so capture starts instantly."""
    try:
        vad = importlib.import_module("robot.vad")
        robot_settings = importlib.import_module("robot.settings")
        vad.create_vad(robot_settings.settings.vad_engine)
    except Exception as exc:  # best-effort — a cold capture still works
        logger.warning("recorder warm-up skipped (the first take may lose its start): %s", exc)


def _run_validate(options: SpeakerCliOptions) -> int:
    manifest = load_manifest(options.manifest_path, options.corpus_root)
    validate_corpus(manifest)
    _require_no_orphan_wavs(manifest, options.corpus_root)
    logger.info("corpus OK: %d samples under %s", len(manifest.samples), options.corpus_root)
    return 0


def _require_no_orphan_wavs(manifest: SpeakerManifest, corpus_root: Path) -> None:
    orphans = find_orphan_wavs(manifest, corpus_root)
    if orphans:
        raise ValueError(
            f"{len(orphans)} WAV file(s) under the corpus root are not in the manifest - "
            "delete them by hand or re-add them; none was touched"
        )


def _run_embed(options: SpeakerCliOptions, backend: SpeakerEmbeddingBackend | None) -> int:
    if backend is None:
        logger.error("embed needs the frozen speaker backend, which is not loaded")
        return 1
    manifest = load_manifest(options.manifest_path, options.corpus_root)
    if manifest.samples:  # one discarded embedding so the first timing is not a cold start
        backend.embed_wav(manifest.samples[0].wav_path.read_bytes())
    arrays: dict[str, np.ndarray] = {MODEL_KEY: np.array(backend.model_id)}
    for sample in manifest.samples:
        vector, latency_ms = _embed_sample(backend, sample)
        arrays[sample.sample_id] = vector
        arrays[LATENCY_KEY_PREFIX + sample.sample_id] = np.array(latency_ms)
        arrays[SHA_KEY_PREFIX + sample.sample_id] = np.array(sample.sha256)
    _write_npz_atomic(options.corpus_root / EMBEDDINGS_NAME, arrays)
    logger.info("wrote %d embeddings for model %s", len(manifest.samples), backend.model_id)
    return 0


def _embed_sample(
    backend: SpeakerEmbeddingBackend, sample: SpeakerSample
) -> tuple[np.ndarray, float]:
    """Embed one corpus WAV (16 000 Hz, mono, signed int16) and time the embedding."""
    wav_bytes = sample.wav_path.read_bytes()
    validate_wav_bytes(wav_bytes)
    start = time.perf_counter()
    vector = backend.embed_wav(wav_bytes)
    latency_ms = (time.perf_counter() - start) * 1000.0
    return checked_embedding(vector), latency_ms


def checked_embedding(vector: np.ndarray) -> np.ndarray:
    flat = np.asarray(vector, dtype=np.float64).ravel()
    if flat.shape != (EMBEDDING_DIM,):
        raise ValueError(f"embedding must hold exactly {EMBEDDING_DIM} values, got {flat.shape}")
    if not np.all(np.isfinite(flat)):
        raise ValueError("embedding contains non-finite values")
    if not np.any(flat):
        raise ValueError("embedding is the all-zero vector")
    return flat


def _write_npz_atomic(target: Path, arrays: dict[str, np.ndarray]) -> None:
    tmp = target.with_name(target.name + ".tmp")
    try:
        with tmp.open("wb") as handle:
            # numpy's savez stub misbinds a ``**dict[str, ndarray]`` splat to its
            # ``allow_pickle`` bool parameter; the runtime call is correct.
            np.savez(handle, **arrays)  # type: ignore[arg-type]
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        tmp.unlink(missing_ok=True)  # a failed write must not leave a stale temp file
        raise
    swap_into_place(tmp, target)


def _run_analyze(options: SpeakerCliOptions) -> int:
    """Score the corpus and write the aggregate report (Task 6).

    Never opens the microphone or the network. Returns ``0`` whenever the report
    was produced — a measured ``fail_distance_overlap`` is a result, not an error.
    """
    output = options.output_path or (options.corpus_root / REPORT_NAME)
    if output.exists():
        logger.error("refusing to overwrite an existing report: %s", output)
        return 1
    manifest = load_manifest(options.manifest_path, options.corpus_root)
    validate_corpus(manifest)
    _require_no_orphan_wavs(manifest, options.corpus_root)
    # Deferred: both modules import this one at load time.
    from scripts.speaker_calibration_analysis import build_report  # noqa: PLC0415
    from scripts.speaker_calibration_backend import frozen_model_identity  # noqa: PLC0415

    model_id, package_version = frozen_model_identity()
    embeddings, latencies = _load_embeddings(
        options.corpus_root / EMBEDDINGS_NAME, manifest, model_id
    )
    report = build_report(
        manifest, embeddings, latencies, model_id=model_id, package_version=package_version
    )
    write_text_atomic(output, render_aggregate_report(report))
    logger.info("analysis outcome: %s (aggregate report written)", report.outcome)
    return 0


def _load_embeddings(
    path: Path, manifest: SpeakerManifest, model_id: str
) -> tuple[dict[str, np.ndarray], list[float]]:
    """Load one checked vector and one latency per manifest sample.

    Args:
        path: The ``embeddings.npz`` written by ``embed``.
        manifest: The validated manifest the vectors must cover.
        model_id: The frozen model id the vectors must have been computed with.

    Raises:
        ValueError: If the file is absent, was produced by another model or from
            different audio than the manifest records, or any manifest sample
            lacks a vector or a valid latency (counts only, never sample ids).
    """
    if not path.exists():
        raise ValueError(f"no embeddings at {path} - run `embed` first")
    ids = [sample.sample_id for sample in manifest.samples]
    with np.load(path) as stored:
        present = set(stored.files)
        if MODEL_KEY not in present or str(stored[MODEL_KEY]) != model_id:
            raise ValueError("embeddings were not produced by the frozen model - re-run embed")
        stale = sum(
            1
            for sample in manifest.samples
            if SHA_KEY_PREFIX + sample.sample_id not in present
            or str(stored[SHA_KEY_PREFIX + sample.sample_id]) != sample.sha256
        )
        if stale:
            raise ValueError(f"embeddings are stale for {stale} sample(s) - re-run embed")
        vectors = {i: checked_embedding(stored[i]) for i in ids if i in present}
        latencies = [
            _checked_latency(stored[LATENCY_KEY_PREFIX + i])
            for i in ids
            if LATENCY_KEY_PREFIX + i in present
        ]
    if len(vectors) != len(ids) or len(latencies) != len(ids):
        raise ValueError(f"embeddings incomplete for {len(ids)} sample(s) - re-run embed")
    return vectors, latencies


def _checked_latency(value: np.ndarray) -> float:
    latency = float(value)
    if not math.isfinite(latency) or latency < 0.0:
        raise ValueError("a stored embedding latency is not a finite non-negative number")
    return latency


def _run_discard(options: SpeakerCliOptions) -> int:
    """Permanently delete one participant's (or one sample's) private data.

    Covers a participant's withdrawal and a technical exclusion: the WAV files,
    their embeddings, their manifest rows and any now-stale aggregate report.
    Idempotent — an interrupted run can be repeated. Nothing is deleted when the
    selector matches nothing or the confirmation is not typed.
    """
    # Lenient load: a withdrawal must succeed even if a file is already gone or damaged.
    manifest = load_manifest(options.manifest_path, options.corpus_root, verify_files=False)
    targets = select_samples(manifest, subject_id=options.subject_id, sample_id=options.sample_id)
    if not targets:
        logger.error("nothing matches that selector; nothing was deleted")
        return 1
    counts = {c: sum(s.sample_class == c for s in targets) for c in SAMPLE_CLASSES}
    described = ", ".join(f"{n} {c}" for c, n in counts.items() if n)
    logger.warning("about to permanently delete %d sample(s) (%s)", len(targets), described)
    logger.warning("their WAV files, embeddings and manifest rows, plus any stale report")
    if not _confirmed("discard"):
        logger.info("discard cancelled - nothing deleted")
        return 1
    ids = {s.sample_id for s in targets}
    for sample in targets:
        sample.wav_path.unlink(missing_ok=True)
    _purge_embeddings(options.corpus_root / EMBEDDINGS_NAME, ids)
    remove_samples_atomic(options.manifest_path, ids)
    (options.corpus_root / REPORT_NAME).unlink(missing_ok=True)
    logger.info("discarded %d sample(s); re-run embed and analyze to refresh results", len(ids))
    return 0


def _purge_embeddings(path: Path, sample_ids: set[str]) -> None:
    """Drop the vectors and latencies of *sample_ids* from ``embeddings.npz``."""
    if not path.exists():
        return
    drop = sample_ids | {
        prefix + sample_id
        for sample_id in sample_ids
        for prefix in (LATENCY_KEY_PREFIX, SHA_KEY_PREFIX)
    }
    with np.load(path) as stored:
        kept = {key: np.asarray(stored[key]) for key in stored.files if key not in drop}
    if any(key != MODEL_KEY for key in kept):
        _write_npz_atomic(path, kept)
    else:
        path.unlink()


def _confirmed(action: str) -> bool:
    """Ask for the typed confirmation word; a missing terminal counts as "no"."""
    try:
        answer = input(f"Type '{_CONFIRM_WORD}' to confirm: ")
    except EOFError:
        logger.error("%s needs an interactive terminal to confirm; nothing was deleted", action)
        return False
    return answer.strip().lower() == _CONFIRM_WORD


def _cleanup_kind(root: Path, path: Path) -> str | None:
    """Classify a file under the corpus root: ``corpus``, ``model-cache`` or ``None`` (unknown)."""
    parts = path.relative_to(root).parts
    if parts[0] == MODEL_CACHE_DIRNAME and len(parts) > 1:
        return "model-cache"
    if len(parts) == 1 and (path.name in _CLEANABLE_NAMES or path.suffix in _CLEANABLE_SUFFIXES):
        return "corpus"
    return None


def _run_cleanup(options: SpeakerCliOptions) -> int:
    """Delete the private corpus artifacts, keeping the reusable model cache by default.

    Refuses any directory that holds files other than the known corpus artifacts
    (so a wrong ``--corpus-root`` can never wipe unrelated work) and any file that
    resolves outside the root. ``--purge-model-cache`` also removes the ~85 MB
    downloaded model. Reports counts only, never file names.
    """
    root = options.corpus_root.resolve()
    if not root.exists():
        logger.info("nothing to clean under %s", root)
        return 0
    files = sorted(path for path in root.rglob("*") if path.is_file())
    kinds: dict[Path, str | None] = {path: _cleanup_kind(root, path) for path in files}
    for path in files:
        if not path.resolve().is_relative_to(root):
            logger.error("refusing to delete a path outside the corpus root: %s", path)
            return 1
    unknown = sum(1 for kind in kinds.values() if kind is None)
    if unknown:
        logger.error(
            "refusing to clean %s: %d file(s) are not corpus artifacts; nothing was deleted",
            root,
            unknown,
        )
        return 1
    wanted = {"corpus", "model-cache"} if options.purge_model_cache else {"corpus"}
    targets = [path for path in files if kinds[path] in wanted]
    kept_cache = sum(1 for kind in kinds.values() if kind == "model-cache") - sum(
        1 for path in targets if kinds[path] == "model-cache"
    )
    logger.warning(
        "about to delete %d file(s) under %s (%d model-cache file(s) kept)",
        len(targets),
        root,
        kept_cache,
    )
    if not _confirmed("cleanup"):
        logger.info("cleanup cancelled - nothing deleted")
        return 1
    for path in targets:
        path.unlink()
    for directory in sorted((d for d in root.rglob("*") if d.is_dir()), reverse=True):
        if not any(directory.iterdir()):
            directory.rmdir()
    logger.info("deleted %d file(s) under %s", len(targets), root)
    return 0


def _load_frozen_backend() -> SpeakerEmbeddingBackend | None:
    """Build the frozen offline backend, or ``None`` (logged) if it cannot load."""
    from scripts.speaker_calibration_backend import (  # noqa: PLC0415 -- keeps torch deferred
        SpeechBrainEcapaBackend,
        load_frozen_encoder,
    )

    try:
        return SpeechBrainEcapaBackend(load_frozen_encoder(allow_network=False))
    except Exception:  # any model/cache fault: embed then fails cleanly without a backend
        logger.exception("could not load the frozen speaker backend; run model-contract first")
        return None


def _keep_huggingface_offline(action: CliAction) -> None:
    """Forbid Hugging Face network access for every action but the cache warm-up.

    ``huggingface_hub`` makes an unrelated once-a-day GET (an agent-harness
    registry) even for cache-only work. Plan 0047 promises that ``embed`` and
    ``analyze`` never open the network, so only ``model-contract`` - the one-time
    download of the pinned revision - may. Must run before ``huggingface_hub``
    is imported, which the deferred imports guarantee. Hub telemetry is off for
    every action, the warm-up included.
    """
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    if action != "model-contract":
        os.environ["HF_HUB_OFFLINE"] = "1"


def main() -> None:
    """CLI entry point for ``just speaker-calibration``."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    options = parse_cli_args()
    _keep_huggingface_offline(options.action)
    backend = _load_frozen_backend() if options.action == "embed" else None
    raise SystemExit(run_cli(options, backend=backend))


if __name__ == "__main__":
    main()
