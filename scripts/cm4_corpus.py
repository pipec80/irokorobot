"""cm4_corpus.py — the private CM-4 conversation corpus (Plan 0075 Task 2).

Pipec records one or more continuous raw takes of spontaneous conversation with
the robot's exact capture parameters; the clip the robot would upload is cut from
each take offline by the robot's own adopted segmentation (400 / 1200 / 300),
reusing ``robot.audio_capture.segment_utterance`` through ``stt_corpus.segment_take``.
Pipec then annotates a coarse phrase type per clip. Everything lives under
``project-history/calibration/cm4/`` (ignored by git) and ``cleanup`` deletes it only
after Pipec types ``delete``. An agent never runs ``capture-conversation``,
``capture-reference`` or ``annotate``: they open the microphone or play Pipec's
voice. Tracked outputs carry counts, never a transcript.

Usage:
    just cm4-corpus capture-conversation --session s1 --minutes 5
    just cm4-corpus capture-reference --session ref1 --seconds 6
    just cm4-corpus segment --session s1
    just cm4-corpus annotate --session s1
    just cm4-corpus validate
    just cm4-corpus cleanup

Audio contract of every WAV: WAV, 16 000 Hz, mono, int16.
"""

from __future__ import annotations

from pathlib import Path
import sys

# Direct execution puts ``scripts/`` on ``sys.path[0]``; the ``from scripts.…`` imports
# below need the repo root (pytest already has it through pyproject ``pythonpath``).
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse  # after the sys.path bootstrap, by design
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import logging
import shutil
import time
from typing import TYPE_CHECKING, Final
import wave

import numpy as np
from robot.audio_capture import CHUNK_FRAMES, SegmentationPolicy

from scripts.speaker_calibration_corpus import (
    resolve_corpus_path,
    sha256_of_file,
    write_new_file_atomic,
)
from scripts.stt_audio_levels import CONTRACT_RATE, wav_bytes
from scripts.stt_corpus import segment_take

if TYPE_CHECKING:
    from collections.abc import Callable

    from robot.vad import VoiceActivityDetector

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_CM4_CORPUS_ROOT",
    "MANIFEST_NAME",
    "PHRASE_TYPES",
    "ClipRecord",
    "append_clip",
    "capture_conversation",
    "capture_guidance",
    "cleanup",
    "load_clips",
    "segment_session_take",
    "validate_phrase_type",
]

DEFAULT_CM4_CORPUS_ROOT: Final = Path("project-history/calibration/cm4")
MANIFEST_NAME: Final = "manifest.jsonl"
PHRASE_TYPES: Final = ("short_answer", "taste_statement", "question", "command", "other")

type Recorder = Callable[[float], np.ndarray]


@dataclass(frozen=True)
class ClipRecord:
    """One annotated corpus clip. Never carries the text of what was said.

    Attributes:
        clip_id: Stable id, ``<session>-NNN``.
        session: The recording session.
        duration_s: Decoded clip length in seconds.
        phrase_type: One of :data:`PHRASE_TYPES`.
        sha256: Hex SHA-256 of the clip WAV.
    """

    clip_id: str
    session: str
    duration_s: float
    phrase_type: str
    sha256: str


def capture_guidance() -> str:
    """Return the on-screen guide shown before a capture.

    Two things in one place so a future reader knows what this tool expects: a
    suggested script of phrases that covers the five types, and the legend of how
    each clip is later annotated. Printed by the CLI; never used in tests of the
    capture itself.

    Returns:
        A multi-line Spanish guide (suggested phrases, then the annotation legend).
    """
    return (
        "Guion sugerido (di cada frase y PAUSA ~2 s para que sea su propio clip):\n"
        "  Cortas:    Sí.  No.  Ya.  Acepto.  Autorizo.  Dale.\n"
        "  Gustos:    Me gusta el pastel de choclo.  Prefiero el té antes que el café.\n"
        "  Preguntas: ¿Qué hora es?  ¿Cómo está el clima hoy?  ¿Me recuerdas algo?\n"
        "  Órdenes:   Apaga la luz.  Enciende la música.  Sube el volumen.\n"
        "  Otras:     Hoy fui a comprar pan.  Estoy un poco cansado.\n"
        "\n"
        "Al anotar (annotate), cada clip se marca con UNO de estos tipos:\n"
        "  short_answer     respuesta corta: sí, no, ya, acepto, autorizo\n"
        "  taste_statement  un gusto o preferencia: me gusta..., prefiero...\n"
        "  question         le preguntas algo al robot\n"
        "  command          una orden: apaga..., enciende...\n"
        "  other            cualquier otra cosa: narración, relleno, inaudible o ruido\n"
    )


