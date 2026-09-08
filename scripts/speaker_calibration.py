"""speaker_calibration.py - Plan 0047 (PC-3A) speaker-evidence calibration study.

Three isolated layers, built one task at a time:

1. **Pure numeric harness** (Task 1): L2 normalization, reference centroid,
   cosine distance, deterministic threshold sweep, zero-observed-FAR selection
   and nearest-rank latency percentiles. No audio, model, network or disk.
2. **Private-corpus manifest and safe CLI** (Task 2, this task): strict sample
   schema (``scripts.speaker_calibration_models``), atomic manifest, WAV-contract
   validation, corpus-rule enforcement and aggregate-report rendering
   (``scripts.speaker_calibration_corpus``), and the six-action CLI below.
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
import time
from typing import TYPE_CHECKING
import wave

import numpy as np

from scripts.speaker_calibration_corpus import (
    append_sample_atomic,
    load_manifest,
    resolve_corpus_path,
    sha256_of_file,
    validate_corpus,
    validate_wav_bytes,
)
from scripts.speaker_calibration_models import (
    CAPTURE_FLAGS,
    CLI_ACTIONS,
    CONDITIONS,
    DEFAULT_CORPUS_ROOT,
    EMBEDDING_DIM,
    EMBEDDINGS_NAME,
    IMPOSTOR_ID_PATTERN,
    MANIFEST_NAME,
    OWNER_SUBJECT_ID,
    PHRASE_IDS,
    PHRASE_TEXT,
    REPORT_NAME,
    SAMPLE_CLASSES,
    SpeakerCliOptions,
    SpeakerSample,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from scripts.speaker_calibration_models import SpeakerEmbeddingBackend

logger = logging.getLogger(__name__)

# A full read of any frozen phrase lasts ~4-5 s; a brisk-but-complete one still
# clears ~2.8 s. Below this the VAD almost certainly closed on a mid-phrase
# pause or clipped the start, so the capture is rejected rather than stored.
_MIN_UTTERANCE_SECONDS = 2.5


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
    parser.add_argument("--session", dest="session_id", default=None)
    parser.add_argument("--phrase", dest="phrase_id", choices=PHRASE_IDS, default=None)
    parser.add_argument("--condition", choices=CONDITIONS, default=None)
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
    )


def _cross_check_flags(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    supplied = {name for name in CAPTURE_FLAGS if getattr(args, name) is not None}
    if args.action == "capture":
        missing = sorted(set(CAPTURE_FLAGS) - supplied)
        if missing:
            parser.error(f"capture requires every metadata flag; missing {missing}")
        _check_capture_subject(parser, args)
    elif supplied:
        parser.error(f"{args.action} does not accept capture flags: {sorted(supplied)}")
    if args.output is not None and args.action != "analyze":
        parser.error("--output is only valid for analyze")


def _check_capture_subject(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.sample_class == "impostor":
        if not IMPOSTOR_ID_PATTERN.match(args.subject_id):
            parser.error("impostor --subject must match impostor_[a-z]+")
    elif args.subject_id != OWNER_SUBJECT_ID:
        parser.error(f"--subject must be {OWNER_SUBJECT_ID!r} for {args.sample_class}")


def run_cli(
    options: SpeakerCliOptions,
    *,
    backend: SpeakerEmbeddingBackend | None = None,
    capture_audio: Callable[[], bytes] | None = None,
) -> int:
    """Execute one safe action and return zero only for complete success.

    Args:
        options: The parsed action and its metadata.
        backend: Embedding backend for ``embed`` (the concrete one arrives in
            Task 3); ``None`` makes ``embed`` fail cleanly.
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
            return _run_capture(options, capture_audio)
        case "validate":
            return _run_validate(options)
        case "embed":
            return _run_embed(options, backend)
        case "analyze":
            return _run_analyze(options)
        case "cleanup":
            return _run_cleanup(options)
        case "model-contract":
            return _run_model_contract()


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
    if None in (
        options.sample_class,
        options.subject_id,
        options.session_id,
        options.phrase_id,
        options.condition,
    ):
        raise ValueError("capture requires full sample metadata")  # parse_cli_args enforces this
    live = capture_audio is None  # a real human is at the microphone
    wav_bytes = _capture_live(str(options.phrase_id)) if capture_audio is None else capture_audio()
    validate_wav_bytes(wav_bytes)
    if live:
        _reject_if_too_short(wav_bytes)
    options.corpus_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    wav_name = f"{options.sample_class}-{options.session_id}-{options.phrase_id}-{stamp}.wav"
    wav_path = resolve_corpus_path(options.corpus_root, wav_name)
    wav_path.write_bytes(wav_bytes)
    sample = SpeakerSample(
        sample_id=wav_path.stem,
        subject_id=str(options.subject_id),
        sample_class=options.sample_class,  # type: ignore[arg-type]  # narrowed by the guard above
        session_id=str(options.session_id),
        phrase_id=str(options.phrase_id),
        condition=str(options.condition),
        wav_path=wav_path,
        sha256=sha256_of_file(wav_path),
    )
    append_sample_atomic(options.manifest_path, options.corpus_root, sample)
    logger.info("captured %s under %s", sample.sample_id, options.corpus_root)
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
        logger.debug("recorder warm-up skipped: %s", exc)


