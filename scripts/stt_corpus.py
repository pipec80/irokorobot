"""stt_corpus.py - the private speech-to-text corpus of Plan 0069 (Task 5).

Pipec reads the tracked, invented script (``tests/evals/stt_reading_script.yaml``) at
the microphone; every take is one **continuous raw recording** that starts before the
visual cue, and the clip the robot would upload is cut from it offline by the robot's
own segmentation (``robot.audio_capture.segment_utterance``, D-3), so a segmentation
policy can be replayed later without recording again. Read and spontaneous speech stay
apart (D-4). Everything is written under ``project-history/calibration/stt/`` (ignored
by git) and deleted by ``cleanup`` only after Pipec types ``delete``. An agent never runs
``capture``, ``free`` or ``annotate``: they open the microphone or play Pipec's voice.

Usage:
    just stt-corpus capture --session s0 --condition c60 --block
    just stt-corpus capture --session s1 --condition c60 --style careful --max-takes 124
    just stt-corpus capture --session s1 --condition c60 --style relaxed --layers D
    just stt-corpus capture --session s1 --condition c60 --layers ABCDE --once
    just stt-corpus free --session s4 --minutes 10
    just stt-corpus annotate --session s4
    just stt-corpus annotate --session s4 --draft-run P0-free-STAMP
    just stt-corpus validate
    just stt-corpus expect
    just stt-corpus cleanup

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
import asyncio
from collections import Counter
from dataclasses import replace
import io
import json
import logging
import random
import shutil
from typing import TYPE_CHECKING
import wave
import zlib

import numpy as np
from robot.audio_capture import SegmentationPolicy, segment_utterance
from robot.settings import settings as robot_settings
from robot.vad import create_vad

from scripts.speaker_calibration_corpus import (
    resolve_corpus_path,
    sha256_of_file,
    write_new_file_atomic,
)
from scripts.stt_audio_levels import CONTRACT_RATE, level_report, level_verdicts
from scripts.stt_corpus_models import (
    MANIFEST_NAME,
    STT_CORPUS_ROOT,
    Clip,
    ScriptItem,
    Take,
    append_take,
    load_script,
    load_takes,
    replace_takes,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from robot.vad import VoiceActivityDetector

logger = logging.getLogger(__name__)

CONDITIONS = ("c60", "c15", "c30", "c60-noenh", "c60-wasapi", "c60-noise", "c60-fast")
_TAIL_S = 0.1

type Recorder = Callable[[float, str], np.ndarray]
type Ask = Callable[[str], str]


class _ArraySource:
    """A take read back chunk by chunk, then silence (so a last utterance closes)."""

    def __init__(self, samples: np.ndarray) -> None:
        self._samples = samples
        self.position = 0

    def read(self, frames: int) -> tuple[np.ndarray, bool]:
        chunk = self._samples[self.position : self.position + frames]
        self.position += frames
        if len(chunk) < frames:
            chunk = np.concatenate([chunk, np.zeros(frames - len(chunk), dtype=np.int16)])
        return chunk.reshape(-1, 1), False


def segment_take(
    raw: np.ndarray,
    policy: SegmentationPolicy,
    vad_factory: Callable[[], VoiceActivityDetector] | None = None,
) -> list[bytes]:
    """Cut every utterance out of a raw take with the robot's own segmentation.

    Args:
        raw: Int16 samples, 16 000 Hz, mono — the continuous take.
        policy: Pre-roll, closing silence and upload tail.
        vad_factory: Builds a fresh VAD per utterance; ``None`` uses the robot's engine.

    Returns:
        The clips in order, each WAV bytes at 16 kHz, mono, int16; ``[]`` for silence.
    """
    make_vad = vad_factory or (lambda: create_vad(robot_settings.vad_engine))
    source = _ArraySource(raw)
    clips: list[bytes] = []
    while source.position < len(raw):
        remaining_s = (len(raw) - source.position) / CONTRACT_RATE + _TAIL_S
        clip = asyncio.run(segment_utterance(source, make_vad(), policy, max_wait_s=remaining_s))
        if not clip:
            break
        clips.append(clip)
    return clips


def _wav(samples: np.ndarray) -> bytes:
    """Encode int16 samples as WAV bytes — 16 kHz, mono, int16."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(CONTRACT_RATE)
        handle.writeframes(samples.astype(np.int16).tobytes())
    return buffer.getvalue()