def validate_phrase_type(value: str) -> str:
    """Return *value* if it is one of the five phrase types, else raise.

    Args:
        value: The annotation Pipec typed.

    Returns:
        The same value.

    Raises:
        ValueError: If *value* is not a known phrase type.
    """
    if value not in PHRASE_TYPES:
        raise ValueError(f"unknown phrase type {value!r}; expected one of {PHRASE_TYPES}")
    return value


def segment_session_take(
    raw: np.ndarray,
    *,
    policy: SegmentationPolicy | None = None,
    vad_factory: Callable[[], VoiceActivityDetector] | None = None,
) -> list[bytes]:
    """Cut a raw take into the clips the robot would upload (reuses ``segment_take``).

    Args:
        raw: Int16 samples, 16 000 Hz, mono — one continuous take.
        policy: Segmentation policy; ``None`` uses the robot's adopted settings
            (400 / 1200 / 300).
        vad_factory: Builds a fresh VAD per utterance; ``None`` uses the robot's engine.

    Returns:
        The clips in order, each WAV bytes at 16 kHz, mono, int16; ``[]`` for silence.
    """
    return segment_take(raw, policy or SegmentationPolicy.from_settings(), vad_factory)


def append_clip(manifest: Path, root: Path, record: ClipRecord) -> None:
    """Append one clip record as a JSON line, proving the manifest stays in *root*.

    Args:
        manifest: The manifest path (``<root>/manifest.jsonl``).
        root: The corpus root; the manifest must resolve inside it.
        record: The clip to append.

    Raises:
        ValueError: If *manifest* escapes *root*.
    """
    resolved = resolve_corpus_path(root, manifest)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(record)) + "\n")


def load_clips(manifest: Path, root: Path) -> list[ClipRecord]:
    """Read every clip record back from the manifest.

    Args:
        manifest: The manifest path.
        root: The corpus root; the manifest must resolve inside it.

    Returns:
        The records in file order; ``[]`` when the manifest does not exist.

    Raises:
        ValueError: If *manifest* escapes *root*.
    """
    resolved = resolve_corpus_path(root, manifest)
    if not resolved.exists():
        return []
    records: list[ClipRecord] = []
    for line in resolved.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(ClipRecord(**json.loads(line)))
    return records


def cleanup(root: Path, answer: str) -> bool:
    """Delete every artifact under *root* only when *answer* is exactly ``delete``.

    Args:
        root: The corpus root.
        answer: What Pipec typed at the confirmation prompt.

    Returns:
        ``True`` when the artifacts were deleted, ``False`` otherwise.
    """
    if answer != "delete":
        return False
    for child in sorted(root.glob("*")):
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    return True


def capture_conversation(session: str, minutes: float, *, recorder: Recorder, root: Path) -> Path:
    """Record one continuous raw take and save it under ``<root>/takes/``.

    Args:
        session: The session id.
        minutes: How long to record.
        recorder: Seam that returns int16 samples for a number of seconds; the CLI
            wires the microphone, tests inject a fake.
        root: The corpus root.

    Returns:
        The saved raw-take path.
    """
    (root / "takes").mkdir(parents=True, exist_ok=True)
    samples = recorder(minutes * 60.0)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    target = resolve_corpus_path(root, f"takes/{session}-{stamp}.wav")
    write_new_file_atomic(target, wav_bytes(samples))
    logger.info("Saved raw take under takes/ (%d samples)", len(samples))
    return target


def _decode(path: Path) -> np.ndarray:
    """Decode a contract WAV file to int16 samples."""
    with wave.open(str(path), "rb") as handle:
        return np.frombuffer(handle.readframes(handle.getnframes()), dtype=np.int16)


def _microphone_recorder(seconds: float) -> np.ndarray:
    """Record *seconds* of audio exactly as the robot opens the microphone.

    Audio contract: WAV, 16 000 Hz, mono, int16 (returned as int16 samples).
    """
    import sounddevice as sd  # noqa: PLC0415 -- the mic is only needed for a real capture

    frames = int(seconds * CONTRACT_RATE)
    logger.info("Recording %.1f s at %d Hz, mono, int16", seconds, CONTRACT_RATE)
    recording = sd.rec(
        frames, samplerate=CONTRACT_RATE, channels=1, dtype="int16", blocksize=CHUNK_FRAMES
    )
    sd.wait()
    return recording.reshape(-1).astype(np.int16)