def _run_validate(options: SpeakerCliOptions) -> int:
    manifest = load_manifest(options.manifest_path, options.corpus_root)
    validate_corpus(manifest)
    logger.info("corpus OK: %d samples under %s", len(manifest.samples), options.corpus_root)
    return 0


def _run_embed(options: SpeakerCliOptions, backend: SpeakerEmbeddingBackend | None) -> int:
    if backend is None:
        logger.error("embed needs a speaker embedding backend (the frozen one arrives in Task 3)")
        return 1
    manifest = load_manifest(options.manifest_path, options.corpus_root)
    embeddings: dict[str, np.ndarray] = {}
    for sample in manifest.samples:
        wav_bytes = sample.wav_path.read_bytes()
        validate_wav_bytes(wav_bytes)
        vector = _checked_embedding(backend.embed_wav(wav_bytes))
        embeddings[sample.sample_id] = vector
    _write_npz_atomic(options.corpus_root / EMBEDDINGS_NAME, embeddings)
    logger.info("wrote %d embeddings for model %s", len(embeddings), backend.model_id)
    return 0


def _checked_embedding(vector: np.ndarray) -> np.ndarray:
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
    with tmp.open("wb") as handle:
        # numpy's savez stub misbinds a ``**dict[str, ndarray]`` splat to its
        # ``allow_pickle`` bool parameter; the runtime call is correct.
        np.savez(handle, **arrays)  # type: ignore[arg-type]
    try:
        tmp.replace(target)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def _run_analyze(options: SpeakerCliOptions) -> int:
    output = options.output_path or (options.corpus_root / REPORT_NAME)
    if output.exists():
        logger.error("refusing to overwrite an existing report: %s", output)
        return 1
    manifest = load_manifest(options.manifest_path, options.corpus_root)
    validate_corpus(manifest)
    embeddings_path = options.corpus_root / EMBEDDINGS_NAME
    if not embeddings_path.exists():
        logger.error(
            "no embeddings at %s - run `embed` first (backend arrives in Task 3)", embeddings_path
        )
        return 1
    # Task 6 wires the Task 1 numeric layer (reference_centroid, cosine_distance,
    # sweep_speaker_thresholds, zero_far_speaker_threshold) over these embeddings
    # into an AggregateSpeakerReport rendered to `output`. No microphone, no network.
    logger.error("analyze aggregation is implemented in Plan 0047 Task 6")
    return 1


def _run_cleanup(options: SpeakerCliOptions) -> int:
    root = options.corpus_root.resolve()
    if not root.exists():
        logger.info("nothing to clean under %s", root)
        return 0
    targets = sorted(path for path in root.rglob("*") if path.is_file())
    for path in targets:
        if not path.resolve().is_relative_to(root):
            logger.error("refusing to delete a path outside the corpus root: %s", path)
            return 1
    logger.warning("about to delete %d file(s) under %s", len(targets), root)
    if input("Type 'delete' to confirm: ").strip().lower() != "delete":
        logger.info("cleanup cancelled - nothing deleted")
        return 1
    for path in targets:
        path.unlink()
    logger.info("deleted %d file(s) under %s", len(targets), root)
    return 0


def main() -> None:
    """CLI entry point for ``just speaker-calibration``."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    raise SystemExit(run_cli(parse_cli_args()))


if __name__ == "__main__":
    main()