def _samples(wav_bytes: bytes) -> np.ndarray:
    with wave.open(io.BytesIO(wav_bytes), "rb") as handle:
        return np.frombuffer(handle.readframes(handle.getnframes()), dtype=np.int16)


def _api(condition: str) -> str:
    return "wasapi" if "wasapi" in condition else "mme"


def _target(item: ScriptItem, style: str, block: bool) -> int:
    if block:
        return 1 if item.block else 0
    return item.relaxed if style == "relaxed" else item.reps - item.relaxed


def pending_items(
    items: Sequence[ScriptItem],
    takes: Sequence[Take],
    *,
    session: str,
    condition: str,
    style: str,
    block: bool,
    once: bool = False,
) -> list[ScriptItem]:
    """List what is still to read, one entry per missing take, in a session-seeded order.

    The main condition counts main takes over every session (D-5: an item's ``reps`` are
    spread over the two main sessions); the block counts each item once per condition over
    every session, so the pilot is the block's ``c60`` cell (D-6). Neither counts the other.

    Args:
        items: The script items in scope.
        takes: Every take already in the manifest.
        session: This session (it seeds the order).
        condition: This condition (D-6).
        style: ``careful`` or ``relaxed``.
        block: Whether this is the condition block.
        once: A single pass: each item at most once over every main take, whatever its reps.

    Returns:
        The items to read, repeated once per missing take, shuffled reproducibly.
    """
    done = Counter(
        take.item_id
        for take in takes
        if take.mode == "read"
        and take.condition == condition
        and take.style == style
        and take.block == block
    )
    pending = [
        item
        for item in items
        for _ in range(max(0, (1 if once else _target(item, style, block)) - done[item.id]))
    ]
    seed = zlib.crc32(f"{session}:{condition}:{style}".encode())
    random.Random(seed).shuffle(pending)  # noqa: S311 -- a reproducible reading order, not security
    return pending