def _cmd_capture(args: argparse.Namespace) -> None:
    minutes = args.minutes if args.subcommand == "capture-conversation" else args.seconds / 60.0
    # Operator-facing console output (the point of the tool), not logging.
    print(capture_guidance())  # noqa: T201
    print(f"\nCaptura de {minutes:.1f} min. Prepárate...")  # noqa: T201
    for remaining in (3, 2, 1):
        print(f"  {remaining}...")  # noqa: T201
        time.sleep(1)
    print(">>> GRABANDO - HABLA AHORA <<<")  # noqa: T201
    path = capture_conversation(
        args.session, minutes, recorder=_microphone_recorder, root=DEFAULT_CM4_CORPUS_ROOT
    )
    print(f">>> LISTO - grabación detenida. Guardado: {path.name}")  # noqa: T201


def _cmd_segment(args: argparse.Namespace) -> None:
    root = DEFAULT_CM4_CORPUS_ROOT
    clips_dir = root / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    index = 0
    for take in sorted((root / "takes").glob(f"{args.session}-*.wav")):
        for clip in segment_session_take(_decode(take)):
            target = resolve_corpus_path(root, f"clips/{args.session}-{index:03d}.wav")
            write_new_file_atomic(target, clip)
            index += 1
    print(f"wrote {index} clips for session {args.session}")  # noqa: T201 -- operator feedback


def _cmd_annotate(args: argparse.Namespace) -> None:
    import sounddevice as sd  # noqa: PLC0415 -- playback is only needed to annotate

    root = DEFAULT_CM4_CORPUS_ROOT
    manifest = root / MANIFEST_NAME
    known = {record.clip_id for record in load_clips(manifest, root)}
    for clip_path in sorted((root / "clips").glob(f"{args.session}-*.wav")):
        clip_id = clip_path.stem
        if clip_id in known:
            continue
        samples = _decode(clip_path)
        sd.play(samples, samplerate=CONTRACT_RATE)
        sd.wait()
        phrase_type = validate_phrase_type(input(f"{clip_id} phrase type {PHRASE_TYPES}: ").strip())
        append_clip(
            manifest,
            root,
            ClipRecord(
                clip_id=clip_id,
                session=args.session,
                duration_s=round(len(samples) / CONTRACT_RATE, 2),
                phrase_type=phrase_type,
                sha256=sha256_of_file(clip_path),
            ),
        )
    print("annotation complete")  # noqa: T201 -- operator feedback


def _cmd_validate(_args: argparse.Namespace) -> None:
    root = DEFAULT_CM4_CORPUS_ROOT
    records = load_clips(root / MANIFEST_NAME, root)
    for record in records:
        clip = resolve_corpus_path(root, f"clips/{record.clip_id}.wav")
        if not clip.is_file() or sha256_of_file(clip) != record.sha256:
            raise ValueError(f"clip {record.clip_id} is missing or does not match its sha256")
    counts = Counter(record.phrase_type for record in records)
    print(f"{len(records)} annotated clips: {dict(counts)}")  # noqa: T201 -- operator feedback


def _cmd_cleanup(_args: argparse.Namespace) -> None:
    answer = input(f"type delete to erase {DEFAULT_CM4_CORPUS_ROOT}: ").strip()
    deleted = cleanup(DEFAULT_CM4_CORPUS_ROOT, answer)
    print("deleted" if deleted else "kept")  # noqa: T201 -- operator feedback


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CM-4 private conversation corpus (Plan 0075).")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    conversation = subparsers.add_parser("capture-conversation")
    conversation.add_argument("--session", required=True)
    conversation.add_argument("--minutes", type=float, default=5.0)
    conversation.set_defaults(handler=_cmd_capture)
    reference = subparsers.add_parser("capture-reference")
    reference.add_argument("--session", required=True)
    reference.add_argument("--seconds", type=float, default=6.0)
    reference.set_defaults(handler=_cmd_capture)
    segment = subparsers.add_parser("segment")
    segment.add_argument("--session", required=True)
    segment.set_defaults(handler=_cmd_segment)
    annotate = subparsers.add_parser("annotate")
    annotate.add_argument("--session", required=True)
    annotate.set_defaults(handler=_cmd_annotate)
    subparsers.add_parser("validate").set_defaults(handler=_cmd_validate)
    subparsers.add_parser("cleanup").set_defaults(handler=_cmd_cleanup)
    return parser


def main(argv: list[str] | None = None) -> None:
    """Run the corpus CLI."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _build_parser().parse_args(argv)
    args.handler(args)


if __name__ == "__main__":
    main()
