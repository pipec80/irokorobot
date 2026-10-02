"""STT probes (Plan 0056): synthetic-noise echo/hallucination and first-turn accuracy.

Usage:
    just probe-stt noise [--clips 100] [--seconds 1.5] [--wav local_clip.wav ...]
    just probe-stt first-turn [--processes 5] [--rounds 3]

Both load the real Whisper model through the production `server.stt` module, so run
them with the server stopped. Audio contract: WAV · 16000 Hz · mono · int16. Noise is
synthetic; first-turn speech is synthesized by Piper from fixed Spanish phrases. No
household voice or name is used. A `--wav` file stays local and is never printed.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
from dataclasses import dataclass
import io
import json
import logging
from pathlib import Path
import statistics
import subprocess
import sys
from typing import TYPE_CHECKING
import wave

import numpy as np
from server.settings import settings

from server import stt, tts

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

_SAMPLE_RATE = 16_000
_NOISE_KINDS = ("white", "hiss", "pink", "hum")
_NOISE_FOLLOW_UP_RATE = 0.05  # Plan 0056 D-6
_FIRST_TURN_MARGIN = 0.15  # Plan 0056 D-6: first call worse than the same phrase later
_ACCURACY_FLAG_WER = 0.25  # Plan 0056 D-6: reported, never opens a follow-up by itself
_PHRASES = (
    "¿Qué hora es en este momento?",
    "Enciende la luz de la sala, por favor.",
    "Cuéntame un chiste corto.",
)
_PEAK = 0.05


def noise_clip(kind: str, seconds: float, seed: int) -> bytes:
    """Build a deterministic synthetic noise WAV.

    Args:
        kind: One of ``white``, ``hiss``, ``pink``, ``hum``.
        seconds: Clip length.
        seed: RNG seed; the same seed gives the same bytes.

    Returns:
        WAV bytes — 16000 Hz · mono · int16.

    Raises:
        ValueError: If ``kind`` is unknown.
    """
    if kind not in _NOISE_KINDS:
        raise ValueError(f"unknown noise kind {kind!r}; expected one of {_NOISE_KINDS}")
    rng = np.random.default_rng(seed)
    count = int(seconds * _SAMPLE_RATE)
    if kind == "white":
        signal = rng.normal(0, _PEAK, count)
    elif kind == "hiss":
        signal = rng.normal(0, _PEAK / 10, count)
    elif kind == "pink":
        walk = np.cumsum(rng.normal(0, 1, count))
        walk -= np.convolve(walk, np.ones(800) / 800, mode="same")
        signal = _PEAK * walk / (np.abs(walk).max() or 1.0)
    else:
        t = np.arange(count) / _SAMPLE_RATE
        signal = _PEAK * np.sin(2 * np.pi * 60 * t) + rng.normal(0, _PEAK / 10, count)
    pcm = (np.clip(signal, -1, 1) * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(_SAMPLE_RATE)
        wav.writeframes(pcm.tobytes())
    return buffer.getvalue()


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Return the word-level edit distance over the reference length.

    Raises:
        ValueError: If the reference has no words.
    """
    ref = stt._normalize_words(reference).split()
    hyp = stt._normalize_words(hypothesis).split()
    if not ref:
        raise ValueError("reference must contain at least one word")
    previous = list(range(len(hyp) + 1))
    for i, ref_word in enumerate(ref, start=1):
        current = [i]
        for j, hyp_word in enumerate(hyp, start=1):
            cost = previous[j - 1] + (ref_word != hyp_word)
            current.append(min(previous[j] + 1, current[j - 1] + 1, cost))
        previous = current
    return previous[-1] / len(ref)


@dataclass(frozen=True)
class NoiseSummary:
    """Counts of what Whisper returned for clips that contain no speech."""

    clips: int
    empty: int
    echo: int
    other: int

    @property
    def other_rate(self) -> float:
        """Share of clips with a non-empty, non-echo transcript (a hallucination)."""
        return self.other / self.clips if self.clips else 0.0

    @property
    def needs_follow_up(self) -> bool:
        """Plan 0056 D-6: more than 5 % hallucinated transcripts opens a follow-up."""
        return self.other_rate > _NOISE_FOLLOW_UP_RATE


def summarize_noise(transcripts: Sequence[str], prompt: str | None) -> NoiseSummary:
    """Classify raw Whisper transcripts of noise clips as empty, echo or other."""
    empty = sum(1 for text in transcripts if not text.strip())
    echo = sum(1 for text in transcripts if text.strip() and stt.is_prompt_echo(text, prompt))
    return NoiseSummary(len(transcripts), empty, echo, len(transcripts) - empty - echo)


@dataclass(frozen=True)
class FirstTurnSummary:
    """First-utterance accuracy against the same phrase later in the same process."""

    first_mean: float
    later_mean: float
    delta_mean: float
    overall_mean: float

    @property
    def needs_follow_up(self) -> bool:
        """Plan 0056 D-6: the first call is worse by more than 0.15 (a warm-up effect)."""
        return self.delta_mean > _FIRST_TURN_MARGIN

    @property
    def accuracy_flag(self) -> bool:
        """Every call is poor: a general accuracy finding, not a first-turn effect."""
        return self.overall_mean > _ACCURACY_FLAG_WER


