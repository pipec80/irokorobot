"""stt_bench.py - the deterministic speech-to-text bench of Plan 0069 (Task 7).

Runs the production decode function (``server.stt.run_whisper``) under the named
configurations of Appendix B over the same clips of the private corpus, so every
difference against ``P0`` is paired. Results stay under
``project-history/calibration/stt/results/`` (ignored by git). Run it with the server
stopped: it loads Whisper itself. Machine conditions go in ``--conditions``.

Usage:
    just stt-bench run --configs P0 T0 V-off --half dev --repeat 2 --conditions max-perf charger no-chrome
    just stt-bench segment --policies close800-tail300 close1200-tail300
    just stt-bench run --configs P0 --half dev --segmentation close800-tail300 --conditions max-perf
    just stt-bench report --runs P0-dev T0-dev
    just stt-bench calibrate --run P0-dev
    just stt-bench probe --model small --device cuda --compute int8_float16 --cuda-dll-dir DIR
    just stt-bench external-template

Audio contract of every clip: WAV, 16 000 Hz, mono, int16.
"""

from __future__ import annotations

from pathlib import Path
import sys

# Direct execution puts ``scripts/`` on ``sys.path[0]``; the ``from scripts.…`` imports
# below need the repo root (pytest already has it through pyproject ``pythonpath``).
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse  # after the sys.path bootstrap, by design
from contextlib import contextmanager
import ctypes
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import io
import json
import logging
import os
import subprocess
import time
from typing import TYPE_CHECKING
import wave

import numpy as np
from robot.audio_capture import CHUNK_FRAMES
from robot.settings import settings as robot_settings
from robot.vad import create_vad
from server.settings import settings

from scripts.speaker_calibration_corpus import resolve_corpus_path, write_new_file_atomic
from scripts.stt_bench_configs import (
    SEGMENTATION_POLICIES,
    BenchConfig,
    configs,
    split_items,
)
from scripts.stt_corpus import segment_take
from scripts.stt_corpus_models import (
    MANIFEST_NAME,
    STT_CORPUS_ROOT,
    ScriptItem,
    Take,
    load_script,
    load_takes,
)
from server import stt

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Mapping, Sequence

    from robot.audio_capture import SegmentationPolicy
    from robot.vad import VoiceActivityDetector

logger = logging.getLogger(__name__)

__all__ = ["BenchConfig", "split_items"]

type Loader = Callable[[BenchConfig], object]
type Transcriber = Callable[[object, bytes, stt.WhisperDecodeOptions, str | None], stt.Transcript]

_RESULTS = "results"
_PROBE_SECONDS = 3.0
_PROBE_TIMINGS = 4
_DOWNLOAD_GB = {"medium": 1.5, "large-v3-turbo": 1.6, "large-v3": 3.1}
_CHUNK_S = CHUNK_FRAMES / 16_000
_DLL_HANDLES: list[object] = []  # kept for the whole process (os.add_dll_directory)


@dataclass(frozen=True)
class ClipJob:
    """One clip of one take, as the bench transcribes it."""

    take: Take
    index: int
    count: int
    path: Path


@dataclass(frozen=True)
class ProbeResult:
    """A device probe: load time, four timings of a 3 s synthetic clip, peak VRAM."""

    load_s: float
    timings: tuple[float, ...]
    vram_peak_mb: float | None


def register_cuda_dlls(directory: Path) -> None:
    """Let CTranslate2 find the CUDA libraries of a scratch environment (Windows only).

    Args:
        directory: A ``site-packages/nvidia/<lib>/bin`` directory.
    """
    if sys.platform == "win32":
        _DLL_HANDLES.append(os.add_dll_directory(str(directory.resolve())))
        os.environ["PATH"] = f"{directory.resolve()}{os.pathsep}{os.environ['PATH']}"