def _save(root: Path, take: Take, raw: np.ndarray, clips: list[bytes]) -> Take:
    """Write the raw take and its clips, then append the manifest line."""
    raw_path = resolve_corpus_path(root, take.raw_path)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    write_new_file_atomic(raw_path, _wav(raw))
    saved: list[Clip] = []
    for number, clip in enumerate(clips, 1):
        relative = f"clips/{take.take_id}-{number}.wav"
        path = resolve_corpus_path(root, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_new_file_atomic(path, clip)
        saved.append(Clip(path=relative, sha256=sha256_of_file(path)))
    final = replace(take, raw_sha256=sha256_of_file(raw_path), clips=tuple(saved))
    append_take(root / MANIFEST_NAME, root, final)
    return final


def _show(message: str) -> None:
    logger.info("%s", message)


def take_verdicts(raw: np.ndarray, clips: list[bytes]) -> dict[str, str]:
    """Judge a take's levels on its clips, the audio the robot would upload.

    The raw take carries the countdown, so a short word is a few percent of it and the
    90th-percentile speech level lands in the silence; a clip is mostly voice.

    Args:
        raw: Int16 samples, 16 000 Hz, mono — the continuous take.
        clips: Its clips (WAV bytes, 16 kHz, mono, int16); ``[]`` judges the take itself.

    Returns:
        ``level_verdicts`` of the clips joined, or of the raw take when there is none.
    """
    audio = np.concatenate([_samples(clip) for clip in clips]) if clips else raw
    return level_verdicts(level_report(audio))


def _report(raw: np.ndarray, clips: list[bytes]) -> None:
    verdicts = take_verdicts(raw, clips)
    _show(
        f"   clips: {len(clips)}  peak {verdicts['peak']}  speech {verdicts['speech']}  "
        f"floor {verdicts['floor']}  clipping {verdicts['clipping']}"
    )


def capture_session(
    items: Sequence[ScriptItem],
    *,
    root: Path,
    session: str,
    condition: str,
    style: str,
    block: bool,
    max_takes: int | None,
    recorder: Recorder,
    ask: Ask,
    vad_factory: Callable[[], VoiceActivityDetector] | None = None,
    once: bool = False,
) -> int:
    """Read the pending items aloud, one take each, and keep them.

    Args:
        items: The script items in scope.
        root: The corpus root.
        session: This session id.
        condition: This condition (D-6).
        style: ``careful`` or ``relaxed``.
        block: Whether this is the condition block.
        max_takes: Stop after this many kept takes (``None``: all pending).
        recorder: Records one take: (window seconds, api) to int16 16 kHz mono samples.
        ask: Asks Pipec a question and returns the typed answer.
        vad_factory: Builds a fresh VAD per utterance (``None``: the robot's engine).
        once: A single pass: each item once, whatever its reps (see ``pending_items``).

    Returns:
        How many takes were kept.
    """
    policy = SegmentationPolicy.from_settings()
    takes = load_takes(root / MANIFEST_NAME, root)
    pending = pending_items(
        items, takes, session=session, condition=condition, style=style, block=block, once=once
    )
    kept = 0
    for item in pending[:max_takes]:
        while True:
            _show(f"---- {item.id} ({condition}, {style}) ----")
            _show(f"LEE:  {item.text}")
            raw = recorder(item.window_s, _api(condition))
            clips = segment_take(raw, policy, vad_factory)
            _report(raw, clips)
            choice = ask("[Enter] guardar · r repetir · q terminar: ").strip().lower()
            if choice != "r":
                break
        if choice == "q":
            break
        exact = ask("¿Leíste exactamente la frase? [S/n] ").strip().lower() != "n"
        reference = item.text if exact else ask("Escribe lo que dijiste: ").strip()
        take_id = f"{session}-{condition}-{style}-{item.id}-{len(takes) + kept + 1}"
        _save(
            root,
            Take(
                take_id=take_id,
                session=session,
                condition=condition,
                style=style,
                mode="read",
                item_id=item.id,
                raw_path=f"takes/{take_id}.wav",
                raw_sha256="",
                clips=(),
                reference=reference,
                deviated=not exact,
                block=block,
            ),
            raw,
            clips,
        )
        kept += 1
    _show(f"kept {kept} takes; {max(0, len(pending) - kept)} still pending for this pass")
    return kept


def record_window(window_s: float, api: str) -> np.ndarray:
    """Record one take from the microphone: settle, count down, cue, then the window.

    The sequence lives in ``mic_test.record`` (D-3): samples are kept from the start of
    the countdown and the cue is visual only. Hardware path: Pipec runs it, never an agent.

    Args:
        window_s: Seconds recorded after the cue.
        api: ``mme`` (the robot's way) or ``wasapi``.

    Returns:
        Int16 samples, 16 000 Hz, mono.
    """
    from scripts.mic_test import record  # noqa: PLC0415 -- microphone only here

    return record(api, window_s)[0]


def free_session(
    root: Path,
    session: str,
    minutes: float,
    recorder: Recorder,
    vad_factory: Callable[[], VoiceActivityDetector] | None = None,
) -> int:
    """Record one continuous spontaneous session and cut it into clips (D-4).

    Args:
        root: The corpus root.
        session: This session id.
        minutes: Length of the recording.
        recorder: Records one take (see ``capture_session``).
        vad_factory: Builds a fresh VAD per utterance (``None``: the robot's engine).

    Returns:
        The number of clips cut from it.
    """
    _show("Habla como le hablarías al robot; el audio se corta en turnos después.")
    raw = recorder(minutes * 60, "mme")
    clips = segment_take(raw, SegmentationPolicy.from_settings(), vad_factory)
    take_id = f"{session}-free"
    _save(
        root,
        Take(
            take_id=take_id,
            session=session,
            condition="c60",
            style="natural",
            mode="free",
            item_id=None,
            raw_path=f"takes/{take_id}.wav",
            raw_sha256="",
            clips=(),
            reference=None,
        ),
        raw,
        clips,
    )
    _show(f"{len(clips)} clips; transcribe them with: just stt-corpus annotate --session {session}")
    return len(clips)


def _play(path: Path) -> None:
    import sounddevice as sd  # noqa: PLC0415 -- playback only in annotate, run by Pipec

    sd.play(_samples(path.read_bytes()), CONTRACT_RATE)
    sd.wait()


def _reference_for(
    clip_path: Path, draft: str | None, ask: Ask, play: Callable[[Path], None]
) -> str:
    """Play one clip until Pipec answers; with a draft, Enter confirms it and ``r`` replays."""
    while True:
        play(clip_path)
        if draft is None:
            answer = ask("Lo que dijiste (vacío repite, «inaudible» lo salta): ").strip()
            if answer:
                return answer
            continue
        answer = ask(
            f"Whisper entendió: «{draft}»\n"
            "Enter si es exacto · escribe lo que dijiste · r repite · inaudible lo salta: "
        ).strip()
        if answer.lower() == "r":
            continue
        return answer or draft


def annotate(
    root: Path,
    session: str,
    ask: Ask,
    play: Callable[[Path], None] = _play,
    drafts: Mapping[tuple[str, int], str] | None = None,
) -> int:
    """Play each spontaneous clip to Pipec and keep the reference Pipec types (D-4).

    With *drafts* (what a baseline run heard, per take and clip) Pipec confirms with Enter or
    types a correction instead of typing every clip; the draft anchors the reference, so the
    baseline's own errors read as fewer than they are and a candidate is never favoured by it.

    Args:
        root: The corpus root.
        session: The spontaneous session.
        ask: Asks Pipec a question and returns the typed answer.
        play: Plays one clip (Pipec's own voice, to Pipec).
        drafts: What the baseline heard, keyed by (take id, clip index); ``None`` types all.

    Returns:
        How many clips were annotated in this run.
    """
    manifest = root / MANIFEST_NAME
    takes = load_takes(manifest, root)
    done = 0
    for index, take in enumerate(takes):
        if take.mode != "free" or take.session != session:
            continue
        clips = list(take.clips)
        for number, clip in enumerate(clips):
            if clip.reference is not None or clip.inaudible:
                continue
            draft = (drafts or {}).get((take.take_id, number))
            answer = _reference_for(resolve_corpus_path(root, clip.path), draft, ask, play)
            continued = ask("¿La frase seguía en el clip siguiente? [s/N] ").strip().lower() == "s"
            inaudible = answer.lower() == "inaudible"
            clips[number] = Clip(
                path=clip.path,
                sha256=clip.sha256,
                reference=None if inaudible else answer,
                continued=continued,
                inaudible=inaudible,
            )
            takes[index] = replace(take, clips=tuple(clips))
            replace_takes(manifest, root, takes)
            done += 1
    return done


def load_drafts(root: Path, run_id: str) -> dict[tuple[str, int], str]:
    """Read what a bench run heard on the spontaneous clips, to use as annotation drafts.

    Args:
        root: The corpus root.
        run_id: A bench run file stem (the first repeat of each clip is used).

    Returns:
        The text per (take id, clip index), only for the free takes.
    """
    path = resolve_corpus_path(root, f"results/runs/{run_id}.jsonl")
    drafts: dict[tuple[str, int], str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line) if line else {}
        if row.get("mode") == "free" and row.get("repeat") == 1:
            drafts[str(row["take_id"]), int(row["clip_index"])] = str(row["text"]).strip()
    return drafts


def validate(root: Path, items: Sequence[ScriptItem]) -> int:
    """Check every file and hash, and print counts (never a sentence).

    Args:
        root: The corpus root.
        items: The script items.

    Returns:
        0 when every file exists with its hash, 1 otherwise.
    """
    takes = load_takes(root / MANIFEST_NAME, root)
    broken = 0
    for take in takes:
        for relative, digest in (
            (take.raw_path, take.raw_sha256),
            *((clip.path, clip.sha256) for clip in take.clips),
        ):
            path = resolve_corpus_path(root, relative)
            if not path.exists() or sha256_of_file(path) != digest:
                broken += 1
    counts = Counter(
        (take.mode, "block" if take.block else "main", take.condition, take.style) for take in takes
    )
    for (mode, part, condition, style), number in sorted(counts.items()):
        _show(f"{mode:5} {part:5} {condition:11} {style:8} {number:4} takes")
    main = Counter(
        t.item_id for t in takes if t.mode == "read" and t.condition == "c60" and not t.block
    )
    short = [item.id for item in items if main[item.id] < item.reps]
    _show(f"main condition: {len(short)} items under their reps")
    _show(f"files missing or changed: {broken}")
    return 1 if broken else 0


def expectations(items: Sequence[ScriptItem]) -> int:
    """List each item's recorded expectation and flag where today's code now differs.

    Args:
        items: The script items.

    Returns:
        The number of items whose expectation drifted.
    """
    from server.cognition.intent_resolution import (  # noqa: PLC0415 -- server only here
        parse_memory_answer,
        resolve_information_need,
    )
    from server.memory.preference_gate import match_preference  # noqa: PLC0415

    drift = 0
    for item in items:
        answer = parse_memory_answer(item.text)
        now = {
            "need": resolve_information_need(item.text).need.value,
            "taste": "yes" if match_preference(item.text).matches else "no",
            "answer": "none" if answer is None else ("accept" if answer.accept else "reject"),
        }
        flag = "" if now == item.expect else "  <-- changed"
        drift += bool(flag)
        print(f"{item.id}  {item.text}  {now}{flag}")  # noqa: T201 -- the review list
    return drift


def cleanup(root: Path, ask: Ask) -> int:
    """Delete the whole private corpus, only after the exact typed word ``delete``.

    Args:
        root: The corpus root.
        ask: Asks Pipec to confirm.

    Returns:
        0 when deleted, 1 when nothing was deleted.
    """
    answer = ask(f"Escribe delete para borrar todo {root}: ")
    if answer != "delete":
        _show("nothing deleted")
        return 1
    shutil.rmtree(root, ignore_errors=False)
    _show("corpus deleted")
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the corpus commands.

    Args:
        argv: Arguments without the program name.

    Returns:
        The parsed namespace.
    """
    parser = argparse.ArgumentParser(description="Private speech-to-text corpus (Plan 0069)")
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("capture")
    capture.add_argument("--session", required=True)
    capture.add_argument("--condition", choices=CONDITIONS, default="c60")
    capture.add_argument("--style", choices=("careful", "relaxed"), default="careful")
    capture.add_argument("--layers", default="ABCDEFGH")
    capture.add_argument("--block", action="store_true")
    capture.add_argument("--max-takes", type=int, default=None)
    capture.add_argument("--once", action="store_true", help="read each item once, not its reps")
    free = commands.add_parser("free")
    free.add_argument("--session", required=True)
    free.add_argument("--minutes", type=float, default=10.0)
    notes = commands.add_parser("annotate")
    notes.add_argument("--session", required=True)
    notes.add_argument(
        "--draft-run", default=None, help="a bench run whose text is the draft to confirm"
    )
    commands.add_parser("validate")
    commands.add_parser("expect")
    commands.add_parser("cleanup")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run one corpus command.

    Args:
        argv: Arguments without the program name.

    Returns:
        The process exit code.
    """
    args = parse_args(argv)
    root = STT_CORPUS_ROOT
    items = load_script()
    match args.command:
        case "capture":
            scoped = [item for item in items if item.layer in args.layers]
            capture_session(
                scoped,
                root=root,
                session=args.session,
                condition=args.condition,
                style=args.style,
                block=args.block,
                max_takes=args.max_takes,
                once=args.once,
                recorder=record_window,
                ask=input,
            )
            return 0
        case "free":
            free_session(root, args.session, args.minutes, record_window)
            return 0
        case "annotate":
            drafts = load_drafts(root, args.draft_run) if args.draft_run else None
            annotate(root, args.session, input, drafts=drafts)
            return 0
        case "validate":
            return validate(root, items)
        case "expect":
            return 1 if expectations(items) else 0
        case _:
            return cleanup(root, input)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