def summarize_first_turn(runs: Sequence[Sequence[tuple[int, float]]]) -> FirstTurnSummary:
    """Compare each process's first call with the same phrase later in that process.

    Args:
        runs: One list per fresh process of ``(phrase_index, word_error_rate)`` in call
            order; the first entry is that process's first utterance.

    Returns:
        Mean error of the first calls, of the same phrases later, their paired
        difference and the mean over every call.

    Raises:
        ValueError: If a process never repeats its first phrase.
    """
    firsts: list[float] = []
    laters: list[float] = []
    deltas: list[float] = []
    for run in runs:
        phrase, first_wer = run[0]
        same_later = [wer for index, wer in run[1:] if index == phrase]
        if not same_later:
            raise ValueError("a process must repeat its first phrase in a later call")
        firsts.append(first_wer)
        laters.append(statistics.fmean(same_later))
        deltas.append(first_wer - laters[-1])
    every = [wer for run in runs for _index, wer in run]
    return FirstTurnSummary(
        first_mean=statistics.fmean(firsts),
        later_mean=statistics.fmean(laters),
        delta_mean=statistics.fmean(deltas),
        overall_mean=statistics.fmean(every),
    )


def _run_noise(args: argparse.Namespace) -> int:
    stt.preload()
    clips = [
        noise_clip(_NOISE_KINDS[i % len(_NOISE_KINDS)], args.seconds, seed=i)
        for i in range(args.clips)
    ]
    clips += [Path(path).read_bytes() for path in args.wav]
    transcripts = [stt._whisper_text(clip, None) for clip in clips]  # raw, before the guard
    summary = summarize_noise(transcripts, settings.whisper_initial_prompt)
    print(  # noqa: T201
        f"clips={summary.clips} empty={summary.empty} echo={summary.echo} "
        f"other={summary.other} other_rate={summary.other_rate:.3f} "
        f"follow_up={'YES' if summary.needs_follow_up else 'no'}"
    )
    return 0


async def _first_turn_child(rotation: int, rounds: int) -> list[tuple[int, float]]:
    """Transcribe the three phrases ``rounds`` times in a fresh process, rotated."""
    stt.preload()
    tts.preload()
    wavs: dict[int, bytes] = {}
    for index, phrase in enumerate(_PHRASES):
        audio_base64, _duration_ms = await tts.synthesize(phrase)
        wavs[index] = base64.b64decode(audio_base64)
    order = [(rotation + offset) % len(_PHRASES) for offset in range(len(_PHRASES))] * rounds
    return [
        (index, word_error_rate(_PHRASES[index], await stt.transcribe(wavs[index])))
        for index in order
    ]


def _run_first_turn(args: argparse.Namespace) -> int:
    runs = [
        [
            (int(index), float(wer))
            for index, wer in json.loads(
                subprocess.run(  # noqa: S603 — fixed interpreter and our own script
                    [
                        sys.executable,
                        __file__,
                        "first-turn-child",
                        "--rotation",
                        str(process % len(_PHRASES)),
                        "--rounds",
                        str(args.rounds),
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                .stdout.strip()
                .splitlines()[-1]
            )
        ]
        for process in range(args.processes)
    ]
    summary = summarize_first_turn(runs)
    print(  # noqa: T201
        f"processes={args.processes} rounds={args.rounds} "
        f"first_mean_wer={summary.first_mean:.3f} later_mean_wer={summary.later_mean:.3f} "
        f"delta={summary.delta_mean:.3f} overall_mean_wer={summary.overall_mean:.3f} "
        f"follow_up={'YES' if summary.needs_follow_up else 'no'} "
        f"accuracy_flag={'YES' if summary.accuracy_flag else 'no'}"
    )
    return 0


def main() -> int:
    """Entry point: ``noise``, ``first-turn`` or the internal ``first-turn-child``."""
    parser = argparse.ArgumentParser(description="STT probes (Plan 0056)")
    sub = parser.add_subparsers(dest="command", required=True)
    noise = sub.add_parser("noise")
    noise.add_argument("--clips", type=int, default=100)
    noise.add_argument("--seconds", type=float, default=1.5)
    noise.add_argument("--wav", action="append", default=[])
    first = sub.add_parser("first-turn")
    first.add_argument("--processes", type=int, default=5)
    first.add_argument("--rounds", type=int, default=3)
    child = sub.add_parser("first-turn-child")
    child.add_argument("--rotation", type=int, default=0)
    child.add_argument("--rounds", type=int, default=3)
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    if args.command == "noise":
        return _run_noise(args)
    if args.command == "first-turn":
        return _run_first_turn(args)
    print(json.dumps(asyncio.run(_first_turn_child(args.rotation, args.rounds))))  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