def peak_working_set_mb() -> float | None:
    """Return this process's peak working set in MB (Windows), or ``None`` elsewhere."""
    if sys.platform != "win32":
        return None

    class _Counters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = _Counters()
    counters.cb = ctypes.sizeof(_Counters)
    process = ctypes.windll.kernel32.GetCurrentProcess()
    if not ctypes.windll.psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
        return None
    return round(counters.PeakWorkingSetSize / 2**20, 1)


@contextmanager
def vram_sampler(device: str) -> Generator[list[float]]:
    """Sample used VRAM every 100 ms while the block runs (``cuda`` only).

    Yields:
        A list that holds the peak in MB once the block ends; empty off CUDA.
    """
    peak: list[float] = []
    if device != "cuda":
        yield peak
        return
    child = subprocess.Popen(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits", "-lms", "100"],  # noqa: S607
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        yield peak
    finally:
        child.terminate()
        output, _ = child.communicate(timeout=5)
        values = [float(line) for line in output.split() if line.strip().isdigit()]
        if values:
            peak.append(max(values))


def load_whisper(config: BenchConfig) -> object:
    """Load one configuration's model, downloading it once if it is not cached.

    Args:
        config: The configuration.

    Returns:
        The loaded ``WhisperModel``.
    """
    from faster_whisper import WhisperModel  # noqa: PLC0415 -- loaded only when benching

    arguments = {
        "device": config.device,
        "compute_type": config.compute_type,
        "cpu_threads": config.cpu_threads,
    }
    try:
        return WhisperModel(config.model, local_files_only=True, **arguments)
    except Exception:
        size = _DOWNLOAD_GB.get(config.model)
        logger.info("downloading %s once%s", config.model, f" (about {size} GB)" if size else "")
        return WhisperModel(config.model, local_files_only=False, **arguments)


def _segment_index(root: Path, name: str) -> dict[str, dict[str, list[object]]]:
    path = resolve_corpus_path(root, f"{_RESULTS}/segments/{name}.json")
    return json.loads(path.read_text(encoding="utf-8"))


def clip_jobs(
    root: Path, takes: Sequence[Take], keep: frozenset[str] | None, segmentation: str | None
) -> list[ClipJob]:
    """List the clips to transcribe: read takes of the kept items, and every free take.

    Args:
        root: The corpus root.
        takes: The manifest's takes.
        keep: Item ids to keep (``None`` keeps all).
        segmentation: A replayed policy name, or ``None`` for the clips cut at capture.

    Returns:
        One job per clip, in manifest order.
    """
    index = _segment_index(root, segmentation) if segmentation else {}
    jobs: list[ClipJob] = []
    for take in takes:
        if take.mode == "read" and keep is not None and take.item_id not in keep:
            continue
        paths = (
            [str(p) for p in index.get(take.take_id, {}).get("clips", [])]
            if segmentation
            else [clip.path for clip in take.clips]
        )
        jobs.extend(
            ClipJob(take, number, len(paths), resolve_corpus_path(root, path))
            for number, path in enumerate(paths)
        )
    return jobs


def _row(
    config: BenchConfig,
    job: ClipJob,
    repeat: int,
    transcript: stt.Transcript,
    seconds: float,
    extra: Mapping[str, object],
) -> dict[str, object]:
    confidence = transcript.confidence
    return {
        "config": config.name,
        "take_id": job.take.take_id,
        "item_id": job.take.item_id,
        "mode": job.take.mode,
        "clip_index": job.index,
        "clip_count": job.count,
        "repeat": repeat,
        "text": transcript.text,
        "avg_logprob": None if confidence is None else confidence.avg_logprob,
        "no_speech_prob": None if confidence is None else confidence.no_speech_prob,
        "temperature": None if confidence is None else confidence.temperature,
        "clip_s": transcript.clip_s,
        "after_vad_s": transcript.after_vad_s,
        "seconds": round(seconds, 4),
        "peak_working_set_mb": peak_working_set_mb(),
        **extra,
    }


def _run_one(
    config: BenchConfig,
    model: object,
    jobs: Sequence[ClipJob],
    repeat: int,
    transcribe: Transcriber,
    extra: Mapping[str, object],
) -> tuple[list[dict[str, object]], float | None]:
    rows: list[dict[str, object]] = []
    with vram_sampler(config.device) as vram:
        if jobs:  # warm-up, untimed
            transcribe(model, jobs[0].path.read_bytes(), config.options, config.hotwords)
        for number in range(1, repeat + 1):
            for job in jobs:
                audio = job.path.read_bytes()
                start = time.perf_counter()
                transcript = transcribe(model, audio, config.options, config.hotwords)
                elapsed = time.perf_counter() - start
                rows.append(_row(config, job, number, transcript, elapsed, extra))
    return rows, (vram[0] if vram else None)


def _write_run(
    root: Path, run_id: str, rows: list[dict[str, object]], meta: dict[str, object]
) -> Path:
    path = resolve_corpus_path(root, f"{_RESULTS}/runs/{run_id}.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    write_new_file_atomic(path, lines.encode("utf-8"))
    path.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return path


def run_bench(
    names: Sequence[str],
    *,
    root: Path,
    half: str,
    repeat: int,
    segmentation: str | None,
    conditions: Sequence[str],
    load_model: Loader = load_whisper,
    transcribe: Transcriber = stt.run_whisper,  # type: ignore[assignment]  # WhisperModel is the object
    run_id: str | None = None,
) -> list[Path]:
    """Run the named configurations over the same clips and write one run file each.

    Args:
        names: Appendix B names.
        root: The corpus root.
        half: ``dev``, ``test`` or ``all`` (D-8; free takes are always included).
        repeat: Passes over every clip (repeatability).
        segmentation: A replayed policy name (see ``segment_policies``), or ``None``.
        conditions: Machine conditions, recorded on every row.
        load_model: Loads a configuration's model (once per model, device, compute, threads).
        transcribe: Runs one decode (``stt.run_whisper`` in production).
        run_id: Suffix of the run files (default: a UTC timestamp).

    Returns:
        The run files, one per configuration, in the order given.
    """
    table = configs(stt.decode_options(settings))
    dev, test = split_items([item.id for item in load_script()])
    keep = {"dev": dev, "test": test}.get(half)
    jobs = clip_jobs(root, load_takes(root / MANIFEST_NAME, root), keep, segmentation)
    suffix = run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    models: dict[tuple[str, str, str, int], object] = {}
    paths: list[Path] = []
    for name in names:
        config = table[name]
        key = (config.model, config.device, config.compute_type, config.cpu_threads)
        meta: dict[str, object] = {
            "config": name,
            "model": config.model,
            "device": config.device,
            "compute_type": config.compute_type,
            "cpu_threads": config.cpu_threads,
            "hotwords": config.hotwords,
            "options": asdict(config.options),
            "half": half,
            "repeat": repeat,
            "segmentation": segmentation,
            "conditions": list(conditions),
            "clips": len(jobs),
            "unavailable": None,
        }
        rows: list[dict[str, object]] = []
        try:
            if key not in models:
                start = time.perf_counter()
                models[key] = load_model(config)
                meta["load_s"] = round(time.perf_counter() - start, 2)
            extra = {"conditions": list(conditions), "segmentation": segmentation}
            rows, meta["vram_peak_mb"] = _run_one(
                config, models[key], jobs, repeat, transcribe, extra
            )
        except Exception as exc:
            meta["unavailable"] = type(exc).__name__
            logger.warning("%s unavailable: %s", name, type(exc).__name__)
        paths.append(_write_run(root, f"{name}-{half}-{suffix}", rows, meta))
    return paths


def _synthetic_clip(seconds: float = _PROBE_SECONDS) -> bytes:
    """A harmonic tone with a little noise — WAV 16 kHz, mono, int16 (no voice)."""
    t = np.arange(int(seconds * 16_000)) / 16_000
    tone = sum(np.sin(2 * np.pi * f * t) / k for k, f in enumerate((140, 280, 420, 560), 1))
    signal = 0.2 * tone * (0.5 + 0.5 * np.sin(2 * np.pi * 3 * t))
    noise = np.random.default_rng(1).normal(0, 0.005, t.size)
    samples = np.round((signal + noise) * 32767).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(samples.tobytes())
    return buffer.getvalue()


def probe(
    model: str,
    device: str,
    compute: str,
    *,
    load_model: Loader = load_whisper,
    transcribe: Transcriber = stt.run_whisper,  # type: ignore[assignment]  # WhisperModel is the object
) -> ProbeResult:
    """Load one model on one device and time a synthetic 3 s clip four times.

    Args:
        model: The faster-whisper model name.
        device: ``cpu`` or ``cuda``.
        compute: The compute type.
        load_model: Loads the model.
        transcribe: Runs one decode.

    Returns:
        The load time, four timings and, on CUDA, the peak VRAM.
    """
    base = configs(stt.decode_options(settings))["P0"]
    config = BenchConfig("probe", model, device, compute, 0, base.options)
    clip = _synthetic_clip()
    with vram_sampler(device) as vram:
        start = time.perf_counter()
        loaded = load_model(config)
        load_s = time.perf_counter() - start
        transcribe(loaded, clip, config.options, None)
        timings = []
        for _ in range(_PROBE_TIMINGS):
            start = time.perf_counter()
            transcribe(loaded, clip, config.options, None)
            timings.append(round(time.perf_counter() - start, 3))
    return ProbeResult(round(load_s, 2), tuple(timings), vram[0] if vram else None)


def speech_gaps(
    raw: np.ndarray, vad_factory: Callable[[], VoiceActivityDetector] | None = None
) -> list[float]:
    """Measure the silent gaps between speech bursts of a raw take (D-17).

    Args:
        raw: Int16 samples, 16 000 Hz, mono.
        vad_factory: Builds the VAD (``None``: the robot's engine).

    Returns:
        The gaps in seconds, between the first and the last speech chunk.
    """
    vad = (vad_factory or (lambda: create_vad(robot_settings.vad_engine)))()
    usable = len(raw) - len(raw) % CHUNK_FRAMES
    flags = [vad.detect(chunk) for chunk in raw[:usable].reshape(-1, CHUNK_FRAMES)]
    speech = [number for number, flag in enumerate(flags) if flag]
    if not speech:
        return []
    gaps: list[float] = []
    run = 0
    for flag in flags[speech[0] : speech[-1] + 1]:
        if flag:
            if run:
                gaps.append(round(run * _CHUNK_S, 3))
            run = 0
        else:
            run += 1
    return gaps


def _raw_samples(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as handle:
        return np.frombuffer(handle.readframes(handle.getnframes()), dtype=np.int16)


def segment_policies(
    root: Path,
    policies: Mapping[str, SegmentationPolicy],
    vad_factory: Callable[[], VoiceActivityDetector] | None = None,
) -> dict[str, dict[str, dict[str, list[object]]]]:
    """Replay segmentation policies on every raw take and index the clips and gaps.

    Args:
        root: The corpus root.
        policies: Named policies (``SEGMENTATION_POLICIES``).
        vad_factory: Builds a fresh VAD (``None``: the robot's engine).

    Returns:
        Per policy, per take: the clip paths and the in-take speech gaps.
    """
    takes = load_takes(root / MANIFEST_NAME, root)
    result: dict[str, dict[str, dict[str, list[object]]]] = {}
    for name, policy in policies.items():
        index: dict[str, dict[str, list[object]]] = {}
        for take in takes:
            raw = _raw_samples(resolve_corpus_path(root, take.raw_path))
            paths: list[object] = []
            for number, clip in enumerate(segment_take(raw, policy, vad_factory), 1):
                relative = f"{_RESULTS}/segments/{name}/{take.take_id}-{number}.wav"
                target = resolve_corpus_path(root, relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(clip)
                paths.append(relative)
            gaps: list[object] = list(speech_gaps(raw, vad_factory))
            index[take.take_id] = {"clips": paths, "gaps": gaps}
        target = resolve_corpus_path(root, f"{_RESULTS}/segments/{name}.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(index, indent=2), encoding="utf-8")
        result[name] = index
    return result


def write_external_template(root: Path, items: Sequence[ScriptItem]) -> Path:
    """Write the template for an outside dictation tool's output (D-20).

    Args:
        root: The corpus root.
        items: The script items; the block items are listed.

    Returns:
        The template path: one ``item_id<TAB>`` line per block item, its text above it.
    """
    path = resolve_corpus_path(root, f"{_RESULTS}/external-template.tsv")
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Paste what the dictation tool wrote after each tab. Tool and microphone:"]
    for item in items:
        if item.block:
            lines += [f"# {item.text}", f"{item.id}\t"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def load_external(path: Path) -> dict[str, str]:
    """Read a filled-in external template.

    Args:
        path: The template.

    Returns:
        Item id to the text the outside tool wrote (empty lines skipped).
    """
    pairs = (
        line.split("\t", 1)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "\t" in line
    )
    return {item_id: text.strip() for item_id, text in pairs if text.strip()}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the bench commands.

    Args:
        argv: Arguments without the program name.

    Returns:
        The parsed namespace.
    """
    parser = argparse.ArgumentParser(description="Deterministic STT bench (Plan 0069)")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--configs", nargs="+", required=True)
    run.add_argument("--half", choices=("dev", "test", "all"), default="dev")
    run.add_argument("--repeat", type=int, default=2)
    run.add_argument("--segmentation", default=None)
    run.add_argument("--conditions", nargs="+", default=[])
    run.add_argument("--cuda-dll-dir", type=Path, nargs="+", default=[])
    segment = commands.add_parser("segment")
    segment.add_argument("--policies", nargs="+", default=list(SEGMENTATION_POLICIES))
    report = commands.add_parser("report")
    report.add_argument("--runs", nargs="+", required=True)
    report.add_argument("--baseline", default=None)
    report.add_argument("--external", type=Path, default=None)
    report.add_argument("--label", default="external")
    calibrate = commands.add_parser("calibrate")
    calibrate.add_argument("--run", required=True)
    probing = commands.add_parser("probe")
    probing.add_argument("--model", default="small")
    probing.add_argument("--device", default="cpu")
    probing.add_argument("--compute", default="int8")
    probing.add_argument("--cuda-dll-dir", type=Path, nargs="+", default=[])
    commands.add_parser("external-template")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run one bench command.

    Args:
        argv: Arguments without the program name.

    Returns:
        The process exit code.
    """
    from scripts import stt_bench_report  # noqa: PLC0415 -- the report only when asked

    args = parse_args(argv)
    root = STT_CORPUS_ROOT
    for directory in getattr(args, "cuda_dll_dir", []):
        register_cuda_dlls(directory)
    match args.command:
        case "run":
            for path in run_bench(
                args.configs,
                root=root,
                half=args.half,
                repeat=args.repeat,
                segmentation=args.segmentation,
                conditions=args.conditions,
            ):
                logger.info("wrote %s", path.name)
            return 0
        case "segment":
            chosen = {name: SEGMENTATION_POLICIES[name] for name in args.policies}
            segment_policies(root, chosen)
            return 0
        case "report":
            external = load_external(args.external) if args.external else None
            report = stt_bench_report.render_report(
                root, args.runs, args.baseline, external, args.label
            )
            print(report)  # noqa: T201 -- the report
            return 0
        case "calibrate":
            print(stt_bench_report.render_calibration(root, args.run))  # noqa: T201 -- the report
            return 0
        case "probe":
            result = probe(args.model, args.device, args.compute)
            print(json.dumps(asdict(result)))  # noqa: T201 -- the probe's numbers
            return 0
        case _:
            logger.info("wrote %s", write_external_template(root, load_script()))
            return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    raise SystemExit(main())
